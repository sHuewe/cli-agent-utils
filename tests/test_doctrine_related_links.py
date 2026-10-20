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
    assert list(steps)[-1] == "link_related_concepts"
    assert "post_split_final_verify" not in steps

    links = steps["link_related_concepts"][1]
    assert links["flow"] == f"{BASE}/flows/link-folder-concepts.toml"
    assert links["foreach"] == "steps.post_split_verify_folders.output.iterations"
    assert links["iteration_id"] == "${item.id}"
    assert links["input"]["folder_scan"] == "${item.output}"
    assert links["input"]["okf_root"] == "${steps.design_structure.output.okf_root}"



def test_per_concept_subflow_inputs_and_checkpoints() -> None:
    folder = _load(f"{BASE}/flows/link-folder-concepts.toml")
    steps = folder["steps"]
    assert folder["inputs"] == ["folder_scan", "structure", "okf_root"]
    assert folder["result"] == "steps.link_concepts.output"
    assert len(steps) == 1
    assert steps[0]["foreach"] == "input.folder_scan.concept_paths"
    assert steps[0]["input"]["concept_path"] == "${item}"
    assert steps[0]["input"]["concept_id"] == "${iteration.id}"

    concept = _load(f"{BASE}/flows/link-concept.toml")
    assert concept["result"] == "steps.verify.output"
    assert [s["id"] for s in concept["steps"]] == ["snapshot", "link", "verify"]
    snapshot, link, verify = concept["steps"]
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
    for step in (snapshot, link, verify):
        assert "${input.folder_id}" in step["output"]
        assert "${input.concept_id}" in step["output"]


def test_link_prompts_enforce_concept_scope_and_read_only_verification() -> None:
    linker = (ROOT / BASE / "prompts/17_link_related_concept.md").read_text(
        encoding="utf-8"
    )
    verifier = (ROOT / BASE / "prompts/18_verify_related_concept.md").read_text(
        encoding="utf-8"
    )
    assert "{{var:concept_path}}" in linker
    assert "{{var:link_result}}" in verifier
    assert "{{var:snapshot}}" in linker
    assert "{{var:snapshot}}" in verifier
    assert "snapshot.content" in verifier
    assert "reconstructed entire current text" in verifier
    assert "INSIDE the existing concept" in linker
    assert "link_text" in linker
    assert "Related concepts footer" in linker
    assert "ONLY file you may modify" in linker
    assert "Add at most three DISTINCT target paths" in linker
    assert "relative" in linker.lower()
    assert "read-only" in verifier


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

def test_inventory_precedes_shared_folder_verification() -> None:
    flow = _load("flow/okf/flows/verify-folder.toml")
    assert [step["id"] for step in flow["steps"]] == ["inventory", "verify"]
    assert flow["steps"][0]["filesystem_operation"]["kind"] == "inventory"
    assert flow["steps"][1]["vars"]["inventory"] == "${steps.inventory.output}"
    assert flow["steps"][1]["output"].endswith("verification-verify-${input.scope_id}-${input.folder.id}.json")


def test_inventory_precedes_split_discovery() -> None:
    flow = _load("flow/okf/flows/split-folder.toml")
    assert [step["id"] for step in flow["steps"]] == ["inventory", "discover", "split"]
    assert flow["steps"][0]["filesystem_operation"]["kind"] == "inventory"
    assert flow["steps"][1]["vars"]["inventory"] == "${steps.inventory.output}"
    assert not flow["steps"][1]["overwrite_output"]
