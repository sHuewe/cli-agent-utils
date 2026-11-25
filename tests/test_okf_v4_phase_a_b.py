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
from source_repair import prepare as source_repair_tasks, apply as apply_source_repair
from source_coverage import (
    prepare as coverage_tasks, additions as coverage_additions,
    compare_prepare as coverage_compare_tasks,
)
from phase_a_contract import checked_phase_a
from prepare_inventory import prepare
from publish_indexes import publish
from refine_b import apply_quality
from prepare_merges import prepare as prepare_merges
from apply_merges import merge
from prepare_final_inventory import prepare as prepare_final_inventory
from prepare_initial_verification import prepare as prepare_initial_verification
from repair_b import select as select_repairs, apply as apply_repairs
from repair_b import verification_tasks as repair_verification_tasks, certify as certify_repairs
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


def prepare_repaired(root: Path) -> dict:
    """Materialize the mandatory B-source stage before any B inventory tests."""
    tasks=source_repair_tasks(root)
    if tasks["count"]:
        raise AssertionError("Complete fixture unexpectedly requires source repair.")
    apply_source_repair(root,tasks)
    return prepare(root,"okf-v4/b-source-repaired")


def test_bounded_source_coverage_discovers_original_claim_absent_from_v3(tmp_path):
    fixture(tmp_path)
    source=tmp_path/"doctrines/example.md"
    source.write_text(
        source.read_text(encoding="utf-8")
        + "A separate previously omitted source fact.\n",
        encoding="utf-8",
    )
    state=tmp_path/"okf-batched/state-v3/docs/example"
    sections=json.loads((state/"sections.json").read_text(encoding="utf-8"))
    sections["sections"][0]["end_line"]=3
    put_json(state/"sections.json",sections)
    scan=json.loads((state/"scan-s001.json").read_text(encoding="utf-8"))
    scan["end_line"]=3
    put_json(state/"scan-s001.json",scan)
    migrate_applied(tmp_path)
    audit=coverage_tasks(tmp_path)
    assert audit["count"]>=1
    assert any(
        "A separate previously omitted source fact." in line["text"]
        for task in audit["chunks"] for line in task["lines"]
    )
    put_json(tmp_path/"okf-v4/state-b/coverage/tasks.json",audit)
    for task in audit["chunks"]:
        assert len(str(task["lines"])) < 9000
        missing=[]
        for line in task["lines"]:
            if "A separate previously omitted source fact." in line["text"]:
                missing.append({
                    "line":line["line"],
                    "source_quote":"A separate previously omitted source fact.",
                    "statement":"There is a separate source fact that was not included in the original scan.",
                    "normative":False,
                    "facets":["A separate source fact is present in the text."],
                })
        put_json(
            tmp_path/f"okf-v4/state-b/coverage/reviews/{task['key']}.json",
            {"key":task["key"],"status":"claims" if missing else "ok",
             "missing":missing},
        )
    compare_tasks=coverage_compare_tasks(tmp_path)
    put_json(
        tmp_path/"okf-v4/state-b/coverage/comparison-tasks.json",compare_tasks,
    )
    for comparison in compare_tasks["comparisons"]:
        put_json(
            tmp_path/f"okf-v4/state-b/coverage/comparisons/{comparison['key']}.json",
            {"key":comparison["key"],"covered_facets":[]},
        )
    missing_items=coverage_additions(tmp_path,required=True)
    assert len(missing_items)==1
    assert missing_items[0]["id"].startswith("example:audit-")
    repair_tasks=source_repair_tasks(tmp_path,require_coverage=True)
    assert repair_tasks["count"]==1
    task=repair_tasks["concepts"][0]
    assert task["kind"]=="audit_missing"
    put_json(
        tmp_path/f"okf-v4/state-b/source-repair/proposals/{task['key']}.json",
        {
            "id":task["id"],"action":"rewrite","title":"Ergänzende Quellaussage",
            "markdown":(
                "---\ntitle: Ergänzende Quellaussage\ntype: concept\n---\n"
                "# Ergänzende Quellaussage\n"
                "Das Quelldokument enthält eine zusätzliche Aussage, die in der"
                " ursprünglichen Wissensextraktion übersehen wurde.\n"
            ),
            "knowledge_item_ids":task["knowledge_item_ids"],
        },
    )
    apply_source_repair(tmp_path,repair_tasks,require_coverage=True)
    _,cat,_=checked_b(tmp_path,root="okf-v4/b-source-repaired",stage="B-source")
    assert len(cat["concepts"])==2
    assert sum(len(c["knowledge_items"]) for c in cat["concepts"])==2
    # A remains an immutable record of the original (incomplete) V3 scan.
    _,a_catalog,_=checked_phase_a(tmp_path)
    assert len(a_catalog["documents"][0]["source_knowledge_items"])==1
    assert cat["source_coverage_sha256"]
    # Reviewed B output must retain the extra item even after concept quality
    # processing, not merely at the temporary source-repair checkpoint.
    inventory=prepare(tmp_path,"okf-v4/b-source-repaired")
    for entry in inventory["concepts"]:
        put_json(
            tmp_path/f"okf-v4/state-b/summaries/{entry['key']}.json",
            {
                "id":entry["id"],"summary":"Fachliche Zusammenfassung einer geprüften Quellaussage.",
                "tags":["Quellenauswertung"],
            },
        )
        put_json(
            tmp_path/f"okf-v4/state-b/reviews/{entry['key']}.json",
            {"id":entry["id"],"action":"keep",
             "reason":"Erfüllt die geltenden Anforderungen.","parts":[]},
        )
    apply_quality(
        tmp_path,phase_a="okf-v4/b-source-repaired",
        state="okf-v4/state-b",tasks=inventory,destination="okf-v4/b-reviewed",
    )
    _,reviewed,_=checked_b(tmp_path,root="okf-v4/b-reviewed",stage="B-draft")
    assert reviewed["source_coverage_sha256"] == cat["source_coverage_sha256"]
    assert sum(len(c["knowledge_items"]) for c in reviewed["concepts"])==2


def test_source_coverage_rejects_unsupported_quote_and_incomplete_reviews(tmp_path):
    fixture(tmp_path)
    migrate_applied(tmp_path)
    audit=coverage_tasks(tmp_path)
    put_json(tmp_path/"okf-v4/state-b/coverage/tasks.json",audit)
    with pytest.raises(ValueError,match="Required file"):
        coverage_additions(tmp_path,required=True)
    for task in audit["chunks"]:
        put_json(
            tmp_path/f"okf-v4/state-b/coverage/reviews/{task['key']}.json",
            {
                "key":task["key"],"status":"claims",
                "missing":[{
                    "line":task["first_line"],
                    "source_quote":"Invented quotation not present in source",
                    "statement":"Invented claim that is unsupported by original evidence.",
                    "normative":False,
                    "facets":["An unsupported invented claim is present."],
                }],
            },
        )
    with pytest.raises(ValueError,match="Source quote absent"):
        coverage_additions(tmp_path,required=True)


