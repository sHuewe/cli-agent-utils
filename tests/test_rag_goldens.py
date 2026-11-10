"""Static and deterministic regression checks for the RAG golden flow.

No network, model, or external package required besides pytest (repository CI).
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import sys
import tomllib

import pytest

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "flow/rag/generate_goldens"
sys.path.insert(0, str(BASE / "scripts"))
from export import make_golden, export  # noqa: E402


def config(path: Path) -> dict:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def test_flow_paths_and_prompt_variable_bindings():
    paths = [BASE / "flow.toml", *sorted((BASE / "flows").glob("*.toml"))]
    assert len(paths) >= 8
    for path in paths:
        flow = config(path)
        assert flow["version"] == 1
        seen = set()
        for step in flow["steps"]:
            assert step["id"] not in seen, (path, step["id"])
            seen.add(step["id"])
            assert sum(kind in step for kind in (
                "flow", "prompt_file", "json_operation", "filesystem_operation"
            )) == 1, (path, step["id"])
            if "flow" in step:
                assert (ROOT / step["flow"]).is_file(), step
            if "prompt_file" in step:
                prompt = ROOT / step["prompt_file"]
                assert prompt.is_file(), (path, step["id"])
                placeholders = set(re.findall(
                    r"\{\{var:([A-Za-z_][A-Za-z0-9_]*)\}\}",
                    prompt.read_text(encoding="utf-8")
                ))
                assert placeholders <= (set(step.get("vars", {})) |
                                        set(step.get("json_inputs", {}))), (path, placeholders)
            if "json_operation" in step:
                kind = step["json_operation"]["kind"]
                assert kind == "batch"
                assert 1 <= step["json_operation"]["batch_size"] <= 5
                assert step["json_operation"]["max_batch_bytes"] <= 32000
            for data in step.get("json_inputs", {}).values():
                if "iterate" in data:
                    assert data["iterate"].startswith(("input.", "item."))
                    assert data["iterate"].endswith("[]")


def test_design_scales_by_document_and_section():
    root = config(BASE / "flow.toml")
    steps = {step["id"]: step for step in root["steps"]}
    assert steps["inventory"]["filesystem_operation"]["kind"] == "inventory"
    assert steps["inventory"]["filesystem_operation"]["stable_slugs"]
    assert steps["analyze_documents"]["foreach"] == "steps.inventory.output.files"
    assert steps["global_topics"]["input"]["document_results"] == (
        "${steps.analyze_documents.output.iterations}"
    )
    analyzer = config(BASE / "flows/analyze-document.toml")
    by_id = {step["id"]: step for step in analyzer["steps"]}
    sectioner = by_id["sections"]["filesystem_operation"]
    assert sectioner["kind"] == "markdown_sections"
    assert 25000 <= sectioner["target_chars"] <= 30000
    assert sectioner["max_sections"] <= 100
    assert by_id["section_topics"]["foreach"] == "steps.sections.output.sections"
    assert by_id["section_topics"]["overwrite_output"] is False
    assert analyzer["result_fallback"] == "steps.direct_topics.output"
    global_flow = config(BASE / "flows/global-topics.toml")
    global_steps = {step["id"]: step for step in global_flow["steps"]}
    assert global_steps["profile_batches"]["json_inputs"]["profiles"]["iterate"] == (
        "input.document_results[]"
    )
    assert global_steps["profile_batches"]["json_inputs"]["profiles"]["path"] == (
        "${each.output.profile_path}"
    )
    assert global_steps["registry"]["workspace_access"] == "none"


def fixture(tmp_path: Path):
    docs = tmp_path / "doctrines"
    docs.mkdir()
    files = {
        "a.md": "# Gateway\nA gateway validates bearer tokens before routing requests.\n",
        "b.md": "# Policy\nThe policy rejects requests missing authentication tokens.\n",
    }
    for name, value in files.items():
        (docs / name).write_text(value, encoding="utf-8")
    group = {
        "id": "g0001", "topic": "authentication", "relation": "constraint",
        "sources": [
            {"path": "doctrines/a.md", "start_line": 2, "end_line": 2,
             "claim": "The gateway validates bearer tokens"},
            {"path": "doctrines/b.md", "start_line": 2, "end_line": 2,
             "claim": "Missing tokens are rejected"}
        ]
    }
    draft = {
        "status": "ok", "group_id": "g0001",
        "question": "What does the gateway do with authentication tokens?",
        "expected_output": "The gateway validates tokens and rejects requests lacking them.",
        "category": "multi_document", "difficulty": "hard",
        "evidence": [
            {"path": "doctrines/a.md",
             "quote": "gateway validates bearer tokens",
             "start_line": 2, "end_line": 2, "supports": "validation"},
            {"path": "doctrines/b.md",
             "quote": "policy rejects requests missing authentication tokens",
             "start_line": 2, "end_line": 2, "supports": "rejection"}
        ],
        "necessity": {"without_first": "gateway behavior missing",
                      "without_second": "missing token rejection missing"}
    }
    review = {
        "status": "accepted", "group_id": "g0001", "reason": "Both sources required",
        "checks": {"grounded": True, "both_documents_necessary": True,
                   "unambiguous": True, "no_source_leakage": True}
    }
    return group, draft, review


def test_golden_validation_rejects_bad_quotes_and_unapproved_reviews(tmp_path):
    group, draft, review = fixture(tmp_path)
    assert make_golden(tmp_path, group, draft, review, {})
    incorrect = json.loads(json.dumps(draft))
    incorrect["evidence"][0]["quote"] = "invented substring"
    assert make_golden(tmp_path, group, incorrect, review, {}) is None
    incorrect = json.loads(json.dumps(draft))
    incorrect["evidence"][1]["path"] = "doctrines/a.md"
    assert make_golden(tmp_path, group, incorrect, review, {}) is None
    wrong_review = json.loads(json.dumps(review))
    wrong_review["checks"]["both_documents_necessary"] = False
    assert make_golden(tmp_path, group, draft, wrong_review, {}) is None


def test_export_two_source_goldens(tmp_path):
    group, draft, review = fixture(tmp_path)
    state = tmp_path / "rag-goldens/state"
    (state / "topics").mkdir(parents=True)
    (state / "topics/registry.json").write_text(
        json.dumps({"status": "ok", "groups": [group], "warnings": []}),
        encoding="utf-8"
    )
    (state / "draft-g0001.json").write_text(json.dumps(draft), encoding="utf-8")
    (state / "review-g0001.json").write_text(json.dumps(review), encoding="utf-8")
    result = export(tmp_path)
    assert result["accepted"] == 1
    exported = json.loads((tmp_path / "rag-goldens/goldens.json").read_text())
    assert len(exported[0]["sources"]) == 2
    assert all(len(source["sha256"]) == 64 for source in exported[0]["sources"])
    simple = json.loads((tmp_path / "rag-goldens/deepeval-goldens.json").read_text())
    assert simple[0]["input"] == draft["question"]
    assert len(simple[0]["context"]) == 2
    with pytest.raises(ValueError, match="Refusing symlink"):
        link = tmp_path / "doctrines/link.md"
        link.symlink_to(tmp_path / "doctrines/a.md")
        group["sources"][0]["path"] = "doctrines/link.md"
        draft["evidence"][0]["path"] = "doctrines/link.md"
        make_golden(tmp_path, group, draft, review, {})
