"""Static contracts for the independent doctrine OKF pipeline (no LLM required)."""
from __future__ import annotations

from pathlib import Path
import re
import tomllib

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "flow/okf/flow_okf_from_doctrine_seperated"


def _flow(path: Path) -> dict:
    with path.open("rb") as f:
        return tomllib.load(f)


def test_all_subflows_and_prompts_exist_and_compile():
    assert (BASE / "flow.toml").exists()
    flows = [BASE / "flow.toml", *sorted((BASE / "flows").glob("*.toml"))]
    assert len(flows) >= 8
    for flow_path in flows:
        config = _flow(flow_path)
        assert config["version"] == 1
        steps = config["steps"]
        ids = [step["id"] for step in steps]
        assert len(ids) == len(set(ids)), flow_path
        previous_ids = set()
        for step in steps:
            assert sum(k in step for k in ("flow", "prompt_file", "json_operation", "filesystem_operation")) == 1
            if "flow" in step:
                assert (ROOT / step["flow"]).exists(), (flow_path, step["id"])
            if "prompt_file" in step:
                prompt = (ROOT / step["prompt_file"])
                assert prompt.is_file(), prompt
                variables = set(re.findall(r"\{\{var:([a-zA-Z_][a-zA-Z0-9_]*)\}\}", prompt.read_text(encoding="utf-8")))
                bound = set(step.get("vars", {})) | set(step.get("json_inputs", {}))
                assert variables <= bound, (flow_path, step["id"], variables - bound)
            if "when" in step:
                for ref in re.findall(r"steps\.([a-zA-Z_][a-zA-Z0-9_]*)\.output", str(step["when"])):
                    assert ref in previous_ids, (flow_path, step["id"], ref)
            previous_ids.add(step["id"])


def test_all_json_operations_are_bounded():
    for flow_path in [BASE / "flow.toml", *(BASE / "flows").glob("*.toml")]:
        for step in _flow(flow_path)["steps"]:
            operation = step.get("json_operation")
            if not operation:
                continue
            assert operation["kind"] in {"batch", "batch_routes", "group_items", "verify_coverage"}
            if operation["kind"] in {"batch", "batch_routes"}:
                assert operation["batch_size"] <= 8
                assert operation["max_batch_bytes"] <= 48000
            if operation["kind"] == "group_items":
                assert operation["max_concept_bytes"] <= 48000


def test_isolation_and_progressive_navigation_contract():
    root = _flow(BASE / "flow.toml")
    inventory = root["steps"][0]
    assert inventory["filesystem_operation"]["kind"] == "inventory"
    assert inventory["overwrite_output"] is True
    assert inventory["filesystem_operation"]["recursive"] is True
    assert root["steps"][1]["foreach"] == "steps.inventory.output.files"

    build = _flow(BASE / "flows/build-doctrine.toml")
    assert build["steps"][2]["foreach"] == "steps.partition.output.chunks"
    assert all(step.get("workspace_access", "none") != "write"
               for step in build["steps"][:3])

    integrate = _flow(BASE / "flows/integrate.toml")
    assert integrate["steps"][0]["json_operation"]["kind"] == "batch"
    assert integrate["steps"][0]["json_inputs"]["modules"]["iterate"] == "input.sources[]"
    assert any(step["id"] == "tag_modules" for step in integrate["steps"])
    assert any(step["id"] == "write_themes" for step in integrate["steps"])
    assert any(step["id"] == "root_index" for step in integrate["steps"])


def test_shared_doctrine_flow_remains_separate():
    original = _flow(ROOT / "flow/okf/flow_okf_from_doctrine/flow.toml")
    separated = _flow(BASE / "flow.toml")
    assert "design_structure" in {s["id"] for s in original["steps"]}
    assert "design_structure" not in {s["id"] for s in separated["steps"]}


def test_global_okf_root_is_forwarded_to_both_subflows():
    """PR #231 makes static parent [vars] usable in steps.input."""
    root = _flow(BASE / "flow.toml")
    assert root["vars"]["okf_root"] == "okf-generated"
    assert root["vars"]["doctrine_path"] == "doctrines"

    steps = {step["id"]: step for step in root["steps"]}
    assert steps["inventory"]["filesystem_operation"]["directory"] == (
        "${var.doctrine_path}"
    )
    assert steps["build_modules"]["input"]["okf_root"] == "${var.okf_root}"
    assert steps["integrate"]["input"]["okf_root"] == "${var.okf_root}"

    # Changes to [vars].okf_root must propagate to both child invocations.
    # Hardcoded paths in steps.input would silently ignore that setting.
    for step in root["steps"]:
        if "flow" in step:
            assert step["input"]["okf_root"] == "${var.okf_root}"

    build = _flow(BASE / "flows/build-doctrine.toml")
    generate = _flow(BASE / "flows/generate-doctrine.toml")
    assert build["steps"][-1]["input"]["okf_root"] == "${input.okf_root}"
    assert generate["steps"][4]["input"]["okf_root"] == "${input.okf_root}"
