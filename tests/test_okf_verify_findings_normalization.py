"""Tests for narrowly scoped legacy verify-checkpoint normalization."""
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "flow/okf/flow_okf_from_doctrine_batched/normalize_legacy_verify_findings.py"
spec = importlib.util.spec_from_file_location("normalize_verify_findings", SCRIPT)
normalizer = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(normalizer)

SCHEMA = ROOT / "flow/okf/flow_okf_from_doctrine_batched/schemas/concept-verify.schema.json"


def workspace(tmp_path):
    schema = tmp_path / normalizer.SCHEMA_PATH
    schema.parent.mkdir(parents=True)
    schema.write_bytes(SCHEMA.read_bytes())
    docs = tmp_path / "okf-batched/state-v3/docs/example"
    docs.mkdir(parents=True)
    return docs


def checkpoint(docs, name="s028-t004", **overrides):
    path = docs / f"concept-{name}-verify.json"
    value = {
        "status": "needs_repair",
        "concept_id": name,
        "path": f"doctrines/example/{name}.md",
        "documented_item_ids": [],
        "findings": [
            {"severity": "warning", "item_id": "",
             "problem": "General concern", "required_change": "Review text"},
            {"severity": "error", "item_id": "item-1",
             "problem": "Missing coverage", "required_change": "Add coverage"},
        ],
    }
    value.update(overrides)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return path


def test_dry_run_does_not_write_anything(tmp_path, capsys):
    docs = workspace(tmp_path)
    path = checkpoint(docs)
    original = path.read_bytes()
    assert normalizer.run(["--workspace", str(tmp_path)]) == 0
    assert path.read_bytes() == original
    assert not path.with_name(path.name + normalizer.BACKUP_SUFFIX).exists()
    assert "WOULD NORMALIZE" in capsys.readouterr().out


def test_apply_removes_only_empty_optional_ids_and_preserves_valid_items(tmp_path):
    docs = workspace(tmp_path)
    path = checkpoint(docs)
    original = path.read_bytes()
    assert normalizer.run(["--workspace", str(tmp_path), "--apply"]) == 0
    backup = path.with_name(path.name + normalizer.BACKUP_SUFFIX)
    assert backup.read_bytes() == original
    updated = json.loads(path.read_text(encoding="utf-8"))
    assert "item_id" not in updated["findings"][0]
    assert updated["findings"][0]["problem"] == "General concern"
    assert updated["findings"][1]["item_id"] == "item-1"
    assert normalizer.plan_updates(tmp_path) == []


def test_valid_checkpoint_not_modified(tmp_path):
    docs = workspace(tmp_path)
    path = checkpoint(docs, findings=[{"item_id": "item-1"}])
    original = path.read_bytes()
    assert normalizer.run(["--workspace", str(tmp_path), "--apply"]) == 0
    assert path.read_bytes() == original
    assert not path.with_name(path.name + normalizer.BACKUP_SUFFIX).exists()


def test_other_schema_violation_blocks_all_writes(tmp_path):
    docs = workspace(tmp_path)
    first = checkpoint(docs, name="s001-t001")
    second = checkpoint(docs, name="s002-t002", documented_item_ids=[""])
    first_bytes, second_bytes = first.read_bytes(), second.read_bytes()
    with pytest.raises(ValueError, match="still violates verify schema"):
        normalizer.run(["--workspace", str(tmp_path), "--apply"])
    assert first.read_bytes() == first_bytes
    assert second.read_bytes() == second_bytes
    assert not first.with_name(first.name + normalizer.BACKUP_SUFFIX).exists()


def test_conflicting_backup_blocks_all_writes(tmp_path):
    docs = workspace(tmp_path)
    first = checkpoint(docs, name="s001-t001")
    second = checkpoint(docs, name="s002-t002")
    prior = second.with_name(second.name + normalizer.BACKUP_SUFFIX)
    prior.write_text("already exists", encoding="utf-8")
    original = first.read_bytes()
    with pytest.raises(FileExistsError, match="Existing normalization backup"):
        normalizer.run(["--workspace", str(tmp_path), "--apply"])
    assert first.read_bytes() == original
    assert prior.read_text(encoding="utf-8") == "already exists"
    assert not first.with_name(first.name + normalizer.BACKUP_SUFFIX).exists()


def test_unexpected_duplicate_keys_fail_closed(tmp_path):
    docs = workspace(tmp_path)
    path = checkpoint(docs)
    path.write_text('{"concept_id":"a","concept_id":"b"}', encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate JSON"):
        normalizer.plan_updates(tmp_path)


def test_symlinked_checkpoint_rejected(tmp_path):
    docs = workspace(tmp_path)
    external = tmp_path.parent / (tmp_path.name + "-external-verify.json")
    external.write_text('{"findings":[]}', encoding="utf-8")
    link = docs / "concept-s001-t001-verify.json"
    try:
        link.symlink_to(external)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks unavailable")
    with pytest.raises(ValueError, match="Symlink or junction"):
        normalizer.plan_updates(tmp_path)
    assert external.read_text(encoding="utf-8") == '{"findings":[]}'
