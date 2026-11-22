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
from refine_b import apply_quality
from prepare_merges import prepare as prepare_merges
from apply_merges import merge
from prepare_final_inventory import prepare as prepare_final_inventory
from complete_b import complete
from prepare_links import prepare as prepare_links
from phase_b_contract import checked_b


def put_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def refresh_scan_for_fixture(root: Path, slug: str = "example") -> None:
    """Reproduce V3 scan-local IDs and full source records for test fixtures."""
    state=root/f"okf-batched/state-v3/docs/{slug}"
    sections=json.loads((state/"sections.json").read_text())
    group=json.loads((state/"group.json").read_text())
    for section in sections["sections"]:
        raw=[]
        for concept in group["concepts"]:
            for item in concept["coverage_items"]:
                if item["id"].startswith(slug+":"):
                    raw.append({**item,"id":item["id"][len(slug)+1:]})
        put_json(state/f"scan-{section['id']}.json",{
            "status":"ok","source_path":sections["source_path"],
            "section_id":section["id"],"chunk_id":section["id"],
            "document_id":slug,"folder_id":slug,
            "start_line":section["start_line"],"end_line":section["end_line"],
            "knowledge_items":raw,"candidate_concepts":[],
            "warnings":[],
        })


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
            "coverage_items":[{"id":item_id,"normative":True,"description":"Source statement",
                               "evidence_ranges":[{"doctrine":source_path,"start_line":1,"end_line":2}]}],
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
    refresh_scan_for_fixture(workspace, slug)


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


def finished_b(workspace: Path, *, review_mode: str = "keep") -> dict:
    tasks=prepare(workspace,"okf-v4/phase-a")
    for item in tasks["concepts"]:
        put_json(workspace/f"okf-v4/state-b/summaries/{item['key']}.json",{
            "id":item["id"],
            "summary":"Das Konzept beschreibt die Zuordnung und Koordination von Aufgaben.",
            "tags":["Koordination"],
        })
        put_json(workspace/f"okf-v4/state-b/reviews/{item['key']}.json",{
            "id":item["id"],"action":"keep",
            "reason":"Die Aussagen sind klar voneinander abgegrenzt.",
            "parts":[],
        })
    result=apply_quality(workspace,phase_a="okf-v4/phase-a",
                         state="okf-v4/state-b",tasks=tasks,
                         destination="okf-v4/b-reviewed")
    assert result["reviewed_concepts"]==len(tasks["concepts"])
    groups=prepare_merges(workspace)
    for group in groups["groups"]:
        put_json(workspace/f"okf-v4/state-b/merges/{group['key']}.json",{
            "group_key":group["key"],"action":"skip",
            "reason":"Die Konzeptinhalte sind voneinander verschieden.",
            "member_ids":[],"title":"","markdown":"","summary":"","tags":[],
        })
    merge(workspace,groups=groups)
    final_tasks=prepare_final_inventory(workspace)
    for task in final_tasks["concepts"]:
        put_json(workspace/f"okf-v4/state-b/final/verification/{task['key']}.json",{
            "id":task["id"],"status":"ok",
            "missing_item_ids":[],"warnings":[],
        })
        put_json(workspace/f"okf-v4/state-b/final/summaries/{task['key']}.json",{
            "id":task["id"],
            "summary":"Das final geprüfte Konzept beschreibt die Zuordnung von Aufgaben.",
            "tags":["Koordination"],
        })
    complete(workspace,tasks=final_tasks)
    checked_b(workspace,root="okf-v4/phase-b",stage="B")
    return final_tasks


def finished_c(workspace: Path) -> dict:
    tasks=prepare_links(workspace)
    for item in tasks["concepts"]:
        put_json(workspace/f"okf-v4/state-c/links/{item['key']}.json",{
            "source_id":item["id"],
            "related_ids":[c["id"] for c in item["candidates"][:1]],
        })
    return publish(workspace,phase_b="okf-v4/phase-b",
                   state_root="okf-v4/state-c",
                   destination="okf-v4/published",tasks=tasks)


