"""Static contracts for per-concept doctrine OKF cross-links.

These tests deliberately do not need an LLM or external cli-agent installation.
"""
from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "flow/okf/flow_okf_from_doctrine"


def _load(path: str) -> dict:
    with (ROOT / path).open("rb") as f:
        return tomllib.load(f)


def test_related_links_run_after_split_and_folder_verification() -> None:
    main = _load(f"{BASE}/flow.toml")
    steps = {s["id"]: (i, s) for i, s in enumerate(main["steps"])}
    assert steps["split_concepts"][0] < steps["post_split_verify_folders"][0]
    assert steps["post_split_verify_folders"][0] < steps["link_related_concepts"][0]
    assert steps["link_related_concepts"][0] < steps["post_split_final_verify"][0]

    links = steps["link_related_concepts"][1]
    assert links["flow"] == f"{BASE}/flows/link-folder-concepts.toml"
    assert links["foreach"] == "steps.post_split_verify_folders.output.iterations"
    assert links["iteration_id"] == "${item.id}"
    assert links["input"]["folder_scan"] == "${item.output}"
    assert links["input"]["okf_root"] == "${steps.design_structure.output.okf_root}"
    final = steps["post_split_final_verify"][1]
    assert final["prompt_file"].endswith("19_post_link_final_verify.md")
    assert final["vars"]["link_verifications"] == (
        "${steps.link_related_concepts.output.iterations}"
    )
    assert final["output"].endswith("post-link-final-verification-v3.json")



def test_per_concept_subflow_inputs_and_checkpoints() -> None:
    folder = _load(f"{BASE}/flows/link-folder-concepts.toml")
    steps = folder["steps"]
    assert folder["inputs"] == ["folder_scan", "structure", "okf_root", "target_folders"]
    assert folder["result"] == "steps.link_concepts.output"
    assert len(steps) == 1
    assert steps[0]["foreach"] == "input.folder_scan.concept_paths"
    assert steps[0]["input"]["concept_path"] == "${item}"
    assert steps[0]["input"]["concept_id"] == "${iteration.id}"

    adapter = _load(f"{BASE}/flows/link-concept.toml")
    assert adapter["result"] == "steps.shared.output"
    assert [step["id"] for step in adapter["steps"]] == ["shared"]
    assert adapter["steps"][0]["flow"] == "flow/okf/flows/link-concept.toml"
    assert adapter["steps"][0]["input"]["concept_path"] == (
        "${input.okf_root}/${input.concept_path}"
    )

    concept = _load("flow/okf/flows/link-concept.toml")
    assert concept["result"] == "steps.verify.output"
    assert [step["id"] for step in concept["steps"]] == ["snapshot", "discover_folders", "batch_candidates", "review_batches", "link", "verify"]
    snapshot, discover, batch, review, link, verify = concept["steps"]
    assert batch["json_operation"]["kind"] == "batch"
    assert batch["json_operation"]["max_batch_bytes"] == 32000
    assert review["foreach"] == "steps.batch_candidates.output.batches"
    assert review["workspace_access"] == "read"
    assert discover["foreach"] == "input.target_folders"
    assert discover["workspace_access"] == "read"
    assert discover["output"].endswith("/${item.path}.json")
    assert link["vars"]["batch_reviews"] == "${steps.review_batches.output.iterations}"
    assert snapshot["workspace_access"] == "read"
    assert snapshot["response_format"] == "json"
    assert not snapshot["overwrite_output"]
    assert link["vars"]["snapshot"] == "${steps.snapshot.output}"
    assert verify["vars"]["snapshot"] == "${steps.snapshot.output}"
    assert link["workspace_access"] == "write"
    assert link["approve_tools"] == ["os__write_file"]
    assert link["response_format"] == "json"
    assert not link["overwrite_output"]
    assert verify["workspace_access"] == "read"
    assert verify["response_format"] == "json"
    assert not verify["overwrite_output"]
    assert link["output"] != verify["output"]
    assert adapter["steps"][0]["input"]["checkpoint_key"] == (
        "${input.folder_id}-${input.concept_id}"
    )
    for step in (snapshot, link, verify):
        assert step["output"].endswith(
            f"/{step['id']}-v3-${{input.checkpoint_key}}.json"
        )
    assert discover["output"] == (
        "${input.state_dir}/discover-v3-${input.checkpoint_key}/${item.path}.json"
    )
    assert discover["prompt_file"] == "flow/okf/prompts/link_discover_folder.md"
    assert not discover["overwrite_output"]


def test_link_prompts_enforce_concept_scope_and_read_only_verification() -> None:
    shared = _load("flow/okf/flows/link-concept.toml")
    prompts_by_step = {step["id"]: step["prompt_file"] for step in shared["steps"]}
    assert prompts_by_step == {
        "snapshot": "flow/okf/prompts/link_snapshot.md",
        "discover_folders": "flow/okf/prompts/link_discover_folder.md",
        "batch_candidates": None,
        "review_batches": "flow/okf/prompts/link_review_batch.md",
        "link": "flow/okf/prompts/link_concept.md",
        "verify": "flow/okf/prompts/link_verify.md",
    }
    linker = (ROOT / "flow/okf/prompts/link_concept.md").read_text(encoding="utf-8")
    verifier = (ROOT / "flow/okf/prompts/link_verify.md").read_text(encoding="utf-8")
    assert "{{var:concept_path}}" in linker
    assert "{{var:link_result}}" in verifier
    assert "{{var:snapshot}}" in linker
    assert "{{var:snapshot}}" in verifier
    assert "snapshot.content" in verifier
    assert "reconstruct" in verifier.lower()
    assert "link_text" in linker
    assert "relative" in linker.lower()
    assert "read only" in verifier.lower() or "read-only" in verifier.lower()


def test_doctrine_concept_build_repair_preapprove_move_and_delete() -> None:
    steps = _load(f"{BASE}/flows/process-concept.toml")["steps"]
    assert [s["id"] for s in steps] == ["build", "verify", "repair"]
    for step in (steps[0], steps[2]):
        assert step["workspace_access"] == "write"
        assert {"os__move_file", "os__delete_file", "os__copy_file"} <= set(
            step["approve_tools"]
        )
    assert steps[1]["workspace_access"] == "read"
    assert "approve_tools" not in steps[1]

def test_final_review_requires_all_nested_link_verifications() -> None:
    prompt = (ROOT / BASE / "prompts/19_post_link_final_verify.md").read_text(
        encoding="utf-8"
    )
    assert "{{var:link_verifications}}" in prompt
    assert "concept_paths" in prompt
    assert "needs_attention" in prompt
    assert "EVERY nested" in prompt


def test_related_link_prompts_use_index_and_text_search_without_count_cap() -> None:
    linker = (ROOT / "flow/okf/prompts/link_concept.md").read_text(encoding="utf-8")
    verifier = (ROOT / "flow/okf/prompts/link_verify.md").read_text(encoding="utf-8")
    for prompt in (linker, verifier):
        assert "NO FIXED MAXIMUM" in prompt
        assert "THREE" not in prompt
    discovery = (ROOT / "flow/okf/prompts/link_discover_folder.md").read_text(encoding="utf-8")
    assert "index.md" in discovery
    assert "targeted text searches" in discovery
    assert "CURRENT target folder" in discovery
    assert "do NOT redo repository-wide searches" in linker
    assert "ONE link per distinct target" in linker
    assert "Zero links is valid" in linker
    assert "verify ALL reported links" in verifier
    assert "distinct target for each" in verifier
