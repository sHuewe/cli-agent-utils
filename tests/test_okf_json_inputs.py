"""Static contract tests for OKF runner-managed JSON artifact handoff.

No model, network or external cli-agent installation is required.
"""
from __future__ import annotations

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PREFIX = ROOT / "flow" / "okf"


def _load(relative: str) -> dict:
    with (ROOT / relative).open("rb") as handle:
        return tomllib.load(handle)


def test_persisted_scan_and_route_checkpoint_contracts() -> None:
    for kind, root_id, scan_id, route_id in (
        ("doctrine", "doctrines", "scan_doctrines", "route_doctrines"),
        ("manual", "manuals", "scan_manuals", "route_manuals"),
    ):
        base = f"flow/okf/flow_okf_from_{kind}"
        main = _load(f"{base}/flow.toml")
        assert main["exclude_paths"] == ["flow"]
        assert all(
            step["id"] in [s["id"] for s in main["steps"]]
            for step in ({"id": scan_id}, {"id": route_id})
        )
        scanner = _load(f"{base}/flows/scan-{kind}.toml")
        router = _load(f"{base}/flows/route-chunk.toml")
        folder = _load(f"{base}/flows/process-folder.toml")
        scan_step = next(s for s in scanner["steps"] if s["id"] == "scan_chunks")
        route_step = next(s for s in router["steps"] if s["id"] == "route")
        plan_step = next(s for s in folder["steps"] if s["id"] == (
            "batch_routes" if kind == "doctrine" else "plan"
        ))
        assert scan_step["overwrite_output"] is False
        assert route_step["overwrite_output"] is False
        assert plan_step["overwrite_output"] is False
        assert scan_step["response_format"] == "json"
        assert route_step["response_format"] == "json"
        if kind == "doctrine":
            assert [step["id"] for step in router["steps"]] == ["route", "finalize"]
            assert route_step["foreach"] == "input.structure.folders"
            assert plan_step["json_operation"]["kind"] == "batch_routes"
            assert plan_step["json_operation"]["batch_size"] > 0
            assert plan_step["json_operation"]["max_batch_bytes"] > 0
        else:
            assert plan_step["response_format"] == "json"
            assert plan_step["workspace_access"] == "none"
        assert route_step["workspace_access"] == "none"

        scan_path = scan_step["output"].replace(
            "${input." + kind + ".id}", "${input.chunk.document_id}"
        ).replace("${iteration.id}", "${input.chunk.id}")
        assert route_step["json_inputs"]["scan"]["path"] == scan_path

        route_path = route_step["output"].replace(
            "${input.chunk.document_id}", "${each.document_id}"
        ).replace("${input.chunk.id}", "${each.id}"
        ).replace("${iteration.id}", "${input.folder.id}")
        assert plan_step["json_inputs"]["routes"]["path"] == route_path
        assert plan_step["json_inputs"]["routes"]["iterate"] == (
            "input.scans[].output.chunks[]"
        )
        assert "{{var:scan}}" in (ROOT / base / "prompts/05_route_chunk.md").read_text(encoding="utf-8")
        assert "{{var:routes}}" in (ROOT / base / "prompts/07_plan_folder.md").read_text(encoding="utf-8")


def test_all_configured_json_inputs_have_prompt_variables() -> None:
    for kind in ("doctrine", "manual"):
        base = f"flow/okf/flow_okf_from_{kind}"
        for subflow in ("route-chunk.toml", "process-folder.toml"):
            flow = _load(f"{base}/flows/{subflow}")
            for step in flow["steps"]:
                for variable, value in step.get("json_inputs", {}).items():
                    assert set(value) <= {"path", "iterate"}
                    assert "state/" in value["path"]
                    if "json_operation" in step:
                        assert variable == step["json_operation"]["input"]
                    else:
                        prompt = (ROOT / step["prompt_file"]).read_text(encoding="utf-8")
                        assert "{{var:" + variable + "}}" in prompt


def test_doctrine_batch_global_consolidation_contract() -> None:
    base = "flow/okf/flow_okf_from_doctrine"
    folder = _load(f"{base}/flows/process-folder.toml")
    by_id = {step["id"]: step for step in folder["steps"]}
    assert by_id["suggest_topics"]["foreach"] == "steps.batch_routes.output.batches"
    assert by_id["assign_topics"]["foreach"] == "steps.batch_routes.output.batches"
    assert by_id["group_plan"]["flow"].endswith("group-folder-plan.toml")
    assert by_id["concepts"]["foreach"] == "steps.group_plan.output.concepts"

    grouping = _load(f"{base}/flows/group-folder-plan.toml")
    group = grouping["steps"][0]
    assert group["json_operation"]["kind"] == "group_items"
    assert set(group["json_inputs"]) == {"routes", "assignments", "topics"}

    coverage = _load(f"{base}/flows/verify-folder-coverage.toml")
    verify = coverage["steps"][0]
    assert verify["json_operation"]["kind"] == "verify_coverage"
    assert set(verify["json_inputs"]) == {"plan", "results"}
