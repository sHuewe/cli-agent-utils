# Benchmark: one shared Golden set, interchangeable team agents

The [benchmark notebook](../benchmark.ipynb) evaluates independently
developed agents against **exactly the same** exported
`rag-goldens/deepeval-goldens.json`. DeepEval loads the Golden dataset,
judges the saved answers, caches judge metrics and generates reports.
**Agent execution does not depend on DeepEval.**

## Minimal contract for each team

Install the team's Python package into the Jupyter environment and
provide one public callable, synchronous or asynchronous:

```python
# team_b/benchmark.py
async def answer(question: str) -> str:
    return await my_agent.answer(question)
```

Optional retrieval evidence:

```python
async def answer(question: str) -> dict:
    result = await my_agent.answer(question)
    return {
        "answer": result.text,
        "retrieval_context": result.actual_retrieved_passages,
    }
```

`retrieval_context` must contain **actual** passages retrieved by that
agent, never ideal passages from the Golden dataset. No context is also
valid: the agent can still compete on answer correctness/relevancy.
Each adapter owns initialization, cleanup, and **isolation of conversation
state per question**.

There is no required base class, inheritance, mixin, SDK, tracer or
DeepEval dependency. A module can simply export `def answer(...)`.
External modules are imported by name; install them instead of modifying
`sys.path`.

## Configure participants

In the notebook's `AGENTS` mapping:

```python
AGENTS = {
    "team-a": {
        "entrypoint": "team_a.benchmark:answer",
        "revision": "git-commit-a1b2c3",
    },
    "team-b": {
        "entrypoint": "team_b.benchmark:answer",
        "revision": "git-commit-d4e5f6",
    },
}
```

The supplied `builtin:cli-agent` entry is an **optional example**.
For external-only agents, `cli-agent` itself does not need to be installed.
Only that example's adapter imports the SDK.

To change frameworks, agents or teams, change `AGENTS`: **no editing
of DeepEval's evaluation loop or metric construction**.

## Run

```bash
python -m pip install "deepeval>=4,<5" pandas jupyterlab ipykernel
# install each team's agent package in the same environment
jupyter lab flow/rag/generate_goldens/benchmark.ipynb
```

Launch Jupyter from the workspace root containing
`rag-goldens/deepeval-goldens.json`; if necessary, regenerate the
Golden JSON using the separate exporter. Set `MAX_CASES=3` for a quick
check and `MAX_CASES=None` to judge all shared Goldens.

## Evaluation and fairness

- **Common answer quality**: fixed-reference G-Eval correctness and
  answer relevancy, using the same Golden questions, judge model,
  rubric and threshold for every team
- **Optional retrieval quality**: DeepEval faithfulness, contextual
  recall/precision, and uncertainty calibration only where the agent
  actually supplies complete retrieval passages
- **Optional style**: a team's `style_criteria` may be assessed separately,
  but incomparable style rubrics must not be pooled or ranked as a common
  quality metric

DeepEval is used only to evaluate constructed `LLMTestCase` objects
via `evaluate()`. No `DeepEvalTarget`, `evals_iterator()` or
DeepEval-specific interface is needed in agent implementations.

Execution is sequential across agents and Golden questions. Successful
responses are checkpointed; failures are recorded with Golden ID and
exception class and never silently counted as successful. The notebook
reports the **number of answered Goldens and failed requests** alongside
average judge scores. Do not compare averages on unequal question subsets
without considering the missing cases.

Use the same corpus/index snapshot, judge configuration and Golden
dataset for a fair team comparison. Every agent should be able to handle
the same request timeout and question-only input. A sync function runs
in a worker thread and may continue after timeout; prefer async
cancellation for costly model calls.

## Caching and privacy

Response cache keys include agent ID, entrypoint, revision, workspace,
Golden ID, question/reference, and `CACHE_EPOCH`. For the built-in SDK
agent, the local config, admin policy and file-backed system prompt are
also hashed. Teams must update their revision after any agent code,
model or prompt change, or use `FRESH_RESPONSES=True`; external index
changes can be recorded through `CACHE_EPOCH`.

Responses are written atomically with owner-only permissions (0600 where
supported). Judge cache is independent (`FRESH_EVALUATION=True` to skip
reuse). Local responses and judge reports may contain confidential
information and should not be committed to version control.