def test_dense_overlapping_knowledge_items_are_compared_without_loss(
    tmp_path, monkeypatch,
):
    """A real 9 KB overlap must never truncate or abort claim extraction."""
    fixture(tmp_path)
    migrate_applied(tmp_path)
    import source_coverage as coverage
    real_check=coverage.checked_phase_a

    def dense_checked(workspace, root="okf-v4/phase-a"):
        marker,catalog,base=real_check(workspace,root)
        import copy
        catalog=copy.deepcopy(catalog)
        original=catalog["documents"][0]["source_knowledge_items"][0]
        catalog["documents"][0]["source_knowledge_items"] = [
            {
                **original,
                "id":f"example:synthetic-{i:03d}",
                "description":(
                    "Original overlapping source assertion " + str(i)
                    + " with a substantial description to fill the bounded batches. "
                    + "This record must be considered, never dropped."
                ),
            }
            for i in range(180)
        ]
        return marker,catalog,base

    monkeypatch.setattr(coverage,"checked_phase_a",dense_checked)
    tasks=coverage_tasks(tmp_path)
    assert tasks["chunks"]
    assert all("known_items" not in task for task in tasks["chunks"])
    put_json(tmp_path/"okf-v4/state-b/coverage/tasks.json",tasks)
    for task in tasks["chunks"]:
        claim=[]
        if task == tasks["chunks"][0]:
            line=next(x for x in task["lines"] if len(x["text"]) >= 5)
            quote=line["text"][:min(40,len(line["text"]))]
            claim=[{
                "line":line["line"],"source_quote":quote,
                "statement":"A source assertion to compare against all overlapping items.",
                "normative":False,
                "facets":["The source describes a particular assertion."],
            }]
        put_json(
            tmp_path/f"okf-v4/state-b/coverage/reviews/{task['key']}.json",
            {"key":task["key"],"status":"claims" if claim else "ok",
             "missing":claim},
        )
    batches=coverage_compare_tasks(tmp_path)
    assert batches["count"]>1
    flattened=[
        ki["id"] for task in batches["comparisons"] for ki in task["known_items"]
    ]
    assert len(flattened)==180
    assert len(set(flattened))==180
    assert all(
        len(coverage.canonical(task["known_items"])) < 7500
        for task in batches["comparisons"]
    )
    put_json(tmp_path/"okf-v4/state-b/coverage/comparison-tasks.json",batches)
    claim_id=batches["comparisons"][0]["claims"][0]["id"]
    for i, task in enumerate(batches["comparisons"]):
        put_json(
            tmp_path/f"okf-v4/state-b/coverage/comparisons/{task['key']}.json",
            {"key":task["key"],
             "covered_facets":[{"claim_id":claim_id,"facet_indices":[0]}]
                if i==len(batches["comparisons"])-1 else []},
        )
    assert coverage_additions(tmp_path,required=True)==[]
    (tmp_path/f"okf-v4/state-b/coverage/comparisons/"
     f"{batches['comparisons'][-1]['key']}.json").unlink()
    with pytest.raises(ValueError,match="Required file"):
        coverage_additions(tmp_path,required=True)


def test_collective_facet_coverage_across_disjoint_item_batches(tmp_path, monkeypatch):
    """A compound claim must be covered by distinct KIs in separate batches."""
    fixture(tmp_path)
    migrate_applied(tmp_path)
    import source_coverage as coverage
    real_check=coverage.checked_phase_a

    def two_items(workspace, root="okf-v4/phase-a"):
        marker,catalog,base=real_check(workspace,root)
        import copy
        catalog=copy.deepcopy(catalog)
        original=catalog["documents"][0]["source_knowledge_items"][0]
        catalog["documents"][0]["source_knowledge_items"]=[
            {**original,"id":"example:approval",
             "description":"Approval must be obtained before proceeding."},
            {**original,"id":"example:logging",
             "description":"The operation must be logged."},
        ]
        return marker,catalog,base

    monkeypatch.setattr(coverage,"checked_phase_a",two_items)
    monkeypatch.setattr(coverage,"MAX_COMPARE_ITEM_BYTES",180)
    tasks=coverage_tasks(tmp_path)
    put_json(tmp_path/"okf-v4/state-b/coverage/tasks.json",tasks)
    for task in tasks["chunks"]:
        missing=[]
        if task==tasks["chunks"][0]:
            line=next(x for x in task["lines"] if len(x["text"])>=10)
            missing=[{
                "line":line["line"],"source_quote":line["text"][:10],
                "statement":"Approval and logging are both required.",
                "normative":True,
                "facets":["Approval must be obtained first.",
                          "The operation must be logged."],
            }]
        put_json(
            tmp_path/f"okf-v4/state-b/coverage/reviews/{task['key']}.json",
            {"key":task["key"],"status":"claims" if missing else "ok",
             "missing":missing},
        )
    comparisons=coverage_compare_tasks(tmp_path)
    assert comparisons["count"]==2
    assert all(len(x["known_items"])==1 for x in comparisons["comparisons"])
    put_json(tmp_path/"okf-v4/state-b/coverage/comparison-tasks.json",comparisons)
    ident=comparisons["comparisons"][0]["claims"][0]["id"]
    for index, task in enumerate(comparisons["comparisons"]):
        put_json(
            tmp_path/f"okf-v4/state-b/coverage/comparisons/{task['key']}.json",
            {"key":task["key"],
             "covered_facets":[{"claim_id":ident,"facet_indices":[index]}]},
        )
    assert coverage_additions(tmp_path,required=True)==[]
    last=comparisons["comparisons"][-1]
    put_json(
        tmp_path/f"okf-v4/state-b/coverage/comparisons/{last['key']}.json",
        {"key":last["key"],"covered_facets":[]},
    )
    findings=coverage_additions(tmp_path,required=True)
    assert len(findings)==1
    assert findings[0]["id"]==ident


def test_source_coverage_windows_console_transport_is_ascii_safe(tmp_path):
    fixture(tmp_path)
    migrate_applied(tmp_path)
    task=coverage_tasks(tmp_path)
    import json
    # The task JSON may contain umlauts, but subprocess output is ASCII
    # transport even with Windows cp1252 stdout.
    encoded=json.dumps(task,ensure_ascii=True).encode("cp1252")
    assert json.loads(encoded.decode("cp1252"))==task


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


@pytest.mark.parametrize("legacy,valid", [
    ("md-ttp-example-the-russian-reconnaissance-fire-complex-2d4ab5ebcc37cb28", True),
    ("md-ttp-example-the-russian-reconnaissance-fire-complex-2d4ab5ebcc37cb29", False),
    ("unrelated-2d4ab5ebcc37cb28", False),
    ("md-ttp-example-the-russian-2d4ab5ebcc37cb28", False),
    ("md-ttp-example-the-russian-reconnaissance-fire-complex-2d4ab5ebcc37cb28-extra", False),
])
def test_legacy_scan_document_slug_alias_is_bounded_and_hash_checked(legacy, valid):
    from migrate_v3 import _same_legacy_document_slug
    canonical = (
        "md-ttp-example-the-russian-reconnaissance-fire-complex-comes-"
        "2d4ab5ebcc37cb28"
    )
    assert _same_legacy_document_slug(legacy,canonical) is valid


@pytest.mark.parametrize("field", ["document_id", "folder_id"])
def test_migration_accepts_hash_identical_legacy_scan_document_id(tmp_path,field):
    slug = "example-a-detailed-source-comes-2d4ab5ebcc37cb28"
    fixture(tmp_path, slug)
    original = tmp_path/f"okf-batched/state-v3/docs/{slug}/scan-s001.json"
    scan=json.loads(original.read_text(encoding="utf-8"))
    scan[field]="example-a-detailed-source-2d4ab5ebcc37cb28"
    put_json(original,scan)
    before=original.read_bytes()
    migrate_applied(tmp_path)
    _,catalog,_=checked_phase_a(tmp_path)
    assert catalog["documents"][0]["legacy_scan_route_aliases"] == [{
        "section_id":"s001", "field":field, "legacy":scan[field],
        "canonical":slug,
    }]
    assert original.read_bytes()==before


