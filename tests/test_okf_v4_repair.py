"""Regression tests for bounded, targeted LLM repair in Phase B."""
from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

from test_okf_v4_phase_a_b import fixture, migrate_applied, finished_b, put_json

V4 = Path(__file__).resolve().parents[1] / "flow/okf/v4"
sys.path.insert(0, str(V4))
from phase_a_contract import checked_phase_a
from phase_b_contract import checked_b
from prepare_initial_verification import prepare as initial_tasks
from prepare_final_inventory import prepare as final_tasks
from repair_b import select, apply, verification_tasks, certify
from complete_b import complete


def prepare_failure(root: Path, *, docs: int = 1) -> tuple[dict, str]:
    fixture(root)
    if docs > 1:
        fixture(root, "second")
    migrate_applied(root)
    finished_b(root)
    initial = initial_tasks(root)
    first = initial["concepts"][0]
    put_json(root/f"okf-v4/state-b/final/verification/{first['key']}.json", {
        "id":first["id"], "status":"needs_revision",
        "missing_item_ids":[first["knowledge_items"][0]["id"]],
        "warnings":["Wichtige Quellenbehauptung fehlt."],
    })
    return initial, first["id"]


def propose(root: Path, round_number: int, task: dict, *, text: str = "Korrigierte Aussage.") -> None:
    title = task["title"]
    body = (
        f"---\ntype: concept\ntitle: {title}\n---\n"
        f"# {title}\nDie Quellanforderungen, Bedingungen und Einschränkungen "
        f"werden hier korrekt und ausführlich umgesetzt. {text}\n"
    )
    put_json(root/f"okf-v4/state-b/repair-{round_number}/proposals/{task['key']}.json", {
        "id":task["id"],"title":title,
        "markdown":body,
        "knowledge_item_ids":[x["id"] for x in task["knowledge_items"]],
        "summary":"Das korrigierte Konzept enthält die maßgeblichen fachlichen Anforderungen.",
        "tags":["Koordination"],
    })


def verdict(root: Path, round_number: int, task: dict, *, ok: bool) -> None:
    put_json(root/f"okf-v4/state-b/repair-{round_number}/verification/{task['key']}.json", {
        "id":task["id"],
        "status":"ok" if ok else "needs_revision",
        "missing_item_ids":[] if ok else [task["knowledge_items"][0]["id"]],
        "warnings":[] if ok else ["Die Aussage ist noch nicht korrekt abgebildet."],
    })


def test_only_failed_concepts_are_repaired_and_good_verdicts_reused(tmp_path):
    initial, failed_id = prepare_failure(tmp_path, docs=2)
    original_a=(tmp_path/"okf-v4/phase-a/phase-a.json").read_bytes()
    selected=select(tmp_path,1)
    assert selected["count"]==1
    task=selected["concepts"][0]
    assert task["id"]==failed_id
    assert task["feedback"]["missing_item_ids"]==[task["knowledge_items"][0]["id"]]
    propose(tmp_path,1,task)
    outcome=apply(tmp_path,1,selected)
    assert outcome["repaired_count"]==1
    checked_b(tmp_path,root="okf-v4/b-repair-1",stage="B-repair-1")
    reevaluate=verification_tasks(tmp_path,1,selected)
    assert len(reevaluate["concepts"])==1
    repaired=reevaluate["concepts"][0]
    assert repaired["key"]!=task["key"]
    verdict(tmp_path,1,repaired,ok=True)
    selected2=select(tmp_path,2)
    assert selected2["count"]==0
    apply(tmp_path,2,selected2)
    checked_b(tmp_path,root="okf-v4/b-repair-2",stage="B-repair-2")
    certification=certify(tmp_path)
    assert certification["verified_count"]==2
    assert certification["first_round_repaired"]==1
    assert certification["second_round_repaired"]==0
    assert {x["source"] for x in certification["concepts"]}=={
        "initial","repair-1"
    }
    tasks=final_tasks(tmp_path)
    for item in tasks["concepts"]:
        put_json(tmp_path/f"okf-v4/state-b/final/summaries/{item['key']}.json",{
            "id":item["id"],
            "summary":"Die endgültigen Aussagen sind fachlich vollständig und geprüft.",
            "tags":["Koordination"],
        })
    complete(tmp_path,tasks=tasks,certification=certification)
    checked_b(tmp_path,root="okf-v4/phase-b",stage="B")
    checked_phase_a(tmp_path)
    assert (tmp_path/"okf-v4/phase-a/phase-a.json").read_bytes()==original_a
    assert not list((tmp_path/"okf-v4/phase-b").rglob("index.md"))


