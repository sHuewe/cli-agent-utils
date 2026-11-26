"""Preserve valid legacy checkpoints under the stricter source-repair schema."""
import json
from pathlib import Path
import sys

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "flow/okf/v4"))
from diagnose_source_repair_proposals import validate_proposal, inspect, quarantine
from source_repair import prepare
from test_okf_v4_phase_a_b import fixture, migrate_applied, put_json


SCHEMA_PATH = ROOT / "flow/okf/v4/schemas/source-repair.schema.json"
SCHEMA = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
VALIDATOR = Draft202012Validator(SCHEMA)


def proposal(task):
    return {
        "id": task["id"], "action": "keep", "title": task["title"],
        "markdown": "", "knowledge_item_ids": task["knowledge_item_ids"],
    }


def test_schema_keeps_legacy_shape_and_constrains_new_action_pairs():
    Draft202012Validator.check_schema(SCHEMA)
    example = {
        "id": "test:s1", "action": "keep", "title": "Existing",
        "markdown": "", "knowledge_item_ids": ["test:k1"],
    }
    assert VALIDATOR.is_valid(example)
    assert not VALIDATOR.is_valid({**example, "markdown": "---\nchanged"})
    rewrite = {**example, "action": "rewrite", "markdown": "---\ntitle: Existing\n"}
    assert VALIDATOR.is_valid(rewrite)
    assert not VALIDATOR.is_valid({**rewrite, "markdown": ""})
    assert not VALIDATOR.is_valid({**rewrite, "markdown": "No frontmatter"})


def test_keep_and_rewrite_validation_use_existing_apply_rules(tmp_path):
    fixture(tmp_path)
    migrate_applied(tmp_path)
    task = prepare(tmp_path, skip_coverage=True)["concepts"][0]
    p = proposal(task)
    validate_proposal(p, task)
    with pytest.raises(ValueError, match="Keep proposal cannot carry"):
        validate_proposal({**p, "markdown": "Not empty"}, task)
    assert task["kind"] == "existing"
    body = (
        "---\ntype: concept\n"
        "title: " + task["title"] + "\n---\n"
        "# A source-grounded rewrite\n"
        "The source statement is preserved and the scope is retained.\n"
    )
    revised = {**p, "action": "rewrite", "markdown": body}
    validate_proposal(revised, task)
    with pytest.raises(ValueError, match="frontmatter"):
        validate_proposal({**revised, "markdown": "Invalid body"}, task)


def test_existing_valid_proposal_is_never_mutated_and_invalid_can_be_quarantined(tmp_path):
    fixture(tmp_path)
    migrate_applied(tmp_path)
    task = prepare(tmp_path, skip_coverage=True)["concepts"][0]
    path = (tmp_path / "okf-v4/state-b/source-repair/proposals"
            / (task["key"] + ".json"))
    put_json(path, proposal(task))
    before = path.read_bytes()
    report, invalid = inspect(tmp_path)
    assert (report["valid"], report["invalid"], report["missing"]) == (1, 0, 0)
    assert invalid == []
    assert path.read_bytes() == before
    assert quarantine(tmp_path, invalid) is None

    broken = {**proposal(task), "markdown": "---\nWrong action"}
    put_json(path, broken)
    broken_bytes = path.read_bytes()
    report, invalid = inspect(tmp_path)
    assert (report["valid"], report["invalid"], report["missing"]) == (0, 1, 0)
    assert path.read_bytes() == broken_bytes
    target = quarantine(tmp_path, invalid)
    assert target is not None
    assert not path.exists()
    assert (target / path.name).read_bytes() == broken_bytes
    manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
    assert len(manifest["files"]) == 1
    report, invalid = inspect(tmp_path)
    assert (report["invalid"], report["missing"]) == (0, 1)
