# Native DeepEval benchmark

The [notebook](../benchmark.ipynb) loads the generated
`rag-goldens/deepeval-goldens.json` **directly** using DeepEval:

```python
from deepeval.dataset import EvaluationDataset

dataset = EvaluationDataset()
dataset.add_goldens_from_json_file(
    str(WORKSPACE / "rag-goldens" / "deepeval-goldens.json")
)
```

No `scripts/` import, custom loader, JSON converter or `sys.path` hack
is needed. The original detailed `goldens.json` remains available for
audits, document provenance and source-hash verification.

## Installation

Use a cli-agent SDK version with
`AgentBuilder.build_deepeval_target()` (introduced in
[cli-agent PR #312](https://github.com/sHuewe/cli-agent/pull/312)):

```bash
python -m pip install --upgrade cli-agent "deepeval>=4,<5" jupyterlab ipykernel
jupyter lab flow/rag/generate_goldens/benchmark.ipynb
```

Run Jupyter from your **RAG workspace root** (containing
`rag-goldens/deepeval-goldens.json`). After updating the exporter,
**rerun the export command**, not the entire Golden-generation Flow:

```bash
python flow/rag/generate_goldens/scripts/export.py --workspace .
```

This regenerates the native JSON with `additional_metadata.golden_id`,
which gives every Golden a stable response checkpoint identifier.
The export includes `input`, `expected_output`, and
`additional_metadata.required_sources`. It deliberately does **not**
include `context` or `retrieval_context` sourced from the answer's
reference quotations, because they are not what the target actually
retrieved.

## Target and judge are independent

- **Target:** normal `AgentBuilder.with_project_config()`, including
  `workspace/.cli-agent/project.toml` and its `system_prompt`.
  `build_deepeval_target()` provides the optional observed SDK adapter.
  DeepEval's `evals_iterator()` drives each observed agent ask and retains
  a trace. Expected answers never enter target prompts.
- **Judge:** a **separate** `OpenRouterModel`, `OpenAIModel`, or
  `OllamaModel`, specified in notebook configuration. API credentials
  come from environment variables. The judge sees actual/reference answers
  and, for contextual evaluations, selected source passages.
- **Evaluation:** native DeepEval `evaluate()` scores answer correctness
  and relevancy; optional faithfulness, contextual recall and precision
  run only when verified selected Knowledge passages are present.
- **Caching:** the notebook stores successful target answers under
  `rag-goldens/evaluation/responses/` while DeepEval owns metric caching
  and its reports. Changing a judge does not rerun the target. The local
  target fingerprint includes project config and the content of the
  configured system-prompt file. For changes to external Knowledge indexes,
  use `FRESH_SDK=True` or update `CACHE_EPOCH`.

The observed target pass is sequential for safe DeepEval trace scoping;
native judge calls can run concurrently.

## Privacy

Stored answers/Knowledge traces and judge requests may contain confidential
data. Keep `rag-goldens/evaluation/` private and use an approved judge
provider. There is no automatic substitution of golden reference evidence
for actually retrieved Knowledge text.
