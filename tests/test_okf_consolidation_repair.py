"""Contracts for local consolidation membership verification and targeted repair."""
from pathlib import Path
import tomllib

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "flow" / "okf" / "flow_okf_from_doctrine_batched"


def _read(name: str):
    return tomllib.loads((BASE / name).read_text(encoding="utf-8"))


def _steps(name: str):
    return {s["id"]: s for s in _read(name)["steps"]}


def test_original_consolidation_step_and_checkpoints_remain_identical():
    # Keep the original checkpoint paths and parent step identity so already
    # generated document/batch results are not rerun when this fix is deployed.
    base = _steps("flows/finish-document.toml")
    assert base["consolidate"]["id"] == "consolidate"
    assert base["consolidate"]["foreach"] == "steps.consolidation_batches.output.batches"
    assert base["consolidate"]["iteration_id"] == "${item.id}"
    assert base["consolidate"]["output"] == (
        "okf-batched/state-v3/docs/${input.source.slug}/consolidation-${iteration.id}.json"
    )
    assert base["consolidated"]["json_operation"]["results_step"] == "validated_batches"
    assert base["consolidated"]["json_operation"]["batches_step"] == "consolidation_batches"


def test_every_batch_is_checked_before_document_wide_assembly():
    base = _steps("flows/finish-document.toml")
    validated = base["validated_batches"]
    assert validated["foreach"] == "steps.consolidate.output.iterations"
    assert validated["iteration_id"] == "${item.id}"
    assert validated["input"]["batch_id"] == "${item.id}"
    assert validated["input"]["source_slug"] == "${input.source.slug}"


def test_repair_only_on_invalid_and_uses_deterministic_recheck():
    flow = _read("flows/validate-consolidation.toml")
    assert flow["result"] == "steps.recheck.output.value"
    assert flow["result_fallback"] == "steps.validate.output.value"
    steps = _steps("flows/validate-consolidation.toml")
    check = steps["validate"]["json_operation"]
    assert check["kind"] == "json_validate_allowed_values"
    assert check["input"] == "candidate"
    assert check["allowed_path"] == "/folders/*/id"
    assert check["values_path"] == "/groups/*/folder_id"
    assert check["null_policy"] == "when_allowed_empty"
    assert check["on_invalid"] == "report"
    for name in ("repair", "recheck"):
        assert steps[name]["when"] == {
            "ref": "steps.validate.output.status", "eq": "needs_attention"
        }
    recheck = steps["recheck"]["json_operation"]
    assert recheck["on_invalid"] == "raise"
    assert recheck["values_path"] == check["values_path"]
    assert recheck["allowed_path"] == check["allowed_path"]
    assert steps["repair"]["workspace_access"] == "none"


def test_all_referenced_flow_and_prompt_paths_exist():
    for name in ("flows/finish-document.toml", "flows/validate-consolidation.toml"):
        for step in _read(name)["steps"]:
            for key in ("flow", "prompt_file"):
                if key in step:
                    assert (ROOT / step[key]).is_file(), (name, step["id"], key)
