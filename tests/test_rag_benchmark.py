"""Native DeepEval benchmark contract tests.

The benchmark imports no generator script. Source evidence is intentionally
not embedded as retrieval context; only the live SDK trace may supply it.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

BASE = Path(__file__).resolve().parents[1] / "flow/rag/generate_goldens"


def notebook():
    return json.loads((BASE / "benchmark.ipynb").read_text(encoding="utf-8"))


def notebook_sources():
    return [
        "".join(cell["source"])
        for cell in notebook()["cells"]
        if cell["cell_type"] == "code"
    ]


def test_notebook_uses_native_json_loader_and_sdk_not_scripts():
    sources = notebook_sources()
    code = "\n".join(sources)
    assert 'dataset.add_goldens_from_json_file(str(GOLDENS_FILE))' in code
    assert 'deepeval-goldens.json' in code
    assert 'builder.build_deepeval_target(' in code
    assert 'dataset.evals_iterator(' in code
    assert 'await target.ask(' in code
    assert 'from deepeval import evaluate' in code
    assert 'answer_results = evaluate(' in code
    assert 'retrieval_results = evaluate(' in code
    assert 'benchmark_adapter' not in code
    assert 'sys.path' not in code
    assert 'from scripts' not in code
    assert 'import scripts' not in code
    assert 'collect_responses(' not in code
    assert 'deep_eval_dataset(' not in code
    for cell in sources:
        compile(cell, "<benchmark cell>", "exec",
                flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)


def test_exported_deepeval_dataset_is_directly_importable():
    """Check supported DeepEval fields independently of the SDK adapter."""
    export = (BASE / "scripts/export.py").read_text(encoding="utf-8")
    assert '"deepeval-goldens.json"' in export
    assert '"additional_metadata": {' in export
    assert '"golden_id": g["id"]' in export
    assert '"required_sources":' in export
    assert '"input": g["input"]' in export
    assert '"expected_output": g["expected_output"]' in export
    assert '"context": [item["quote"]' not in export
    assert '"retrieval_context": [item["quote"]' not in export


def test_dataset_notebook_does_not_use_reference_context_as_retrieval():
    code = "\n".join(notebook_sources())
    assert 'response.get("knowledge_trace") or {}' in code
    assert 'trace.get("content_included") is True' in code
    assert 'trace.get("truncated") is not True' in code
    assert 'retrieval_context=[hit["content"] for hit in selected]' in code
    assert 'golden.context' not in code
    assert 'golden.retrieval_context' not in code


def test_separate_judge_and_cache_fingerprint_includes_prompt_file():
    code = "\n".join(notebook_sources())
    assert 'JUDGE_PROVIDER = "openrouter"' in code
    assert 'JUDGE_MODEL = "openai/gpt-4.1"' in code
    assert 'OpenRouterModel(model=JUDGE_MODEL' in code
    assert 'judge = OpenAIModel(' in code
    assert 'judge = OllamaModel(' in code
    assert 'model=JUDGE_MODEL' in code
    assert 'effective_config_hash(prompt_text)' in code
    assert 'files.append(WORKSPACE / ".cli-agent" / filename)' in code
    assert 'builder.with_system_prompt(prompt_text)' in code
    assert 'PROMPT_VARIANTS = {' in code
    assert 'all_responses[variant_id]' in code
    assert 'identifier=f"rag-{variant_id}-answer"' in code
    assert 'identifier=f"rag-{variant_id}-retrieval"' in code
    assert 'name="Style compliance"' in code
    assert 'name="Uncertainty calibration"' in code
    assert 'SingleTurnParams.RETRIEVAL_CONTEXT' in code
    assert 'CACHE_EPOCH' in code
    assert 'CACHE_EPOCH' in code
    assert 'cached_response=cached' in code
    assert 'default_admin_config_file()' in code
    assert 'os.chmod(tmp, 0o600)' in code
    assert 'os.replace(tmp, checkpoint)' in code
    assert 'tempfile.NamedTemporaryFile(' in code
    assert 'CacheConfig(use_cache=not FRESH_EVALUATION' in code


def test_native_dataset_loader_on_real_deepeval_when_available(tmp_path):
    """Optional real-API smoke test; no LLM calls and no network needed."""
    import pytest

    dataset_module = pytest.importorskip("deepeval.dataset")
    path = tmp_path / "deepeval-goldens.json"
    payload = [{
        "input": "What happens without a token?",
        "expected_output": "The gateway rejects the request.",
        "additional_metadata": {
            "golden_id": "b0001-g0001",
            "required_sources": ["md/a.md", "md/b.md"],
        },
    }]
    path.write_text(json.dumps(payload), encoding="utf-8")
    ds = dataset_module.EvaluationDataset()
    ds.add_goldens_from_json_file(str(path))
    assert len(ds.goldens) == 1
    assert ds.goldens[0].input == payload[0]["input"]
    assert ds.goldens[0].expected_output == payload[0]["expected_output"]
    assert ds.goldens[0].additional_metadata == payload[0]["additional_metadata"]



def test_prompt_comparison_uses_same_reference_and_independent_score_dimensions():
    code = "\n".join(notebook_sources())
    # All variants reuse one dataset and its fixed expected_output. The
    # experiment must never rewrite reference answers per response style.
    assert "dataset.add_goldens_from_json_file(str(GOLDENS_FILE))" in code
    assert "expected_output=golden.expected_output" in code
    assert 'name="Answer correctness"' in code
    assert 'name="Style compliance"' in code
    assert 'name="Uncertainty calibration"' in code
    assert 'if retrieval_cases:' in code
    assert 'trace.get("content_included") is True' in code
    assert 'trace.get("truncated") is not True' in code
    assert "metric.error or metric.score is None" in code
    assert 'metric.name.removesuffix(" [GEval]")' in code
    assert '"retrieval_cases": outputs["retrieval_case_count"]' in code


def test_prompt_variant_cache_separation_and_config_order():
    code = "\n".join(notebook_sources())
    assert 'for variant_id, variant in PROMPT_VARIANTS.items():' in code
    assert 'builder.with_project_config(' in code
    assert 'builder.with_system_prompt(prompt_text)' in code
    assert code.index("builder.with_project_config(") < code.index(
        "builder.with_system_prompt(prompt_text)"
    )
    assert '[variant_id, fingerprint, golden_id, golden.input, golden.expected_output]' in code
    assert 'prompt_text": prompt_text' in code
    assert 'cache_epoch": CACHE_EPOCH' in code
    assert 'os.chmod(tmp, 0o600)' in code
    assert 'os.replace(tmp, checkpoint)' in code
    assert 'FRESH_SDK' in code and 'FRESH_EVALUATION' in code



def test_target_factory_contract_and_single_injection_point():
    notebook_cells = notebook()["cells"]
    code_cells = ["".join(c["source"]) for c in notebook_cells
                  if c["cell_type"] == "code"]
    factory_cells = [s for s in code_cells if "def create_target(" in s]
    assert len(factory_cells) == 1
    factory = factory_cells[0]
    assert "class BenchmarkTarget(Protocol):" in factory
    assert "class TargetSpec:" in factory
    assert "target: BenchmarkTarget" in factory
    assert "cache_identity: str" in factory
    assert 'target=builder.build_deepeval_target(include_knowledge_content=True)' in factory
    assert 'cache_identity="cli-agent-sdk:" + effective_config_hash(prompt_text)' in factory
    # The experiment loop cannot depend on the SDK Builder: one return
    # value from create_target provides the implementation and cache identity.
    execution = next(s for s in code_cells if "for golden in dataset.evals_iterator(" in s)
    assert "target_spec = create_target(variant_id, variant)" in execution
    assert "target = target_spec.target" in execution
    assert "fingerprint = target_spec.cache_identity" in execution
    assert "AgentBuilder(" not in execution
    assert "with_project_config(" not in execution
    assert "with_system_prompt(" not in execution
    assert "await target.ask(" in execution
    assert "cached_response=cached" in execution


def test_factory_can_produce_alternative_implementation_without_sdk_builder(monkeypatch):
    """Execute actual factory definition with stubbed external SDK dependencies."""
    import sys
    import types
    from dataclasses import dataclass
    from typing import Protocol

    factory = next("".join(c["source"]) for c in notebook()["cells"]
                   if c["cell_type"] == "code"
                   and "def create_target(" in "".join(c["source"]))
    fake_sdk_module = types.ModuleType("cli_agent.sdk.deepeval_adapter")
    fake_sdk_module.DeepEvalTarget = type("FakeDeepEvalTarget", (), {})
    monkeypatch.setitem(sys.modules, "cli_agent.sdk.deepeval_adapter", fake_sdk_module)

    env = {
        "dataclass": dataclass,
        "Protocol": Protocol,
        "AgentBuilder": object,  # must not be called for other agents
        "effective_config_hash": lambda _: "default-hash",
    }
    exec(compile(factory, "<benchmark-target-factory>", "exec"), env)
    TargetSpec = env["TargetSpec"]

    class OtherTarget:
        async def ask(self, question, *, expected_output, cached_response=None):
            # Only question goes to the underlying agent implementation;
            # reference remains outside the model call.
            return {"actual_output": question.upper(), "knowledge_trace": None}

    def alternate_factory(variant_id, variant):
        return TargetSpec(OtherTarget(), "other-v1:" + variant_id)

    spec = alternate_factory("concise", {"system_prompt": "anything"})
    assert spec.cache_identity == "other-v1:concise"
    assert hasattr(spec.target, "ask")
