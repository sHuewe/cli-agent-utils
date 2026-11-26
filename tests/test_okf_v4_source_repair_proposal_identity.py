"""Proposal KI references must preserve complete coverage independently of order."""
from pathlib import Path
import copy
import json
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "flow/okf/v4"))
from source_repair import _check_proposal_identity, _diagnose_proposals
from test_okf_v4_phase_a_b import fixture, migrate_applied, put_json
from source_repair import prepare


def test_accepts_only_complete_permutation():
    task = {"id": "test:s1", "key": "test--s1--abc123", "knowledge_item_ids": ["a", "b", "c"]}
    original = {"id": "test:s1", "knowledge_item_ids": ["a", "b", "c"]}
    assert _check_proposal_identity(original, task) is False
    reordered = {"id": "test:s1", "knowledge_item_ids": ["c", "a", "b"]}
    assert _check_proposal_identity(reordered, task) is True
    assert task["knowledge_item_ids"] == ["a", "b", "c"]
    # A few existing LLM reviews echo the task key rather than the concept ID.
    # This exact same-task alias is safe only with complete source KI coverage.
    key_as_id = {"id": task["key"], "knowledge_item_ids": ["c", "a", "b"]}
    assert _check_proposal_identity(key_as_id, task) is True
    with pytest.raises(ValueError, match="KI coverage mismatch"):
        _check_proposal_identity(
            {"id": task["key"], "knowledge_item_ids": ["a", "b"]}, task
        )
    with pytest.raises(ValueError, match="proposal ID mismatch"):
        _check_proposal_identity(
            {"id": "test--s2--abc123", "knowledge_item_ids": ["a", "b", "c"]},
            task,
        )

    for bad, detail in [
        (["a", "b"], "missing="),
        (["a", "b", "c", "d"], "unexpected="),
        (["a", "b", "b"], "missing="),
        (["a", "b", 42], "invalid"),
    ]:
        with pytest.raises(ValueError, match=detail):
            _check_proposal_identity(
                {"id": "test:s1", "knowledge_item_ids": bad}, task
            )
    with pytest.raises(ValueError, match="proposal ID mismatch"):
        _check_proposal_identity(
            {"id": "test:other", "knowledge_item_ids": ["a", "b", "c"]},
            task,
        )


def test_readonly_proposal_diagnostic_summarizes_missing_and_reordered(tmp_path):
    fixture(tmp_path)
    (tmp_path / "okf-batched/state-v3/docs/example/"
     "concept-s001-c010-repair.json").unlink()
    migrate_applied(tmp_path)
    tasks = prepare(tmp_path, skip_coverage=True)
    task = tasks["concepts"][0]
    result = _diagnose_proposals(
        tmp_path, require_coverage=False, skip_coverage=True,
    )
    assert result["checked"] == 1
    assert result["invalid"] == 1
    assert "Required file" in result["examples"][0]["reason"] or (
        "exist" in result["examples"][0]["reason"].lower()
    )

    path = (tmp_path / "okf-v4/state-b/source-repair/proposals"
            / (task["key"] + ".json"))
    proposal = {
        "id": task["id"], "action": "keep",
        "title": task["title"], "markdown": "",
        "knowledge_item_ids": task["knowledge_item_ids"],
    }
    put_json(path, proposal)
    before = path.read_bytes()
    result = _diagnose_proposals(
        tmp_path, require_coverage=False, skip_coverage=True,
    )
    assert result["status"] == "ok"
    assert result["invalid"] == 0
    assert result["reordered"] == 0
    assert result["id_is_task_key"] == 0
    assert path.read_bytes() == before

    # The exact task-key echo is counted separately, without rewriting the
    # checkpointed JSON or changing the canonical concept identity.
    proposal["id"] = task["key"]
    put_json(path, proposal)
    before = path.read_bytes()
    result = _diagnose_proposals(
        tmp_path, require_coverage=False, skip_coverage=True,
    )
    assert result["status"] == "ok"
    assert result["id_is_task_key"] == 1
    assert path.read_bytes() == before
