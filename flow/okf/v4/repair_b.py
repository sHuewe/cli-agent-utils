"""Bounded, fail-closed Phase-B semantic repair workflow.

Two repair rounds. Read-only LLMs propose revisions to defective concepts;
only Python writes snapshots. Successful verifications are retained only when
the final content and its original Knowledge Items are unchanged.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from migrate_v3 import safe_path
from phase_b_contract import checked_b
from refine_b import (
    B_SCHEMA, _semantic, encode, inventory_tasks, markdown, sha, snapshot,
)


STATE = "okf-v4/state-b"
SOURCES = {
    1: ("okf-v4/b-merged", "B-merged"),
    2: ("okf-v4/b-repair-1", "B-repair-1"),
}
TARGETS = {
    1: ("okf-v4/b-repair-1", "B-repair-1"),
    2: ("okf-v4/b-repair-2", "B-repair-2"),
}


def _validated(workspace: Path, root: str, stage: str) -> tuple[dict, dict, Path]:
    return checked_b(workspace, root=root, stage=stage)


def _task_map(catalog: dict, root: str) -> dict[str, dict]:
    tasks = inventory_tasks(catalog, root)["concepts"]
    if len({t["id"] for t in tasks}) != len(tasks):
        raise ValueError("Repeated concept identity in repair inventory.")
    return {t["id"]: t for t in tasks}


def _read_verification(
    workspace: Path, *, path: str, task: dict,
) -> dict:
    result = json.loads(safe_path(workspace, path).read_text(encoding="utf-8"))
    if not isinstance(result, dict) or result.get("id") != task["id"]:
        raise ValueError(f"Verification identity mismatch: {task['id']}")
    status = result.get("status")
    missing = result.get("missing_item_ids")
    warnings = result.get("warnings")
    if (status not in ("ok", "needs_revision")
            or not isinstance(missing, list)
            or any(not isinstance(x, str) for x in missing)
            or len(set(missing)) != len(missing)
            or not set(missing).issubset({
                x["id"] for x in task["knowledge_items"]
            })
            or not isinstance(warnings, list)
            or any(not isinstance(x, str) or not x.strip() for x in warnings)):
        raise ValueError(f"Malformed verification result: {task['id']}")
    if status == "ok":
        if missing or warnings:
            raise ValueError(f"Verification reports inconsistent success: {task['id']}")
    elif not missing and not warnings:
        raise ValueError(f"Failed verification lacks actionable findings: {task['id']}")
    return {"id": task["id"], "status": status,
            "missing_item_ids": missing, "warnings": warnings}


def _initial_verdicts(workspace: Path) -> tuple[dict[str, dict], dict[str, dict]]:
    _, catalog, _ = _validated(workspace, *SOURCES[1])
    tasks = _task_map(catalog, SOURCES[1][0])
    verdicts = {
        ident: _read_verification(
            workspace,
            path=f"{STATE}/final/verification/{task['key']}.json",
            task=task,
        )
        for ident, task in tasks.items()
    }
    return tasks, verdicts


def _round_verdicts(
    workspace: Path, round_number: int, selected: dict,
) -> tuple[dict[str, dict], dict[str, dict]]:
    root, stage = TARGETS[round_number]
    _, catalog, _ = _validated(workspace, root, stage)
    all_tasks = _task_map(catalog, root)
    tasks: dict[str, dict] = {}
    verdicts: dict[str, dict] = {}
    for old in selected["concepts"]:
        task = all_tasks.get(old["id"])
        if task is None:
            raise ValueError("Repaired concept disappeared.")
        if task["key"] == old["key"]:
            raise ValueError(f"Repair did not change content: {old['id']}")
        tasks[old["id"]] = task
        verdicts[old["id"]] = _read_verification(
            workspace,
            path=f"{STATE}/repair-{round_number}/verification/{task['key']}.json",
            task=task,
        )
    return tasks, verdicts


def select(workspace: Path, round_number: int) -> dict:
    if round_number not in SOURCES:
        raise ValueError("Only repair rounds 1 and 2 are supported.")
    root, stage = SOURCES[round_number]
    _, catalog, _ = _validated(workspace, root, stage)
    available = _task_map(catalog, root)
    original, first = _initial_verdicts()
    if set(original) != set(available):
        raise ValueError("Concept identities changed between B and repair stages.")
    findings: dict[str, dict] = {}
    if round_number == 1:
        findings = {i: v for i, v in first.items() if v["status"] != "ok"}
    else:
        selected1 = select(workspace, 1)
        _, checked1 = _round_verdicts(workspace, 1, selected1)
        findings = {i: v for i, v in checked1.items() if v["status"] != "ok"}
    concepts = [{**available[ident], "feedback": findings[ident]}
                for ident in sorted(findings)]
    return {
        "schema": "okf.repair-tasks.v1", "round": round_number,
        "source": root, "status": "ok",
        "count": len(concepts), "concepts": concepts,
    }


def _check_selection(workspace: Path, round_number: int, given: Any) -> dict:
    expected = select(workspace, round_number)
    if given != expected:
        raise ValueError("Repair task selection is stale or has been modified.")
    return expected


def apply(
    workspace: Path, round_number: int, tasks: dict,
) -> dict:
    selected = _check_selection(workspace, round_number, tasks)
    root, stage = SOURCES[round_number]
    destination, dest_stage = TARGETS[round_number]
    _, catalog, base = _validated(workspace, root, stage)
    by_id = {c["id"]: c for c in catalog["concepts"]}
    files = {c["path"]: (base / c["path"]).read_bytes()
             for c in catalog["concepts"]}
    changed: dict[str, dict] = {}
    for task in selected["concepts"]:
        ident = task["id"]
        proposal = json.loads(safe_path(
            workspace, f"{STATE}/repair-{round_number}/proposals/{task['key']}.json",
        ).read_text(encoding="utf-8"))
        if not isinstance(proposal, dict) or proposal.get("id") != ident:
            raise ValueError(f"Repair identity mismatch: {ident}")
        original = by_id[ident]
        if proposal.get("title") != original["title"]:
            raise ValueError(f"Repair cannot rename a concept: {ident}")
        if proposal.get("knowledge_item_ids") != original["knowledge_item_ids"]:
            raise ValueError(f"Repair cannot change source Knowledge-Item assignments: {ident}")
        result = markdown(original["title"], proposal.get("markdown"))
        if sha(result) == original["sha256"]:
            raise ValueError(f"Repair did not change concept content: {ident}")
        semantic = _semantic(proposal, ident)
        files[original["path"]] = result
        changed[ident] = {
            **original, "sha256": sha(result),
            "summary": semantic["summary"], "tags": semantic["tags"],
        }
    next_concepts = [changed.get(c["id"], c) for c in catalog["concepts"]]
    for doc in catalog["documents"]:
        files[doc["source_snapshot"]] = (base / doc["source_snapshot"]).read_bytes()
    next_catalog = {**catalog, "stage": dest_stage, "concepts": next_concepts}
    files["catalog.json"] = encode(next_catalog)
    files[f"repair-{round_number}.json"] = encode({
        "schema": B_SCHEMA, "stage": dest_stage,
        "status": "reviewed", "catalog_sha256": sha(files["catalog.json"]),
        "concept_count": len(next_concepts),
        "knowledge_item_count": sum(len(c["knowledge_items"]) for c in next_concepts),
        "repaired_concept_ids": sorted(changed),
    })
    snapshot(
        workspace, destination, files, f"repair-{round_number}.json",
        protected_inputs=("okf-v4/phase-a", root, STATE),
    )
    _validated(workspace, destination, dest_stage)
    return {
        "status": "ok", "round": round_number, "root": destination,
        "repaired_count": len(changed), "concept_count": len(next_concepts),
    }


def verification_tasks(workspace: Path, round_number: int, tasks: dict) -> dict:
    selected = _check_selection(workspace, round_number, tasks)
    source, stage = TARGETS[round_number]
    _, catalog, _ = _validated(workspace, source, stage)
    fresh = _task_map(catalog, source)
    concepts = []
    for old in selected["concepts"]:
        item = fresh[old["id"]]
        if item["key"] == old["key"]:
            raise ValueError(f"Repair had no content changes: {old['id']}")
        concepts.append(item)
    return {
        "schema": "okf.repair-verification-tasks.v1",
        "round": round_number, "source": source,
        "count": len(concepts), "concepts": concepts,
    }


def certify(workspace: Path) -> dict:
    """Reconcile every final B concept against its latest successful verdict.

    A prior 'ok' is valid only for the exact unmodified concept and source
    item fingerprint. A failed concept requires a new review and fresh 'ok'
    before completing B, or the entire stage fails closed.
    """
    initial_tasks, initial = _initial_verdicts(workspace)
    selected1 = select(workspace, 1)
    repaired1, verified1 = _round_verdicts(workspace, 1, selected1)
    selected2 = select(workspace, 2)
    repaired2, verified2 = _round_verdicts(workspace, 2, selected2)
    final_root, final_stage = TARGETS[2]
    _, final_catalog, _ = _validated(workspace, final_root, final_stage)
    final_tasks = _task_map(final_catalog, final_root)
    if set(final_tasks) != set(initial_tasks):
        raise ValueError("Repair process changed the set of concept identities.")
    ledger = []
    for ident in sorted(final_tasks):
        original = initial_tasks[ident]
        current = final_tasks[ident]
        if initial[ident]["status"] == "ok":
            winning = original
            verdict = initial[ident]
            verified_in = "initial"
        elif verified1[ident]["status"] == "ok":
            winning = repaired1[ident]
            verdict = verified1[ident]
            verified_in = "repair-1"
        else:
            if ident not in verified2:
                raise ValueError(f"Unverified failed concept: {ident}")
            winning = repaired2[ident]
            verdict = verified2[ident]
            verified_in = "repair-2"
        if verdict["status"] != "ok":
            raise ValueError(f"Unresolved semantic verification after two repairs: {ident}")
        if winning["key"] != current["key"]:
            raise ValueError(f"Valid verification is stale after repair: {ident}")
        ledger.append({
            "id": ident, "key": current["key"],
            "source": verified_in,
        })
    return {
        "schema": "okf.repair-certification.v1",
        "status": "complete", "verified_count": len(ledger),
        "first_round_repaired": len(selected1["concepts"]),
        "second_round_repaired": len(selected2["concepts"]),
        "final_source": final_root, "concepts": ledger,
    }


def main() -> None:
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument("--mode", required=True,
                      choices=("select", "apply", "verify-tasks", "certify"))
    args.add_argument("--round", type=int, choices=(1, 2))
    values = args.parse_args()
    envelope = json.load(sys.stdin)
    workspace = Path(".").resolve()
    if values.mode == "certify":
        if values.round is not None:
            raise ValueError("Certify does not take a round.")
        result = certify(workspace)
    else:
        if values.round is None:
            raise ValueError("A repair round is required.")
        tasks = envelope.get("inputs", {}).get("tasks")
        if values.mode == "select":
            result = select(workspace, values.round)
        elif not isinstance(tasks, dict):
            raise ValueError("Expected verified repair tasks in json_inputs.tasks.")
        elif values.mode == "apply":
            result = apply(workspace, values.round, tasks)
        else:
            result = verification_tasks(workspace, values.round, tasks)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
