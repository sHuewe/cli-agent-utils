"""Static contracts for the bounded, separated OKF pipeline.

These tests do not claim to execute the cli-agent runner or the GLM model.
"""
from pathlib import Path
import re
import tomllib

ROOT = Path(__file__).resolve().parents[1]
NEW = ROOT / "flow" / "okf" / "flow_okf_from_doctrine_batched"
GOLDEN = ROOT / "flow" / "rag" / "generate_goldens"


def _load(path: Path) -> dict:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def test_all_nested_flows_and_prompts_exist() -> None:
    files = [NEW / "flow.toml", *sorted((NEW / "flows").glob("*.toml"))]
    assert len(files) >= 8
    for path in files:
        flow = _load(path)
        assert flow["version"] == 1
        steps = flow["steps"]
        ids = [step["id"] for step in steps]
        assert len(ids) == len(set(ids)), path
        for step in steps:
            for reference in ("flow", "prompt_file"):
                if reference in step:
                    assert (ROOT / step[reference]).is_file(), (path, reference)
            for context in step.get("add_file_context", []):
                assert (ROOT / context).is_file(), (path, context)


def test_reused_golden_scan_is_identical() -> None:
    new = _load(NEW / "flow.toml")
    old = _load(GOLDEN / "flow.toml")
    original_inventory = next(s for s in old["steps"] if s["id"] == "inventory")
    new_inventory = next(s for s in new["steps"] if s["id"] == "inventory")
    assert new_inventory == original_inventory
    new_scan = next(s for s in new["steps"] if s["id"] == "golden_profiles")
    assert new_scan["flow"] == "flow/rag/generate_goldens/flows/analyze-document.toml"
    assert new_scan["foreach"] == "steps.inventory.output.files"
    assert new_scan["input"]["source"] == "${item}"


def test_small_section_and_sharded_global_steps() -> None:
    doc = _load(NEW / "flows" / "build-document.toml")
    sections = next(s for s in doc["steps"] if s["id"] == "sections")
    assert sections["filesystem_operation"]["target_chars"] == 5000
    assert doc["result"] == "steps.manifest_inventory.output"
    global_flow = _load(NEW / "flows" / "global-topics.toml")
    global_steps = global_flow["steps"]
    ids = {s["id"] for s in global_steps}
    assert {"candidates", "reduce1", "reduce2", "reduce3", "registry", "build_themes"} <= ids
    for step in global_steps:
        operation = step.get("json_operation")
        if operation and operation["kind"] == "batch_arrays":
            assert operation["batch_size"] <= 2
            assert operation["max_batch_bytes"] <= 12000
        if step.get("id") in {"candidates", "reduce1", "reduce2", "reduce3", "registry"}:
            assert "foreach" in step
            assert step.get("workspace_access") == "none"
    batch = _load(NEW / "flows" / "batch-global.toml")["steps"][0]
    assert batch["json_operation"]["kind"] == "batch_arrays"
    assert batch["json_operation"]["max_batch_bytes"] == 12000
    assert batch["json_operation"]["batch_size"] == 2


def test_coverage_is_deterministic_and_path_isolated() -> None:
    sec = _load(NEW / "flows" / "process-section.toml")
    group = next(s for s in sec["steps"] if s["id"] == "group")
    assert group["json_operation"]["kind"] == "group_items"
    assert {"routes", "assignments", "topics"} == set(group["json_inputs"])
    assert group["json_operation"]["max_concept_bytes"] <= 12000
    coverage = _load(NEW / "flows" / "verify-section.toml")
    assert coverage["steps"][0]["json_operation"]["kind"] == "verify_coverage"
    for path in [NEW / "flow.toml", *sorted((NEW / "flows").glob("*.toml"))]:
        source = path.read_text(encoding="utf-8")
        for match in re.finditer(r'^output\s*=\s*"([^"]+)"', source, re.M):
            destination = match.group(1)
            assert not destination.startswith("flow/okf/flow_okf_from_doctrine_seperated/state"), path

def test_final_status_preserves_each_registry_shard() -> None:
    global_flow = _load(NEW / "flows" / "global-topics.toml")
    assert global_flow["result"] == "steps.final_reports.output"
    by_id = {step["id"]: step for step in global_flow["steps"]}
    assert by_id["build_themes"]["foreach"] == "steps.registry.output.iterations"
    assert by_id["final_reports"]["foreach"] == "steps.build_themes.output.iterations"
    assert by_id["final_reports"]["input"]["root_index"] == "${steps.root_index.output}"
    audit = _load(NEW / "flows" / "build-themes-batch.toml")
    assert audit["result"] == "steps.audit.output"
    assert next(s for s in audit["steps"] if s["id"] == "audit")["vars"]["registry"] == "${input.registry}"
    final = _load(NEW / "flows" / "report-shard.toml")
    assert final["result"] == "steps.result.output"
    for path in ("12_shard_audit.md", "13_final_audit.md"):
        prompt = (NEW / "prompts" / path).read_text(encoding="utf-8")
        assert "needs_attention" in prompt


def test_global_reduction_does_not_silently_drop_singletons() -> None:
    prompt = (NEW / "prompts" / "07_global.md").read_text(encoding="utf-8")
    assert "At most 20 groups" not in prompt
    assert "preserve them as separate entries" in prompt
    batch = _load(NEW / "flows" / "batch-global.toml")
    op = batch["steps"][0]["json_operation"]
    assert op["batch_size"] == 2
    assert op["max_batch_bytes"] <= 8000
