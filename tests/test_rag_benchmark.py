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
    # Notebook must be fully generic; SDK integration lives in sibling file.
    assert "from cli_agent" not in code
    assert "CliAgentWrapper" not in next(
        cell for cell in notebook_code() if "def create_wrapper(spec)" in cell
    )
    assert 'if entrypoint == "builtin:cli-agent":' not in code
    assert "wrapper_class = getattr(importlib.import_module(module_name), class_name)" in code
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
    assert answer == {
        "actual_output": "Q1", "retrieval_context": ["selected passage"],
        "tools_called": None,
    }


def test_built_in_retrieval_validation():
    from flow.rag.generate_goldens.cli_agent_wrapper import selected_knowledge_passages
    trace = {
        "content_included": True, "truncated": False,
        "selected": [{"content": "Observed passage"}],
    }
    assert selected_knowledge_passages(trace) == ["Observed passage"]
    assert selected_knowledge_passages({**trace, "truncated": True}) is None
    assert selected_knowledge_passages({**trace, "selected": [{"content": ""}]}) is None


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
    assert env["normalize_answer"]({"answer": "ok", "retrieval_context": []}) == {
        "actual_output": "ok",
        "retrieval_context": None,
        "tools_called": None,
    }
    assert env["normalize_answer"]({"answer": "ok", "retrieval_context": None}) == {
        "actual_output": "ok",
        "retrieval_context": None,
        "tools_called": None,
    }

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



def test_optional_tool_calls_normalization_and_redacted_sdk_mapping():
    env = wrapper_namespace()
    normalized = env["normalize_answer"]({
        "answer": "The gateway rejects the request.",
        "retrieval_context": [],
        "tools_called": [
            {
                "name": "search",
                "input_parameters": {"query": "auth"},
                "call_id": "run123",
                "status": "finished",
                "duration_ms": 12.5,
            },
            {"name": "fetch"},
        ],
    })
    assert normalized == {
        "actual_output": "The gateway rejects the request.",
        "retrieval_context": None,
        "tools_called": [
            {"name": "search", "input_parameters": {"query": "auth"},
             "call_id": "run123", "status": "finished", "duration_ms": 12.5},
            {"name": "fetch"},
        ],
    }
    assert env["normalize_answer"]({"answer": "fine", "tools_called": []}) == {
        "actual_output": "fine", "retrieval_context": None, "tools_called": [],
    }
    for bad in (
        {"tools_called": ["search"]},
        {"tools_called": [{"name": ""}]},
        {"tools_called": [{"name": "search", "input_parameters": "secret"}]},
        {"tools_called": [{"name": "search", "duration_ms": -2}]},
        {"tools_called": [{"name": "search", "duration_ms": float("nan")}]},
        {"tools_called": [{"name": "search", "input_parameters": {"x": object()}}]},
        {"tools_called": [{"name": "search", "arguments_truncated": "yes"}]},
    ):
        with pytest.raises(ValueError, match="tools_called|input_parameters"):
            env["normalize_answer"]({"answer": "fine", **bad})
    full = notebook_text()
    from flow.rag.generate_goldens import cli_agent_wrapper
    wrapper_source = Path(cli_agent_wrapper.__file__).read_text(encoding="utf-8")
    assert '"tools_called": [' in wrapper_source
    assert 'for call in result.tool_calls' in wrapper_source
    assert 'call.call_id' in wrapper_source and 'call.duration_ms' in wrapper_source
    assert 'call.status' in wrapper_source
    assert 'if call.input_parameters is not None else {}' in wrapper_source
    assert '"arguments_truncated": call.arguments_truncated' in wrapper_source


def test_tool_correctness_runs_only_for_goldens_with_expected_tools():
    full = notebook_text()
    assert "ToolCorrectnessMetric(" in full
    assert "ToolCall(" in full
    assert "golden.expected_tools is not None" in full
    assert 'response["tools_called"] is not None' in full
    assert "if tool_cases:" in full
    assert 'identifier=f"rag-{agent_id}-tools"' in full
    assert 'results["tool_cases"]' in full
    assert '"tool_telemetry_cases"' in full
    assert '"total_tool_calls"' in full
    assert '"tool_error_calls"' in full
    assert '"tool_calls_with_arguments"' in full



def test_cli_agent_wrapper_importable_through_same_generic_factory():
    """No special entrypoint, no SDK dependency during import."""
    env = wrapper_namespace()
    spec = {
        "entrypoint": "flow.rag.generate_goldens.cli_agent_wrapper:CliAgentWrapper",
        "kwargs": {
            "workspace": ".", "system_prompt": "Be accurate",
            "include_tool_arguments": False,
        },
    }
    wrapper = env["create_wrapper"](spec)
    assert type(wrapper).__name__ == "CliAgentWrapper"
    assert wrapper.system_prompt == "Be accurate"
    assert wrapper.include_tool_arguments is False
    assert wrapper.agent is None
    for name in ("start", "answer", "close"):
        assert callable(getattr(wrapper, name))