@pytest.mark.parametrize("field,blank", [
    ("document_id", None), ("folder_id", ""), ("chunk_id", "  "),
])
def test_migration_accepts_legacy_missing_scan_route_without_modifying_v3(
    tmp_path, field, blank,
):
    fixture(tmp_path)
    scan_path=tmp_path/"okf-batched/state-v3/docs/example/scan-s001.json"
    scan=json.loads(scan_path.read_text(encoding="utf-8"))
    if blank is None:
        scan.pop(field)
    else:
        scan[field]=blank
    put_json(scan_path,scan)
    original=scan_path.read_bytes()
    migrate_applied(tmp_path)
    _,catalog,_=checked_phase_a(tmp_path)
    assert catalog["documents"][0]["source_knowledge_items"][0]["id"]=="example:k001"
    assert scan_path.read_bytes()==original


@pytest.mark.parametrize("field,wrong", [
    ("document_id", "another-document"),
    ("folder_id", "another-document"),
    ("chunk_id", "s099"),
    ("section_id", "s099"),
    ("source_path", "md/other.md"),
    ("start_line", 2),
    ("end_line", 3),
])
def test_migration_rejects_conflicting_scan_metadata(tmp_path,field,wrong):
    fixture(tmp_path)
    scan_path=tmp_path/"okf-batched/state-v3/docs/example/scan-s001.json"
    scan=json.loads(scan_path.read_text(encoding="utf-8"))
    scan[field]=wrong
    put_json(scan_path,scan)
    original=scan_path.read_bytes()
    with pytest.raises(ValueError,match=field):
        migrate_applied(tmp_path)
    assert scan_path.read_bytes()==original
    assert not (tmp_path/"okf-v4/phase-a").exists()


def test_v3_original_source_links_become_text_with_catalog_provenance(tmp_path):
    fixture(tmp_path)
    old=tmp_path/"okf-batched-generated-v3/doctrines/example/organization/s001-c010.md"
    old.write_text(
        old.read_text(encoding="utf-8")
        + "\n[Originalquelle](../../../../doctrines/example.md)\n",
        encoding="utf-8",
    )
    migrate_applied(tmp_path)
    _,catalog,base=checked_phase_a(tmp_path)
    concept=(base/catalog["concepts"][0]["path"]).read_text(encoding="utf-8")
    assert "Originalquelle" in concept
    assert "../../../../doctrines/example.md" not in concept
    assert catalog["documents"][0]["original_path"]=="doctrines/example.md"
    assert (base/"sources/example.md").is_file()
    assert not (base/"doctrines/example.md").exists()
    finished_b(tmp_path)
    finished_c(tmp_path)
    published=(tmp_path/"okf-v4/published"/catalog["concepts"][0]["path"]).read_text(
        encoding="utf-8"
    )
    assert "Originalquelle" in published
    assert "../../../../doctrines/example.md" not in published


def test_source_link_matches_md_root_but_not_unrelated_markdown():
    from migrate_v3 import _markdown_links
    old="doctrines/example/organization/s001-c010.md"
    exact=frozenset({"../md/source.md"})
    assert _markdown_links(
        "[Source](../../../../md/source.md)",
        old,old,{},source_targets=exact,
    )=="Source"
    with pytest.raises(ValueError, match="Unresolved concept Markdown link"):
        _markdown_links(
            "[Unrelated](../../../../md/unknown.md)",
            old,old,{},source_targets=exact,
        )


