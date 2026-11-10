# RAG Golden Benchmark · Jupyter Notebook

The executable **[benchmark.ipynb](../benchmark.ipynb)** replaces the former
`scripts/benchmark.py`. It uses `AgentBuilder` from **cli-agent's Python SDK**
to ask the real RAG each golden question and DeepEval to score the answers.
There is no separate Python benchmark script to run.

## Setup

Open a Jupyter kernel with Python 3.11+ and the required packages:

```bash
python -m pip install "cli-agent" "deepeval" "jupyterlab" "ipykernel"
jupyter lab flow/rag/generate_goldens/benchmark.ipynb
```

Launch Jupyter **from your RAG workspace root** so `WORKSPACE = Path.cwd()`
resolves to the directory with `rag-goldens/goldens.json`. You can also
edit `WORKSPACE` explicitly in the notebook configuration cell.

For Chroma vector retrieval, install `cli-agent[rag]` and configure the
existing collection. For OKF use the normal cli-agent OKF config.
The notebook never builds or updates the knowledge database.

DeepEval needs a separately configured LLM judge, often through
`OPENAI_API_KEY`. `JUDGE_MODEL` selects another supported DeepEval model.
If relevant, review the judge provider's confidentiality and data-handling
requirements before submitting any references or actual answers.

## Notebook cell sequence

1. **Configuration:** set `WORKSPACE`, `GOLDENS_FILE`, `OUTPUT_DIR`,
   `CONFIG_FILE`, `ADMIN_CONFIG_FILE`, exact `APPROVE_TOOLS`, `MAX_CASES`,
   `SDK_TIMEOUT_SECONDS`, `CAPTURE_KNOWLEDGE_CONTENT`, `JUDGE_MODEL` and
   `THRESHOLD`. The default
   `MAX_CASES = 3` provides a small smoke test.
2. **Load goldens:** obtain the model config and hashed fingerprint.
3. **SDK run:** `await run_cases(...)` executes only the golden **input**
   against a fresh cli-agent SDK session per question, saving the answer,
   tool-call metadata and reported token counts into
   `rag-goldens/evaluation/responses/<id>.json`.
4. **Answers preview:** inspect answer excerpts, Knowledge searches,
   selected chunks and the individual response fingerprint. Reference
   facts are **never** passed to the tested agent.
5. **Observed retrieval:** by default the SDK trace is captured and stored
   with the response. An external JSON file is optional for independent
   instrumentation; it must match the exact SDK execution.
6. **DeepEval:** `evaluate_cases(...)` scores the saved answers and writes
   `scores/<id>.json` and `summary.json`, without rerunning SDK queries.
7. **Summary:** display DeepEval metric averages and deterministic
   document recall from initial search, all found/read candidates and
   final Knowledge selection, alongside completed/passed/failed cases.

## Metrics

**Always available** with a configured judge:

- `GEval` / AnswerCorrectness: semantic completeness and correctness
  against `expected_output`, emphasizing multi-document dependencies.
- `AnswerRelevancyMetric`: relevance to the question.

**Optional, only with observed retrieval passages:**

- `FaithfulnessMetric`
- `ContextualRecallMetric`
- `ContextualPrecisionMetric`

The **new optional Knowledge trace** (`AgentBuilder.with_knowledge_trace`,
cli-agent PR #303) captures verified Chroma/OKF search results and selected
content directly from the SDK. The notebook enables this explicitly in the
SDK factory and uses only **selected** content as DeepEval
`retrieval_context`. When content capture is disabled, incomplete, truncated
or empty, only answer metrics run.

The notebook never substitutes golden `evidence` or
`deepeval-goldens.json.context` fields for actual retrieval. Such a
substitution would falsely score ideal reference context rather than the
retriever.

## Observed retrieval JSON (optional external override)

The notebook ordinarily uses the SDK's captured selected context. If a
separate trusted retriever produces its own trace data, set
`OBSERVED_RETRIEVAL_FILE` to a JSON document like:

```json
{
  "b0001-g0001": {
    "runner_sha256": "<full RUNNER_SHA from the notebook>",
    "response_sha256": "<response_sha256 from the answer-preview cell>",
    "chunks": ["real retrieved chunk 1", "real retrieved chunk 2"]
  }
}
```

The `response_sha256` includes a unique `execution_id` generated for each
successful SDK run. Changing a question **or rerunning the same question**
invalidates older captured retrieval chunks. A mismatched fingerprint is a
hard evaluation error, not a silently ignored context.

If the observed chunk list is empty, the notebook skips retrieval-dependent
metrics for that particular case. The resulting per-metric sample counts
show how many cases have actual retrieval context.

## Document recall and diagnostic attribution

The notebook uses `golden.sources[].path` as the expected source document
set and compares those paths to `KnowledgeTrace.searches[].hits[].source`
and `KnowledgeTrace.selected[].source`, reporting:

- `initial_recall`: required documents seen in the initial search;
- `candidate_recall`: required documents found across all searches or
  verified OKF reads;
- `selection_recall`: required documents finally passed to the main LLM.

This distinguishes **missing search candidates** from **candidates rejected
by the Knowledge LLM**. Reentry searches are included in candidate recall.
In OKF-only mode without a vector index, initial recall may be zero because
there is no ranked initial vector search; the meaningful discovery measure
is candidate recall, including actual `knowledge_read` documents.

Only normalized matching source paths are compared. There is **no guessing
from filenames**, so externally supplied Chroma metadata must use source
identifiers aligned with the golden source paths. A zero recall can reflect
an ID mismatch; inspect the stored trace before interpreting it.

The trace shows what the system retrieved/selected, not which passages the
main LLM actually relied on. Do not treat a high recall as proof of correct
reasoning.

## Checkpoints and repeatability

The notebook reuses compatible response and evaluation checkpoints, allowing
you to change the judge without rerunning the RAG. Set `FRESH_SDK = True`
to force new SDK answers, or `FRESH_EVALUATION = True` to force new judge
scores. Change `OUTPUT_DIR` to compare configurations independently.

Configuration hashes account for user/admin config and the workspace's
`.cli-agent/project.toml`, but **cannot detect changes to a live vector
database, OKF documents, model weights or external MCP tools**. Rerun
fresh after such changes.

Each golden gets an isolated new agent session; no previous conversation
history or approval state leaks between questions. Errors are recorded
by type without raw exception text. For confidentiality, do not commit the
output JSON containing source-derived answers or judge explanations.

The notebook has static mock-based contract tests in
`tests/test_rag_benchmark.py`; actual SDK and DeepEval model calls require
your live knowledge backend and judge credentials.
