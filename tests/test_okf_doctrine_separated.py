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
    assert next(s for s in generate["steps"] if s["id"] == "build_concepts")["input"]["okf_root"] == "${input.okf_root}"


def test_global_suggestion_batching_uses_declared_subflow_inputs():
    """Prevent using steps.* in json_inputs.iterate (runner only permits input/item)."""
    integrate = _flow(BASE / "flows/integrate.toml")
    steps = {step["id"]: step for step in integrate["steps"]}
    batching = steps["batch_suggestions"]
    assert batching["flow"].endswith("/flows/batch-global-suggestions.toml")
    assert batching["input"]["batches"] == "${steps.batch_modules.output.batches}"

    child = _flow(BASE / "flows/batch-global-suggestions.toml")
    assert "batches" in child["inputs"]
    json_step = child["steps"][0]
    assert json_step["json_inputs"]["suggestions"]["iterate"] == "input.batches[]"
    assert json_step["json_operation"]["kind"] == "batch"
    assert json_step["json_inputs"]["suggestions"]["path"].endswith(
        "/suggestions-${each.id}.json"
    )
    assert steps["theme_registry"]["vars"]["reduced"] == (
        "${steps.reduce_themes.output.iterations}"
    )


def test_all_json_input_iterators_refer_to_input_or_item():
    for flow_path in [BASE / "flow.toml", *(BASE / "flows").glob("*.toml")]:
        for step in _flow(flow_path)["steps"]:
            for spec in step.get("json_inputs", {}).values():
                selector = spec.get("iterate")
                if selector is not None:
                    assert selector.startswith(("input.", "item.")), (
                        flow_path, step["id"], selector
                    )


def test_separated_scan_only_requests_bounded_read_file():
    build = _flow(BASE / "flows/build-doctrine.toml")
    scan = next(step for step in build["steps"] if step["id"] == "scan")
    assert scan["foreach"] == "steps.partition.output.chunks"
    assert scan["workspace_access"] == "read"
    assert scan["prompt_file"] == (
        "flow/okf/flow_okf_from_doctrine_seperated/prompts/02_scan_chunk.md"
    )
    prompt = (ROOT / scan["prompt_file"]).read_text(encoding="utf-8")
    assert "start_line=chunk.start_line" in prompt
    assert "end_line=chunk.end_line" in prompt
    assert "NEVER call" in prompt
    assert "search_text" in prompt
    assert "exactly ONE document-content tool call" in prompt


def test_semantic_subfolder_flow_contract():
    generate = _flow(BASE / "flows/generate-doctrine.toml")
    steps = {step["id"]: step for step in generate["steps"]}
    assert steps["folder_indexes"]["foreach"] == "steps.group.output.folders"
    assert steps["folder_indexes"]["input"]["folder"] == "${item}"
    assert steps["write_index"]["vars"]["folders"] == "${steps.group.output.folders}"
    assert steps["write_index"]["vars"]["folder_indexes"] == (
        "${steps.folder_indexes.output.iterations}"
    )
    local = _flow(BASE / "flows/index-semantic-folder.toml")
    assert set(local["inputs"]) == {"source", "folder", "okf_root", "coverage"}
    assert local["steps"][0]["filesystem_operation"]["recursive"] is False
    assert local["steps"][1]["when"] == {
        "ref": "input.coverage.status", "eq": "ok"
    }
    prompt = (BASE / "prompts/06_final_local_topics.md").read_text(encoding="utf-8")
    assert '"folders":' in prompt
    assert "folders=[]" in prompt


def test_v2_semantic_states_are_isolated_from_flat_layout():
    all_flows = [BASE / "flow.toml", *(BASE / "flows").glob("*.toml")]
    for path in all_flows:
        cfg = _flow(path)
        for step in cfg["steps"]:
            if "output" in step:
                assert "/state-semantic-v2/" in step["output"], (path, step["id"])
                assert "/state/" not in step["output"], (path, step["id"])
            for value in step.get("json_inputs", {}).values():
                assert "/state-semantic-v2/" in value["path"], (path, step["id"])


def test_assignment_uses_independent_small_bounded_batches():
    generate = _flow(BASE / "flows/generate-doctrine.toml")
    steps = {step["id"]: step for step in generate["steps"]}
    batches = steps["assignment_batches"]
    assert batches["json_operation"] == {
        "kind": "batch_routes", "input": "routes",
        "batch_size": 1, "max_batch_bytes": 12000,
    }
    assert batches["json_inputs"]["routes"]["iterate"] == "input.chunks[]"
    assert batches["overwrite_output"] is True
    assert steps["assign"]["foreach"] == "steps.assignment_batches.output.batches"
    assert steps["assign"]["output"].endswith("/assign-small-${iteration.id}.json")
    assert steps["assign"]["prompt_file"].endswith("/07c_assign_small_batch.md")
    assert steps["group"]["input"]["batches"] == (
        "${steps.assignment_batches.output.batches}"
    )

    grouping = _flow(BASE / "flows/group-local-concepts.toml")["steps"][0]
    assert grouping["json_inputs"]["assignments"]["path"].endswith(
        "/assign-small-${each.id}.json"
    )
    assert grouping["output"].endswith("/concept-plan-small-assign-v1.json")
    coverage = _flow(BASE / "flows/verify-local-coverage.toml")["steps"][0]
    assert coverage["json_inputs"]["plan"]["path"] == grouping["output"]


def test_small_assignment_prompt_requires_exact_one_assignment_per_item():
    generate = _flow(BASE / "flows/generate-doctrine.toml")
    assign = next(s for s in generate["steps"] if s["id"] == "assign")
    prompt = (ROOT / assign["prompt_file"]).read_text(encoding="utf-8")
    assert "document_id + \":\" + knowledge_item.id" in prompt
    assert "exactly one assignment" in prompt.lower()
    assert "topics.topics" in prompt
