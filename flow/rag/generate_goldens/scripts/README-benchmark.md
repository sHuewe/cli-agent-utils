# Native DeepEval benchmark – prompt comparisons

The [benchmark notebook](../benchmark.ipynb) reads the exported
`rag-goldens/deepeval-goldens.json` **directly** through DeepEval's native
`EvaluationDataset.add_goldens_from_json_file()`. No generator scripts are
imported. The detailed `goldens.json` remains for auditing.

## Setup

Install a cli-agent SDK release containing the companion
`AgentBuilder.with_system_prompt(text)` API, then run Jupyter from the
workspace root:

```bash
python -m pip install --upgrade cli-agent "deepeval>=4,<5" pandas jupyterlab ipykernel
python flow/rag/generate_goldens/scripts/export.py --workspace .
jupyter lab flow/rag/generate_goldens/benchmark.ipynb
```

## Prompt experiments

Configure `PROMPT_VARIANTS` in the first notebook code cell.
Each variant contains:

- `system_prompt`: direct system prompt text; `None` uses the configured
  file-based system prompt, if any
- `style_criteria`: a short, **separate** set of intended response-style
  requirements, evaluated only by the style judge

The notebook creates a **new** SDK Builder for each variant. It calls
`with_project_config(...)` and then, if configured,
`with_system_prompt(text)`. The latter overrides the base system prompt
without altering mandatory tool or security instructions.

All variants use **the same Goldens and unchanged expected answers**.
For a fair comparison, fix the target model, corpus/index, judge model
and run parameters across variants, and test all Goldens (`MAX_CASES=None`)
once the smoke test succeeds.

## Separate evaluation dimensions

**Factual quality**: fixed-reference G-Eval answer correctness and DeepEval
answer relevancy are directly comparable across prompt variants because
they use one shared rubric and identical Goldens.

**Grounding and uncertainty**: DeepEval faithfulness/contextual recall/
precision and a separate uncertainty-calibration G-Eval are run **only**
when the SDK returned verified, complete selected Knowledge passages.
This judge checks for unsupported confident assertions and unwarranted
refusals based on the passages available to the agent; this is a proxy,
not a proof that every document relevant to the question was available.
Cases without verified context are marked as *not assessed*; do not
interpret missing scores as zero or success. Compare case counts too.

**Style compliance**: a variant-specific G-Eval assesses whether the response
matches its style criteria. Different style rubrics have different targets,
so those scores cannot be ranked as a single apples-to-apples quality metric.
They should be interpreted alongside the common factual scores.

DeepEval handles judge caching, concurrency and detailed reports. The last
cell displays a summary table with metric means, counted evaluations/errors,
and retrieval-case coverage. Inspect individual judge reasons before
drawing conclusions about small differences.

## Replaceable target factory

The notebook defines `create_target(variant_id, variant) -> TargetSpec`.
The returned `TargetSpec.target` is a `BenchmarkTarget`: an object with

```python
async def ask(question: str, *, expected_output: str,
              cached_response: Mapping | None = None) -> dict:
    # Return {"actual_output": str, "knowledge_trace": dict | None}
    ...
```

`TargetSpec.cache_identity` is a **nonempty stable identifier** of the
target's actual configuration (including agent type, model, prompt, and any
other state that affects responses). The benchmark uses it to separate
response checkpoints; change it when the target changes, or set
`FRESH_SDK=True` after untracked external changes.

The default target is `cli_agent.sdk.deepeval_adapter.DeepEvalTarget`,
**not** a raw SDK `Agent`. It wraps `AgentBuilder.build()`, initializes
a **fresh** agent per noncached question, traces it through DeepEval, and
keeps the reference answer out of the target prompt.

To swap the agent, change only `create_target()`. Example for an agent
with the SDK-like `async with agent` and `agent.ask(question)` protocol
returning `.answer` and `.knowledge_trace`:

```python
from cli_agent.sdk.deepeval_adapter import DeepEvalTarget

def create_target(variant_id, variant) -> TargetSpec:
    return TargetSpec(
        target=DeepEvalTarget(lambda: MyAlternativeAgent(...)),
        cache_identity="my-other-agent-v1:" + stable_configuration_hash,
    )
```

Alternatively return any other adapter implementing `BenchmarkTarget.ask()`
directly; it is then responsible for tracing expected output within DeepEval's
active evaluation context and for safe cache replay. The Golden's
`expected_output` must **never** be forwarded to the answering agent.
The rest of the notebook (iteration, checkpoints, judge and score table)
does not depend on cli-agent SDK internals.

## SDK target and judge

The target uses the normal CLI-agent SDK project/admin settings.
`with_system_prompt(text)` passes a direct override to the SDK worker,
not a file name. In the SDK Builder, the last explicit system prompt wins:
a subsequent file-backed `with_project_config` may replace an earlier
inline prompt. `build_deepeval_target()` snapshots the Builder.

The **judge** uses an independent OpenAI, OpenRouter or Ollama model.
The reference answer is supplied only to DeepEval, never to cli-agent.
The judge can receive actual selected passages; use only approved models/
providers for your content.

## Caching and privacy

Successful target responses are stored in `rag-goldens/evaluation/responses/`
with atomic owner-only files (mode 0600 where supported).
Their cache key includes variant ID, inline prompt, effective project/admin
files, configured file-based prompt, Golden input/reference, workspace and
`CACHE_EPOCH`. The workspace `.cli-agent/project.toml` is **not**
automatically used by SDK runs. If the live RAG index, files, model weights
or external tools change, set `FRESH_SDK=True` or update `CACHE_EPOCH`.

DeepEval metric caching is separate and can be disabled using
`FRESH_EVALUATION=True`. Response files and DeepEval reports may contain
sensitive information and must not be committed or shared without review.
