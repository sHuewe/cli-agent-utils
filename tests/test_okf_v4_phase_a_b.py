"""Regression tests for V3 migration and phase B navigation.

All fixture documents use neutral generic names.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import pytest

V4 = Path(__file__).resolve().parents[1] / "flow/okf/v4"
sys.path.insert(0, str(V4))
from migrate_v3 import migrate
from phase_a_contract import checked_phase_a
from prepare_inventory import prepare
from publish_indexes import publish


def put_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def fixture(workspace: Path, slug: str = "example") -> None:
    original = workspace / f"doctrines/{slug}.md"
    original.parent.mkdir(parents=True, exist_ok=True)
    original.write_text("# Source\nA source statement.\n", encoding="utf-8")
    source_path=f"doctrines/{slug}.md"
    concept_id="s001-c010"
    legacy_path=f"doctrines/{slug}/organization/{concept_id}.md"
    concept=workspace/"okf-batched-generated-v3"/legacy_path
    concept.parent.mkdir(parents=True,exist_ok=True)
    concept.write_text(
        "---\ntitle: Zusammenarbeit und Aufgaben\n---\n"
        "# Zusammenarbeit und Aufgaben\n"
        "Beschreibt Zuständigkeiten und die Koordination von Aufgaben.\n",
        encoding="utf-8",
    )
    # These old indexes are NOT Phase-A inputs, even when present.
    (concept.parent/"index.md").write_text("# Incomplete old index\n", encoding="utf-8")
    (workspace/"okf-batched-generated-v3/index.md").write_text("# Old root index\n",encoding="utf-8")
    state=workspace/f"okf-batched/state-v3/docs/{slug}"
    item_id=f"{slug}:k001"
    put_json(state/"sections.json",{"source_path":source_path,"sections":[{"id":"s001","start_line":1,"end_line":2}]})
    put_json(state/"group.json",{
        "folder":{"id":slug,"path":f"doctrines/{slug}"},
        "total_items":1,
        "concepts":[{
            "id":concept_id,"title":"Zusammenarbeit und Aufgaben","path":legacy_path,
            "coverage_items":[{"id":item_id,"normative":True,"description":"Source statement"}],
            "evidence_ranges":[{"source_path":source_path,"start_line":1,"end_line":2}],
        }],
    })
    put_json(state/"coverage.json",{
        "status":"ok","missing_item_ids":[],"warnings":[],
        "expected_normative_items":1,"expected_descriptive_items":0,
        "documented_normative_items":1,"documented_descriptive_items":0,
    })
    put_json(state/f"concept-{concept_id}-repair.json",{
        "concept_id":concept_id,"path":legacy_path,"status":"repaired","remaining_item_ids":[],
        "remaining_warnings":[],"documented_item_ids":[item_id],
    })


def migrate_applied(root: Path) -> None:
    result=migrate(root,source_root="okf-batched-generated-v3",
                   state_root="okf-batched/state-v3/docs",
                   destination="okf-v4/phase-a",apply=True)
    assert result["status"]=="completed"


def test_migration_copies_only_contract_files_not_indexes_or_old_checkpoints(tmp_path):
    fixture(tmp_path)
    dry=migrate(tmp_path,source_root="okf-batched-generated-v3",
                state_root="okf-batched/state-v3/docs",
                destination="okf-v4/phase-a",apply=False)
    assert dry["dry_run"] is True
    assert not (tmp_path/"okf-v4/phase-a").exists()
    migrate_applied(tmp_path)
    marker,cat,base=checked_phase_a(tmp_path)
    actual={p.relative_to(base).as_posix() for p in base.rglob("*") if p.is_file()}
    assert actual=={
        "catalog.json","phase-a.json","sources/example.md",
        "doctrines/example/organization/zusammenarbeit-und-aufgaben.md"
    }
    assert marker["concept_count"]==1
    assert marker["knowledge_item_count"]==1
    assert cat["concepts"][0]["knowledge_item_ids"]==["example:k001"]
    assert cat["concepts"][0]["evidence_ranges"][0]["start_line"]==1
    assert (tmp_path/"okf-batched-generated-v3/index.md").exists()


def test_migration_rejects_incomplete_coverage_and_preserves_previous_target(tmp_path):
    fixture(tmp_path)
    migrate_applied(tmp_path)
    marker=tmp_path/"okf-v4/phase-a/phase-a.json"
    initial=marker.read_bytes()
    state=tmp_path/"okf-batched/state-v3/docs/example/coverage.json"
    data=json.loads(state.read_text())
    data["missing_item_ids"]=["example:k001"]
    put_json(state,data)
    with pytest.raises(ValueError,match="coverage incomplete"):
        migrate_applied(tmp_path)
    assert marker.read_bytes()==initial


def test_phase_a_rejects_any_uncontracted_index(tmp_path):
    fixture(tmp_path)
    migrate_applied(tmp_path)
    path=tmp_path/"okf-v4/phase-a/doctrines/example/index.md"
    path.write_text("# Should not exist")
    with pytest.raises(ValueError,match="strict contract"):
        checked_phase_a(tmp_path)


def test_same_legacy_concept_id_from_other_doctrine_is_allowed(tmp_path):
    fixture(tmp_path,"example")
    fixture(tmp_path,"second")
    migrate_applied(tmp_path)
    _,catalog,_=checked_phase_a(tmp_path)
    assert {x["id"] for x in catalog["concepts"]}=={
        "example:s001-c010","second:s001-c010"
    }


def test_llm_inventory_and_deterministic_navigation_are_complete(tmp_path):
    fixture(tmp_path)
    fixture(tmp_path,"second")
    migrate_applied(tmp_path)
    tasks=prepare(tmp_path,"okf-v4/phase-a")
    assert tasks["count"]==2
    for item in tasks["concepts"]:
        put_json(tmp_path/f"okf-v4/state-b/summaries/{item['key']}.json",{
            "id":item["id"],
            "summary":"Das Konzept beschreibt die Koordination und die Zuordnung von Aufgaben.",
            "tags":["Koordination"],
        })
    report=publish(tmp_path,phase_a="okf-v4/phase-a",
                   state_root="okf-v4/state-b",destination="okf-v4/published",
                   tasks=tasks)
    assert report["reachable_concepts"]==2
    published=tmp_path/"okf-v4/published"
    assert (published/"index.md").is_file()
    assert (published/"doctrines/index.md").is_file()
    assert (published/"themen/index.md").is_file()
    assert (published/"themen/koordination.md").is_file()
    for slug in ("example","second"):
        assert (published/f"doctrines/{slug}/index.md").is_file()
        index=(published/f"doctrines/{slug}/organization/index.md").read_text()
        assert "zusammenarbeit-und-aufgaben.md" in index
        assert "Das Konzept beschreibt" in index
    assert not (published/"sources").exists()
    assert not (published/"phase-a.json").exists()
    assert len(json.loads((published/"inventory.json").read_text())["concepts"])==2


def test_missing_or_wrong_llm_summary_fails_without_publishing(tmp_path):
    fixture(tmp_path)
    migrate_applied(tmp_path)
    tasks=prepare(tmp_path,"okf-v4/phase-a")
    with pytest.raises(ValueError,match="missing|Required file"):
        publish(tmp_path,phase_a="okf-v4/phase-a",state_root="okf-v4/state-b",
                destination="okf-v4/published",tasks=tasks)
    item=tasks["concepts"][0]
    put_json(tmp_path/f"okf-v4/state-b/summaries/{item['key']}.json",{
        "id":"other:bad","summary":"Unrelated long enough summary text.",
        "tags":["Other"]})
    with pytest.raises(ValueError,match="mismatched"):
        publish(tmp_path,phase_a="okf-v4/phase-a",state_root="okf-v4/state-b",
                destination="okf-v4/published",tasks=tasks)
    assert not (tmp_path/"okf-v4/published").exists()


def test_flow_is_concept_scoped_and_indexes_are_python_only():
    import tomllib
    config=tomllib.loads((V4/"phase-b.toml").read_text(encoding="utf-8"))
    steps={s["id"]:s for s in config["steps"]}
    assert list(steps)==["inventory_tasks","summarize","publish_indexes"]
    assert steps["summarize"]["foreach"]=="steps.inventory_tasks.output.concepts"
    assert steps["summarize"]["workspace_access"]=="read"
    assert steps["summarize"]["output_schema"].endswith("concept-summary.schema.json")
    assert steps["publish_indexes"]["python_script"]["path"].endswith("publish_indexes.py")
    assert steps["publish_indexes"]["overwrite_output"] is True
    assert steps["publish_indexes"]["json_inputs"]["tasks"]["path"]==steps["inventory_tasks"]["output"]



def test_migration_rejects_repair_path_mismatch(tmp_path):
    fixture(tmp_path)
    repair_path=tmp_path/"okf-batched/state-v3/docs/example/concept-s001-c010-repair.json"
    repair=json.loads(repair_path.read_text())
    repair["path"]="doctrines/example/organization/another.md"
    put_json(repair_path,repair)
    with pytest.raises(ValueError,match="Incomplete repair"):
        migrate_applied(tmp_path)
    assert not (tmp_path/"okf-v4/phase-a").exists()


def test_checkpoint_key_changes_when_source_concept_changes(tmp_path):
    fixture(tmp_path)
    migrate_applied(tmp_path)
    old_key=prepare(tmp_path,"okf-v4/phase-a")["concepts"][0]["key"]
    # A new import version with changed content must use a new LLM checkpoint.
    original=tmp_path/"okf-batched-generated-v3/doctrines/example/organization/s001-c010.md"
    original.write_text(original.read_text()+"\nAnother supported detail.\n")
    migrate_applied(tmp_path)
    new_key=prepare(tmp_path,"okf-v4/phase-a")["concepts"][0]["key"]
    assert old_key != new_key


def test_migration_rejects_destination_nested_in_v3_input(tmp_path):
    fixture(tmp_path)
    with pytest.raises(ValueError,match="overlaps"):
        migrate(tmp_path,source_root="okf-batched-generated-v3",
                state_root="okf-batched/state-v3/docs",
                destination="okf-batched-generated-v3/phase-a",apply=False)


def test_theme_membership_deduplicates_equivalent_transliteration(tmp_path):
    fixture(tmp_path)
    migrate_applied(tmp_path)
    tasks=prepare(tmp_path,"okf-v4/phase-a")
    item=tasks["concepts"][0]
    put_json(tmp_path/f"okf-v4/state-b/summaries/{item['key']}.json",{
        "id":item["id"],
        "summary":"Das Konzept beschreibt die Koordination verschiedener Aufgaben.",
        "tags":["Führung","Fuehrung"],
    })
    report=publish(tmp_path,phase_a="okf-v4/phase-a",
                   state_root="okf-v4/state-b",destination="okf-v4/published",
                   tasks=tasks)
    assert report["theme_count"]==1
    index=(tmp_path/"okf-v4/published/themen/fuehrung.md").read_text()
    assert index.count("zusammenarbeit-und-aufgaben.md")==1
