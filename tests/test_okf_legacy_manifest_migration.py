"""Regression tests for non-destructive legacy OKF manifest checkpoint migration."""
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "flow/okf/flow_okf_from_doctrine_batched/normalize_legacy_manifests.py"
spec = importlib.util.spec_from_file_location("okf_legacy_manifest_migration", SCRIPT)
migration = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(migration)

SOURCE = "md-2026-06-04-un-emo-sop-final-v2"
CONCEPT = "s010-t001"
CANONICAL = f"doctrines/{SOURCE}/cell-role-and-authority/{CONCEPT}.md"
ROOT_NAME = "okf-batched-generated-v3"


def fixtures(workspace: Path, *, root_prefix: bool = True, extra: bool = False):
    config = workspace / "flow/okf/flow_okf_from_doctrine_batched/flow.toml"
    config.parent.mkdir(parents=True)
    config.write_text(f'[vars]\nokf_root = "{ROOT_NAME}"\n', encoding="utf-8")
    state = workspace / "okf-batched/state-v3/docs" / SOURCE
    directory = state / "manifests"
    directory.mkdir(parents=True)
    (state / "group.json").write_text(json.dumps({
        "concepts": [{"id": CONCEPT, "path": CANONICAL}]
    }), encoding="utf-8")
    manifest = directory / f"concept-{CONCEPT}.json"
    content = {
        "status": "ok",
        "concepts": [{"path": (f"{ROOT_NAME}/" if root_prefix else "") + CANONICAL,
                      "title": "Source title", "description": "Source meaning",
                      "source_slug": SOURCE}],
        "warnings": ["keep the original warning"],
    }
    if extra:
        content["extra"] = {"nested": ["preserve", 2]}
    manifest.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def test_dry_run_does_not_modify_any_checkpoint(tmp_path, capsys):
    manifest = fixtures(tmp_path)
    original = manifest.read_bytes()
    assert migration.run(["--workspace", str(tmp_path)]) == 0
    assert manifest.read_bytes() == original
    assert not list(manifest.parent.glob("*.bak-pre-root-normalize"))
    assert "WOULD NORMALIZE" in capsys.readouterr().out


def test_apply_backs_up_and_canonicalizes_only_the_exact_path(tmp_path):
    manifest = fixtures(tmp_path, extra=True)
    original = manifest.read_bytes()
    before = json.loads(original)
    assert migration.run(["--workspace", str(tmp_path), "--apply"]) == 0
    backup = manifest.with_name(manifest.name + ".bak-pre-root-normalize")
    assert backup.read_bytes() == original
    after = json.loads(manifest.read_text(encoding="utf-8"))
    before["concepts"][0]["path"] = CANONICAL
    assert after == before
    assert migration.run(["--workspace", str(tmp_path), "--apply"]) == 0
    assert backup.read_bytes() == original


def test_already_canonical_checkpoints_are_left_byte_for_byte(tmp_path):
    manifest = fixtures(tmp_path, root_prefix=False)
    original = manifest.read_bytes()
    assert migration.plan_updates(tmp_path, ROOT_NAME) == []
    migration.run(["--workspace", str(tmp_path), "--apply"])
    assert manifest.read_bytes() == original
    assert not manifest.with_name(manifest.name + ".bak-pre-root-normalize").exists()


@pytest.mark.parametrize("invalid", [
    "other-root/" + CANONICAL,
    "okf-batched-generated-v3/doctrines/elsewhere/unrelated.md",
    "../" + CANONICAL,
])
def test_unknown_or_unsafe_path_is_rejected_before_writes(tmp_path, invalid):
    manifest = fixtures(tmp_path)
    content = json.loads(manifest.read_text())
    content["concepts"][0]["path"] = invalid
    manifest.write_text(json.dumps(content), encoding="utf-8")
    original = manifest.read_bytes()
    with pytest.raises(ValueError, match="Unexpected manifest path"):
        migration.run(["--workspace", str(tmp_path), "--apply"])
    assert manifest.read_bytes() == original


def test_fail_closed_across_multiple_documents_before_writing(tmp_path):
    first = fixtures(tmp_path)
    other = tmp_path / "okf-batched/state-v3/docs" / "another-document"
    (other / "manifests").mkdir(parents=True)
    (other / "group.json").write_text(json.dumps({
        "concepts": [{"id": "s001-t001", "path": "doctrines/another-document/s001-t001.md"}]
    }))
    invalid = other / "manifests/concept-s001-t001.json"
    invalid.write_text(json.dumps({"concepts": [{"path": "unknown/path.md"}]}))
    original = first.read_bytes()
    with pytest.raises(ValueError):
        migration.run(["--workspace", str(tmp_path), "--apply"])
    assert first.read_bytes() == original


def test_never_overwrite_existing_backup(tmp_path):
    manifest = fixtures(tmp_path)
    backup = manifest.with_name(manifest.name + ".bak-pre-root-normalize")
    backup.write_bytes(b"valuable original backup")
    original = manifest.read_bytes()
    with pytest.raises(FileExistsError):
        migration.run(["--workspace", str(tmp_path), "--apply"])
    assert manifest.read_bytes() == original
    assert backup.read_bytes() == b"valuable original backup"
