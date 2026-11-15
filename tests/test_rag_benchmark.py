"""Contract tests for interchangeable AgentWrapper-based Golden evaluation."""
from __future__ import annotations

import ast
import asyncio
import json
import sys
import types
from pathlib import Path

import pytest

BASE = Path(__file__).resolve().parents[1] / "flow/rag/generate_goldens"


def notebook_code():
    notebook = json.loads((BASE / "benchmark.ipynb").read_text(encoding="utf-8"))
    return [
        "".join(cell["source"])
        for cell in notebook["cells"]
        if cell["cell_type"] == "code"
    ]


def notebook_text():
    return "\n".join(notebook_code())


def wrapper_namespace():
    """Run only notebook configuration + wrapper definitions, not the judge."""
    env = {}
    exec(compile(notebook_code()[0], "<benchmark-config>", "exec"), env)
    cell = next(
        text for text in notebook_code()
        if "class AgentWrapper(Protocol):" in text
    )
    exec(compile(cell, "<benchmark-wrappers>", "exec"), env)
    return env


def test_notebook_syntax_and_unmodified_golden_reference():
    code = notebook_text()
    for cell in notebook_code():
        compile(cell, "<notebook>", "exec", flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)
    assert 'dataset.add_goldens_from_json_file(str(GOLDENS_FILE))' in code
    assert '"expected_output": golden.expected_output' in code
    assert "await invoke_agent(wrapper, golden.input)" in code
    assert "dataset.evals_iterator(" not in code
    assert "DeepEvalTarget" not in code
    assert "sys.path" not in code
    assert "from scripts" not in code
    assert "from deepeval import evaluate" in code
    assert "answer_results = evaluate(" in code
    assert "retrieval_results = evaluate(" in code


def test_exported_native_deepeval_goldens():
    export = (BASE / "scripts/export.py").read_text(encoding="utf-8")
    assert '"deepeval-goldens.json"' in export
    assert '"golden_id": g["id"]' in export
    assert '"input": g["input"]' in export
    assert '"expected_output": g["expected_output"]' in export
    assert '"context": [item["quote"]' not in export
    assert '"retrieval_context": [item["quote"]' not in export


def test_wrapper_protocol_and_factory_has_no_deepeval_dependency():
    code = notebook_text()
    assert "class AgentWrapper(Protocol):" in code
    assert "async def start(self) -> None:" in code
    assert "async def answer(self, question: str)" in code
    assert "async def close(self) -> None:" in code
    assert "def create_wrapper(spec) -> AgentWrapper:" in code
    assert "inspect.isclass(factory)" in code
    assert "wrapper = factory(**spec.get(" + '"kwargs", {})' + ")" in code
    assert "from cli_agent.sdk import AgentBuilder" in code
    assert 'if entrypoint == "builtin:cli-agent":' in code
    assert "class CliAgentWrapper:" in code
    assert "await self.agent.reset()" in code
    assert "builder.with_knowledge_trace(include_content=True).build()" in code
    assert "async def start(self)" in code
    assert "async def close(self)" in code
    assert 'target.ask(' not in code


def test_team_wrapper_lifecycle_and_question_only(monkeypatch):
    env = wrapper_namespace()
    calls = []
    package = types.ModuleType("team_b")
    package.__path__ = []
    module = types.ModuleType("team_b.adapter")

    class TeamWrapper:
        def __init__(self, *, model):
            self.model = model

        async def start(self):
            calls.append(("start", self.model))

        async def answer(self, question):
            calls.append(("answer", question))
            return {"answer": question.upper(), "retrieval_context": ["selected passage"]}

        async def close(self):
            calls.append(("close", self.model))

    module.TeamWrapper = TeamWrapper
    monkeypatch.setitem(sys.modules, "team_b", package)
    monkeypatch.setitem(sys.modules, "team_b.adapter", module)

    instance = env["create_wrapper"]({
        "entrypoint": "team_b.adapter:TeamWrapper",
        "kwargs": {"model": "model-x"},
    })

    async def run():
        await instance.start()
        answer = await env["invoke_agent"](instance, "Q1")
        await instance.close()
        return answer

    answer = asyncio.run(run())
    assert calls == [("start", "model-x"), ("answer", "Q1"), ("close", "model-x")]
    assert answer == {"actual_output": "Q1", "retrieval_context": ["selected passage"]}


