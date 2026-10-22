"""Contracts for the independent simplified doctrine OKF experiment."""
from __future__ import annotations

from pathlib import Path
import re
import tomllib

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "flow/okf/flow_okf_from_doctrine_simple"


def load(path: Path) -> dict:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def test_simple_flow_wiring_and_referenced_prompts():
    paths = [BASE / "flow.toml", *sorted((BASE / "flows").glob("*.toml"))]
    assert len(paths) == 5
    for path in paths:
        spec = load(path)
        assert spec["version"] == 1
        ids = [step["id"] for step in spec["steps"]]
        assert len(ids) == len(set(ids))
        for step in spec["steps"]:
            assert sum(key in step for key in ("flow", "prompt_file", "json_operation", "filesystem_operation")) == 1
            if "flow" in step:
                assert (ROOT / step["flow"]).is_file()
            if "prompt_file" in step:
                file = ROOT / step["prompt_file"]
                assert file.is_file()
                variables = set(re.findall(r"\{\{var:([a-zA-Z_][a-zA-Z0-9_]*)\}\}", file.read_text(encoding="utf-8")))
                assert variables <= set(step.get("vars", {})) | set(step.get("json_inputs", {}))
            if "output" in step:
                assert "/flow_okf_from_doctrine_simple/state/" in step["output"]


def test_simple_plan_skips_mandatory_chunks_and_atomic_items():
    build = load(BASE / "flows/build-doctrine.toml")
    ids = [step["id"] for step in build["steps"]]
    assert ids == ["plan", "concepts", "navigation", "manifest"]
    assert build["steps"][1]["foreach"] == "steps.plan.output.concepts"
    assert "batch_routes" not in str(build)
    assert "group_items" not in str(build)
    prompt = (BASE / "prompts/01_plan_doctrine.md").read_text(encoding="utf-8")
    assert "FULL document" in prompt
    assert "NEVER silently" in prompt


def test_conditional_repair_has_verify_fallback():
    flow = load(BASE / "flows/build-concept.toml")
    assert flow["result"] == "steps.repair.output"
    assert flow["result_fallback"] == "steps.verify.output"
    assert flow["steps"][-1]["when"] == {
        "ref": "steps.verify.output.status", "eq": "needs_repair"
    }


def test_simple_flow_isolation_and_global_manifests():
    root = load(BASE / "flow.toml")
    assert root["vars"]["okf_root"] == "okf-simple"
    assert root["steps"][1]["input"]["okf_root"] == "${var.okf_root}"
    assert root["steps"][2]["input"]["okf_root"] == "${var.okf_root}"
    integrate = load(BASE / "flows/integrate.toml")
    assert integrate["steps"][0]["json_inputs"]["modules"]["iterate"] == "input.sources[]"
    assert integrate["steps"][2]["json_inputs"]["modules"]["iterate"] == "input.sources[]"


def test_verified_concepts_gate_navigation_and_manifest():
    flow = load(BASE / "flows/build-doctrine.toml")
    by_id = {step["id"]: step for step in flow["steps"]}
    for step_id in ("navigation", "manifest"):
        assert by_id[step_id]["vars"]["concept_results"] == (
            "${steps.concepts.output.iterations}"
        )
        prompt = (ROOT / by_id[step_id]["prompt_file"]).read_text(encoding="utf-8")
        assert "{{var:concept_results}}" in prompt
        assert "needs_attention" in prompt


def test_theme_files_require_frontmatter():
    theme = (BASE / "prompts/07_write_theme.md").read_text(encoding="utf-8")
    assert "type: concept" in theme
    assert "status: stable" in theme
    assert "Read back" in theme


def test_doctrine_slugs_come_from_deterministic_inventory():
    flow = load(BASE / "flow.toml")
    assert flow["steps"][0]["filesystem_operation"]["stable_slugs"] is True
    prompt = (BASE / "prompts/01_plan_doctrine.md").read_text(encoding="utf-8")
    assert "source.slug" in prompt
    assert "Never" in prompt
