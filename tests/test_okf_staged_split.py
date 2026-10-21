"""Static contract tests for resumable staged OKF concept splitting."""
from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(path: str) -> dict:
    with (ROOT / path).open("rb") as handle:
        return tomllib.load(handle)


def test_legacy_assessment_snapshot_and_apply_checkpoint_paths_preserved() -> None:
    path = "flow/okf/flows/split-concept.toml"
    data = load(path)
    steps = {s["id"]: s for s in data["steps"]}
    assert list(steps) == ["assess", "snapshot", "parts", "overview", "index", "apply", "verify"]
    assert data["result"] == "steps.verify.output"
    assert steps["assess"]["output"].endswith(
        "split-concept-assess-${input.scope_id}-${input.concept_id}.json"
    )
    assert steps["snapshot"]["output"].endswith(
        "split-concept-snapshot-${input.scope_id}-${input.concept_id}.json"
    )
    assert steps["apply"]["output"].endswith(
        "split-concept-apply-${input.scope_id}-${input.concept_id}.json"
    )
    assert steps["verify"]["output"].endswith(
        "split-concept-verify-${input.scope_id}-${input.concept_id}.json"
    )
    assert steps["verify"]["vars"]["change"] == "${steps.apply.output}"
    assert steps["apply"]["workspace_access"] == "none"
    assert steps["apply"]["prompt_file"] == "flow/okf/prompts/finalize_staged_split.md"


def test_each_part_has_distinct_nested_checkpoint() -> None:
    flow = load("flow/okf/flows/split-concept.toml")
    step = next(s for s in flow["steps"] if s["id"] == "parts")
    assert step["foreach"] == "steps.assess.output.parts"
    assert "iteration_id" not in step  # safe 1-based positional identifiers
    assert step["input"]["part"] == "${item}"
    assert step["input"]["part_id"] == "${iteration.id}"
    assert step["input"]["original_content"] == "${steps.snapshot.output.content}"

    part = load("flow/okf/flows/split-part.toml")
    assert part["result"] == "steps.create.output"
    creation = part["steps"][0]
    assert creation["workspace_access"] == "write"
    assert creation["approve_tools"] == ["os__write_file"]
    assert creation["overwrite_output"] is False
    assert "${input.part_id}" in creation["output"]
    assert creation["output"].endswith(".json")


def test_staged_writes_are_individually_checkpointed() -> None:
    flow = load("flow/okf/flows/split-concept.toml")
    steps = {s["id"]: s for s in flow["steps"]}
    for name in ("overview", "index"):
        step = steps[name]
        assert step["workspace_access"] == "write"
        assert step["approve_tools"] == ["os__write_file"]
        assert step["overwrite_output"] is False
        assert step["response_format"] == "json"
        assert "v2" in step["output"]
        assert step["vars"]["parts"] == "${steps.parts.output.iterations}"


def test_split_prompts_preserve_safety_and_resume_rules() -> None:
    for filename in ("create_split_part.md", "update_split_overview.md",
                     "update_split_index.md", "finalize_staged_split.md"):
        prompt = (ROOT / "flow/okf/prompts" / filename).read_text(encoding="utf-8")
        assert "needs_attention" in prompt
        assert "snapshot" in prompt.lower() or filename == "finalize_staged_split.md"
    part = (ROOT / "flow/okf/prompts/create_split_part.md").read_text(encoding="utf-8")
    assert "NEVER overwrite" in part
    index = (ROOT / "flow/okf/prompts/update_split_index.md").read_text(encoding="utf-8")
    assert "earlier completed splits" in index