def test_cli_agent_wrapper_lifecycle_and_trace_passthrough(monkeypatch, tmp_path):
    """Exercise real wrapper with SDK stub: one initialization, two resets."""
    import importlib
    from types import SimpleNamespace

    calls = []

    class FakeAgent:
        async def start(self):
            calls.append("start")

        async def reset(self):
            calls.append("reset")

        async def ask(self, question):
            calls.append(("ask", question))
            return SimpleNamespace(
                answer="reply to " + question,
                knowledge_trace={
                    "content_included": True, "truncated": False,
                    "selected": [{"content": "retrieved text"}],
                },
                tool_calls=[
                    SimpleNamespace(
                        name="knowledge__search", call_id=question,
                        status="success", duration_ms=25.0,
                        input_parameters={"query": question},
                        arguments_truncated=False,
                    )
                ],
            )

        async def close(self):
            calls.append("close")

    class FakeBuilder:
        def with_admin_config(self, **kwargs):
            calls.append(("admin_config", kwargs))
            return self

        def with_project_config(self, **kwargs):
            calls.append(("project_config", kwargs))
            return self

        def with_system_prompt(self, prompt):
            calls.append(("system_prompt", prompt))
            return self

        def with_knowledge_trace(self, **kwargs):
            calls.append(("knowledge_trace", kwargs))
            return self

        def with_tool_trace(self, **kwargs):
            calls.append(("tool_trace", kwargs))
            return self

        def build(self):
            calls.append("build")
            return FakeAgent()

    # The module itself contains no CLI imports at module import time.
    sdk_module = types.ModuleType("cli_agent.sdk")
    sdk_module.AgentBuilder = FakeBuilder
    config_module = types.ModuleType("cli_agent.settings.config")
    config_module.ensure_default_config_file = lambda: tmp_path / "config.toml"
    monkeypatch.setitem(sys.modules, "cli_agent.sdk", sdk_module)
    monkeypatch.setitem(sys.modules, "cli_agent.settings.config", config_module)

    module = importlib.import_module("flow.rag.generate_goldens.cli_agent_wrapper")
    wrapper = module.CliAgentWrapper(
        workspace=str(tmp_path), include_tool_arguments=True,
        redact_keys=["private_info"], approve_tools=["knowledge__search"],
        system_prompt="Be accurate",
    )

    async def scenario():
        await wrapper.start()
        first = await wrapper.answer("q1")
        second = await wrapper.answer("q2")
        await wrapper.close()
        await wrapper.close()
        return first, second

    first, second = asyncio.run(scenario())
    assert first["answer"] == "reply to q1"
    assert first["retrieval_context"] == ["retrieved text"]
    assert first["tools_called"] == [{
        "name": "knowledge__search", "call_id": "q1",
        "status": "success", "duration_ms": 25.0,
        "input_parameters": {"query": "q1"}, "arguments_truncated": False,
    }]
    assert second["tools_called"][0]["call_id"] == "q2"
    assert calls.count("start") == 1 and calls.count("close") == 1
    assert calls.count("reset") == 2
    assert [v for v in calls if isinstance(v, tuple) and v[0] == "system_prompt"] == [
        ("system_prompt", "Be accurate")
    ]
    assert [v for v in calls if isinstance(v, tuple) and v[0] == "tool_trace"] == [
        ("tool_trace", {
            "include_arguments": True, "redact_keys": ("private_info",),
        })
    ]


def test_generic_agent_config_cache_files_validation(tmp_path):
    """A config file influences the cache key for any agent module."""
    ns = {}
    exec(compile(notebook_code()[0], "<benchmark-config>", "exec"), ns)
    ns["WORKSPACE"] = tmp_path
    cache_code = next(cell for cell in notebook_code()
                      if "def agent_fingerprint(" in cell)
    # Avoid executing the notebook's evaluation loop; extract one function.
    import ast
    nodes = ast.parse(cache_code)
    fn = next(node for node in nodes.body
              if isinstance(node, ast.FunctionDef) and node.name == "agent_fingerprint")
    func = ast.Module(body=[fn], type_ignores=[])
    exec(compile(func, "<benchmark-cache>", "exec"), ns)

    config = tmp_path / "agent.toml"
    config.write_text("model = 'A'", encoding="utf-8")
    spec = {
        "entrypoint": "any_team.wrapper:Wrapper", "revision": "1",
        "cache_files": [str(config)],
    }
    first = ns["agent_fingerprint"]("team-1", spec)
    config.write_text("model = 'B'", encoding="utf-8")
    second = ns["agent_fingerprint"]("team-1", spec)
    assert first != second
    assert second != ns["agent_fingerprint"]("team-2", spec)
