"""Regression tests for safe legacy scan route metadata repairs."""
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "flow/okf/flow_okf_from_doctrine_batched/normalize_legacy_scan_route_ids.py"
spec = importlib.util.spec_from_file_location("normalize_scan_route_ids", SCRIPT)
normalizer = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(normalizer)
SCHEMA = ROOT / normalizer.SCHEMA_PATH


def _workspace(tmp_path, slug="example"):
    schema = tmp_path / normalizer.SCHEMA_PATH
    schema.parent.mkdir(parents=True)
    schema.write_bytes(SCHEMA.read_bytes())
    docs = tmp_path / normalizer.STATE_PATH / slug
    docs.mkdir(parents=True)
    (docs / "sections.json").write_text(json.dumps({
        "source_path": "md/example.md",
        "sections": [
            {"id": "s001", "start_line": 1, "end_line": 10},
            {"id": "s002", "start_line": 11, "end_line": 20},
        ],
    }), encoding="utf-8")
    return docs


def _scan(docs, sid="s001", **changes):
    boundaries = {"s001": (1, 10), "s002": (11, 20)}
    start, end = boundaries[sid]
    data = {
        "status": "ok", "section_id": sid, "source_path": "md/example.md",
        "start_line": start, "end_line": end,
        "candidate_concepts": [
            {"topic_key": f"{sid}-t001", "name": "Subject"}
        ],
        "knowledge_items": [
            {"id": f"{sid}:rule001", "topic_key": f"{sid}-t001",
             "kind": "fact", "name": "Fact", "description": "Evidence",
             "normative": False, "evidence_ranges": [
                 {"doctrine": "md/example.md", "start_line": start,
                  "end_line": start}
             ]}
        ],
    }
    data.update(changes)
    path = docs / f"scan-{sid}.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_dry_run_only_reports_missing_identity_fields(tmp_path, capsys):
    docs = _workspace(tmp_path)
    missing = _scan(docs)
    existing = _scan(
        docs, "s002", document_id="example", folder_id="example", chunk_id="s002"
    )
    original = missing.read_bytes()
    updates, scanned = normalizer.plan_updates(tmp_path, document="example")
    assert scanned == 2
    assert len(updates) == 1
    assert updates[0][3] == ("document_id", "folder_id", "chunk_id")
    assert normalizer.run(["--workspace", str(tmp_path), "--document", "example"]) == 0
    assert missing.read_bytes() == original
    assert not existing.with_name(existing.name + normalizer.BACKUP_SUFFIX).exists()
    assert "1 of 2" in capsys.readouterr().out


def test_apply_preserves_knowledge_and_is_idempotent(tmp_path):
    docs = _workspace(tmp_path)
    path = _scan(docs, document_id=" ", chunk_id="s001")
    original = path.read_bytes()
    assert normalizer.run([
        "--workspace", str(tmp_path), "--document", "example", "--apply"
    ]) == 0
    backup = path.with_name(path.name + normalizer.BACKUP_SUFFIX)
    assert backup.read_bytes() == original
    corrected = json.loads(path.read_text(encoding="utf-8"))
    assert corrected["document_id"] == corrected["folder_id"] == "example"
    assert corrected["chunk_id"] == "s001"
    assert corrected["knowledge_items"] == json.loads(original)["knowledge_items"]
    assert normalizer.plan_updates(tmp_path, document="example") == ([], 1)


@pytest.mark.parametrize("changes", [
    {"document_id": "other"},
    {"folder_id": "other"},
    {"chunk_id": "s001"},  # Conflicts with the s002 scan checkpoint
    {"start_line": 2},
    {"source_path": "md/other.md"},
])
def test_conflicting_identity_or_section_metadata_blocks_all_writes(tmp_path, changes):
    docs = _workspace(tmp_path)
    first = _scan(docs)
    second = _scan(docs, "s002", **changes)
    original = first.read_bytes()
    with pytest.raises(ValueError):
        normalizer.run(["--workspace", str(tmp_path), "--apply"])
    assert first.read_bytes() == original
    assert second.is_file()
    assert not first.with_name(first.name + normalizer.BACKUP_SUFFIX).exists()


def test_unrelated_schema_error_blocks_all_writes(tmp_path):
    docs = _workspace(tmp_path)
    first = _scan(docs)
    _scan(docs, "s002", start_line=11, end_line=20, knowledge_items={})
    with pytest.raises(ValueError, match="still violates schema"):
        normalizer.run(["--workspace", str(tmp_path), "--apply"])
    assert "document_id" not in json.loads(first.read_text(encoding="utf-8"))


def test_existing_backup_blocks_all_writes(tmp_path):
    docs = _workspace(tmp_path)
    first = _scan(docs)
    second = _scan(docs, "s002")
    second.with_name(second.name + normalizer.BACKUP_SUFFIX).write_text(
        "existing", encoding="utf-8"
    )
    with pytest.raises(FileExistsError, match="Existing backup"):
        normalizer.run(["--workspace", str(tmp_path), "--apply"])
    assert "document_id" not in json.loads(first.read_text(encoding="utf-8"))
    assert not first.with_name(first.name + normalizer.BACKUP_SUFFIX).exists()


def test_scan_schema_requires_all_route_id_fields():
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    for field in ("document_id", "folder_id", "chunk_id"):
        assert field in schema["required"]
        assert schema["properties"][field]["type"] == "string"
        assert schema["properties"][field]["minLength"] >= 1


def test_refuses_symlinked_scans(tmp_path):
    docs = _workspace(tmp_path)
    external = tmp_path.parent / (tmp_path.name + "-external-scan.json")
    external.write_text('{"document_id": "outside"}', encoding="utf-8")
    link = docs / "scan-s001.json"
    try:
        link.symlink_to(external)
    except (OSError, NotImplementedError):
        pytest.skip("Symlink creation not supported")
    with pytest.raises(ValueError, match="Symlink or junction"):
        normalizer.plan_updates(tmp_path, document="example")
    assert external.read_text(encoding="utf-8") == '{"document_id": "outside"}'
