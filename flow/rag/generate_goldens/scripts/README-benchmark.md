# RAG benchmark · DeepEval owns the target execution

The [notebook](../benchmark.ipynb) now uses DeepEval 4.x's native
`EvaluationDataset.evals_iterator()` to **drive** the target agent, annotate
an observed trace and capture each golden's target trace. DeepEval's native, cache-aware
`evaluate()` then scores the recorded answers and owns judge metric caching
and report generation. The cli-agent-specific observed callback lives
in the **cli-agent SDK**, not in this repository:

```python
from cli_agent.sdk import AgentBuilder

target = builder.build_deepeval_target(include_knowledge_content=True)
# Called while DeepEval's evals_iterator() has yielded a Golden:
response = await target.ask(
    golden.input, expected_output=golden.expected_output,
    cached_response=previous_response,  # optional; avoids an agent model call
)
```

`DeepEvalTarget` constructs an isolated SDK agent instance for each
non-cached request; its `@observe(type="agent")` callback annotates the
native DeepEval trace with `input`, `output`, reference answer, and
**verified selected Knowledge context**. The reference answer is never
sent to cli-agent. The SDK method does not require DeepEval merely to
import `cli_agent.sdk`, but does require it when `ask()` is called.

## Installation and versions

Requires both companion changes:
- [cli-agent PR #312](https://github.com/sHuewe/cli-agent/pull/312):
  `AgentBuilder.build_deepeval_target()` + optional observed adapter.
- [cli-agent-utils](https://github.com/sHuewe/cli-agent-utils):
  notebook + lightweight benchmark helpers.

```bash
python -m pip install --upgrade cli-agent "deepeval>=4,<5" pandas jupyterlab ipykernel
jupyter lab flow/rag/generate_goldens/benchmark.ipynb
```

Use the **new cli-agent version containing PR #312** before starting the
notebook. Run Jupyter from the workspace root, which must contain
`rag-goldens/goldens.json`. For initial testing, use `MAX_CASES=3`,
then `MAX_CASES=None` to test all questions.

## Independent target and judge

Target: cli-agent project/admin configuration, using
`CONFIG_FILE`, `ADMIN_CONFIG_FILE`, and optionally explicitly approved
tool names from `APPROVE_TOOLS`. Each uncached request has a fresh agent.

Judge: `JUDGE_PROVIDER`, `JUDGE_MODEL`, and optional `JUDGE_BASE_URL`
are **completely independent of the target**. OpenAI, OpenRouter and
Ollama are supported. Configure the appropriate provider credentials in
environment variables, such as `OPENROUTER_API_KEY`. The default example
uses OpenRouter `openai/gpt-4.1`, but you must choose a DeepEval
GEval-compatible model allowed to receive your reference answers and
verified Knowledge passages.

The only data sent to the **target** is each question. The judge receives
the expected answer and actual agent answer; contextual metrics additionally
receive only **observed actual selected Knowledge content**, never
reference quotations from `goldens.json`.

## Native evaluation flow

1. Load `goldens.json` and construct a genuine DeepEval
   `EvaluationDataset(goldens=[Golden(...), ...])` with stable golden IDs
   in `additional_metadata`. No agent calls yet.
2. Use `for golden in dataset.evals_iterator(metrics=..., ...):`.
   **Within this iterator body**, call `await target.ask(...)`. The SDK
   records answer, reference and retrieval context on the DeepEval trace.
   The iterator uses a deterministic, no-LLM response-recorded metric.
   `AsyncConfig(run_async=False)` preserves the notebook coroutine's
   active observation context; `asyncio.timeout()` stays in the same task.
   This avoids repeating paid judge calls: the synchronous DeepEval iterator
   does not reuse cached individual judge metrics.
3. The small `benchmark_adapter.py` still handles input validation,
   target response checkpoints, judge selection and optional source recall.
   Cached successful target responses are **replayed through the observed
   callback** inside the iterator. Therefore a different judge never
   triggers new target model calls unless `FRESH_SDK=True`.
4. Native cache-aware `evaluate()` runs answer correctness and relevance
   on all recorded target responses. A separate native `evaluate()` runs
   faithfulness/contextual recall/precision on **only** cases with actual,
   complete selected Knowledge text. Both support concurrent judging and
   DeepEval metric-cache reuse.
5. DeepEval saves native test-run reports under
   `rag-goldens/evaluation/deepeval/`. Additional initial/candidate/
   selection document recall is computed deterministically from the SDK
   Knowledge trace, not by an LLM judge.

The initial observed *target-execution* pass is sequential by design, as
`evals_iterator()` establishes one active trace per Golden. The later
quality and retrieval passes can parallelize their judge calls.

DeepEval controls the **metric** cache; the helper controls only
**target response** reuse. Changing `JUDGE_MODEL` changes the evaluator,
but should not change the cached target answer. Set `FRESH_SDK=True`
after changing the RAG corpus, index, external MCP tools or model
weights, because their live content is not included in the config
fingerprint.

## Privacy and compatibility

Response JSON may contain private Knowledge excerpts. DeepEval sends
answers, references and potentially retrieved passages to your chosen
judge. Keep `rag-goldens/evaluation` private; review external reporting
and provider data policy settings.

Existing response caches written by the preceding benchmark version use
the same checksum contract and remain reusable when the config and Goldens
are unchanged. The previous bespoke per-metric score/checkpoint files are
not used; DeepEval's native reports are authoritative.
