"""Repair incomplete V3 source coverage before the ordinary Phase-B inventory.

The migrated Phase A is immutable. Every V3 scan Knowledge Item is preserved
in its catalog, including items not assigned by the incomplete V3 group.
Only bounded LLM proposals are read; this script exclusively writes the
fully source-reconciled B-source snapshot.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

from migrate_v3 import safe_path, slugify
from phase_a_contract import checked_phase_a
from phase_b_contract import checked_b
from source_coverage import additions as coverage_additions, digest as coverage_digest
from refine_b import B_SCHEMA, encode, markdown, sha, snapshot

PHASE_A = "okf-v4/phase-a"
STATE = "okf-v4/state-b"
DESTINATION = "okf-v4/b-source-repaired"


def _key(identity: str, payload: dict) -> str:
    signature = sha(json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8"))[:20]
    result = identity.replace(":", "--") + "--" + signature
    if not re.fullmatch(r"[a-z0-9_-]+", result):
        raise ValueError(f"Unsafe source repair task key: {identity}")
    return result


def prepare(workspace: Path, phase_a: str = PHASE_A,
            require_coverage: bool = False) -> dict:
    _, catalog, _ = checked_phase_a(workspace, phase_a)
    by_document = {doc["id"]: doc for doc in catalog["documents"]}
    entries = []
    existing_ids = {c["id"] for c in catalog["concepts"]}
    for concept in sorted(catalog["concepts"], key=lambda c: c["id"]):
        if not concept.get("source_repair_required", False):
            continue
        doc = by_document[concept["document_id"]]
        item = {
            "id": concept["id"], "kind": "existing",
            "title": concept["title"], "path": phase_a + "/" + concept["path"],
            "source": phase_a + "/" + concept["source_path"],
            "knowledge_item_ids": concept["knowledge_item_ids"],
            "knowledge_items": concept["knowledge_items"],
            "feedback": doc.get("coverage_diagnostics", {}),
        }
        item["key"] = _key(item["id"], {
            **item, "content_sha256": concept["sha256"],
            "source_sha256": doc["sha256"],
        })
        entries.append(item)
    for doc in sorted(catalog["documents"], key=lambda d: d["id"]):
        missing = set(doc.get("pending_knowledge_item_ids", []))
        for ki in doc.get("source_knowledge_items", []):
            if ki["id"] not in missing:
                continue
            ident = doc["id"] + ":recovered-" + hashlib.sha256(
                ki["id"].encode("utf-8")
            ).hexdigest()[:16]
            if ident in existing_ids:
                raise ValueError(f"Recovery concept identity collision: {ident}")
            existing_ids.add(ident)
            item = {
                "id": ident, "kind": "missing", "title": "",
                "path": None, "source": phase_a + "/" + doc["source_snapshot"],
                "knowledge_item_ids": [ki["id"]], "knowledge_items": [ki],
                "feedback": doc.get("coverage_diagnostics", {}),
            }
            item["key"] = _key(ident, {
                **item, "source_sha256": doc["sha256"],
            })
            entries.append(item)
    # Independent source audit can identify claims that the V3 scanner
    # omitted entirely. These are separately source-quoted and line-anchored;
    # their identities are distinct from all immutable V3 scan identities.
    audited = coverage_additions(
        workspace, required=require_coverage, phase_a=phase_a,
    )
    for ki in audited:
        slug = ki["id"].split(":", 1)[0]
        if ki["id"] in existing_ids or slug not in by_document:
            raise ValueError("Source audit item identity/document collision.")
        existing_ids.add(ki["id"])
        doc = by_document[slug]
        item = {
            "id": ki["id"], "kind": "audit_missing", "title": "",
            "path": None, "source": phase_a + "/" + doc["source_snapshot"],
            "knowledge_item_ids": [ki["id"]], "knowledge_items": [ki],
            "feedback": {"status": "new_source_assertion",
                         "evidence": ki["evidence_ranges"]},
        }
        item["key"] = _key(item["id"], {
            **item, "source_sha256": doc["sha256"],
        })
        entries.append(item)
    if len({x["key"] for x in entries}) != len(entries):
        raise ValueError("Duplicate source repair task key.")
    return {
        "schema": "okf.source-repair-tasks.v1", "status": "ok",
        "count": len(entries), "concepts": entries,
    }


def apply(workspace: Path, tasks: dict, *, phase_a: str = PHASE_A,
          state: str = STATE, destination: str = DESTINATION,
          require_coverage: bool = False) -> dict:
    if tasks != prepare(workspace, phase_a, require_coverage):
        raise ValueError("Source repair tasks are missing, stale or modified.")
    _, original, base = checked_phase_a(workspace, phase_a)
    docs = original["documents"]
    audited = coverage_additions(
        workspace, required=require_coverage, phase_a=phase_a, state=state,
    )
    original_concepts = original["concepts"]
    by_id = {c["id"]: c for c in original_concepts}
    by_doc = {d["id"]: d for d in docs}
    files = {c["path"]: (base / c["path"]).read_bytes() for c in original_concepts}
    new_concepts = {c["id"]: dict(c) for c in original_concepts}
    paths = {c["path"].casefold() for c in original_concepts}

    # Validate *every* proposal before staging any output. The source-item
    # assignments are deterministic and cannot be edited by a model.
    for task in tasks["concepts"]:
        proposal = json.loads(safe_path(
            workspace, f"{state}/source-repair/proposals/{task['key']}.json"
        ).read_text(encoding="utf-8"))
        if (not isinstance(proposal, dict)
                or proposal.get("id") != task["id"]
                or proposal.get("knowledge_item_ids") != task["knowledge_item_ids"]):
            raise ValueError(f"Invalid source repair identity/coverage: {task['id']}")
        action = proposal.get("action")
        title = proposal.get("title")
        body = proposal.get("markdown")
        if task["kind"] == "existing":
            old = by_id[task["id"]]
            if title != old["title"] or action not in ("keep", "rewrite"):
                raise ValueError(f"Source repair cannot rename/reassign: {task['id']}")
            if action == "keep":
                if body != "":
                    raise ValueError("Keep proposal cannot carry revised Markdown.")
                continue
            content = markdown(title, body)
            files[old["path"]] = content
            new_concepts[old["id"]] = {**old, "sha256": sha(content)}
        else:
            if action != "rewrite" or not isinstance(title, str) or not title.strip():
                raise ValueError(f"Missing source item requires a new concept: {task['id']}")
            content = markdown(title, body)
            slug = task["id"].split(":", 1)[0]
            path = (f"doctrines/{slug}/recovered/{slugify(title)}-"
                    f"{task['id'].rsplit('-', 1)[-1][:10]}.md")
            if path.casefold() in paths:
                raise ValueError(f"Recovered concept path collision: {path}")
            paths.add(path.casefold())
            ki = task["knowledge_items"][0]
            doc = by_doc[slug]
            files[path] = content
            new_concepts[task["id"]] = {
                "id": task["id"], "document_id": slug, "title": title,
                "description": ki.get("description", ""),
                "type": "concept", "tags": [], "related": [],
                "path": path, "source_path": doc["source_snapshot"],
                "source_original_path": doc["original_path"],
                "knowledge_item_ids": task["knowledge_item_ids"],
                "knowledge_items": task["knowledge_items"],
                "evidence_ranges": ki["evidence_ranges"],
                "sha256": sha(content),
            }

    concepts = sorted(new_concepts.values(), key=lambda c: c["id"])
    for doc in docs:
        files[doc["source_snapshot"]] = (base / doc["source_snapshot"]).read_bytes()
    next_docs = [
        {**doc, "concept_ids": [c["id"] for c in concepts
                               if c["document_id"] == doc["id"]]}
        for doc in docs
    ]
    catalog = {
        "schema": B_SCHEMA, "stage": "B-source",
        "origin_phase_a_sha256": sha((base / "phase-a.json").read_bytes()),
        "documents": next_docs, "concepts": concepts, "aliases": {},
        "source_coverage_sha256": coverage_digest(audited)
            if require_coverage or audited else None,
    }
    files["catalog.json"] = encode(catalog)
    files["source-repaired.json"] = encode({
        "schema": B_SCHEMA, "stage": "B-source", "status": "repaired",
        "catalog_sha256": sha(files["catalog.json"]),
        "concept_count": len(concepts),
        "knowledge_item_count": sum(len(c["knowledge_items"]) for c in concepts),
        "repaired_existing_count": sum(
            x["kind"] == "existing" for x in tasks["concepts"]
        ),
        "recovered_item_count": sum(
            x["kind"] == "missing" for x in tasks["concepts"]
        ),
        "audited_source_item_count": len(audited),
    })
    snapshot(
        workspace, destination, files, "source-repaired.json",
        protected_inputs=(phase_a, state),
    )
    checked_b(workspace, root=destination, stage="B-source", phase_a=phase_a)
    return {
        "status": "ok", "source": destination,
        "concept_count": len(concepts),
        "recovered_item_count": files["source-repaired.json"] is not None
            and sum(x["kind"] == "missing" for x in tasks["concepts"]),
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mode", choices=("prepare", "apply"), required=True)
    p.add_argument("--require-coverage", action="store_true")
    args = p.parse_args()
    envelope = json.load(sys.stdin)
    workspace = Path(".").resolve()
    if args.mode == "prepare":
        result = prepare(workspace, require_coverage=args.require_coverage)
    else:
        given = envelope.get("inputs", {}).get("tasks")
        if not isinstance(given, dict):
            raise ValueError("Missing source repair tasks JSON input.")
        result = apply(workspace, given, require_coverage=args.require_coverage)
    print(json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    main()
