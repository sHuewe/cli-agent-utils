"""Regression checks for standalone OKF relinking flow configuration."""
from pathlib import Path
import re
import tomllib

ROOT = Path(__file__).resolve().parents[1]
FLOW = ROOT / "flow/okf/flow_okf_relink"


def _read(path: Path):
    return tomllib.loads(path.read_text(encoding="utf-8"))


def test_relink_foreach_ids_are_not_self_referential():
    for path in (FLOW / "flow.toml", FLOW / "flows/link-folder.toml"):
        flow = _read(path)
        for step in flow["steps"]:
            assert step.get("iteration_id") != "${iteration.id}"


def test_shared_link_prompts_have_exact_variable_bindings():
    shared = _read(ROOT / "flow/okf/flows/link-concept.toml")
    for step in shared["steps"]:
        prompt = (ROOT / step["prompt_file"]).read_text(encoding="utf-8")
        expected = set(re.findall(r"\{\{var:([a-zA-Z_][a-zA-Z0-9_]*)\}\}", prompt))
        assert set(step["vars"]) == expected, step["id"]


def test_relink_forwards_real_iteration_ids():
    adapter = _read(FLOW / "flows/link-concept.toml")["steps"][0]["input"]
    assert adapter["concept_id"] == "${input.concept_id}"
    assert adapter["folder_id"] == "${input.folder_id}"


def test_relink_checkpoint_paths_do_not_depend_on_inventory_positions():
    shared = _read(ROOT / "flow/okf/flows/link-concept.toml")
    adapter = _read(FLOW / "flows/link-concept.toml")["steps"][0]["input"]
    assert adapter["checkpoint_key"] == "relink"
    assert adapter["state_dir"] == (
        "flow/okf/flow_okf_relink/state/concepts/${input.concept.path}"
    )
    for step in shared["steps"]:
        assert "v2" in step["output"]
    assert shared["steps"][1]["foreach"] == "input.target_folders"

    def checkpoint_paths(concept_path: str, folder_pos: str, concept_pos: str):
        state_dir = adapter["state_dir"].replace(
            "${input.concept.path}", concept_path
        )
        return {
            (step["output"]
             .replace("${input.state_dir}", state_dir)
             .replace("${input.checkpoint_key}", adapter["checkpoint_key"])
             .replace("${item.path}", "security")
             .replace("${input.folder_id}", folder_pos)
             .replace("${input.concept_id}", concept_pos))
            for step in shared["steps"]
        }

    original = checkpoint_paths("okf-generated/alpha/topic.md", "1", "3")
    reordered = checkpoint_paths("okf-generated/alpha/topic.md", "7", "18")
    other = checkpoint_paths("okf-generated/beta/topic.md", "7", "18")
    assert original == reordered
    assert original.isdisjoint(other)
    root = _read(FLOW / "flow.toml")
    assert root["steps"][1]["input"]["target_folders"] == "${steps.inventory.output.directories}"