def test_built_in_retrieval_validation():
    env = wrapper_namespace()
    trace = {
        "content_included": True, "truncated": False,
        "selected": [{"content": "Observed passage"}],
    }
    assert env["cli_agent_retrieval_context"](trace) == ["Observed passage"]
    assert env["cli_agent_retrieval_context"]({**trace, "truncated": True}) is None
    assert env["cli_agent_retrieval_context"]({**trace, "selected": [{"content": ""}]}) is None


def test_wrapper_validation_and_missing_methods(monkeypatch):
    env = wrapper_namespace()
    with pytest.raises(ValueError, match="entrypoint"):
        env["create_wrapper"]({"entrypoint": "bad-entrypoint"})
    with pytest.raises(ValueError, match="Invalid wrapper module"):
        env["create_wrapper"]({"entrypoint": "../file:Wrapper"})
    with pytest.raises(ValueError, match="Invalid wrapper class"):
        env["create_wrapper"]({"entrypoint": "valid.module:wrong-name"})
    with pytest.raises(ValueError, match="empty answer"):
        env["normalize_answer"](" ")
    with pytest.raises(TypeError, match="string or an answer mapping"):
        env["normalize_answer"](7)
    with pytest.raises(ValueError, match="retrieval_context"):
        env["normalize_answer"]({"answer": "ok", "retrieval_context": [""]})

    module = types.ModuleType("fake_wrapper")
    class MissingClose:
        async def start(self): pass
        async def answer(self, question): return "ok"
    module.MissingClose = MissingClose
    monkeypatch.setitem(sys.modules, "fake_wrapper", module)
    with pytest.raises(TypeError, match="missing close"):
        env["create_wrapper"]({"entrypoint": "fake_wrapper:MissingClose"})


def test_execution_loop_starts_once_closes_and_restarts_on_error():
    code = notebook_text()
    assert "wrapper = create_wrapper(spec)" in code
    assert "if wrapper is None:" in code
    assert "await asyncio.wait_for(started, timeout=TIMEOUT_SECONDS)" in code
    assert "response = await invoke_agent(wrapper, golden.input)" in code
    assert "await close_wrapper(wrapper)" in code
    assert "wrapper = None" in code
    assert "finally:" in code
    assert "all_failures[agent_id] = failures" in code
    assert "if cached is not None:" in code
    assert '"agent_failures": len(all_failures[agent_id])' in code


def test_caching_keys_and_private_checkpoint():
    code = notebook_text()
    assert '"kwargs": spec.get("kwargs", {})' in code
    assert 'spec["revision"]' in code
    assert '"epoch": CACHE_EPOCH' in code
    assert '"entrypoint": spec["entrypoint"]' in code
    assert 'golden.additional_metadata["golden_id"]' in code
    assert "FRESH_RESPONSES" in code
    assert 'os.chmod(temporary, 0o600)' in code
    assert 'os.replace(temporary, path)' in code


def test_evaluation_uses_actual_retrieval_context_and_counts_failures():
    code = notebook_text()
    assert 'retrieval_context=response["retrieval_context"]' in code
    assert '"answered": results["successful_cases"]' in code
    assert '"agent_failures": len(all_failures[agent_id])' in code
    assert 'metric.name.removesuffix(" [GEval]")' in code
    assert 'name="Answer correctness"' in code
    assert 'name="Uncertainty calibration"' in code


def test_deepeval_native_json_loader_if_available(tmp_path):
    deepeval = pytest.importorskip("deepeval.dataset")
    file = tmp_path / "deepeval-goldens.json"
    file.write_text(json.dumps([{
        "input": "Question", "expected_output": "Reference",
        "additional_metadata": {"golden_id": "g1", "required_sources": []},
    }]), encoding="utf-8")
    dataset = deepeval.EvaluationDataset()
    dataset.add_goldens_from_json_file(str(file))
    assert dataset.goldens[0].additional_metadata["golden_id"] == "g1"
