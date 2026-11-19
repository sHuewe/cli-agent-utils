"""Artifact audit must detect cross-concept writes and preserve unaffected state."""
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "flow/okf/flow_okf_from_doctrine_batched/audit_concepts.py"
spec = importlib.util.spec_from_file_location("okf_concept_audit", SCRIPT)
audit_module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(audit_module)


def data(tmp_path: Path):
    docs = tmp_path / "okf-batched/state-v3/docs/example"
    docs.mkdir(parents=True)
    root = tmp_path / "okf-batched-generated-v3"
    a = "doctrines/example/planning/s003-t001.md"
    b = "doctrines/example/planning/s006-t001.md"
    c = "doctrines/example/planning/s007-t001.md"
    (root / a).parent.mkdir(parents=True)
    (root / a).write_text("# potentially overwritten", encoding="utf-8")
    (root / c).write_text("# other", encoding="utf-8")
    (docs / "group.json").write_text(json.dumps({
        "concepts": [
            {"id": "s003-t001", "path": a},
            {"id": "s006-t001", "path": b},
            {"id": "s007-t001", "path": c},
        ]
    }), encoding="utf-8")
    for cid, path in (("s003-t001", a), ("s006-t001", a), ("s007-t001", c)):
        for step in ("build", "verify", "repair"):
            (docs / f"concept-{cid}-{step}.json").write_text(json.dumps({
                "concept_id": cid, "status": "created", "path": "okf-batched-generated-v3/" + path,
                "documented_item_ids": [], "changed_paths": [
                    "okf-batched-generated-v3/" + path
                ] if step == "repair" else [],
            }))
        (docs / "manifests").mkdir(exist_ok=True)
        (docs / "manifests" / f"concept-{cid}.json").write_text(json.dumps({
            "concepts": [{"path": path}]
        }))
    (docs / "coverage.json").write_text('{"status":"ok"}', encoding="utf-8")
    return docs, root, a, b, c


def test_detects_foreign_path_and_missing_target_without_touching_other_concepts(tmp_path):
    docs, root, a, b, c = data(tmp_path)
    report = audit_module.audit(tmp_path, "okf-batched-generated-v3")
    assert report["affected"]["example"] == ["s003-t001", "s006-t001"]
    assert "s007-t001" not in report["affected"]["example"]
    assert {"wrong_path", "missing_markdown", "potentially_overwritten"} <= {
        item["reason"] for item in report["findings"]
    }
    assert (root / c).is_file()
    assert (docs / "concept-s007-t001-build.json").is_file()


def test_selective_quarantine_backups_affected_only(tmp_path):
    docs, root, a, b, c = data(tmp_path)
    report = audit_module.audit(tmp_path, "okf-batched-generated-v3")
    moved = audit_module.quarantine(tmp_path, "okf-batched-generated-v3", report, {"example": {"s003-t001", "s006-t001"}})
    assert moved
    assert not (docs / "concept-s006-t001-build.json").exists()
    assert not (docs / "concept-s003-t001-repair.json").exists()
    assert not (root / a).exists()
    assert (docs / "concept-s007-t001-build.json").exists()
    assert (root / c).exists()
    assert not (docs / "coverage.json").exists()
    assert (tmp_path / "okf-batched/recovery-v3/generated" / a).exists()


def test_preflight_conflict_preserves_every_original(tmp_path):
    docs, root, a, b, c = data(tmp_path)
    report = audit_module.audit(tmp_path, "okf-batched-generated-v3")
    target = tmp_path / "okf-batched/recovery-v3/generated" / a
    target.parent.mkdir(parents=True)
    target.write_text("existing", encoding="utf-8")
    with pytest.raises(FileExistsError):
        audit_module.quarantine(tmp_path, "okf-batched-generated-v3", report, {"example": {"s003-t001", "s006-t001"}})
    assert (root / a).is_file()
    assert (docs / "concept-s006-t001-build.json").is_file()
    assert target.read_text() == "existing"


def test_quarantine_refuses_to_ignore_the_overwritten_owner(tmp_path):
    docs, root, a, b, c = data(tmp_path)
    report = audit_module.audit(tmp_path, "okf-batched-generated-v3")
    with pytest.raises(ValueError, match="Select all affected"):
        audit_module.quarantine(
            tmp_path, "okf-batched-generated-v3", report,
            {"example": {"s006-t001"}}
        )
    assert (docs / "concept-s006-t001-build.json").exists()
    assert (root / a).exists()
