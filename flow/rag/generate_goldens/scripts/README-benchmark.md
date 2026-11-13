# Native DeepEval benchmark

The [notebook](../benchmark.ipynb) is now a short native DeepEval workflow.
The cli-agent dependency is limited to [`benchmark_adapter.py`](benchmark_adapter.py):
`CliAgentTarget(agent)` wraps one SDK agent and exposes `async ask(question)`.
DeepEval handles data cases, model-based metrics, concurrency, scoring cache,
and native JSON reports.

## Install

```bash
python -m pip install cli-agent "deepeval>=4,<5" jupyterlab ipykernel pandas
jupyter lab flow/rag/generate_goldens/benchmark.ipynb
```

Run Jupyter from your RAG workspace root (containing
`rag-goldens/goldens.json`) and start with `MAX_CASES=3`, then `None`
for all. This notebook targets the current DeepEval 4.x API.

## Two independently configured models

**Target** uses cli-agent SDK's project/admin config with `CONFIG_FILE`,
`ADMIN_CONFIG_FILE`, optional exact `APPROVE_TOOLS`, and a new session
per golden. It receives **only the question**, not the reference answer or
source quotations.

**Judge** uses explicit `JUDGE_PROVIDER` and `JUDGE_MODEL` and never reads
cli-agent's model configuration. Supported providers: `openai`,
`openrouter`, and `ollama`, with optional `JUDGE_BASE_URL`.
Credentials: `OPENAI_API_KEY` or `OPENROUTER_API_KEY` from the environment.
For OpenRouter, the example is `openai/gpt-4.1`. Choose a G-Eval-compatible
model; some reasoning models cannot supply the required log probabilities.
The judge sees reference answers and (when available) actual selected
Knowledge passages. Confirm your data-processing policies before use.

## Separation of concerns

1. The adapter loads validated original `goldens.json` and executes a
   fresh cli-agent for each `input`. Only successful answers are reused
   from `rag-goldens/evaluation/responses/<id>.json`. The target fingerprint
   covers SDK config, admin policy, project override and capture settings.
   Use `FRESH_SDK=True` after changes to the live index, external tools,
   model weights, or corpus, which file hashes cannot reliably detect.
2. The adapter builds a native DeepEval `EvaluationDataset` with
   `LLMTestCase` records.
3. Native `evaluate()` executes correctness and relevancy metrics over all
   cases, plus a separate optional evaluation on cases with verified actual
   Knowledge retrieval context for faithfulness and contextual metrics.
   **Golden source evidence never substitutes for actual retrieval context.**
4. DeepEval manages concurrent judge calls, cache and writes its native
   `test_run_*.json` reports to `rag-goldens/evaluation/deepeval/`.
   To recalculate scores, set `FRESH_EVALUATION=True`.
5. An optional deterministic summary computes initial, candidate and
   selection document recall using exact normalized source paths.

Legacy hand-written `scores/*.json`, `summary.json` and independent
metric-evaluation loops are no longer used. DeepEval's reports are authoritative.
To change judges, edit only judge settings and rerun notebook cells 3–5.
This does not call the target again.

## Privacy

Response checkpoints can contain source-derived Knowledge passages.
DeepEval sends answers, references and selected passages to the selected
judge. Do not commit `rag-goldens/evaluation`. Review DeepEval's local or
cloud reporting settings in your environment.