def test_nested_source_root_resolves_only_real_workspace_sources(tmp_path):
    fixture(tmp_path)
    generated=tmp_path/"okf-batched-generated-v3"
    nested=tmp_path/"nested/generated"
    nested.parent.mkdir(parents=True,exist_ok=True)
    generated.rename(nested)
    old=nested/"doctrines/example/organization/s001-c010.md"
    old.write_text(
        old.read_text(encoding="utf-8")
        + "\n[Actual source](../../../../../doctrines/example.md)\n",
        encoding="utf-8",
    )
    from migrate_v3 import migrate
    kwargs={
        "source_root":"nested/generated",
        "state_root":"okf-batched/state-v3/docs",
        "destination":"okf-v4/phase-a",
    }
    migrate(tmp_path,**kwargs,apply=True)
    _,catalog,base=checked_phase_a(tmp_path)
    content=(base/catalog["concepts"][0]["path"]).read_text(encoding="utf-8")
    assert "Actual source" in content
    assert "../../../../../doctrines/example.md" not in content

    # A path resolving to nested/doctrines rather than the actual workspace
    # source must not be silently accepted, even when the basename matches.
    old.write_text(
        old.read_text(encoding="utf-8")
        + "\n[Wrong source](../../../../doctrines/example.md)\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError,match="Unresolved concept Markdown link"):
        migrate(tmp_path,**kwargs,apply=False)


def test_source_hyperlink_to_ungrouped_existing_md_is_accepted(tmp_path):
    fixture(tmp_path)
    original=tmp_path/"doctrines/Other_Source.md"
    original.write_text("# A valid but ungrouped source\n",encoding="utf-8")
    old=tmp_path/"okf-batched-generated-v3/doctrines/example/organization/s001-c010.md"
    old.write_text(
        old.read_text(encoding="utf-8")
        + "\n[Other source](../../../../doctrines/other_source.MD)\n",
        encoding="utf-8",
    )
    migrate_applied(tmp_path)
    _,catalog,base=checked_phase_a(tmp_path)
    concept=catalog["concepts"][0]
    imported=(base/concept["path"]).read_text(encoding="utf-8")
    assert "Other source" in imported
    assert "other_source.MD" not in imported
    assert concept["source_reference_paths"]==["doctrines/Other_Source.md"]
    # Referenced but ungrouped sources cannot silently enter the A file set.
    assert not (base/"sources/Other_Source.md").exists()
    assert not (base/"doctrines/Other_Source.md").exists()


def test_source_hyperlink_to_missing_md_still_fails(tmp_path):
    fixture(tmp_path)
    old=tmp_path/"okf-batched-generated-v3/doctrines/example/organization/s001-c010.md"
    old.write_text(
        old.read_text(encoding="utf-8")
        + "\n[Other source](../../../../doctrines/Other_Source.md)\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError,match="Unresolved concept Markdown link"):
        migrate_applied(tmp_path)


def test_source_hyperlink_with_nested_v3_root_uses_actual_file(tmp_path):
    fixture(tmp_path)
    generated=tmp_path/"okf-batched-generated-v3"
    nested=tmp_path/"nested/generated"
    nested.parent.mkdir(parents=True,exist_ok=True)
    generated.rename(nested)
    source=tmp_path/"doctrines/Other_Source.md"
    source.write_text("# Another source\n",encoding="utf-8")
    old=nested/"doctrines/example/organization/s001-c010.md"
    old.write_text(
        old.read_text(encoding="utf-8")
        + "\n[Other source](../../../../../doctrines/Other_Source.md)\n",
        encoding="utf-8",
    )
    result=migrate(
        tmp_path,source_root="nested/generated",
        state_root="okf-batched/state-v3/docs",
        destination="okf-v4/phase-a",apply=True,
    )
    assert result["status"]=="completed"
    _,catalog,base=checked_phase_a(tmp_path)
    concept=catalog["concepts"][0]
    assert concept["source_reference_paths"]==["doctrines/Other_Source.md"]
    assert "Other source" in (base/concept["path"]).read_text(encoding="utf-8")
    old.write_text(
        old.read_text(encoding="utf-8")
        + "\n[False path](../../../../doctrines/Other_Source.md)\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError,match="Unresolved concept Markdown link"):
        migrate(
            tmp_path,source_root="nested/generated",
            state_root="okf-batched/state-v3/docs",
            destination="okf-v4/phase-a",
        )


def test_workspace_rooted_md_source_link_in_legacy_concept(tmp_path):
    fixture(tmp_path)
    from migrate_v3 import migrate
    original=tmp_path/"doctrines/example.md"
    md=tmp_path/"md"
    md.mkdir()
    source=md/"Enemy_SOP_RUS_example.md"
    source.write_text("# External reference\n",encoding="utf-8")
    original.rename(md/"example.md")
    state=tmp_path/"okf-batched/state-v3/docs/example"
    sections=json.loads((state/"sections.json").read_text(encoding="utf-8"))
    sections["source_path"]="md/example.md"
    put_json(state/"sections.json",sections)
    scan=json.loads((state/"scan-s001.json").read_text(encoding="utf-8"))
    scan["source_path"]="md/example.md"
    for item in scan["knowledge_items"]:
        for evidence in item["evidence_ranges"]:
            evidence["doctrine"]="md/example.md"
    put_json(state/"scan-s001.json",scan)
    group=json.loads((state/"group.json").read_text(encoding="utf-8"))
    for concept in group["concepts"]:
        for item in concept["coverage_items"]:
            for evidence in item["evidence_ranges"]:
                evidence["doctrine"]="md/example.md"
        for evidence in concept["evidence_ranges"]:
            evidence["source_path"]="md/example.md"
    put_json(state/"group.json",group)
    old=tmp_path/"okf-batched-generated-v3/doctrines/example/organization/s001-c010.md"
    old.write_text(
        old.read_text(encoding="utf-8")
        + "\n[Quelle](md/Enemy_SOP_RUS_example.md)\n",
        encoding="utf-8",
    )
    kwargs=dict(
        source_root="okf-batched-generated-v3",
        state_root="okf-batched/state-v3/docs",
        destination="okf-v4/phase-a",
        document_root="md",
    )
    migrate(tmp_path,**kwargs,apply=True)
    _,catalog,base=checked_phase_a(tmp_path)
    concept=catalog["concepts"][0]
    imported=(base/concept["path"]).read_text(encoding="utf-8")
    assert "\nQuelle\n" in imported
    assert "md/Enemy_SOP_RUS_example.md" not in imported
    assert concept["source_reference_paths"]==["md/Enemy_SOP_RUS_example.md"]
    assert not (base/"sources/Enemy_SOP_RUS_example.md").exists()
    # Unknown files under the same workspace-relative prefix must fail.
    old.write_text(
        old.read_text(encoding="utf-8") +
        "\n[Not there](md/not-existing.md)\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError,match="Unresolved concept Markdown link"):
        migrate(tmp_path,**kwargs)


def test_workspace_rooted_source_lookup_never_accepts_traversal():
    from migrate_v3 import _markdown_links
    old="doctrines/example/organization/old.md"
    targets=frozenset({"../md/example.md"})
    assert _markdown_links(
        "[Quelle](md/example.md)",old,old,{},
        source_targets=targets,workspace_source_root="okf-batched-generated-v3",
        document_root="md",
    )=="Quelle"
    with pytest.raises(ValueError,match="Unresolved concept Markdown link"):
        _markdown_links(
            "[Wrong](md/../example.md)",old,old,{},
            source_targets=targets,workspace_source_root="okf-batched-generated-v3",
            document_root="md",
        )


def test_workspace_source_fallback_does_not_shadow_imported_concept():
    from migrate_v3 import _markdown_links
    old="doctrines/example/old.md"
    target="doctrines/example/doctrines/other.md"
    source_target="../doctrines/other.md"
    references=set()
    result=_markdown_links(
        "[Concept](doctrines/other.md)",old,old,
        {target:"doctrines/example/new-concept.md"},
        source_targets=frozenset({source_target}),
        source_references=references,
        workspace_source_root="okf-batched-generated-v3",
        document_root="doctrines",
    )
    assert result=="[Concept](new-concept.md)"
    assert references==set()


def test_workspace_source_fallback_matches_full_nested_document_root():
    from migrate_v3 import _markdown_links
    old="doctrines/example/organization/old.md"
    references=set()
    result=_markdown_links(
        "[Nested](inputs/md/example.md)",old,old,{},
        source_targets=frozenset({"../inputs/md/example.md"}),
        source_references=references,
        workspace_source_root="okf-batched-generated-v3",
        document_root="inputs/md",
    )
    assert result=="Nested"
    assert references=={"../inputs/md/example.md"}
    with pytest.raises(ValueError,match="Unresolved concept Markdown link"):
        _markdown_links(
            "[Wrong](inputs/md/../example.md)",old,old,{},
            source_targets=frozenset({"../inputs/example.md"}),
            workspace_source_root="okf-batched-generated-v3",
            document_root="inputs/md",
        )
    with pytest.raises(ValueError,match="Unresolved concept Markdown link"):
        _markdown_links(
            "[Wrong](inputs/example.md)",old,old,{},
            source_targets=frozenset({"../inputs/example.md"}),
            workspace_source_root="okf-batched-generated-v3",
            document_root="inputs/md",
        )


def test_migration_defers_legacy_index_navigation_to_phase_c(tmp_path):
    fixture(tmp_path)
    legacy = tmp_path/"okf-batched-generated-v3/doctrines/example/organization/s001-c010.md"
    legacy.write_text(
        legacy.read_text(encoding="utf-8")
        + "\n[Ordnerübersicht](index.md)\n"
        + "[Doktrinübersicht](../index.md)\n"
        + "[Startseite](../../../index.md)\n",
        encoding="utf-8",
    )
    migrate_applied(tmp_path)
    _, catalog, base = checked_phase_a(tmp_path)
    migrated = base/catalog["concepts"][0]["path"]
    body = migrated.read_text(encoding="utf-8")
    assert "[Ordnerübersicht](index.md)" in body
    assert "[Doktrinübersicht](../index.md)" in body
    assert "[Startseite](../../../index.md)" in body
    assert not list(base.rglob("index.md"))
    # C must resolve those links against the freshly generated indexes.
    finished_b(tmp_path)
    finished_c(tmp_path)
    published = tmp_path/"okf-v4/published"/catalog["concepts"][0]["path"]
    text = published.read_text(encoding="utf-8")
    assert "[Ordnerübersicht](index.md)" in text
    assert "[Doktrinübersicht](../index.md)" in text
    assert "[Startseite](../../../index.md)" in text


def test_migration_ignores_case_variant_legacy_index_link_only_in_a(tmp_path):
    from migrate_v3 import _markdown_links
    text = "[Overview](../INDEX.MD)"
    old = "doctrines/example/organization/old.md"
    new = "doctrines/example/organization/new.md"
    assert _markdown_links(
        text, old, new, {}, allow_deferred_index_links=True
    ) == text
    assert _markdown_links(
        text, old, new, {"doctrines/example/index.md":"doctrines/example/index.md"}
    ) == "[Overview](../index.md)"
    with pytest.raises(ValueError, match="Unresolved concept Markdown link"):
        _markdown_links(text, old, new, {})


def test_migration_still_rejects_missing_non_index_concept_target(tmp_path):
    fixture(tmp_path)
    legacy = tmp_path/"okf-batched-generated-v3/doctrines/example/organization/s001-c010.md"
    legacy.write_text(
        legacy.read_text(encoding="utf-8") + "\n[Lost](../missing.md)\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Unresolved concept Markdown link"):
        migrate_applied(tmp_path)


def test_phase_c_rejects_deferred_index_link_when_page_is_not_generated(tmp_path):
    from migrate_v3 import _markdown_links
    with pytest.raises(ValueError, match="Unresolved concept Markdown link"):
        _markdown_links(
            "[Missing](../../other/index.md)",
            "doctrines/example/organization/a.md",
            "doctrines/example/organization/a.md",
            {"doctrines/example/index.md": "doctrines/example/index.md"},
        )


def test_migration_accepts_configurable_original_document_root(tmp_path):
    fixture(tmp_path)
    old_source=tmp_path/"doctrines/example.md"
    new_source=tmp_path/"md/example.md"
    new_source.parent.mkdir(parents=True,exist_ok=True)
    old_source.rename(new_source)
    state=tmp_path/"okf-batched/state-v3/docs/example"
    sections=json.loads((state/"sections.json").read_text(encoding="utf-8"))
    sections["source_path"]="md/example.md"
    put_json(state/"sections.json",sections)
    scan=json.loads((state/"scan-s001.json").read_text(encoding="utf-8"))
    scan["source_path"]="md/example.md"
    for item in scan["knowledge_items"]:
        for evidence in item["evidence_ranges"]:
            evidence["doctrine"]="md/example.md"
    put_json(state/"scan-s001.json",scan)
    group=json.loads((state/"group.json").read_text(encoding="utf-8"))
    for concept in group["concepts"]:
        for item in concept["coverage_items"]:
            for evidence in item["evidence_ranges"]:
                evidence["doctrine"]="md/example.md"
        for evidence in concept["evidence_ranges"]:
            evidence["source_path"]="md/example.md"
    put_json(state/"group.json",group)
    kwargs={
        "source_root":"okf-batched-generated-v3",
        "state_root":"okf-batched/state-v3/docs",
        "destination":"okf-v4/phase-a",
    }
    with pytest.raises(ValueError,match="Unexpected source document path"):
        migrate(tmp_path,**kwargs)
    result=migrate(tmp_path,**kwargs,document_root="md",apply=True)
    assert result["status"]=="completed"
    marker,catalog,base=checked_phase_a(tmp_path)
    assert marker["document_count"]==1
    assert catalog["documents"][0]["original_path"]=="md/example.md"
    assert catalog["concepts"][0]["source_original_path"]=="md/example.md"
    assert (base/"sources/example.md").read_bytes()==new_source.read_bytes()
    assert (base/"doctrines/example/organization/zusammenarbeit-und-aufgaben.md").is_file()
    assert not (base/"md").exists()


def test_document_root_rejects_unsafe_or_overlapping_paths(tmp_path):
    fixture(tmp_path)
    kwargs={
        "source_root":"okf-batched-generated-v3",
        "state_root":"okf-batched/state-v3/docs",
        "destination":"okf-v4/phase-a",
    }
    for document_root in ("../md", "/md", "C:/md", r"md\\sub"):
        with pytest.raises(ValueError,match="Unsafe workspace path"):
            migrate(tmp_path,**kwargs,document_root=document_root)
    with pytest.raises(ValueError,match="overlaps"):
        migrate(tmp_path,**{**kwargs,"destination":"doctrines/phase-a"})


def test_migration_keeps_incomplete_coverage_for_pre_inventory_repair(tmp_path):
    fixture(tmp_path)
    state=tmp_path/"okf-batched/state-v3/docs/example"
    original_scan=state/"scan-s001.json"
    scan=json.loads(original_scan.read_text())
    scan["knowledge_items"].append({
        "id":"k002", "normative":True,
        "description":"A distinct source-grounded requirement",
        "evidence_ranges":[{
            "doctrine":"doctrines/example.md", "start_line":1, "end_line":2
        }],
    })
    put_json(original_scan, scan)
    coverage=json.loads((state/"coverage.json").read_text())
    coverage.update({
        "status":"needs_revision",
        "missing_item_ids":["example:k002"],
        "warnings":["Uncovered scanned assertion"],
        "expected_normative_items":2,
    })
    put_json(state/"coverage.json",coverage)
    # Incomplete V3 repair is expected and no longer a migration blocker.
    repair=state/"concept-s001-c010-repair.json"
    repair.unlink()
    migrate_applied(tmp_path)
    marker,catalog,_=checked_phase_a(tmp_path)
    assert marker["knowledge_item_count"]==1
    assert marker["source_knowledge_item_count"]==2
    assert marker["pending_knowledge_item_count"]==1
    assert catalog["documents"][0]["pending_knowledge_item_ids"]==["example:k002"]
    tasks=source_repair_tasks(tmp_path)
    assert {t["kind"] for t in tasks["concepts"]}=={"existing","missing"}
    for task in tasks["concepts"]:
        if task["kind"]=="existing":
            proposal={
                "id":task["id"],"action":"keep","title":task["title"],
                "markdown":"","knowledge_item_ids":task["knowledge_item_ids"],
            }
        else:
            title="Zusaetzliche Anforderung"
            proposal={
                "id":task["id"],"action":"rewrite","title":title,
                "markdown":(
                    "---\ntitle: Zusaetzliche Anforderung\ntype: concept\n---\n"
                    "# Zusaetzliche Anforderung\n"
                    "Eine weitere Anforderung, die ausdrücklich in der Ursprungsvorschrift belegt ist.\n"
                ),
                "knowledge_item_ids":task["knowledge_item_ids"],
            }
        put_json(tmp_path/f"okf-v4/state-b/source-repair/proposals/{task['key']}.json",proposal)
    apply_source_repair(tmp_path,tasks)
    checked_b(tmp_path,root="okf-v4/b-source-repaired",stage="B-source")
    recovered=prepare(tmp_path,"okf-v4/b-source-repaired")
    assert len(recovered["concepts"])==2
    assert sum(x["knowledge_item_count"] for x in recovered["concepts"])==2


def test_source_repair_diagnose_reports_nested_field_without_llm(tmp_path):
    fixture(tmp_path)
    repair=tmp_path/"okf-batched/state-v3/docs/example/concept-s001-c010-repair.json"
    repair.unlink()
    migrate_applied(tmp_path)
    tasks=source_repair_tasks(tmp_path,skip_coverage=True)
    path=tmp_path/"okf-v4/state-b/source-repair/tasks.json"
    put_json(path,tasks)
    import subprocess
    process=subprocess.run(
        [sys.executable,str(V4/"source_repair.py"),
         "--mode","diagnose","--skip-coverage"],
        input="",cwd=tmp_path,capture_output=True,text=True,
    )
    assert process.returncode==0,process.stderr
    assert json.loads(process.stdout)["task_count"]==1
    import copy
    changed=copy.deepcopy(tasks)
    changed["concepts"][0]["feedback"]["status"]="altered"
    put_json(path,changed)
    process=subprocess.run(
        [sys.executable,str(V4/"source_repair.py"),
         "--mode","diagnose","--skip-coverage"],
        input="",cwd=tmp_path,capture_output=True,text=True,
    )
    assert process.returncode==0, process.stdout
    result=json.loads(process.stdout)
    assert result["status"]=="ok"
    assert path.exists()
    # Identity and source evidence must still be validated strictly.
    changed["concepts"][0]["knowledge_items"][0]["id"]="fabricated"
    put_json(path,changed)
    process=subprocess.run(
        [sys.executable,str(V4/"source_repair.py"),
         "--mode","diagnose","--skip-coverage"],
        input="",cwd=tmp_path,capture_output=True,text=True,
    )
    assert process.returncode==1
    assert "$.knowledge_items[0].id" in json.loads(process.stdout)["detail"]


def test_source_repair_accepts_reordered_checkpoint_task_ledger(tmp_path):
    """The 1,687 review files are keyed; task array order is not identity."""
    fixture(tmp_path, "example")
    fixture(tmp_path, "second")
    for slug in ("example", "second"):
        repair=tmp_path/f"okf-batched/state-v3/docs/{slug}/concept-s001-c010-repair.json"
        repair.unlink()
    migrate_applied(tmp_path)
    tasks=source_repair_tasks(tmp_path,skip_coverage=True)
    assert tasks["count"]==2
    for task in tasks["concepts"]:
        put_json(
            tmp_path/f"okf-v4/state-b/source-repair/proposals/{task['key']}.json",
            {"id":task["id"],"action":"keep","title":task["title"],
             "markdown":"","knowledge_item_ids":task["knowledge_item_ids"]},
        )
    reordered={**tasks,"concepts":list(reversed(tasks["concepts"]))}
    apply_source_repair(tmp_path,reordered,skip_coverage=True)
    checked_b(tmp_path,root="okf-v4/b-source-repaired",stage="B-source")


def test_source_repair_preserves_checkpointed_proposal_when_replacement_escape_differs(
    tmp_path,
):
    """Literal '\\ufffd' in V3 and U+FFFD after JSON transit are equivalent
    only in Knowledge Item descriptions; source identities remain strict.
    """
    fixture(tmp_path)
    repair=tmp_path/"okf-batched/state-v3/docs/example/concept-s001-c010-repair.json"
    repair.unlink()
    migrate_applied(tmp_path)
    from source_repair import _reconcile_tasks
    import copy
    expected=source_repair_tasks(tmp_path,skip_coverage=True)
    assert expected["count"]==1
    expected=copy.deepcopy(expected)
    task=expected["concepts"][0]
    assert task["knowledge_items"]
    task["knowledge_items"][0]["description"]=r"Standing Opera\ufffdting Procedure"
    incoming=copy.deepcopy(expected)
    incoming["concepts"][0]["knowledge_items"][0]["description"]=(
        "Standing Opera\ufffdting Procedure"
    )
    assert _reconcile_tasks(incoming,expected)==expected
    proposal=tmp_path/f"okf-v4/state-b/source-repair/proposals/{task['key']}.json"
    put_json(proposal,{"id":task["id"],"action":"keep","title":task["title"],
                       "markdown":"","knowledge_item_ids":task["knowledge_item_ids"]})
    assert proposal.exists()
    # Description text is advisory after JSON transport, even when it
    # differs beyond a specific replacement marker.
    changed=copy.deepcopy(incoming)
    changed["concepts"][0]["knowledge_items"][0]["description"]=(
        "Standing Operating Procedure and extra wording"
    )
    assert _reconcile_tasks(changed,expected)==expected
    changed=copy.deepcopy(incoming)
    changed["concepts"][0]["knowledge_items"][0]["id"]="example:invented"
    with pytest.raises(ValueError,match=r"identity/provenance mismatch"):
        _reconcile_tasks(changed,expected)
    changed=copy.deepcopy(incoming)
    changed["concepts"][0]["title"]="Not the original title"
    with pytest.raises(ValueError,match=r"identity/provenance mismatch"):
        _reconcile_tasks(changed,expected)
    changed=copy.deepcopy(incoming)
    changed["concepts"][0]["knowledge_items"][0]["evidence_ranges"][0]["start_line"]=999
    with pytest.raises(ValueError,match=r"identity/provenance mismatch"):
        _reconcile_tasks(changed,expected)
    assert proposal.exists()


def test_source_repair_keeps_keyed_identity_checks_without_prose_checks():
    from source_repair import _reconcile_tasks
    import copy
    expected={"schema":"v1","status":"ok","count":1,"concepts":[{
        "id":"example:s1","key":"stable-key","knowledge_items":[{
            "id":"ki1","description":r"Standing Opera\ufffdng Procedure"
        }]}]}
    given=copy.deepcopy(expected)
    given["concepts"][0]["knowledge_items"][0]["description"]="Standing Operating Procedure"
    assert _reconcile_tasks(given,expected)==expected
    given["concepts"][0]["knowledge_items"][0]["description"]="Standing Operating Different"
    assert _reconcile_tasks(given,expected)==expected
    given["concepts"][0]["knowledge_items"][0]["id"]="invented"
    with pytest.raises(ValueError,match="identity/provenance mismatch"):
        _reconcile_tasks(given,expected)


def test_source_repair_accepts_optional_missing_ki_description():
    from source_repair import _reconcile_tasks
    import copy

    expected = {
        "schema": "v1", "status": "ok", "count": 1,
        "concepts": [{
            "id": "example:s1", "key": "stable-key",
            "knowledge_items": [{"id": "ki1", "normative": False}],
        }],
    }
    incoming = copy.deepcopy(expected)
    assert _reconcile_tasks(incoming, expected) == expected
    incoming["concepts"][0]["knowledge_items"][0]["description"] = "added"
    with pytest.raises(ValueError, match="identity/provenance mismatch"):
        _reconcile_tasks(incoming, expected)
    incoming = copy.deepcopy(expected)
    incoming["concepts"][0]["knowledge_items"][0]["normative"] = True
    with pytest.raises(ValueError, match="identity/provenance mismatch"):
        _reconcile_tasks(incoming, expected)


def test_source_repair_reports_first_different_field_and_preserves_proposals(
    tmp_path,
):
    fixture(tmp_path)
    repair=tmp_path/"okf-batched/state-v3/docs/example/concept-s001-c010-repair.json"
    repair.unlink()
    migrate_applied(tmp_path)
    tasks=source_repair_tasks(tmp_path,skip_coverage=True)
    task=tasks["concepts"][0]
    proposal=tmp_path/f"okf-v4/state-b/source-repair/proposals/{task['key']}.json"
    put_json(
        proposal,
        {"id":task["id"],"action":"keep","title":task["title"],
         "markdown":"","knowledge_item_ids":task["knowledge_item_ids"]},
    )
    import copy
    modified=copy.deepcopy(tasks)
    modified["concepts"][0]["title"]="Wrong"
    with pytest.raises(ValueError,match=r"identity/provenance mismatch \$\.title:"):
        apply_source_repair(tmp_path,modified,skip_coverage=True)
    assert proposal.exists()
    modified=copy.deepcopy(tasks)
    modified["concepts"][0]["key"]="wrong-task-key"
    with pytest.raises(ValueError,match="task keys differ"):
        apply_source_repair(tmp_path,modified,skip_coverage=True)
    assert proposal.exists()
    with pytest.raises(ValueError,match="task count differs"):
        apply_source_repair(
            tmp_path,{**tasks,"concepts":[]},skip_coverage=True,
        )
    assert proposal.exists()


def test_source_repair_rejects_modified_original_knowledge_item_ids(tmp_path):
    fixture(tmp_path)
    migrate_applied(tmp_path)
    tasks=source_repair_tasks(tmp_path)
    assert tasks["count"]==0
    apply_source_repair(tmp_path,tasks)
    checked_b(tmp_path,root="okf-v4/b-source-repaired",stage="B-source")
    catalog_path=tmp_path/"okf-v4/b-source-repaired/catalog.json"
    catalog=json.loads(catalog_path.read_text())
    catalog["concepts"][0]["knowledge_items"][0]["id"]="fabricated:k999"
    put_json(catalog_path,catalog)
    with pytest.raises(ValueError):
        checked_b(tmp_path,root="okf-v4/b-source-repaired",stage="B-source")


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
    tasks=prepare_repaired(workspace)
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
    result=apply_quality(workspace,phase_a="okf-v4/b-source-repaired",
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
    original_tasks=prepare_initial_verification(workspace)
    for task in original_tasks["concepts"]:
        put_json(workspace/f"okf-v4/state-b/final/verification/{task['key']}.json",{
            "id":task["id"],"status":"ok",
            "missing_item_ids":[],"warnings":[],
        })
    first=select_repairs(workspace,1)
    assert not first["concepts"]
    apply_repairs(workspace,1,first)
    assert not repair_verification_tasks(workspace,1,first)["concepts"]
    second=select_repairs(workspace,2)
    assert not second["concepts"]
    apply_repairs(workspace,2,second)
    assert not repair_verification_tasks(workspace,2,second)["concepts"]
    certification=certify_repairs(workspace)
    final_tasks=prepare_final_inventory(workspace)
    for task in final_tasks["concepts"]:
        put_json(workspace/f"okf-v4/state-b/final/summaries/{task['key']}.json",{
            "id":task["id"],
            "summary":"Das final geprüfte Konzept beschreibt die Zuordnung von Aufgaben.",
            "tags":["Koordination"],
        })
    complete(workspace,tasks=final_tasks,certification=certification)
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
    tasks=prepare_repaired(tmp_path)
    item=tasks["concepts"][0]
    put_json(tmp_path/f"okf-v4/state-b/reviews/{item['key']}.json",{
        "id":item["id"],"action":"keep","reason":"Valid concept.","parts":[],
    })
    with pytest.raises(ValueError,match="Required file"):
        apply_quality(tmp_path,phase_a="okf-v4/b-source-repaired",state="okf-v4/state-b",
                      tasks=tasks,destination="okf-v4/b-reviewed")
    assert not (tmp_path/"okf-v4/phase-b").exists()
    assert not (tmp_path/"okf-v4/published").exists()


def test_main_b_ignores_partial_legacy_full_source_audit(tmp_path):
    """Old aborted audit ledgers must not block the streamlined V3-only B."""
    fixture(tmp_path)
    migrate_applied(tmp_path)
    stale=tmp_path/"okf-v4/state-b/coverage/tasks.json"
    put_json(stale, {"schema":"old", "chunks":[{"key":"stale"}]})
    tasks=source_repair_tasks(tmp_path, skip_coverage=True)
    assert tasks["count"]==0
    assert tasks["concepts"]==[]
    with pytest.raises(ValueError):
        source_repair_tasks(tmp_path, require_coverage=True, skip_coverage=True)
    from source_repair import apply as apply_source_repair
    apply_source_repair(tmp_path, tasks, skip_coverage=True)
    _,catalog,_=checked_b(tmp_path,root="okf-v4/b-source-repaired",stage="B-source")
    assert catalog["source_coverage_sha256"] is None
    assert sum(len(c["knowledge_items"]) for c in catalog["concepts"]) == sum(
        len(d["source_knowledge_items"]) for d in catalog["documents"]
    )


def test_flows_separate_quality_and_publishing():
    import tomllib
    b=tomllib.loads((V4/"phase-b.toml").read_text(encoding="utf-8"))
    c=tomllib.loads((V4/"phase-c.toml").read_text(encoding="utf-8"))
    bsteps={step["id"]:step for step in b["steps"]}
    csteps={step["id"]:step for step in c["steps"]}
    assert list(bsteps)==[
        "source_repair_tasks","source_repair_review","apply_source_repairs",
        "inventory_tasks","summarize","quality_review","apply_quality",
        "merge_candidates","merge_review","apply_merges",
        "initial_verification_tasks","verify_final",
        "repair_candidates_1","repair_review_1","apply_repair_1",
        "repair_verification_tasks_1","verify_repair_1",
        "repair_candidates_2","repair_review_2","apply_repair_2",
        "repair_verification_tasks_2","verify_repair_2",
        "certify_repairs","final_inventory_tasks","summarize_final","complete_b",
    ]
    assert list(csteps)==["link_candidates","relate","publish_indexes"]
    assert b["result"]=="steps.complete_b.output"
    assert bsteps["source_repair_tasks"]["python_script"]["args"] == [
        "--mode", "prepare", "--skip-coverage",
    ]
    assert bsteps["apply_source_repairs"]["python_script"]["args"] == [
        "--mode", "apply", "--skip-coverage",
    ]
    assert not any(step.startswith("source_coverage") for step in bsteps)
    assert "certify_source_coverage" not in bsteps
    assert c["result"]=="steps.publish_indexes.output"
    assert bsteps["quality_review"]["foreach"]=="steps.inventory_tasks.output.concepts"
    assert bsteps["quality_review"]["workspace_access"]=="read"
    assert csteps["relate"]["workspace_access"]=="none"
    assert csteps["publish_indexes"]["python_script"]["path"].endswith("publish_indexes.py")
    assert csteps["publish_indexes"]["overwrite_output"] is True


@pytest.mark.parametrize("corruption,expected", [
    ({"path":"doctrines/example/organization/another.md"}, "path_mismatch"),
    ({"concept_id":"s999-t001"}, "concept_id_mismatch"),
    ({"documented_item_ids":["example:k999"]}, "documented_ids_mismatch"),
    ({"documented_item_ids":["example:k001","example:k001"]}, "documented_ids_invalid"),
    ({"remaining_item_ids":["example:k001"]}, "remaining_item_findings"),
    ({"status":"needs_revision"}, "status_incomplete"),
])
def test_migration_preserves_inconsistent_legacy_repair_as_finding(tmp_path, corruption, expected):
    fixture(tmp_path)
    repair_path=tmp_path/"okf-batched/state-v3/docs/example/concept-s001-c010-repair.json"
    repair=json.loads(repair_path.read_text())
    repair.update(corruption)
    put_json(repair_path,repair)
    migrate_applied(tmp_path)
    marker, catalog, _=checked_phase_a(tmp_path)
    assert marker["knowledge_item_count"]==1
    concept=catalog["concepts"][0]
    assert concept["knowledge_item_ids"]==["example:k001"]
    assert concept["source_repair_required"] is True
    assert expected in concept["legacy_repair_diagnostics"]["issues"]
    tasks=source_repair_tasks(tmp_path)
    assert tasks["count"]==1
    assert tasks["concepts"][0]["id"]==concept["id"]


def test_migration_trusts_authoritative_group_not_repair_item_claims(tmp_path):
    fixture(tmp_path)
    repair_path=tmp_path/"okf-batched/state-v3/docs/example/concept-s001-c010-repair.json"
    repair=json.loads(repair_path.read_text())
    repair["documented_item_ids"]=["example:unknown"]
    put_json(repair_path,repair)
    migrate_applied(tmp_path)
    _,catalog,_=checked_phase_a(tmp_path)
    assert catalog["concepts"][0]["knowledge_item_ids"]==["example:k001"]
    assert catalog["documents"][0]["source_knowledge_items"][0]["id"]=="example:k001"


def test_checkpoint_key_changes_when_source_concept_changes(tmp_path):
    fixture(tmp_path)
    migrate_applied(tmp_path)
    old_key=prepare_repaired(tmp_path)["concepts"][0]["key"]
    # A new import version with changed content must use a new LLM checkpoint.
    original=tmp_path/"okf-batched-generated-v3/doctrines/example/organization/s001-c010.md"
    original.write_text(original.read_text()+"\nAnother supported detail.\n")
    migrate_applied(tmp_path)
    new_key=prepare_repaired(tmp_path)["concepts"][0]["key"]
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
    with pytest.raises(ValueError,match="different source|V3 scan section mismatch"):
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
    migrate_applied(tmp_path)
    _,catalog,_=checked_phase_a(tmp_path)
    assert len(catalog["documents"][0]["pending_knowledge_item_ids"])==1


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
    original_key=prepare_repaired(tmp_path)["concepts"][0]["key"]
    concept_path="okf-batched-generated-v3/doctrines/example/organization/s001-c010.md"
    md_before=(tmp_path/concept_path).read_bytes()
    group_file=tmp_path/"okf-batched/state-v3/docs/example/group.json"
    group=json.loads(group_file.read_text())
    group["concepts"][0]["coverage_items"][0]["description"]="A modified source item description."
    put_json(group_file,group)
    refresh_scan_for_fixture(tmp_path)
    migrate_applied(tmp_path)
    new_key=prepare_repaired(tmp_path)["concepts"][0]["key"]
    assert new_key!=original_key
    assert (tmp_path/concept_path).read_bytes()==md_before

@pytest.mark.parametrize("destination", [
    "okf-v4/phase-a/published",
    "okf-v4/phase-b/published",
    "okf-v4",
    "okf-v4/phase-a",
    "okf-v4/phase-b",
])
def test_c_refuses_publication_overlapping_phase_a_or_b(tmp_path, destination):
    fixture(tmp_path)
    migrate_applied(tmp_path)
    finished_b(tmp_path)
    tasks=prepare_links(tmp_path)
    for item in tasks["concepts"]:
        put_json(tmp_path/f"okf-v4/state-c/links/{item['key']}.json", {
            "source_id": item["id"], "related_ids": [],
        })
    original_a=(tmp_path/"okf-v4/phase-a/phase-a.json").read_bytes()
    original_b=(tmp_path/"okf-v4/phase-b/phase-b.json").read_bytes()
    with pytest.raises(ValueError, match="overlaps protected"):
        publish(tmp_path, phase_b="okf-v4/phase-b",
                state_root="okf-v4/state-c", destination=destination,
                tasks=tasks)
    assert (tmp_path/"okf-v4/phase-a/phase-a.json").read_bytes()==original_a
    assert (tmp_path/"okf-v4/phase-b/phase-b.json").read_bytes()==original_b
    checked_phase_a(tmp_path)
    checked_b(tmp_path, root="okf-v4/phase-b", stage="B")
    assert not (tmp_path/"okf-v4/phase-a/published").exists()
    assert not (tmp_path/"okf-v4/phase-b/published").exists()


@pytest.mark.parametrize("destination", [
    "okf-v4/phase-a/reviewed", "okf-v4/phase-a",
    "okf-v4", "okf-v4/state-b/reviewed",
])
def test_quality_refuses_destination_overlapping_protected_inputs(tmp_path, destination):
    fixture(tmp_path)
    migrate_applied(tmp_path)
    tasks=prepare_repaired(tmp_path)
    for item in tasks["concepts"]:
        put_json(tmp_path/f"okf-v4/state-b/summaries/{item['key']}.json",{
            "id":item["id"], "summary":"Dieses Konzept beschreibt die Aufgaben und ihre Koordination.",
            "tags":["Koordination"],
        })
        put_json(tmp_path/f"okf-v4/state-b/reviews/{item['key']}.json",{
            "id":item["id"], "action":"keep",
            "reason":"Die ursprünglichen Aussagen sind vollständig.",
            "parts":[],
        })
    original=(tmp_path/"okf-v4/phase-a/phase-a.json").read_bytes()
    with pytest.raises(ValueError,match="overlaps protected input"):
        apply_quality(tmp_path,phase_a="okf-v4/b-source-repaired",
                      state="okf-v4/state-b",tasks=tasks,destination=destination)
    checked_phase_a(tmp_path)
    assert (tmp_path/"okf-v4/phase-a/phase-a.json").read_bytes()==original
    assert not (tmp_path/"okf-v4/phase-a/reviewed").exists()


@pytest.mark.parametrize("stage,destination", [
    ("merge", "okf-v4/phase-a/merged"),
    ("merge", "okf-v4/b-reviewed/merged"),
    ("merge", "okf-v4/state-b/merged"),
    ("merge", "okf-v4"),
    ("complete", "okf-v4/phase-a/completed"),
    ("complete", "okf-v4/b-merged/completed"),
    ("complete", "okf-v4/state-b/completed"),
    ("complete", "okf-v4"),
])
def test_later_b_stages_refuse_protected_input_overlap(tmp_path,stage,destination):
    fixture(tmp_path)
    migrate_applied(tmp_path)
    finished_b(tmp_path)
    original_a=(tmp_path/"okf-v4/phase-a/phase-a.json").read_bytes()
    original_b=(tmp_path/"okf-v4/b-merged/merged.json").read_bytes()
    if stage=="merge":
        groups=prepare_merges(tmp_path)
        with pytest.raises(ValueError,match="overlaps protected input"):
            merge(tmp_path,groups=groups,destination=destination)
    else:
        tasks=prepare_final_inventory(tmp_path)
        with pytest.raises(ValueError,match="overlaps protected input"):
            complete(tmp_path,tasks=tasks,certification=certify_repairs(tmp_path),destination=destination)
    checked_phase_a(tmp_path)
    checked_b(tmp_path,root="okf-v4/b-reviewed",stage="B-draft")
    checked_b(tmp_path,root="okf-v4/b-merged",stage="B-merged")
    assert (tmp_path/"okf-v4/phase-a/phase-a.json").read_bytes()==original_a
    assert (tmp_path/"okf-v4/b-merged/merged.json").read_bytes()==original_b
    assert not (tmp_path/"okf-v4/phase-a/merged").exists()
    assert not (tmp_path/"okf-v4/phase-a/completed").exists()



@pytest.mark.parametrize("label,expected", [
    ("Index", "tag--index"),
    ("index", "tag--index"),
    ("CON", "tag--con"),
    ("PRN", "tag--prn"),
    ("Führung", "fuehrung"),
    ("Organisation", "organisation"),
])
def test_theme_slug_avoids_reserved_filename_and_preserves_normal_tags(label, expected):
    from migrate_v3 import theme_slug
    from refine_b import _semantic
    assert theme_slug(label)==expected
    assert _semantic({
        "id":"example:s001-c010",
        "summary":"Die fachliche Aussage beschreibt die genaue Verteilung der Aufgaben.",
        "tags":[label],
    },"example:s001-c010")["tags"]==[label]


def test_reserved_index_tag_publishes_distinct_theme_and_overview(tmp_path):
    fixture(tmp_path)
    migrate_applied(tmp_path)
    finished_b(tmp_path)
    from publish_indexes import render
    _,catalog,_=checked_b(tmp_path,root="okf-v4/phase-b",stage="B")
    concept=catalog["concepts"][0]
    artifacts,report=render(catalog,[],{concept["id"]:{
        "summary":"Dieses Konzept erklärt die wesentlichen Aufgaben und Verantwortlichkeiten.",
        "tags":["Index", "Organisation"],
    }})
    assert "themen/tag--index.md" in artifacts
    assert "themen/organisation.md" in artifacts
    assert "themen/index.md" in artifacts
    assert report["theme_count"]==2
    assert b"tag--index.md" in artifacts["themen/index.md"]
    assert b"organisation.md" in artifacts["themen/index.md"]


def test_non_latin_theme_slug_is_deterministic_and_safe():
    from migrate_v3 import theme_slug
    tag="管理"
    name=theme_slug(tag)
    assert name.startswith("tag--u-")
    assert len(name)==len("tag--u-")+16
    assert name==theme_slug(tag)
    assert name!=theme_slug("Index")