def test_second_repair_round_succeeds_after_first_failure(tmp_path):
    _,failed_id=prepare_failure(tmp_path)
    first=select(tmp_path,1)
    propose(tmp_path,1,first["concepts"][0],text="Erste Reparaturfassung.")
    apply(tmp_path,1,first)
    verify1=verification_tasks(tmp_path,1,first)
    verdict(tmp_path,1,verify1["concepts"][0],ok=False)
    second=select(tmp_path,2)
    assert second["count"]==1
    assert second["concepts"][0]["id"]==failed_id
    propose(tmp_path,2,second["concepts"][0],text="Zweite verbesserte Reparaturfassung.")
    apply(tmp_path,2,second)
    verify2=verification_tasks(tmp_path,2,second)
    verdict(tmp_path,2,verify2["concepts"][0],ok=True)
    certified=certify(tmp_path)
    assert certified["second_round_repaired"]==1
    assert certified["concepts"][0]["source"]=="repair-2"


def test_unresolved_after_two_attempts_fails_closed(tmp_path):
    prepare_failure(tmp_path)
    first=select(tmp_path,1)
    propose(tmp_path,1,first["concepts"][0],text="Erste, unvollständige Reparatur.")
    apply(tmp_path,1,first)
    verdict(tmp_path,1,verification_tasks(tmp_path,1,first)["concepts"][0],ok=False)
    second=select(tmp_path,2)
    propose(tmp_path,2,second["concepts"][0],text="Zweite, weiterhin unvollständige Reparatur.")
    apply(tmp_path,2,second)
    verdict(tmp_path,2,verification_tasks(tmp_path,2,second)["concepts"][0],ok=False)
    with pytest.raises(ValueError,match="Unresolved semantic verification"):
        certify(tmp_path)
    # The prior already-completed B snapshot (from test setup) is unchanged,
    # but the failed repair cannot re-certify or overwrite it.
    checked_phase_a(tmp_path)
    checked_b(tmp_path,root="okf-v4/b-repair-2",stage="B-repair-2")


@pytest.mark.parametrize("change", ["id","title","knowledge_item_ids"])
def test_repair_never_changes_identity_title_or_source_assignments(tmp_path,change):
    prepare_failure(tmp_path)
    selected=select(tmp_path,1)
    task=selected["concepts"][0]
    propose(tmp_path,1,task)
    path=tmp_path/f"okf-v4/state-b/repair-1/proposals/{task['key']}.json"
    data=json.loads(path.read_text(encoding="utf-8"))
    if change=="id":
        data["id"]="other:concept"
    elif change=="title":
        data["title"]="A different title"
    else:
        data["knowledge_item_ids"]=[]
    put_json(path,data)
    with pytest.raises(ValueError,match="identity mismatch|cannot rename|cannot change"):
        apply(tmp_path,1,selected)


def test_old_verification_cannot_certify_changed_final_markdown(tmp_path):
    prepare_failure(tmp_path)
    first=select(tmp_path,1)
    propose(tmp_path,1,first["concepts"][0],text="Eine erste überarbeitete Aussage.")
    apply(tmp_path,1,first)
    verdict(tmp_path,1,verification_tasks(tmp_path,1,first)["concepts"][0],ok=True)
    second=select(tmp_path,2)
    apply(tmp_path,2,second)
    # Reuse of the original successful checkpoint after an unverified
    # modification is prohibited, even if its concept ID is unchanged.
    catalog_file=tmp_path/"okf-v4/b-repair-2/catalog.json"
    data=json.loads(catalog_file.read_text(encoding="utf-8"))
    data["concepts"][0]["sha256"]="0"*64
    put_json(catalog_file,data)
    with pytest.raises(ValueError,match="Invalid or stale"):
        certify(tmp_path)
