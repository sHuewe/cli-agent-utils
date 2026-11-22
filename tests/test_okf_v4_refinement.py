"""Source-item conservation when Phase B rewrites, splits and merges concepts."""
from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

from test_okf_v4_phase_a_b import fixture, migrate_applied, put_json, refresh_scan_for_fixture

V4=Path(__file__).resolve().parents[1]/"flow/okf/v4"
sys.path.insert(0,str(V4))
from prepare_inventory import prepare as prepare_a
from refine_b import apply_quality
from phase_b_contract import checked_b
from prepare_merges import prepare as prepare_merges
from apply_merges import merge
from phase_a_contract import checked_phase_a


def two_items(root: Path, *, same_concept: bool) -> None:
    doc=root/"okf-batched/state-v3/docs/example"
    group=json.loads((doc/"group.json").read_text())
    ki={
        "id":"example:k002","normative":True,
        "description":"An independent second statement.",
        "evidence_ranges":[{"doctrine":"doctrines/example.md","start_line":1,"end_line":2}],
    }
    if same_concept:
        group["concepts"][0]["coverage_items"].append(ki)
        repair=doc/"concept-s001-c010-repair.json"
        old=json.loads(repair.read_text())
        old["documented_item_ids"].append(ki["id"])
        put_json(repair,old)
    else:
        old_path="doctrines/example/organization/s001-c020.md"
        content=root/"okf-batched-generated-v3"/old_path
        content.write_text(
            "---\ntitle: Aufgabenverteilung\n---\n"
            "# Aufgabenverteilung\nÜbertragung und Abstimmung verschiedener Aufgaben.\n",
            encoding="utf-8",
        )
        group["concepts"].append({
            "id":"s001-c020","title":"Aufgabenverteilung","path":old_path,
            "coverage_items":[ki],
            "evidence_ranges":[{"source_path":"doctrines/example.md",
                                 "start_line":1,"end_line":2}],
        })
        put_json(doc/"concept-s001-c020-repair.json",{
            "concept_id":"s001-c020","path":old_path,"status":"repaired",
            "remaining_item_ids":[],"remaining_warnings":[],
            "documented_item_ids":["example:k002"],
        })
    group["total_items"]=2
    put_json(doc/"group.json",group)
    coverage=json.loads((doc/"coverage.json").read_text())
    coverage["expected_normative_items"]=2
    coverage["documented_normative_items"]=2
    put_json(doc/"coverage.json",coverage)
    refresh_scan_for_fixture(root, "example")


def inputs(root: Path):
    tasks=prepare_a(root,"okf-v4/phase-a")
    for item in tasks["concepts"]:
        put_json(root/f"okf-v4/state-b/summaries/{item['key']}.json",{
            "id":item["id"],"summary":"Fachlich fundierte Zusammenfassung der Aufgaben und ihrer Koordination.",
            "tags":["Koordination"],
        })
        put_json(root/f"okf-v4/state-b/reviews/{item['key']}.json",{
            "id":item["id"],"action":"keep",
            "reason":"Das Konzept ist fachlich korrekt und vollständig.",
            "parts":[],
        })
    return tasks


def markdown(title: str) -> str:
    return (f"---\ntype: concept\ntitle: {title}\n---\n# {title}\n"
            "Beschreibt die fachlichen Anforderungen, ihre Bedingungen "
            "und die Zuordnung der notwendigen Teilaufgaben im Detail.\n")


