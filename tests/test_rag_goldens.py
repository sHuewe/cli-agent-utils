"""Regression tests for bounded, independently reviewed cross-doctrine RAG goldens."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "flow/rag/generate_goldens"
sys.path.insert(0, str(BASE / "scripts"))
from prepare import prepare  # noqa: E402
from export import export, valid_golden  # noqa: E402


def test_flow_contracts():
    configs = [BASE / "flow.toml", BASE / "flows/process-pack.toml"]
    for path in configs:
        with path.open("rb") as stream:
            cfg = tomllib.load(stream)
        assert cfg["version"] == 1
        for step in cfg["steps"]:
            assert sum(key in step for key in (
                "flow", "prompt_file", "json_operation", "filesystem_operation"
            )) == 1
            if "flow" in step:
                assert (ROOT / step["flow"]).is_file()
            if "prompt_file" in step:
                assert (ROOT / step["prompt_file"]).is_file()
    with (BASE / "flow.toml").open("rb") as stream:
        main = tomllib.load(stream)
    assert main["steps"][0]["filesystem_operation"]["stable_slugs"] is True
    assert main["steps"][1]["foreach"] == "steps.packs.output.files"
    with (BASE / "flows/process-pack.toml").open("rb") as stream:
        child = tomllib.load(stream)
    assert child["steps"][0]["workspace_access"] == "read"
    assert child["steps"][1]["workspace_access"] == "read"
    assert child["steps"][0]["overwrite_output"] is False
    assert child["steps"][1]["overwrite_output"] is False


def test_prepare_export_and_source_invalidation(tmp_path: Path):
    docs = tmp_path / "doctrines"
    docs.mkdir()
    (docs / "architecture.md").write_text(
        "# Service authentication\n"
        "A gateway handles requests by checking a trusted bearer token.\n"
        "The gateway enforces token validation before access to protected applications.\n",
        encoding="utf-8",
    )
    (docs / "policy.md").write_text(
        "# Service authentication\n"
        "The policy requires all protected applications to validate authentication tokens.\n"
        "Requests with missing bearer tokens must be rejected by the gateway.\n",
        encoding="utf-8",
    )
    summary = prepare(tmp_path, "doctrines", "rag-goldens/packs", 2, 1200, 0.05)
    assert summary["packs"] >= 1
    root = tmp_path / "rag-goldens"
    manifest = json.loads((root / "manifest.json").read_text())
    name = manifest["pack_ids"][0]
    pack = json.loads((root / "packs" / name).read_text())
    assert pack["sources"][0]["path"] != pack["sources"][1]["path"]
    assert len((root / "packs" / name).read_bytes()) <= 12000
    citations = []
    for s in pack["sources"]:
        line = s["text"].splitlines()[1]
        citations.append({
            "source_id": s["id"], "quote": line,
            "start_line": s["start_line"] + 1, "end_line": s["start_line"] + 1,
            "supports": "This part of the answer needs this source",
        })
    draft = {
        "status": "ok", "pack_id": pack["pack_id"],
        "question": "How should gateway authentication enforce protected access?",
        "expected_output": "The gateway validates bearer tokens and rejects missing credentials.",
        "category": "multi_document", "difficulty": "hard",
        "evidence": citations,
        "necessity": {"without_s1": "Gateway design missing",
                      "without_s2": "Policy missing"},
    }
    review = {
        "status": "accepted", "pack_id": pack["pack_id"], "reason": "Grounded",
        "checks": {"grounded": True, "both_documents_necessary": True,
                   "unambiguous": True, "no_source_leakage": True},
    }
    assert valid_golden(pack, draft, review)
    bad = json.loads(json.dumps(draft))
    bad["evidence"][0]["quote"] = "invented evidence"
    assert valid_golden(pack, bad, review) is None
    state = root / "state"
    state.mkdir()
    from prepare import secure_path
    import re
    rel = f"rag-goldens/packs/{name}"
    prefix = re.sub(r"[^a-z0-9]+", "-", rel.casefold()).strip("-")[:60].strip("-")
    slug = f"{prefix}-{hashlib.sha256(rel.encode()).hexdigest()[:16]}"
    for kind, obj in (("draft", draft), ("review", review)):
        (state / f"{kind}-{slug}.json").write_text(json.dumps(obj), encoding="utf-8")
    stats = export(tmp_path, "rag-goldens")
    assert stats["accepted"] == 1
    result = json.loads((root / "goldens.json").read_text())
    assert len(result) == 1
    assert len(result[0]["sources"]) == 2
    (docs / "policy.md").write_text("changed", encoding="utf-8")
    import pytest
    with pytest.raises(ValueError, match="Stale source"):
        export(tmp_path, "rag-goldens")


def test_reject_single_document_or_unverified():
    sources = [
        {"id": "s1", "path": "a.md", "start_line": 1, "end_line": 1,
         "sha256": "x", "text": "first relevant fact\n"},
        {"id": "s2", "path": "b.md", "start_line": 1, "end_line": 1,
         "sha256": "y", "text": "second relevant fact\n"},
    ]
    pack = {"pack_id": "p0123456789abcdef", "sources": sources}
    draft = {
        "status": "ok", "pack_id": pack["pack_id"],
        "category": "multi_document",
        "question": "How do the two requirements fit together?",
        "expected_output": "First fact plus second fact provide the complete rationale.",
        "evidence": [
            {"source_id": "s1", "quote": "first relevant fact", "start_line": 1,
             "end_line": 1, "supports": "first"},
            {"source_id": "s2", "quote": "second relevant fact", "start_line": 1,
             "end_line": 1, "supports": "second"}
        ],
        "necessity": {"without_s1": "first missing", "without_s2": "second missing"},
    }
    assert valid_golden(pack, draft, {"status": "rejected"}) is None
    assert valid_golden(pack, draft, {"status": "accepted", "pack_id": pack["pack_id"],
        "checks": {"grounded": True, "both_documents_necessary": False,
                   "unambiguous": True, "no_source_leakage": True}}) is None
