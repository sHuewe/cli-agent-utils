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
            require_coverage: bool = False,
            skip_coverage: bool = False) -> dict:
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
    if skip_coverage and require_coverage:
        raise ValueError("Cannot require and skip full-source coverage together.")
    # Main B deliberately ignores any partial/stale coverage checkpoints left
    # by earlier runs. Full-source audit is not a prerequisite for V3 item repair.
    audited = [] if skip_coverage else coverage_additions(
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


def _first_difference(stored: object, expected: object,
                      path: str = "$") -> tuple[str, object, object] | None:
    """Locate the first nested difference, without weakening validation."""
    if type(stored) is not type(expected):
        return path, stored, expected
    if isinstance(stored, dict):
        for key in sorted(set(stored) | set(expected)):
            child = f"{path}.{key}"
            if key not in stored:
                return child, "<missing>", expected[key]
            if key not in expected:
                return child, stored[key], "<missing>"
            mismatch = _first_difference(stored[key], expected[key], child)
            if mismatch is not None:
                return mismatch
        return None
    if isinstance(stored, list):
        if len(stored) != len(expected):
            return f"{path}.length", len(stored), len(expected)
        for index, (before, after) in enumerate(zip(stored, expected)):
            mismatch = _first_difference(before, after, f"{path}[{index}]")
            if mismatch is not None:
                return mismatch
        return None
    if stored != expected:
        return path, stored, expected
    return None


def _brief(value: object) -> str:
    """Short enough for the meaningful portion of a Windows traceback."""
    if isinstance(value, (list, dict)):
        return f"{type(value).__name__}({len(value)} entries)"
    display = repr(value)
    return display[:90] + ("..." if len(display) > 90 else "")


def _same_except_replacement_escape(
    stored: object, expected: object, path: str = "$",
) -> bool:
    """Reconcile only short text gaps at known corrupted KI markers.

    Legacy Phase-A descriptions can contain literal '\\ufffd' sequences or
    the Unicode replacement character itself. The previously checkpointed
    Flow payload may contain either the replacement character or a few
    restored characters at exactly those locations. A simple U+FFFD
    substitution is therefore insufficient.

    Require an unchanged key and exact values for every other task field
    (checked by _reconcile_tasks). Only description text at replacement
    markers may vary, by at most six code points per marker. Literal text
    before, between and after markers must match exactly. The authoritative
    Phase-A item is always used for B output.
    """
    if type(stored) is not type(expected):
        return False
    if isinstance(stored, dict):
        return (
            set(stored) == set(expected)
            and all(
                _same_except_replacement_escape(
                    stored[name], expected[name], f"{path}.{name}",
                )
                for name in stored
            )
        )
    if isinstance(stored, list):
        return len(stored) == len(expected) and all(
            _same_except_replacement_escape(left, right, f"{path}[{index}]")
            for index, (left, right) in enumerate(zip(stored, expected))
        )
    if stored == expected:
        return True
    if (not isinstance(stored, str)
            or not re.fullmatch(
                r"\$\.knowledge_items\[\d+\]\.description", path
            )):
        return False

    # Accept *only* marker-local replacements. The longer unchanged spans
    # remain literal and anchored, so unrelated word edits cannot pass.
    spans = re.split(r"\\ufffd|\ufffd", expected)
    if len(spans) == 1:
        return False
    pattern = r"\A" + r"[\s\S]{0,6}".join(re.escape(span) for span in spans) + r"\Z"
    return re.fullmatch(pattern, stored) is not None


def _reconcile_tasks(given: dict, expected: dict) -> dict:
    """Validate the full repair ledger, independent of harmless list order.

    A checkpointed source_repair_review is keyed by task key, not the
    arbitrary order in which the task list was serialized. Never accept
    additions, removals or changes to the payload of any task.
    """
    if not isinstance(given, dict):
        raise ValueError("Source repair tasks JSON input is not an object.")
    if set(given) != set(expected):
        raise ValueError(
            "Source repair tasks top-level fields differ: "
            f"missing={sorted(set(expected) - set(given))}, "
            f"unexpected={sorted(set(given) - set(expected))}"
        )
    for field in ("schema", "status", "count"):
        if given.get(field) != expected.get(field):
            raise ValueError(
                f"Source repair tasks {field} differs: "
                f"stored={given.get(field)!r}, expected={expected.get(field)!r}"
            )
    supplied, current = given.get("concepts"), expected.get("concepts")
    if not isinstance(supplied, list) or not isinstance(current, list):
        raise ValueError("Source repair tasks concepts must be a list.")
    if len(supplied) != len(current):
        raise ValueError(
            f"Source repair task count differs: stored={len(supplied)}, "
            f"expected={len(current)}"
        )
    def index(rows: list, label: str) -> dict[str, dict]:
        values = {}
        for item in rows:
            if not isinstance(item, dict) or not isinstance(item.get("key"), str):
                raise ValueError(f"{label} has a task without a valid key.")
            key = item["key"]
            if key in values:
                raise ValueError(f"{label} has duplicate task key: {key}")
            values[key] = item
        return values

    actual_by_key = index(supplied, "Stored ledger")
    expected_by_key = index(current, "Recomputed ledger")
    absent = sorted(expected_by_key.keys() - actual_by_key.keys())
    extra = sorted(actual_by_key.keys() - expected_by_key.keys())
    if absent or extra:
        raise ValueError(
            "Source repair task keys differ: "
            f"missing={absent[:3]!r} ({len(absent)} total), "
            f"unexpected={extra[:3]!r} ({len(extra)} total). "
            "Check Phase A, --skip-coverage and the source-repair script version. "
            "Do not delete existing LLM proposals."
        )
    encoding_only_count = 0
    for item in current:
        key = item["key"]
        stored = actual_by_key[key]
        mismatch = _first_difference(stored, item)
        if mismatch is not None:
            if _same_except_replacement_escape(stored, item):
                encoding_only_count += 1
                continue
            field, before, after = mismatch
            raise ValueError(
                f"Source repair mismatch {field}: "
                f"stored={_brief(before)}, expected={_brief(after)}; "
                f"task_id={item['id']!r}. "
                "Existing LLM proposals have NOT been modified."
            )
    if encoding_only_count:
        print(
            "Source repair: accepted marker-local KI description transport "
            f"differences in {encoding_only_count} task(s); "
            "all task keys, evidence and other fields were verified.",
            file=sys.stderr,
        )
    return expected


def apply(workspace: Path, tasks: dict, *, phase_a: str = PHASE_A,
          state: str = STATE, destination: str = DESTINATION,
          require_coverage: bool = False, skip_coverage: bool = False) -> dict:
    tasks = _reconcile_tasks(
        tasks, prepare(workspace, phase_a, require_coverage, skip_coverage),
    )
    _, original, base = checked_phase_a(workspace, phase_a)
    docs = original["documents"]
    audited = [] if skip_coverage else coverage_additions(
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
    p.add_argument("--mode", choices=("prepare", "apply", "diagnose"), required=True)
    p.add_argument("--require-coverage", action="store_true")
    p.add_argument("--skip-coverage", action="store_true")
    args = p.parse_args()
    workspace = Path(".").resolve()
    if args.mode == "diagnose":
        # Read-only: inspect Phase A and the checkpointed task ledger.
        # Never call the LLM, overwrite proposals or publish B artifacts.
        stored = json.loads(safe_path(
            workspace, f"{STATE}/source-repair/tasks.json",
        ).read_text(encoding="utf-8"))
        try:
            expected = prepare(
                workspace, require_coverage=args.require_coverage,
                skip_coverage=args.skip_coverage,
            )
            _reconcile_tasks(stored, expected)
        except ValueError as exc:
            print(json.dumps(
                {"status": "mismatch", "detail": str(exc)},
                ensure_ascii=True,
            ))
            raise SystemExit(1) from None
        print(json.dumps(
            {"status": "ok", "task_count": expected["count"],
             "message": "The stored tasks match recomputed Phase A tasks."},
            ensure_ascii=True,
        ))
        return
    envelope = json.load(sys.stdin)
    if args.mode == "prepare":
        result = prepare(
            workspace, require_coverage=args.require_coverage,
            skip_coverage=args.skip_coverage,
        )
    else:
        given = envelope.get("inputs", {}).get("tasks")
        if not isinstance(given, dict):
            raise ValueError("Missing source repair tasks JSON input.")
        result = apply(
            workspace, given, require_coverage=args.require_coverage,
            skip_coverage=args.skip_coverage,
        )
    print(json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    main()
