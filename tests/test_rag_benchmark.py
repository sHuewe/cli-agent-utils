"""Contract tests for the SDK -> DeepEval RAG benchmark, with no LLM/network."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
import ast
import json
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "flow/rag/generate_goldens/benchmark.ipynb"
BENCHMARK_SCRIPT = ROOT / "flow/rag/generate_goldens/scripts/benchmark.py"
NOTEBOOK_DATA = json.loads(NOTEBOOK.read_text(encoding="utf-8"))

# Load notebook library cells only; never execute costly SDK/Judge cells in CI.
bm = ModuleType("rag_benchmark")
for cell in NOTEBOOK_DATA["cells"]:
    if cell["cell_type"] == "code" and (
        "benchmark-library" in cell.get("metadata", {}).get("tags", [])
    ):
        exec(compile("".join(cell["source"]), f"notebook:{cell['id']}", "exec"), bm.__dict__)


def golden(gid="b0001-g0001"):
    return {
        "id": gid, "input": "What is required?", "expected_output": "Both rules.",
        "evidence": [{"quote": "SECRET REFERENCE", "path": "a.md"}],
    }


class FakeAgent:
    def __init__(self, seen):
        self.seen = seen

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def ask(self, prompt):
        self.seen.append(prompt)
        return SimpleNamespace(
            answer="Both rules.", tool_calls=[
                SimpleNamespace(name="okf__search", status="success", duration_ms=25.0),
            ],
            usage=SimpleNamespace(input_tokens=100, output_tokens=20,
                                  total_tokens=120, model_calls=1,
                                  reported_calls=1, unreported_calls=0),
        )


def test_load_goldens_rejects_duplicates_and_missing_reference(tmp_path):
    path = tmp_path / "goldens.json"
    path.write_text(json.dumps([golden(), golden()]), encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate"):
        bm.load_goldens(path)
    path.write_text(json.dumps([{"id": "x", "input": "Question"}]), encoding="utf-8")
    with pytest.raises(ValueError, match="expected_output"):
        bm.load_goldens(path)


def test_sdk_sees_question_only_and_resumes(tmp_path):
    seen = []
    goldens = [golden()]
    agent_factory = lambda: FakeAgent(seen)
    runner = "config-fingerprint"
    summary = asyncio.run(bm.run_cases(
        goldens, output=tmp_path, runner_sha=runner,
        agent_factory=agent_factory, timeout=5.0, fresh=False,
    ))
    assert summary == {"completed": 1, "reused": 0, "failed": 0}
    assert seen == ["What is required?"]
    assert "SECRET REFERENCE" not in repr(seen)
    record = bm.read_json(bm.case_path(tmp_path, goldens[0]["id"]),
                          max_bytes=bm.MAX_CASE_BYTES)
    assert record["actual_output"] == "Both rules."
    assert record["usage"]["total_tokens"] == 120
    assert record["tool_calls"][0]["name"] == "okf__search"
    again = asyncio.run(bm.run_cases(
        goldens, output=tmp_path, runner_sha=runner,
        agent_factory=agent_factory, timeout=5.0, fresh=False,
    ))
    assert again["reused"] == 1
    assert len(seen) == 1
    invalidated = asyncio.run(bm.run_cases(
        goldens, output=tmp_path, runner_sha="different-config",
        agent_factory=agent_factory, timeout=5.0, fresh=False,
    ))
    assert invalidated["completed"] == 1
    assert len(seen) == 2


def test_each_question_has_a_fresh_session(tmp_path):
    seen = []
    created = []

    def factory():
        obj = FakeAgent(seen)
        created.append(obj)
        return obj

    asyncio.run(bm.run_cases(
        [golden("q1"), golden("q2")], output=tmp_path,
        runner_sha="run", agent_factory=factory, timeout=5, fresh=False,
    ))
    assert len(created) == 2
    assert created[0] is not created[1]
    assert seen == ["What is required?", "What is required?"]


class FakeMetric:
    def __init__(self, name="Correctness", score=0.85):
        self.name = name
        self.score = score
        self.reason = "Correct"

    def measure(self, case):
        assert case.input == "What is required?"
        assert case.expected_output == "Both rules."
        assert case.actual_output == "Both rules."

    def is_successful(self):
        return self.score >= 0.7


def test_evaluate_without_observed_context_does_not_fabricate_retrieval(tmp_path):
    goldens = [golden()]
    asyncio.run(bm.run_cases(
        goldens, output=tmp_path, runner_sha="run",
        agent_factory=lambda: FakeAgent([]), timeout=5, fresh=False,
    ))
    observed = []
    def case_factory(**kwargs):
        observed.append(kwargs)
        return SimpleNamespace(**kwargs)

    def metrics_factory(**kwargs):
        assert kwargs["has_retrieval"] is False
        return [FakeMetric()]
    result = bm.evaluate_cases(
        goldens, output=tmp_path, runner_sha="run", threshold=0.7,
        judge_model="fake", fresh=False, testcase_factory=case_factory,
        metrics_factory=metrics_factory,
    )
    assert result["complete"] is True
    assert result["passed"] == 1
    assert result["scores"]["Correctness"]["mean"] == 0.85
    assert "retrieval_context" not in observed[0]
    assert "SECRET REFERENCE" not in repr(observed[0])
    summary = bm.evaluate_cases(
        goldens, output=tmp_path, runner_sha="run", threshold=0.7,
        judge_model="fake", fresh=False, testcase_factory=case_factory,
        metrics_factory=metrics_factory,
    )
    assert summary["reused"] == 1
    assert len(observed) == 1


def test_evaluate_true_retrieval_context_and_stale_context_rejected(tmp_path):
    goldens = [golden()]
    asyncio.run(bm.run_cases(
        goldens, output=tmp_path, runner_sha="run",
        agent_factory=lambda: FakeAgent([]), timeout=5, fresh=False,
    ))
    cases = []
    response = bm.read_json(
        bm.case_path(tmp_path, goldens[0]["id"]), max_bytes=bm.MAX_CASE_BYTES
    )
    contexts = {"b0001-g0001": {
        "runner_sha256": "run", "response_sha256": bm.digest(response),
        "chunks": ["Actual RAG result"]
    }}
    result = bm.evaluate_cases(
        goldens, output=tmp_path, runner_sha="run", threshold=0.7,
        judge_model="fake", fresh=False, retrieval_contexts=contexts,
        testcase_factory=lambda **kw: cases.append(kw) or SimpleNamespace(**kw),
        metrics_factory=lambda **kw: [FakeMetric("Grounding")],
    )
    assert result["complete"] is True
    assert cases[0]["retrieval_context"] == ["Actual RAG result"]
    contexts["b0001-g0001"]["runner_sha256"] = "not-this-run"
    with pytest.raises(ValueError, match="Stale retrieval"):
        bm.evaluate_cases(
            goldens, output=tmp_path, runner_sha="run", threshold=0.7,
            judge_model="fake", fresh=False, retrieval_contexts=contexts,
            testcase_factory=lambda **kw: SimpleNamespace(**kw),
            metrics_factory=lambda **kw: [FakeMetric()],
        )


def test_error_does_not_reuse_or_claim_complete(tmp_path):
    class BrokenAgent(FakeAgent):
        async def ask(self, prompt):
            raise RuntimeError("Secret-bearing error")

    goldens = [golden()]
    stats = asyncio.run(bm.run_cases(
        goldens, output=tmp_path, runner_sha="run",
        agent_factory=lambda: BrokenAgent([]), timeout=5.0, fresh=False,
    ))
    assert stats["failed"] == 1
    state = bm.read_json(bm.case_path(tmp_path, goldens[0]["id"]),
                         max_bytes=bm.MAX_CASE_BYTES)
    assert state["status"] == "error"
    assert state["error_type"] == "RuntimeError"
    assert "Secret-bearing" not in repr(state)
    summary = bm.evaluate_cases(
        goldens, output=tmp_path, runner_sha="run",
        judge_model=None, threshold=0.7, fresh=False,
        testcase_factory=lambda **kw: SimpleNamespace(**kw),
        metrics_factory=lambda **kw: [FakeMetric()],
    )
    assert summary["complete"] is False
    assert summary["skipped"] == 1


def test_notebook_replaces_script_and_has_separate_phases():
    assert not BENCHMARK_SCRIPT.exists()
    assert NOTEBOOK_DATA["nbformat"] == 4
    ids = [cell["id"] for cell in NOTEBOOK_DATA["cells"]]
    assert "config" in ids
    assert "sdk-run" in ids
    assert "evaluate" in ids
    assert ids.index("sdk-run") < ids.index("evaluate")
    for cell in NOTEBOOK_DATA["cells"]:
        if cell["cell_type"] == "code":
            compile(
                "".join(cell["source"]), f"notebook:{cell['id']}", "exec",
                flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT,
            )
    assert any("await run_cases" in "".join(c["source"])
               for c in NOTEBOOK_DATA["cells"] if c["id"] == "sdk-run")
    assert any("evaluate_cases(" in "".join(c["source"])
               for c in NOTEBOOK_DATA["cells"] if c["id"] == "evaluate")


def test_observed_contexts_validated(tmp_path):
    path = tmp_path / "observed.json"
    path.write_text(json.dumps({"b0001-g0001": {
        "runner_sha256": "run", "response_sha256": "0" * 64,
        "chunks": ["real first chunk"]
    }}), encoding="utf-8")
    assert bm.validate_actual_contexts(path)["b0001-g0001"]["chunks"] == [
        "real first chunk"
    ]
    path.write_text(json.dumps({"b0001-g0001": {
        "runner_sha256": "run", "response_sha256": "0" * 64,
        "chunks": [123]
    }}), encoding="utf-8")
    with pytest.raises(ValueError):
        bm.validate_actual_contexts(path)



def test_observed_contexts_bound_to_exact_execution_even_after_fresh(tmp_path):
    goldens = [golden()]
    agent_factory = lambda: FakeAgent([])
    asyncio.run(bm.run_cases(
        goldens, output=tmp_path, runner_sha="run",
        agent_factory=agent_factory, timeout=5, fresh=False,
    ))
    answer_file = bm.case_path(tmp_path, goldens[0]["id"])
    first = bm.read_json(answer_file, max_bytes=bm.MAX_CASE_BYTES)
    old_contexts = {"b0001-g0001": {
        "runner_sha256": "run",
        "response_sha256": bm.digest(first),
        "chunks": ["Captured before rerun"],
    }}
    assert first["execution_id"]
    asyncio.run(bm.run_cases(
        goldens, output=tmp_path, runner_sha="run",
        agent_factory=agent_factory, timeout=5, fresh=True,
    ))
    second = bm.read_json(answer_file, max_bytes=bm.MAX_CASE_BYTES)
    assert second["execution_id"] != first["execution_id"]
    assert bm.digest(second) != old_contexts["b0001-g0001"]["response_sha256"]
    with pytest.raises(ValueError, match="Stale retrieval"):
        bm.evaluate_cases(
            goldens, output=tmp_path, runner_sha="run",
            judge_model="fake", threshold=0.7, fresh=False,
            retrieval_contexts=old_contexts,
            testcase_factory=lambda **kw: SimpleNamespace(**kw),
            metrics_factory=lambda **kw: [FakeMetric()],
        )
