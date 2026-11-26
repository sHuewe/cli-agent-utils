"""Repair incomplete V3 source coverage before the ordinary Phase-B inventory.

The migrated Phase A is immutable. Every V3 scan Knowledge Item is preserved
in its catalog, including items not assigned by the incomplete V3 group.
Only bounded LLM proposals are read; this script exclusively writes the
fully source-reconciled B-source snapshot.
"""
from __future__ import annotations

import argparse
from collections import Counter
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


def _reconcile_tasks(given: dict, expected: dict) -> dict:
    """Validate task keys, identities and coverage, not transported prose.

    Each task key is a digest tied to the authoritative Phase-A source and
    existing concept content. Checkpoints/proposals are addressed by that
    key, whereas the runner can modify free-text descriptions while
    serializing them through JSON. Compare structural/provenance fields,
    then return freshly recomputed Phase-A tasks for all further processing.
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
    # The task key is a content digest generated from the authoritative
    # Phase-A payload (including source/document hashes). It is also the
    # stable identifier of the preexisting LLM proposal. Once the key set
    # matches, we only compare identity, routing and provenance fields here.
    # In particular, do not compare transported free-text titles,
    # descriptions or advisory LLM diagnostics byte-for-byte.
    #
    # All downstream data come from the freshly checked Phase A (expected),
    # NOT from the checkpointed Flow input (given).
    advisory_changes = 0

    def require_same(stored: object, authoritative: object, path: str,
                     identity: str) -> None:
        mismatch = _first_difference(stored, authoritative, path)
        if mismatch is not None:
            field, before, after = mismatch
            raise ValueError(
                f"Source repair identity/provenance mismatch {field}: "
                f"stored={_brief(before)}, expected={_brief(after)}; "
                f"task_id={identity!r}. Existing LLM proposals were not changed."
            )

    for item in current:
        stored = actual_by_key[item["key"]]
        ident = item["id"]
        if set(stored) != set(item):
            require_same(
                sorted(stored), sorted(item), "$.fields", ident,
            )
        # The title is free text; its authoritative value was included in
        # the hashed task key and is recovered from checked Phase A below.
        # A JSON round-trip can alter the displayed title without changing
        # the stable identity or any source/evidence mapping.
        if not isinstance(stored.get("title"), str) and "title" in stored:
            raise ValueError(f"Invalid source task title type for {ident}.")
        for field in (
            "key", "id", "kind", "path", "source",
            "knowledge_item_ids",
        ):
            require_same(stored.get(field), item.get(field), f"$.{field}", ident)

        # KI ID, evidence ranges, normative flag and every other structural
        # attribute must remain exact. Only the description is advisory
        # text. The original description from Phase A will be used in B.
        saved_ki = stored.get("knowledge_items")
        original_ki = item.get("knowledge_items")
        if not isinstance(saved_ki, list) or not isinstance(original_ki, list):
            raise ValueError(f"Invalid Knowledge Item list in source task {ident}.")
        require_same(len(saved_ki), len(original_ki),
                     "$.knowledge_items.length", ident)
        for index, (saved, original) in enumerate(zip(saved_ki, original_ki)):
            if not isinstance(saved, dict) or not isinstance(original, dict):
                raise ValueError(f"Invalid Knowledge Item at {ident}[{index}].")
            require_same(sorted(saved), sorted(original),
                         f"$.knowledge_items[{index}].fields", ident)
            # V3 scans may omit description entirely. Preserve that
            # absence when both task and authoritative Phase A agree;
            # supplied descriptions must still have the correct type.
            if "description" in saved and not isinstance(saved["description"], str):
                raise ValueError(
                    f"Invalid KI description type at {ident}[{index}]."
                )
            for field in sorted(set(original) - {"description"}):
                require_same(
                    saved[field], original[field],
                    f"$.knowledge_items[{index}].{field}", ident,
                )

        if "feedback" in stored and not isinstance(stored["feedback"], dict):
            raise ValueError(f"Invalid source task feedback for {ident}.")
        if stored != item:
            advisory_changes += 1
    if advisory_changes:
        print(
            f"Source repair: {advisory_changes} task(s) contain JSON-transport "
            "differences in advisory titles, descriptions or feedback. "
            "Task keys, identities, original KI evidence and all structural "
            "fields were checked; using authoritative Phase-A data.",
            file=sys.stderr,
        )
    return expected


def _source_repair_markdown(title: str, body: str) -> bytes:
    """Quote plain title/description scalars containing a YAML-significant colon.

    This compatibility repair changes only frontmatter representation in an
    LLM proposal, never its body or stored checkpoint. The ordinary strict
    validator must accept the entire resulting Markdown document; malformed
    unrelated YAML remains an error.
    """
    try:
        return markdown(title, body)
    except ValueError as exc:
        if str(exc) != "Replacement contains invalid YAML frontmatter.":
            raise

    if not isinstance(title, str) or not isinstance(body, str):
        raise ValueError("Replacement contains invalid YAML frontmatter.")
    lines = body.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\r\n") != "---":
        raise ValueError("Replacement contains invalid YAML frontmatter.")
    closing = next(
        (i for i in range(1, len(lines)) if lines[i].rstrip("\r\n") == "---"),
        None,
    )
    if closing is None:
        raise ValueError("Replacement contains invalid YAML frontmatter.")

    # Only direct, unique, plain-string fields are eligible. In particular,
    # never rewrite nested YAML, multiline scalars, aliases, or collections.
    candidates = {}
    for i in range(1, closing):
        raw = lines[i].rstrip("\r\n")
        for field in ("title", "description"):
            prefix = field + ": "
            if not raw.startswith(prefix):
                continue
            if field in candidates:
                raise ValueError("Replacement contains invalid YAML frontmatter.")
            value = raw[len(prefix):]
            if (": " not in value or not value.strip()
                    or value.lstrip().startswith(('"', "'", "[", "{", "|", ">", "&", "*", "!"))
                    or " #" in value or "\t" in value):
                continue
            if field == "title" and value != title:
                continue
            candidates[field] = (i, value)
    if not candidates:
        raise ValueError("Replacement contains invalid YAML frontmatter.")

    for i, value in candidates.values():
        raw = lines[i].rstrip("\r\n")
        ending = lines[i][len(raw):]
        field = raw.split(":", 1)[0]
        # JSON-quoted UTF-8 text is also a valid YAML string scalar.
        lines[i] = field + ": " + json.dumps(value, ensure_ascii=False) + ending
    return markdown(title, "".join(lines))


def _check_proposal_identity(proposal: object, task: dict) -> bool:
    """Verify deterministic task identity and KI coverage, not model list order.

    Proposals are loaded by immutable, source-bound task key. Accept either
    the canonical task ID or that task's *exact* key as the model-supplied ID;
    both are unambiguous when the complete KI IDs match. Never accept another
    task's ID/key, or change the authoritative catalog identity. A complete
    permutation of the KI IDs is harmless. Return True for reordered lists.
    """
    ident = task["id"]
    if not isinstance(proposal, dict):
        raise ValueError(f"Source repair proposal is not an object: {ident}")
    # The model sometimes copies the iteration/task key (task identity plus
    # source-bound hash) instead of the canonical concept ID. This is safe to
    # recognize ONLY for the exact key of the task whose keyed proposal file
    # was loaded, and ONLY when the full KI reference multiset matches below.
    # Never use the model's identifier in the resulting catalog.
    returned_id = proposal.get("id")
    allowed_ids = (ident, task["key"])
    if returned_id not in allowed_ids:
        raise ValueError(
            f"Source repair proposal ID mismatch for {ident}: "
            f"stored={returned_id!r}, expected={ident!r} "
            f"(or exact own task key={task['key']!r})"
        )
    received = proposal.get("knowledge_item_ids")
    expected = task["knowledge_item_ids"]
    if not isinstance(received, list) or any(
        not isinstance(ki, str) for ki in received
    ):
        raise ValueError(
            f"Source repair KI IDs missing or invalid for {ident}: "
            "expected a list of string IDs."
        )
    actual_counts, expected_counts = Counter(received), Counter(expected)
    if actual_counts != expected_counts:
        missing = list((expected_counts - actual_counts).elements())
        extra = list((actual_counts - expected_counts).elements())
        raise ValueError(
            f"Source repair KI coverage mismatch for {ident}: "
            f"missing={missing[:5]!r} ({len(missing)} total), "
            f"unexpected={extra[:5]!r} ({len(extra)} total). "
            "Only permutations of the complete KI list may be reused."
        )
    return received != expected


def _diagnose_proposals(workspace: Path, *,
                        require_coverage: bool, skip_coverage: bool) -> dict:
    """Read-only survey of ALL checkpointed LLM proposals.

    No model calls, changes to proposals, snapshots or task checkpoints.
    Report a small sample of invalid proposals and an aggregate error count.
    """
    tasks = prepare(
        workspace, require_coverage=require_coverage,
        skip_coverage=skip_coverage,
    )
    counts = {"checked": 0, "reordered": 0, "id_is_task_key": 0, "invalid": 0}
    failures = []
    for task in tasks["concepts"]:
        counts["checked"] += 1
        try:
            path = safe_path(
                workspace,
                f"{STATE}/source-repair/proposals/{task['key']}.json",
            )
            proposal = json.loads(path.read_text(encoding="utf-8"))
            if _check_proposal_identity(proposal, task):
                counts["reordered"] += 1
            if proposal["id"] == task["key"] and task["key"] != task["id"]:
                counts["id_is_task_key"] += 1
        except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
            counts["invalid"] += 1
            if len(failures) < 10:
                failures.append({"task_id": task["id"], "reason": str(exc)})
    return {**counts, "examples": failures, "status": (
        "ok" if counts["invalid"] == 0 else "invalid"
    )}


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
        # Exact completeness is mandatory. Only KI ordering in the model's
        # response is non-authoritative; canonical Phase-A order is retained.
        _check_proposal_identity(proposal, task)
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
            content = _source_repair_markdown(title, body)
            files[old["path"]] = content
            new_concepts[old["id"]] = {**old, "sha256": sha(content)}
        else:
            if action != "rewrite" or not isinstance(title, str) or not title.strip():
                raise ValueError(f"Missing source item requires a new concept: {task['id']}")
            content = _source_repair_markdown(title, body)
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
    p.add_argument(
        "--mode", choices=("prepare", "apply", "diagnose", "diagnose-proposals"),
        required=True,
    )
    p.add_argument("--require-coverage", action="store_true")
    p.add_argument("--skip-coverage", action="store_true")
    args = p.parse_args()
    workspace = Path(".").resolve()
    if args.mode == "diagnose-proposals":
        result = _diagnose_proposals(
            workspace, require_coverage=args.require_coverage,
            skip_coverage=args.skip_coverage,
        )
        print(json.dumps(result, ensure_ascii=True, indent=2))
        if result["invalid"]:
            raise SystemExit(1)
        return
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
