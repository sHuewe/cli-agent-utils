"""Static contracts for the Golden-compatible, section-consolidating OKF Flow."""
from pathlib import Path
import tomllib

ROOT = Path(__file__).resolve().parents[1]
NEW = ROOT / "flow" / "okf" / "flow_okf_from_doctrine_batched"
GOLDEN = ROOT / "flow" / "rag" / "generate_goldens"


def _load(path: Path) -> dict:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def _steps(path: Path) -> dict[str, dict]:
    return {step["id"]: step for step in _load(path)["steps"]}


def test_nested_flow_and_prompt_paths_exist():
    paths = [NEW / "flow.toml", *sorted((NEW / "flows").glob("*.toml"))]
    assert len(paths) >= 8
    for path in paths:
        flow = _load(path)
        assert flow["version"] == 1
        ids = [s["id"] for s in flow["steps"]]
        assert len(ids) == len(set(ids))
        for step in flow["steps"]:
            for reference in ("flow", "prompt_file"):
                if reference in step:
                    assert (ROOT / step[reference]).is_file(), (path, reference)
            for context in step.get("add_file_context", []):
                assert (ROOT / context).is_file(), (path, context)


def test_golden_checkpoint_contract_is_exactly_unchanged():
    golden_inventory = _steps(GOLDEN / "flow.toml")["inventory"]
    source = _steps(NEW / "flow.toml")
    assert source["inventory"] == golden_inventory
    assert source["analyze_documents"]["flow"] == "flow/rag/generate_goldens/flows/analyze-document.toml"
    assert source["analyze_documents"]["foreach"] == "steps.inventory.output.files"
    golden = _steps(GOLDEN / "flow.toml")["analyze_documents"]
    assert source["analyze_documents"] == golden
    assert source["publish_named"]["filesystem_operation"] == {
        "kind": "publish_named_okf",
        "source_root": "${var.okf_root}",
        "destination_root": "okf-batched-published-v3",
        "state_root": "okf-batched/state-v3/docs",
    }
    assert source["publish_named"]["overwrite_output"] is True
    assert source["publish_named"]["output"].endswith("/named-publication.json")
    assert _load(NEW / "flow.toml")["result"] == "steps.publish_named.output"
    assert list(source).index("publish_named") > list(source).index("global_topics")


def test_all_document_scans_complete_before_document_consolidation():
    doc = _steps(NEW / "flows" / "build-document.toml")
    assert doc["sections"]["filesystem_operation"]["target_chars"] == 5000
    assert doc["sections"]["filesystem_operation"]["always_sections"] is True
    assert doc["scan"]["foreach"] == "steps.sections.output.sections"
    assert doc["outline_tasks"]["json_operation"]["kind"] == "prepare_outline_tasks"
    assert doc["outline"]["json_operation"]["kind"] == "assemble_section_outlines"
    assert doc["finish"]["input"]["scans"] == "${steps.scan.output}"
    assert doc["finish"]["flow"].endswith("flows/finish-document.toml")
    plan = _steps(NEW / "flows" / "finish-document.toml")
    assert plan["consolidation_batches"]["json_operation"]["kind"] == "prepare_doctrine_consolidation"
    assert plan["consolidation_batches"]["json_operation"]["batch_size"] == 6
    assert plan["consolidate"]["foreach"] == "steps.consolidation_batches.output.batches"
    assert plan["consolidated"]["json_operation"]["kind"] == "assemble_doctrine_consolidation"
    assert plan["assign"]["json_operation"]["kind"] == "json_join_aliases"
    # Empty semantic candidates need not have source items; actual items still require a mapping.
    assert plan["assign"]["json_operation"]["require_all_aliases"] is False
    assert plan["topics"]["json_operation"]["kind"] == "json_project"
    assert plan["group"]["json_operation"]["kind"] == "group_items"
    assert plan["group"]["json_operation"]["max_concept_bytes"] == 12000
    assert plan["build_concepts"]["foreach"] == "steps.group.output.concepts"
    assert _steps(NEW / "flows" / "verify-document.toml")["coverage"]["json_operation"]["kind"] == "verify_coverage"
    assert "coverage_manifest" in plan and "manifest_inventory" in plan
    assert "navigation_manifest" in plan and "final_manifest_inventory" in plan
    assert _load(NEW / "flows" / "finish-document.toml")["result"] == "steps.final_manifest_inventory.output"
    assert plan["folder_indexes"]["foreach"] == "steps.group.output.folders"
    assert _steps(NEW / "flows" / "index-folder.toml")["inventory"]["filesystem_operation"]["kind"] == "inventory"


def test_sharded_global_registry_count_and_coverage_are_explicit():
    global_steps = _steps(NEW / "flows" / "global-topics.toml")
    assert {"candidates", "reduce1", "reduce2", "reduce3", "registry", "build_themes", "final_reports"} <= set(global_steps)
    assert global_steps["registry"]["flow"].endswith("flows/registry-shard.toml")
    assert global_steps["registry"]["foreach"] == "steps.batch_registry.output.batches"
    assert _load(NEW / "flows" / "global-topics.toml")["result"] == "steps.final_reports.output"
    packing = _steps(NEW / "flows" / "batch-registry.toml")["batch"]["json_operation"]
    assert packing["kind"] == "batch_arrays"
    assert packing["batch_size"] == 1
    assert packing["max_fragment_items"] == 5
    assert packing["max_batch_bytes"] <= 8000
    registry = _steps(NEW / "flows" / "registry-shard.toml")
    assert registry["validate"]["json_operation"]["kind"] == "json_validate_partition"
    assert _load(NEW / "flows" / "registry-shard.toml")["result"] == "steps.validate.output"
    prompt = (NEW / "prompts" / "08_registry.md").read_text(encoding="utf-8")
    assert "group_refs" in prompt
    assert "excluded_group_refs" in prompt
    assert "At most 12 themes" not in prompt


def test_new_state_is_isolated_from_v1_and_original_okf():
    for path in [NEW / "flow.toml", *sorted((NEW / "flows").glob("*.toml"))]:
        text = path.read_text(encoding="utf-8")
        if path == NEW / "flow.toml":
            continue  # Golden state's paths are intentionally shared here.
        assert "okf-batched/state/" not in text
        assert "flow_okf_from_doctrine_seperated/state" not in text


def test_registry_validator_reads_declared_subflow_input_not_json_inputs():
    """Runner contract: source_input selects flow_input, not json_inputs.

    global-topics forwards each complete registry batch as the named
    registry-shard subflow input. The JSON operation reads that source
    directly and uses json_inputs.registry only for the proposed output.
    """
    global_steps = _steps(NEW / "flows" / "global-topics.toml")
    caller = global_steps["registry"]
    assert caller["input"]["batch"] == "${item}"
    assert caller["foreach"] == "steps.batch_registry.output.batches"

    shard = _load(NEW / "flows" / "registry-shard.toml")
    assert "batch" in shard["inputs"]
    validator = _steps(NEW / "flows" / "registry-shard.toml")["validate"]
    assert validator["json_operation"]["kind"] == "json_validate_partition"
    assert validator["json_operation"]["source_input"] == "batch"
    assert validator["json_operation"]["input"] == "registry"
    assert set(validator["json_inputs"]) == {"registry"}
    assert validator["json_inputs"]["registry"]["path"].endswith(
        "/registry-${input.batch.id}.json"
    )
