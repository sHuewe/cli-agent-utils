"""Tests for native DeepEval iterator orchestration and the small benchmark glue.

No live LLM calls or DeepEval installation required for repository CI.
The mocks intentionally follow DeepEval's public Golden/Dataset contracts.
"""
from __future__ import annotations

import ast
import asyncio
import json
from pathlib import Path
import sys
import types

import pytest

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "flow/rag/generate_goldens"
sys.path.insert(0, str(BASE / "scripts"))
import benchmark_adapter as adapter  # noqa: E402


def golden(gid="b0001-g0001"):
    return {
        "id": gid, "input": "What happens with a missing token?",
        "expected_output": "The gateway rejects missing tokens.",
        "sources": [{"path": "doctrines/a.md"}, {"path": "doctrines/b.md"}],
    }


def test_load_goldens_validates_ids_and_reference(tmp_path):
    path = tmp_path / "goldens.json"
    path.write_text(json.dumps([golden()]), encoding="utf-8")
    assert adapter.load_goldens(path)[0]["id"] == "b0001-g0001"
    with pytest.raises(ValueError, match="positive"):
        adapter.load_goldens(path, 0)
    path.write_text(json.dumps([golden(), golden()]), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        adapter.load_goldens(path)
    path.write_text(json.dumps([{"id": "x", "input": "Q"}]), encoding="utf-8")
    with pytest.raises(ValueError, match="expected_output"):
        adapter.load_goldens(path)


def test_native_deepeval_goldens_are_not_precomputed_cases(monkeypatch):
    class FakeGolden:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class FakeDataset:
        def __init__(self, goldens=None, confident_api_key=None):
            assert isinstance(goldens, list)
            assert confident_api_key is None
            self.goldens = goldens

    module = types.ModuleType("deepeval.dataset")
    module.Golden = FakeGolden
    module.EvaluationDataset = FakeDataset
    monkeypatch.setitem(sys.modules, "deepeval.dataset", module)

    dataset = adapter.deep_eval_dataset([golden()])
    assert len(dataset.goldens) == 1
    item = dataset.goldens[0]
    assert item.input == golden()["input"]
    assert item.expected_output == golden()["expected_output"]
    assert item.additional_metadata == {"golden_id": golden()["id"]}
    assert not hasattr(item, "actual_output")


def test_answer_checkpoint_replay_and_target_fingerprint(tmp_path):
    g = golden()
    assert adapter.cached_response(g, output=tmp_path,
                                   target_fingerprint="config-A") is None
    response = {"actual_output": "Answer",
                "knowledge_trace": {
                    "selected": [{"content": "Observed", "source": "doctrines/a.md"}],
                    "truncated": False, "content_included": True,
                }}
    adapter.save_response(g, response, output=tmp_path, target_fingerprint="config-A")
    assert adapter.cached_response(g, output=tmp_path,
                                   target_fingerprint="config-A") == response
    assert adapter.cached_response(g, output=tmp_path,
                                   target_fingerprint="config-B") is None
    assert adapter.cached_response(g, output=tmp_path,
                                   target_fingerprint="config-A", fresh=True) is None
    changed = {**g, "expected_output": "Different reference"}
    assert adapter.cached_response(changed, output=tmp_path,
                                   target_fingerprint="config-A") is None


def test_retrieval_context_is_only_observed_selected_text():
    response = {"actual_output": "Answer",
                "knowledge_trace": {
                    "selected": [{"source": "doctrines/a.md",
                                  "content": "Observed actual passage"}],
                    "content_included": True, "truncated": False,
                    "searches": [{"stage": "initial", "hits": [
                        {"source": "doctrines/a.md"}]},
                        {"stage": "followup", "hits": [
                            {"source": "doctrines/b.md"}]}],
                }}
    assert adapter.selected_context(response) == ["Observed actual passage"]
    assert adapter.source_recall(golden(), response) == {
        "initial_recall": 0.5,
        "candidate_recall": 1.0,
        "selection_recall": 0.5,
    }
    response["knowledge_trace"]["truncated"] = True
    assert adapter.selected_context(response) is None
    assert adapter.source_recall(golden(), response) is None
    response["knowledge_trace"]["truncated"] = False
    response["knowledge_trace"]["selected"][0].pop("content")
    assert adapter.selected_context(response) is None


def test_live_sdk_tuple_trace_preserves_retrieval_coverage():
    """asdict(KnowledgeTrace) preserves tuples on the first, uncached run."""
    response = {
        "actual_output": "Answer",
        "knowledge_trace": {
            "selected": ({"source": "doctrines/b.md",
                          "content": "Verified selected content"},),
            "content_included": True,
            "truncated": False,
            "searches": (
                {"stage": "initial", "hits": ({"source": "doctrines/a.md"},)},
                {"stage": "additional", "hits": ({"source": "doctrines/b.md"},)},
            ),
        },
    }
    assert adapter.selected_context(response) == ["Verified selected content"]
    assert adapter.source_recall(golden(), response) == {
        "initial_recall": 0.5,
        "candidate_recall": 1.0,
        "selection_recall": 0.5,
    }


def test_retrieval_test_cases_never_use_golden_quotes(monkeypatch):
    class FakeCase:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    module = types.ModuleType("deepeval.test_case")
    module.LLMTestCase = FakeCase
    monkeypatch.setitem(sys.modules, "deepeval.test_case", module)

    response = {
        "actual_output": "Actual",
        "knowledge_trace": {
            "selected": [{"content": "Observed Knowledge text"}],
            "content_included": True, "truncated": False,
        },
    }
    cases = adapter.retrieval_test_cases([golden()], {golden()["id"]: response})
    assert len(cases) == 1
    assert cases[0].input == golden()["input"]
    assert cases[0].expected_output == golden()["expected_output"]
    assert cases[0].retrieval_context == ["Observed Knowledge text"]


def test_judge_is_independent_provider_and_model(monkeypatch):
    seen = []
    class FakeJudge:
        def __init__(self, **kwargs):
            seen.append(kwargs)
    models = types.ModuleType("deepeval.models")
    models.OpenAIModel = FakeJudge
    models.OpenRouterModel = FakeJudge
    models.OllamaModel = FakeJudge
    monkeypatch.setitem(sys.modules, "deepeval.models", models)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    adapter.judge_model("openrouter", "openai/gpt-4.1")
    assert seen[-1]["model"] == "openai/gpt-4.1"
    assert seen[-1]["api_key"] == "test-key"
    adapter.judge_model("ollama", "qwen3:8b", "http://localhost:11434")
    assert seen[-1]["base_url"] == "http://localhost:11434"
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        adapter.judge_model("openai", "gpt-4.1")


def test_notebook_uses_native_iterator_and_sdk_observed_target():
    notebook = json.loads((BASE / "benchmark.ipynb").read_text(encoding="utf-8"))
    source = "\n".join(
        "".join(cell["source"]) for cell in notebook["cells"]
        if cell["cell_type"] == "code"
    )
    assert "builder.build_deepeval_target(" in source
    assert "dataset.evals_iterator(" in source
    assert "await target.ask(" in source
    assert "target.ask(" in source[source.index("for golden in dataset.evals_iterator("):]
    assert "async with asyncio.timeout(" in source
    assert "await asyncio.wait_for(" not in source
    assert "collect_responses(" not in source
    assert "sdk_target_factory(" not in source
    assert "cached_response=" in source
    assert "judge_model(JUDGE_PROVIDER, JUDGE_MODEL" in source
    assert "metrics=benchmark_metrics(judge" in source
    for cell in notebook["cells"]:
        if cell["cell_type"] == "code":
            compile("".join(cell["source"]), "<notebook-cell>", "exec",
                    flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)


def test_native_iterator_wraps_ask_and_receives_expected_output(monkeypatch):
    """Actually execute notebook's iterator cell under a compatible fake API."""
    notebook = json.loads((BASE / "benchmark.ipynb").read_text(encoding="utf-8"))
    cell = next(
        "".join(item["source"]) for item in notebook["cells"]
        if item["cell_type"] == "code"
        and "for golden in dataset.evals_iterator(" in "".join(item["source"])
    )
    logs = []
    active = {"observing": False}

    class FakeGolden:
        input = "What happens?"
        expected_output = "Reject"
        additional_metadata = {"golden_id": "b0001-g0001"}

    class FakeDataset:
        def evals_iterator(self, **kwargs):
            logs.append(("iterator", kwargs["identifier"]))
            for item in [FakeGolden()]:
                active["observing"] = True
                yield item
                active["observing"] = False
                logs.append(("evaluated", item.input))

    class FakeTarget:
        async def ask(self, question, *, expected_output, cached_response):
            assert active["observing"]
            logs.append(("ask", question, expected_output, cached_response))
            return {"actual_output": "Reject", "knowledge_trace": None}

    class FakeConfig:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    mod = types.ModuleType("deepeval.evaluate")
    mod.AsyncConfig = FakeConfig
    mod.CacheConfig = FakeConfig
    mod.DisplayConfig = FakeConfig
    monkeypatch.setitem(sys.modules, "deepeval.evaluate", mod)

    env = {
        "dataset": FakeDataset(), "by_id": {"b0001-g0001": golden()},
        "target": FakeTarget(), "judge": object(), "THRESHOLD": 0.7,
        "benchmark_metrics": lambda *a, **kw: [object()],
        "OUTPUT_DIR": ROOT, "target_sha": "config-A",
        "FRESH_EVALUATION": False, "FRESH_SDK": False,
        "SDK_TIMEOUT_SECONDS": 5.0,
        "cached_response": lambda *a, **kw: None,
        "save_response": lambda *a, **kw: logs.append(("saved",)),
        "asyncio": asyncio,
    }
    compiled = compile(cell, "<benchmark iterator>", "exec",
                       flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)

    async def run():
        await eval(compiled, env)

    asyncio.run(run())
    assert logs[0] == ("iterator", "rag-answer-quality")
    assert logs[1] == ("ask", "What happens?", "Reject", None)
    assert logs[2] == ("saved",)
    assert logs[3] == ("evaluated", "What happens?")
    assert env["responses"]["b0001-g0001"]["actual_output"] == "Reject"