def test_b_is_content_quality_only_and_c_builds_complete_navigation(tmp_path):
    fixture(tmp_path)
    fixture(tmp_path,"second")
    migrate_applied(tmp_path)
    finished_b(tmp_path)
    b_root=tmp_path/"okf-v4/phase-b"
    assert not list(b_root.rglob("index.md"))
    assert not (b_root/"themen").exists()
    report=finished_c(tmp_path)
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
        assert "final geprüfte Konzept" in index
    assert not (published/"sources").exists()
    assert not (published/"phase-a.json").exists()
    assert len(json.loads((published/"inventory.json").read_text())["concepts"])==2
    assert report["semantic_links"]==2
    # C links are generated only in the copied published concepts.
    published_concept=published/"doctrines/example/organization/zusammenarbeit-und-aufgaben.md"
    assert "Verwandte Konzepte" in published_concept.read_text()
    b_concept=b_root/"doctrines/example/organization/zusammenarbeit-und-aufgaben.md"
    assert "Verwandte Konzepte" not in b_concept.read_text()


def test_missing_llm_summary_aborts_b_before_any_index_creation(tmp_path):
    fixture(tmp_path)
    migrate_applied(tmp_path)
    tasks=prepare(tmp_path,"okf-v4/phase-a")
    item=tasks["concepts"][0]
    put_json(tmp_path/f"okf-v4/state-b/reviews/{item['key']}.json",{
        "id":item["id"],"action":"keep","reason":"Valid concept.","parts":[],
    })
    with pytest.raises(ValueError,match="Required file"):
        apply_quality(tmp_path,phase_a="okf-v4/phase-a",state="okf-v4/state-b",
                      tasks=tasks,destination="okf-v4/b-reviewed")
    assert not (tmp_path/"okf-v4/phase-b").exists()
    assert not (tmp_path/"okf-v4/published").exists()


def test_flows_separate_quality_and_publishing():
    import tomllib
    b=tomllib.loads((V4/"phase-b.toml").read_text(encoding="utf-8"))
    c=tomllib.loads((V4/"phase-c.toml").read_text(encoding="utf-8"))
    bsteps={step["id"]:step for step in b["steps"]}
    csteps={step["id"]:step for step in c["steps"]}
    assert list(bsteps)==[
        "inventory_tasks","summarize","quality_review","apply_quality",
        "merge_candidates","merge_review","apply_merges",
        "final_inventory_tasks","summarize_final","verify_final","complete_b",
    ]
    assert list(csteps)==["link_candidates","relate","publish_indexes"]
    assert b["result"]=="steps.complete_b.output"
    assert c["result"]=="steps.publish_indexes.output"
    assert bsteps["quality_review"]["foreach"]=="steps.inventory_tasks.output.concepts"
    assert bsteps["quality_review"]["workspace_access"]=="read"
    assert csteps["relate"]["workspace_access"]=="none"
    assert csteps["publish_indexes"]["python_script"]["path"].endswith("publish_indexes.py")
    assert csteps["publish_indexes"]["overwrite_output"] is True


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
    finished_b(tmp_path)
    # Final B inventory is authoritative. Two tags may normalize to the
    # same thematic filename, without duplicating concept membership.
    b=tmp_path/"okf-v4/phase-b"
    # Instead of mutating a certified B snapshot, assert the renderer itself.
    from publish_indexes import render
    _,catalog,_=checked_b(tmp_path,root="okf-v4/phase-b",stage="B")
    concept=catalog["concepts"][0]
    summaries={concept["id"]:{
        "summary":"Das Konzept beschreibt die Koordination verschiedener Aufgaben.",
        "tags":["Führung","Fuehrung"],
    }}
    artifacts,report=render(catalog,[],summaries)
    assert report["theme_count"]==1
    assert artifacts["themen/fuehrung.md"].decode().count(
        "zusammenarbeit-und-aufgaben.md"
    )==1


def test_llm_summary_markdown_does_not_add_untracked_links(tmp_path):
    fixture(tmp_path)
    migrate_applied(tmp_path)
    finished_b(tmp_path)
    from publish_indexes import render
    _,catalog,_=checked_b(tmp_path,root="okf-v4/phase-b",stage="B")
    concept=catalog["concepts"][0]
    artifacts,_=render(catalog,[],{concept["id"]:{
        "summary":"Erläutert fachliche Verantwortung und [untrusted](evil.md) im Kontext.",
        "tags":["Organisation"],
    }})
    index=artifacts["doctrines/example/organization/index.md"].decode()
    assert r"\[untrusted\]" in index
    assert "[untrusted](evil.md)" not in index