def test_review_can_split_without_losing_any_source_item(tmp_path):
    fixture(tmp_path)
    two_items(tmp_path,same_concept=True)
    migrate_applied(tmp_path)
    tasks=inputs(tmp_path)
    item=tasks["concepts"][0]
    put_json(tmp_path/f"okf-v4/state-b/reviews/{item['key']}.json",{
        "id":item["id"],"action":"split",
        "reason":"Zwei eigenständige Aussagen brauchen getrennte Konzepte.",
        "parts":[{
            "title":title,"markdown":markdown(title),
            "knowledge_item_ids":[kid],
            "summary":"Die fachlichen Anforderungen sind hier vollständig beschrieben.",
            "tags":["Koordination"],
        } for title,kid in (
            ("Zusammenarbeit und Aufgaben","example:k001"),
            ("Zusatzaufgaben","example:k002"),
        )],
    })
    result=apply_quality(tmp_path,phase_a="okf-v4/phase-a",
                         state="okf-v4/state-b",tasks=tasks,
                         destination="okf-v4/b-reviewed")
    assert result["split_children"]==1
    _,catalog,_=checked_b(tmp_path,root="okf-v4/b-reviewed",stage="B-draft")
    assert {kid for c in catalog["concepts"] for kid in c["knowledge_item_ids"]}=={
        "example:k001","example:k002"
    }
    assert len(catalog["concepts"])==2
    assert not list((tmp_path/"okf-v4/b-reviewed").rglob("index.md"))
    _,original,_=checked_phase_a(tmp_path)
    assert len(original["concepts"])==1


def test_review_rejects_split_that_duplicates_source_items(tmp_path):
    fixture(tmp_path)
    two_items(tmp_path,same_concept=True)
    migrate_applied(tmp_path)
    tasks=inputs(tmp_path)
    item=tasks["concepts"][0]
    put_json(tmp_path/f"okf-v4/state-b/reviews/{item['key']}.json",{
        "id":item["id"],"action":"split","reason":"Separate the claims.",
        "parts":[{
            "title":title,"markdown":markdown(title),
            "knowledge_item_ids":["example:k001"],
            "summary":"Die Aussage wird präzise und ausführlich dargestellt.",
            "tags":["Koordination"],
        } for title in ("Zusammenarbeit und Aufgaben","Zusatzaufgaben")],
    })
    with pytest.raises(ValueError,match="lost or duplicated"):
        apply_quality(tmp_path,phase_a="okf-v4/phase-a",
                      state="okf-v4/state-b",tasks=tasks,
                      destination="okf-v4/b-reviewed")
    assert not (tmp_path/"okf-v4/b-reviewed").exists()


def test_merge_redirects_removed_concept_and_preserves_both_items(tmp_path):
    fixture(tmp_path)
    two_items(tmp_path,same_concept=False)
    migrate_applied(tmp_path)
    tasks=inputs(tmp_path)
    apply_quality(tmp_path,phase_a="okf-v4/phase-a",
                  state="okf-v4/state-b",tasks=tasks,
                  destination="okf-v4/b-reviewed")
    groups=prepare_merges(tmp_path)
    assert len(groups["groups"])==1
    group=groups["groups"][0]
    ids=[c["id"] for c in group["members"]]
    assert len(ids)==2
    put_json(tmp_path/f"okf-v4/state-b/merges/{group['key']}.json",{
        "group_key":group["key"],"action":"merge",
        "reason":"Die Aussagen sind semantisch eng miteinander verknüpft.",
        "member_ids":ids,
        "title":"Zusammenarbeit und Aufgaben",
        "markdown":markdown("Zusammenarbeit und Aufgaben"),
        "summary":"Das zusammengeführte Konzept beschreibt sämtliche Teilaufgaben.",
        "tags":["Koordination"],
    })
    result=merge(tmp_path,groups=groups)
    assert result["removed_concepts"]==1
    _,catalog,_=checked_b(tmp_path,root="okf-v4/b-merged",stage="B-merged")
    assert len(catalog["concepts"])==1
    assert set(catalog["concepts"][0]["knowledge_item_ids"])=={
        "example:k001","example:k002"
    }
    assert catalog["aliases"][ids[1]]==ids[0]
    assert len(catalog["retired_paths"])==1
    _,original,_=checked_phase_a(tmp_path)
    assert len(original["concepts"])==2
