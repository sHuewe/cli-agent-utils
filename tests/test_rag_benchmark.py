"""Shared-Golden multi-agent benchmark integration contracts.

Agent adapters only accept question text. DeepEval is used exclusively to
judge saved responses; other teams do not need to depend on cli-agent.
"""
from __future__ import annotations

import ast
import asyncio
import json
import sys
import types
from pathlib import Path

import pytest

BASE = Path(__file__).resolve().parents[1] / "flow/rag/generate_goldens"


def cells():
    return json.loads((BASE / "benchmark.ipynb").read_text(encoding="utf-8"))["cells"]


def code_cells():
    return ["".join(c["source"]) for c in cells() if c["cell_type"] == "code"]


def code():
    return "\n".join(code_cells())


def adapter_namespace():
    """Execute notebook's safe configuration and adapter definitions only."""
    ns = {}
    exec(compile(code_cells()[0], "<config>", "exec"), ns)
    definitions = next(s for s in code_cells() if "def create_agent(spec):" in s)
    exec(compile(definitions, "<adapter>", "exec"), ns)
    return ns


def test_notebook_is_native_deepeval_but_agents_are_independent():
    full = code()
    assert 'dataset.add_goldens_from_json_file(str(GOLDENS_FILE))' in full
    assert 'from deepeval import evaluate' in full
    assert "dataset.evals_iterator(" not in full
    assert "DeepEvalTarget" not in full
    assert "builder.build_deepeval_target(" not in full
    assert "from scripts" not in full
    assert "sys.path" not in full
    assert "from cli_agent" not in code_cells()[0]
    assert "def create_agent(spec):" in full
    assert "answer_fn = create_agent(spec)" in full
    assert "await invoke_agent(answer_fn, golden.input)" in full
    assert 'expected_output=golden.expected_output' not in full
    assert '"expected_output": golden.expected_output' in full
    for source in code_cells():
        compile(source, "<notebook-cell>", "exec",
                flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)


def test_exported_goldens_use_deepeval_native_input_and_expected_output():
    export = (BASE / "scripts/export.py").read_text(encoding="utf-8")
    assert '"deepeval-goldens.json"' in export
    assert '"golden_id": g["id"]' in export
    assert '"input": g["input"]' in export
    assert '"expected_output": g["expected_output"]' in export
    assert '"context": [item["quote"]' not in export
    assert '"retrieval_context": [item["quote"]' not in export


def test_adapter_accepts_external_sync_and_async_modules(monkeypatch):
    namespace = adapter_namespace()
    seen = []
    package = types.ModuleType("example_team")
    package.__path__ = []
    mod = types.ModuleType("example_team.adapter")

    def sync_answer(question):
        seen.append(("sync", question))
        return "Synchronous answer"

    async def async_answer(question):
        seen.append(("async", question))
        return {"answer": "Asynchronous answer", "retrieval_context": ["actual passage"]}

    mod.sync_answer = sync_answer
    mod.async_answer = async_answer
    monkeypatch.setitem(sys.modules, "example_team", package)
    monkeypatch.setitem(sys.modules, "example_team.adapter", mod)

    sync_fn = namespace["create_agent"]({"entrypoint": "example_team.adapter:sync_answer"})
    async_fn = namespace["create_agent"]({"entrypoint": "example_team.adapter:async_answer"})
    sync_response = asyncio.run(namespace["invoke_agent"](sync_fn, "Q1"))
    async_response = asyncio.run(namespace["invoke_agent"](async_fn, "Q2"))
    assert sync_response == {"actual_output": "Synchronous answer", "retrieval_context": None}
    assert async_response == {"actual_output": "Asynchronous answer",
                              "retrieval_context": ["actual passage"]}
    assert seen == [("sync", "Q1"), ("async", "Q2")]
    # No expected_output is passed to either answering function.


def test_adapter_output_validation_and_entrypoint_guard():
    ns = adapter_namespace()
    with pytest.raises(ValueError, match="entrypoint"):
        ns["create_agent"]({"entrypoint": "not-a-module"})
    with pytest.raises(ValueError, match="Invalid agent module"):
        ns["create_agent"]({"entrypoint": "../file:answer"})
    with pytest.raises(ValueError, match="empty answer"):
        ns["normalize_answer"]("   ")
    with pytest.raises(ValueError, match="retrieval_context"):
        ns["normalize_answer"]({"answer": "ok", "retrieval_context": [""]})
    with pytest.raises(TypeError, match="string or an answer mapping"):
        ns["normalize_answer"](4)
    assert ns["normalize_answer"]({"answer": "valid"}) == {
        "actual_output": "valid", "retrieval_context": None,
    }


def test_optional_sdk_retrieval_only_verified_complete_text():
    ns = adapter_namespace()
    acceptable = {"content_included": True, "truncated": False,
                  "selected": [{"content": "actual retrieved passage"}]}
    assert ns["cli_agent_retrieval_context"](acceptable) == ["actual retrieved passage"]
    assert ns["cli_agent_retrieval_context"]({**acceptable, "truncated": True}) is None
    assert ns["cli_agent_retrieval_context"]({**acceptable, "selected": [{"content": None}]}) is None
    assert ns["cli_agent_retrieval_context"]({**acceptable, "content_included": False}) is None


def test_deepeval_scores_same_reference_and_reports_agent_failures():
    source = code()
    assert "for golden in dataset.goldens:" in source
    assert "all_failures[agent_id] = failures" in source
    assert 'response = responses.get(golden.additional_metadata["golden_id"])' in source
    assert "if response is None:" in source
    assert '"agent_failures": len(all_failures[agent_id])' in source
    assert '"answered": results["successful_cases"]' in source
    assert '"expected_output": golden.expected_output' in source
    assert 'retrieval_context=response["retrieval_context"]' in source
    assert 'name="Answer correctness"' in source
    assert 'name="Uncertainty calibration"' in source
    assert 'metric.name.removesuffix(" [GEval]")' in source
    assert "answer_results = evaluate(" in source
    assert "retrieval_results = evaluate(" in source


def test_response_cache_is_private_unique_and_invalidates_on_revision():
    source = code()
    assert 'spec["revision"]' in source
    assert '"epoch": CACHE_EPOCH' in source
    assert '"entrypoint": spec["entrypoint"]' in source
    assert 'golden.additional_metadata["golden_id"]' in source
    assert "FRESH_RESPONSES" in source
    assert 'os.chmod(temporary, 0o600)' in source
    assert "os.replace(temporary, path)" in source
    assert "tempfile.NamedTemporaryFile(" in source
    assert "default_admin_config_file" in source


def test_native_deepeval_json_loader_when_installed(tmp_path):
    dataset_mod = pytest.importorskip("deepeval.dataset")
    path = tmp_path / "deepeval-goldens.json"
    sample = [{"input": "Q", "expected_output": "A",
               "additional_metadata": {"golden_id": "g1", "required_sources": []}}]
    path.write_text(json.dumps(sample), encoding="utf-8")
    ds = dataset_mod.EvaluationDataset()
    ds.add_goldens_from_json_file(str(path))
    assert ds.goldens[0].input == "Q"
    assert ds.goldens[0].expected_output == "A"
    assert ds.goldens[0].additional_metadata["golden_id"] == "g1"