def test_migration_rejects_legacy_index_as_planned_concept(tmp_path):
    fixture(tmp_path)
    group_path=tmp_path/"okf-batched/state-v3/docs/example/group.json"
    group=json.loads(group_path.read_text())
    group["concepts"][0]["path"]="doctrines/example/organization/index.md"
    put_json(group_path,group)
    repair_path=tmp_path/"okf-batched/state-v3/docs/example/concept-s001-c010-repair.json"
    repair=json.loads(repair_path.read_text())
    repair["path"]="doctrines/example/organization/index.md"
    put_json(repair_path,repair)
    with pytest.raises(ValueError,match="Unexpected doctrine concept path"):
        migrate_applied(tmp_path)
    assert not (tmp_path/"okf-v4/phase-a").exists()


def test_migration_rejects_mismatched_evidence_document(tmp_path):
    fixture(tmp_path)
    fixture(tmp_path,"second")
    sections_path=tmp_path/"okf-batched/state-v3/docs/example/sections.json"
    sections=json.loads(sections_path.read_text())
    sections["source_path"]="doctrines/second.md"
    put_json(sections_path,sections)
    with pytest.raises(ValueError,match="different source|V3 scan does not match"):
        migrate_applied(tmp_path)
    assert not (tmp_path/"okf-v4/phase-a").exists()


def test_migration_rejects_out_of_range_evidence(tmp_path):
    fixture(tmp_path)
    group_path=tmp_path/"okf-batched/state-v3/docs/example/group.json"
    group=json.loads(group_path.read_text())
    group["concepts"][0]["coverage_items"][0]["evidence_ranges"][0]["end_line"]=100
    put_json(group_path,group)
    with pytest.raises(ValueError,match="outside the source"):
        migrate_applied(tmp_path)



def test_migration_refuses_item_omitted_by_group_but_present_in_scan(tmp_path):
    fixture(tmp_path)
    # The group and derived coverage state both still say "one item".
    # The original scan, however, contains two source-grounded assertions.
    scan_file=tmp_path/"okf-batched/state-v3/docs/example/scan-s001.json"
    scan=json.loads(scan_file.read_text())
    second={**scan["knowledge_items"][0],
            "id":"k002",
            "description":"Another independent source-grounded statement."}
    scan["knowledge_items"].append(second)
    put_json(scan_file,scan)
    with pytest.raises(ValueError,match="Group/scan Knowledge Item mismatch"):
        migrate_applied(tmp_path)
    assert not (tmp_path/"okf-v4/phase-a").exists()


def test_migration_refuses_modified_group_claim_from_original_scan(tmp_path):
    fixture(tmp_path)
    group_file=tmp_path/"okf-batched/state-v3/docs/example/group.json"
    group=json.loads(group_file.read_text())
    group["concepts"][0]["coverage_items"][0]["description"]="Changed content"
    put_json(group_file,group)
    with pytest.raises(ValueError,match="Group/scan Knowledge Item mismatch"):
        migrate_applied(tmp_path)


def test_inventory_key_changes_when_knowledge_item_payload_changes(tmp_path):
    fixture(tmp_path)
    migrate_applied(tmp_path)
    original_key=prepare(tmp_path,"okf-v4/phase-a")["concepts"][0]["key"]
    concept_path="okf-batched-generated-v3/doctrines/example/organization/s001-c010.md"
    md_before=(tmp_path/concept_path).read_bytes()
    group_file=tmp_path/"okf-batched/state-v3/docs/example/group.json"
    group=json.loads(group_file.read_text())
    group["concepts"][0]["coverage_items"][0]["description"]="A modified source item description."
    put_json(group_file,group)
    refresh_scan_for_fixture(tmp_path)
    migrate_applied(tmp_path)
    new_key=prepare(tmp_path,"okf-v4/phase-a")["concepts"][0]["key"]
    assert new_key!=original_key
    assert (tmp_path/concept_path).read_bytes()==md_before
