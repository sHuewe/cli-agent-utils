"""Contract tests for thin cli-agent/DeepEval adapter; no live model calls."""
from __future__ import annotations

import asyncio
import ast
from dataclasses import dataclass
import importlib.util
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
        "expected_output": "The gateway and policy reject the request.",
        "sources": [{"path": "doctrines/a.md"}, {"path": "doctrines/b.md"}],
    }


def test_goldens_loading_checks_identity_and_reference(tmp_path):
    path = tmp_path / "goldens.json"
    path.write_text(json.dumps([golden()]))
    assert adapter.load_goldens(path)[0]["id"] == "b0001-g0001"
    with pytest.raises(ValueError, match="positive"):
        adapter.load_goldens(path, 0)
    path.write_text(json.dumps([golden(), golden()]))
    with pytest.raises(ValueError, match="duplicate"):
        adapter.load_goldens(path)
    path.write_text(json.dumps([{"id": "x", "input": "Q"}]))
    with pytest.raises(ValueError, match="expected_output"):
        adapter.load_goldens(path)


class FakeAgent:
    def __init__(self, questions, trace=None):
        self.questions, self.trace = questions, trace

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def ask(self, question):
        self.questions.append(question)
        return types.SimpleNamespace(
            answer="The request is rejected.", knowledge_trace=self.trace
        )


def test_target_only_asks_question_and_reuses_answers(tmp_path):
    questions = []
    target_factory = lambda: adapter.CliAgentTarget(FakeAgent(questions))
    result = asyncio.run(adapter.collect_responses(
        [golden()], target_factory=target_factory,
        output=tmp_path, target_fingerprint="config-1",
    ))
    assert questions == [golden()["input"]]
    assert result[golden()["id"]]["actual_output"] == "The request is rejected."
    assert "expected_output" not in result[golden()["id"]]
    asyncio.run(adapter.collect_responses(
        [golden()], target_factory=target_factory,
        output=tmp_path, target_fingerprint="config-1",
    ))
    assert len(questions) == 1
    asyncio.run(adapter.collect_responses(
        [golden()], target_factory=target_factory,
        output=tmp_path, target_fingerprint="config-2",
    ))
    assert len(questions) == 2


def test_fresh_session_for_each_question(tmp_path):
    created, questions = [], []
    def target_factory():
        agent = FakeAgent(questions)
        created.append(agent)
        return adapter.CliAgentTarget(agent)
    asyncio.run(adapter.collect_responses(
        [golden("b0001-g0001"), golden("b0001-g0002")],
        target_factory=target_factory, output=tmp_path,
        target_fingerprint="cfg",
    ))
    assert len(created) == 2 and created[0] is not created[1]


@dataclass
class Trace:
    content_included: bool
    truncated: bool
    selected: list
    searches: list


def test_verified_context_only_and_source_recalls(tmp_path):
    trace = Trace(
        content_included=True, truncated=False,
        selected=[{"source": "doctrines/b.md", "content": "Observed passage"}],
        searches=[{"stage": "initial", "hits": [
            {"source": "doctrines/a.md"}]},
                 {"stage": "additional", "hits": [
                     {"source": "doctrines/b.md"}]}],
    )
    questions = []
    out = asyncio.run(adapter.CliAgentTarget(FakeAgent(questions, trace)).ask("Q"))
    assert adapter.selected_context(out) == ["Observed passage"]
    assert adapter.source_recall(golden(), out) == {
        "initial_recall": 0.5,
        "candidate_recall": 1.0,
        "selection_recall": 0.5,
    }
    out["knowledge_trace"]["truncated"] = True
    assert adapter.selected_context(out) is None
    assert adapter.source_recall(golden(), out) is None
    out["knowledge_trace"]["truncated"] = False
    out["knowledge_trace"]["selected"] = [{"source": "doctrines/b.md"}]
    assert adapter.selected_context(out) is None


def test_native_dataset_uses_only_actual_selected_chunks(monkeypatch):
    class FakeLLMTestCase:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class FakeDataset:
        # Mirror the public DeepEval 4.x contract: no test_cases constructor arg.
        def __init__(self, goldens=None, confident_api_key=None):
            self.test_cases = []

        def add_test_case(self, test_case):
            self.test_cases.append(test_case)

    fake_deepeval = types.ModuleType("deepeval")
    dataset_module = types.ModuleType("deepeval.dataset")
    dataset_module.EvaluationDataset = FakeDataset
    testcase_module = types.ModuleType("deepeval.test_case")
    testcase_module.LLMTestCase = FakeLLMTestCase
    monkeypatch.setitem(sys.modules, "deepeval", fake_deepeval)
    monkeypatch.setitem(sys.modules, "deepeval.dataset", dataset_module)
    monkeypatch.setitem(sys.modules, "deepeval.test_case", testcase_module)
    data = adapter.deep_eval_cases(
        [golden()], {golden()["id"]: {
            "actual_output": "Answer",
            "knowledge_trace": {
                "content_included": True, "truncated": False,
                "selected": [{"content": "Only actual retrieved text"}],
            },
        }}
    )
    case = data.test_cases[0]
    assert case.input == golden()["input"]
    assert case.expected_output == golden()["expected_output"]
    assert case.retrieval_context == ["Only actual retrieved text"]
    assert not hasattr(case, "context")


