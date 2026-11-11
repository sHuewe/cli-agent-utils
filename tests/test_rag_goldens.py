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
from export import (
    make_golden, export, read_json, MAX_JSON_BYTES,
    MAX_REGISTRY_MANIFEST_BYTES, MAX_REGISTRY_BATCH_BYTES,
)  # noqa: E402


def config(path: Path) -> dict:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def test_flow_paths_and_prompt_variable_bindings():
    paths = [BASE / "flow.toml", *sorted((BASE / "flows").glob("*.toml"))]
    assert len(paths) >= 10
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
                # The flow validator rejects both missing and UNUSED
                # [steps.vars] entries; check the exact contract, not just
                # whether all placeholders happen to be defined.
                declared = set(step.get("vars", {}))
                assert declared == placeholders, (
                    path, step["id"], "missing", sorted(placeholders - declared),
                    "unused", sorted(declared - placeholders),
                )
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
    assert 8000 <= sectioner["target_chars"] <= 12000
    assert sectioner["max_sections"] <= 100
    assert by_id["section_topics"]["foreach"] == "steps.sections.output.sections"
    assert by_id["section_topics"]["overwrite_output"] is False
    assert analyzer["result"] == "steps.profile_inventory.output"
    assert "result_fallback" not in analyzer
    assert by_id["direct_topics"]["output"].endswith("/profiles/direct.json")
    assert by_id["profile_inventory"]["filesystem_operation"]["kind"] == "inventory"
    assert by_id["profile_inventory"]["filesystem_operation"]["recursive"] is False
    document_reduction = config(BASE / "flows/reduce-document.toml")
    assert document_reduction["result"] == "steps.reduce.output"
    assert not any(step["id"] == "profile" for step in document_reduction["steps"])
    reduced = document_reduction["steps"][-1]
    assert reduced["foreach"] == "steps.reduce_batches.output.batches"
    assert "/profiles/reduced-" in reduced["output"]
    assert reduced["overwrite_output"] is False
    global_flow = config(BASE / "flows/global-topics.toml")
    global_steps = {step["id"]: step for step in global_flow["steps"]}
    assert global_steps["profile_batches"]["json_inputs"]["profiles"]["iterate"] == (
        "input.document_results[].output.files[]"
    )
    assert global_steps["profile_batches"]["json_inputs"]["profiles"]["path"] == (
        "${each.path}"
    )
    assert "registry" not in global_steps
    assert global_steps["registry_batches"]["flow"].endswith("/batch-reduce2.toml")
    final = config(BASE / "flows/batch-reduce2.toml")["steps"][0]
    assert final["json_operation"] == {
        "kind": "batch", "input": "summaries",
        "batch_size": 3, "max_batch_bytes": 24000
    }
    assert final["json_inputs"]["summaries"]["iterate"] == "input.batches[]"
    shard = config(BASE / "flows/process-registry-batch.toml")
    assert shard["steps"][0]["workspace_access"] == "none"
    assert shard["steps"][0]["vars"]["batch"] == "${input.batch}"
    assert shard["steps"][1]["foreach"] == "steps.registry.output.groups"
    assert root["steps"][-1]["foreach"] == "steps.global_topics.output.batches"


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
        "id": "b0001-g0001", "topic": "authentication", "relation": "constraint",
        "sources": [
            {"path": "doctrines/a.md", "start_line": 2, "end_line": 2,
             "claim": "The gateway validates bearer tokens"},
            {"path": "doctrines/b.md", "start_line": 2, "end_line": 2,
             "claim": "Missing tokens are rejected"}
        ]
    }
    draft = {
        "status": "ok", "group_id": "b0001-g0001",
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
        "status": "accepted", "group_id": "b0001-g0001", "reason": "Both sources required",
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
    (state / "topics/registry-batches.json").write_text(
        json.dumps({"batches": [{"id": "b0001", "items": [
            {"status": "ok", "groups": [], "warnings": []}
        ]}]}),
        encoding="utf-8"
    )
    (state / "topics/registry-b0001.json").write_text(
        json.dumps({"status": "ok", "groups": [group], "warnings": []}),
        encoding="utf-8"
    )
    (state / "draft-b0001-g0001.json").write_text(json.dumps(draft), encoding="utf-8")
    (state / "review-b0001-g0001.json").write_text(json.dumps(review), encoding="utf-8")
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


def test_empty_registry_exports_empty_benchmark(tmp_path):
    root = tmp_path / "rag-goldens"
    state = root / "state/topics"
    state.mkdir(parents=True)
    (state / "registry-batches.json").write_text(
        json.dumps({"batches": [{"id": "b0001", "items": []}]}),
        encoding="utf-8"
    )
    (state / "registry-b0001.json").write_text(
        json.dumps({"status": "ok", "groups": [], "warnings": []}),
        encoding="utf-8"
    )
    # Stale output must be overwritten by legitimate zero-result export.
    (root / "goldens.json").write_text('[{"old": true}]', encoding="utf-8")
    assert export(tmp_path)["accepted"] == 0
    assert json.loads((root / "goldens.json").read_text()) == []
    assert json.loads((root / "deepeval-goldens.json").read_text()) == []
    # Equivalent user-provided output spellings must resolve consistently.
    assert export(tmp_path, "./rag-goldens")["total_groups"] == 0


def test_registry_shards_required_and_no_cross_shard_id_collision(tmp_path):
    root = tmp_path / "rag-goldens"
    state = root / "state/topics"
    state.mkdir(parents=True)
    (state / "registry-batches.json").write_text(
        json.dumps({"batches": [{"id": "b0001", "items": []},
                                 {"id": "b0002", "items": []}]}),
        encoding="utf-8"
    )
    (state / "registry-b0001.json").write_text(
        json.dumps({"status": "ok", "groups": [], "warnings": []}),
        encoding="utf-8"
    )
    with pytest.raises(FileNotFoundError):
        export(tmp_path)  # Missing shard must fail, not produce empty output.
    assert not (root / "goldens.json").exists()
    (state / "registry-b0002.json").write_text(
        json.dumps({"status": "needs_attention", "groups": [], "warnings": []}),
        encoding="utf-8"
    )
    stats = export(tmp_path)
    assert stats["registry_count"] == 2
    assert stats["registry_status"] == "needs_attention"


def test_no_unbounded_document_profile_prompt():
    # Regression: 96 section scans must never produce one LLM prompt containing
    # every reduced profile, even if source chunks were individually bounded.
    flow = config(BASE / "flows/reduce-document.toml")
    assert all(step["id"] != "profile" for step in flow["steps"])
    assert not any(
        "${steps.reduce.output.iterations}" in str(step.get("vars", {}))
        for step in flow["steps"]
    )
    # The global collector consumes per-document manifests as file paths and
    # batches actual JSON source files, not full aggregated foreach output.
    global_steps = config(BASE / "flows/global-topics.toml")["steps"]
    batches = next(step for step in global_steps if step["id"] == "profile_batches")
    assert batches["json_operation"]["max_batch_bytes"] <= 32000
    assert batches["json_inputs"]["profiles"]["iterate"] == (
        "input.document_results[].output.files[]"
    )
    assert batches["json_inputs"]["profiles"]["path"] == "${each.path}"


def test_empty_registry_preserves_upstream_needs_attention(tmp_path):
    root = tmp_path / "rag-goldens"
    state = root / "state/topics"
    state.mkdir(parents=True)
    (state / "registry-batches.json").write_text(
        json.dumps({"batches": [{"id": "b0001", "items": [
            {"status": "needs_attention", "groups": [],
             "warnings": ["Input reduced with incomplete coverage"]}
        ]}]}),
        encoding="utf-8",
    )
    # The final LLM loses the upstream status. The exporter must not.
    (state / "registry-b0001.json").write_text(
        json.dumps({"status": "ok", "groups": [], "warnings": []}),
        encoding="utf-8",
    )
    summary = export(tmp_path)
    assert summary["accepted"] == 0
    assert summary["registry_status"] == "needs_attention"
    assert summary["upstream_incomplete_batches"] == 1
    assert "incomplete coverage" in summary["upstream_warnings"][0]
    assert json.loads((root / "goldens.json").read_text()) == []
    assert json.loads((root / "deepeval-goldens.json").read_text()) == []


def test_upstream_status_remains_incomplete_with_valid_groups(tmp_path):
    group, draft, review = fixture(tmp_path)
    root = tmp_path / "rag-goldens"
    state = root / "state/topics"
    state.mkdir(parents=True)
    (state / "registry-batches.json").write_text(
        json.dumps({"batches": [{"id": "b0001", "items": [
            {"status": "needs_attention", "groups": [], "warnings": []}
        ]}]}),
        encoding="utf-8",
    )
    (state / "registry-b0001.json").write_text(
        json.dumps({"status": "ok", "groups": [group], "warnings": []}),
        encoding="utf-8",
    )
    (root / "state/draft-b0001-g0001.json").write_text(
        json.dumps(draft), encoding="utf-8",
    )
    (root / "state/review-b0001-g0001.json").write_text(
        json.dumps(review), encoding="utf-8",
    )
    result = export(tmp_path)
    assert result["accepted"] == 1
    assert result["registry_status"] == "needs_attention"
    assert result["upstream_incomplete_batches"] == 1


def test_invalid_upstream_status_fails_without_export(tmp_path):
    root = tmp_path / "rag-goldens"
    state = root / "state/topics"
    state.mkdir(parents=True)
    (state / "registry-batches.json").write_text(
        json.dumps({"batches": [{"id": "b0001", "items": [
            {"groups": [], "warnings": []}
        ]}]}),
        encoding="utf-8",
    )
    (state / "registry-b0001.json").write_text(
        json.dumps({"status": "ok", "groups": [], "warnings": []}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="upstream coverage status"):
        export(tmp_path)
    assert not (root / "goldens.json").exists()


def test_empty_registry_prompt_preserves_coverage_status():
    prompt = (BASE / "prompts/05_registry.md").read_text(encoding="utf-8")
    assert "groups=[]" in prompt
    assert "needs_attention" in prompt
    assert "batch.items[]" in prompt
    assert '"status":"ok","groups":[],"warnings":[]}' in prompt
    assert "when every input has status=ok" in prompt


def test_document_consolidation_preserves_upstream_coverage_contract():
    # Both stages share the same prompt: prevent any future revision from
    # turning incomplete scans into an apparently complete document profile.
    merge = config(BASE / "flows/consolidate-document.toml")["steps"]
    reduce = config(BASE / "flows/reduce-document.toml")["steps"]
    merge_step = next(s for s in merge if s["id"] == "merge_batches")
    reduce_step = next(s for s in reduce if s["id"] == "reduce")
    assert merge_step["prompt_file"] == reduce_step["prompt_file"]
    assert merge_step["vars"]["layer"] == "section"
    assert reduce_step["vars"]["layer"] == "final-document-shard"
    prompt = (ROOT / merge_step["prompt_file"]).read_text(encoding="utf-8")
    for required in (
        "batch.items[]",
        "If ANY upstream item has status=needs_attention",
        "even if the current merge succeeds",
        "topics list",
        "Preserve all unresolved upstream warnings",
        "Missing, malformed, or unknown upstream status/warnings",
        "Return status=ok ONLY when every upstream item has status=ok",
        "both",  # Both reduction levels use the same monotonic contract.
    ):
        assert required.casefold() in prompt.casefold()


def test_large_registry_manifest_keeps_per_batch_limits(tmp_path):
    # 200 legal 21-KB batches aggregate to >4 MB. Every individual batch
    # remains below the flow's 24 KB context budget.
    root = tmp_path / "rag-goldens"
    state = root / "state/topics"
    state.mkdir(parents=True)
    single = {"status": "ok", "groups": [], "warnings": [], "note": "x" * 7088}
    batches = []
    for i in range(1, 201):
        bid = f"b{i:04d}"
        batch = {"id": bid, "items": [single, single, single]}
        assert len(json.dumps(
            batch, ensure_ascii=False, separators=(",", ":"),
        ).encode("utf-8")) <= MAX_REGISTRY_BATCH_BYTES
        batches.append(batch)
        (state / f"registry-{bid}.json").write_text(
            json.dumps({"status": "ok", "groups": [], "warnings": []}),
            encoding="utf-8",
        )
    file = state / "registry-batches.json"
    file.write_text(json.dumps({"batches": batches}), encoding="utf-8")
    assert file.stat().st_size > MAX_JSON_BYTES
    assert file.stat().st_size < MAX_REGISTRY_MANIFEST_BYTES
    assert export(tmp_path) == {
        "accepted": 0, "total_groups": 0, "registry_count": 200,
        "registry_status": "ok", "upstream_incomplete_batches": 0,
        "upstream_warnings": [],
    }
    assert json.loads((root / "goldens.json").read_text()) == []
    assert json.loads((root / "deepeval-goldens.json").read_text()) == []
    # Ordinary individual JSON outputs retain their smaller size limit.
    with pytest.raises(ValueError, match="Missing/oversized JSON"):
        read_json(tmp_path, "rag-goldens/state/topics/registry-batches.json")


def test_manifest_and_individual_batch_still_bounded(tmp_path):
    root = tmp_path / "rag-goldens"
    state = root / "state/topics"
    state.mkdir(parents=True)
    manifest = state / "registry-batches.json"
    with manifest.open("wb") as stream:
        stream.truncate(MAX_REGISTRY_MANIFEST_BYTES + 1)
    with pytest.raises(ValueError, match="Missing/oversized JSON"):
        export(tmp_path)
    assert not (root / "goldens.json").exists()

    manifest.write_text(json.dumps({"batches": [{
        "id": "b0001",
        "items": [{"status": "ok", "groups": [], "warnings": [],
                   "note": "x" * MAX_REGISTRY_BATCH_BYTES}],
    }]}), encoding="utf-8")
    with pytest.raises(ValueError, match="Oversized registry input batch"):
        export(tmp_path)
    assert not (root / "goldens.json").exists()



def test_scan_prompt_is_bounded_and_preserves_coverage_signals():
    analyzer = config(BASE / "flows/analyze-document.toml")
    sections = next(s for s in analyzer["steps"] if s["id"] == "sections")
    prompt_path = next(s for s in analyzer["steps"] if s["id"] == "section_topics")["prompt_file"]
    prompt = (ROOT / prompt_path).read_text(encoding="utf-8")
    assert sections["filesystem_operation"]["target_chars"] == 12000
    assert "at most 12 distinct topics" in prompt
    assert "summary" in prompt and "<=180 characters" in prompt
    assert "status=needs_attention" in prompt
    assert "Do not invent claims or line numbers" in prompt
    assert "at most 12,000 characters" in prompt
    assert "consolidation" in prompt