def test_independent_judge_provider_model(monkeypatch):
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
    with pytest.raises(ValueError, match="JUDGE_PROVIDER"):
        adapter.judge_model("other", "model")


def test_notebook_uses_native_deepeval_not_custom_evaluation():
    notebook = json.loads((BASE / "benchmark.ipynb").read_text(encoding="utf-8"))
    code = "\n".join(
        "".join(cell["source"])
        for cell in notebook["cells"] if cell["cell_type"] == "code"
    )
    assert "EvaluationDataset" not in code or "deep_eval_cases" in code
    assert "from deepeval import evaluate" in code
    assert "judge_model(JUDGE_PROVIDER, JUDGE_MODEL" in code
    assert "CacheConfig(" in code
    assert "metric.measure(" not in code
    assert "evaluate_cases(" not in code
    assert "answer_results = evaluate(" in code
    assert "test_cases=dataset.test_cases" in code
    assert "test_cases=dataset," not in code
    assert "retrieval_results = evaluate(" in code
    for cell in notebook["cells"]:
        if cell["cell_type"] == "code":
            compile("".join(cell["source"]), "<notebook-cell>", "exec",
                    flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)


def test_metric_judge_is_forwarded_to_every_metric(monkeypatch):
    class Metric:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
    metrics_mod = types.ModuleType("deepeval.metrics")
    for name in ("GEval", "AnswerRelevancyMetric", "FaithfulnessMetric",
                 "ContextualRecallMetric", "ContextualPrecisionMetric"):
        setattr(metrics_mod, name, Metric)
    test_mod = types.ModuleType("deepeval.test_case")
    test_mod.SingleTurnParams = types.SimpleNamespace(
        INPUT="input", ACTUAL_OUTPUT="actual_output",
        EXPECTED_OUTPUT="expected_output",
    )
    monkeypatch.setitem(sys.modules, "deepeval.metrics", metrics_mod)
    monkeypatch.setitem(sys.modules, "deepeval.test_case", test_mod)
    judge = object()
    result = adapter.benchmark_metrics(judge, 0.6, retrieval=True)
    assert len(result) == 5
    assert all(metric.kwargs["model"] is judge for metric in result)
    assert all(metric.kwargs["threshold"] == 0.6 for metric in result)



def test_evaluate_cell_passes_list_not_dataset():
    """Replay notebook's native evaluation with DeepEval's list-only contract."""
    notebook = json.loads((BASE / "benchmark.ipynb").read_text(encoding="utf-8"))
    cell = next(
        "".join(item["source"])
        for item in notebook["cells"]
        if item["cell_type"] == "code"
        and "answer_results = evaluate(" in "".join(item["source"])
    )
    seen = []

    class FakeCases:
        test_cases = [object(), object()]

    class FakeConfig:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    def fake_evaluate(*, test_cases, metrics, **kwargs):
        assert isinstance(test_cases, list), "DeepEval expects a list of cases"
        seen.append(test_cases)
        return {"ok": True}

    deepeval_mod = types.ModuleType("deepeval")
    deepeval_mod.evaluate = fake_evaluate
    eval_mod = types.ModuleType("deepeval.evaluate")
    eval_mod.AsyncConfig = FakeConfig
    eval_mod.CacheConfig = FakeConfig
    eval_mod.DisplayConfig = FakeConfig
    old_deepeval = sys.modules.get("deepeval")
    old_eval = sys.modules.get("deepeval.evaluate")
    try:
        sys.modules["deepeval"] = deepeval_mod
        sys.modules["deepeval.evaluate"] = eval_mod
        env = {
            "dataset": FakeCases(),
            "judge": object(),
            "benchmark_metrics": lambda *args, **kwargs: [object(), object(), object()],
            "THRESHOLD": 0.7,
            "FRESH_EVALUATION": False,
            "JUDGE_MAX_CONCURRENT": 2,
            "OUTPUT_DIR": ROOT,
            "target_sha": "target",
            "JUDGE_PROVIDER": "openrouter",
            "JUDGE_MODEL": "test-model",
        }
        exec(compile(cell, "<benchmark evaluate cell>", "exec"), env)
    finally:
        if old_deepeval is None:
            sys.modules.pop("deepeval", None)
        else:
            sys.modules["deepeval"] = old_deepeval
        if old_eval is None:
            sys.modules.pop("deepeval.evaluate", None)
        else:
            sys.modules["deepeval.evaluate"] = old_eval
    assert len(seen) == 1
    assert seen[0] == env["dataset"].test_cases
