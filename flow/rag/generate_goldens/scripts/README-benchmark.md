# End-to-end cli-agent SDK / DeepEval RAG benchmark

This benchmark evaluates the **real agent pipeline** rather than its golden generator.
It reads the source-verified golden JSON written by export.py and asks each
question through cli-agent's Python SDK. Only golden.input is sent to
Agent.ask(): **no reference answer, evidence quotation, or source path is
injected into the evaluated agent**.

Two independently resumable phases:

1. **SDK run** — fresh AgentBuilder session for every golden. Collect answer,
   tool-call names/statuses and durations, elapsed time and provider-reported
   token usage. Save individual JSON checkpoints under
   rag-goldens/evaluation/responses/.
2. **DeepEval** — score each saved response against the independently generated
   expected_output. By default:
   - GEval AnswerCorrectness checks factual accuracy, completeness and
     multi-document reasoning.
   - AnswerRelevancyMetric checks whether the answer addresses the question.
   - Only with **real observed retrieval chunks**, optionally score
     FaithfulnessMetric, ContextualRecallMetric and ContextualPrecisionMetric.
   Save scores and reasons per golden and aggregate into summary.json.

## Installation

Python 3.11+ with cli-agent and DeepEval:

~~~sh
python -m pip install cli-agent deepeval
~~~

For Chroma vector retrieval, install cli-agent[rag] and configure your
existing collection. For OKF knowledge configure the normal cli-agent OKF
settings. This benchmark does NOT build or alter the RAG index.

DeepEval's LLM-as-a-judge metrics require a separately configured judge
model, often via OPENAI_API_KEY. Use --judge-model to select a judge
supported by your DeepEval installation. The judge is independent of the
cli-agent model; sending reference answers and actual answers to the judge
may have confidentiality implications. Review DeepEval's environment and
privacy settings before using sensitive documents.

## Examples

Execute all goldens with your existing cli-agent config and optional admin
config (from workspace root):

~~~sh
python flow/rag/generate_goldens/scripts/benchmark.py \
  --phase all \
  --goldens rag-goldens/goldens.json \
  --workspace . \
  --config config.toml \
  --admin-config admin_config.toml \
  --threshold 0.7
~~~

Smoke-test three goldens, then evaluate the stored responses:

~~~sh
python flow/rag/generate_goldens/scripts/benchmark.py \
  --phase run --limit 3 --config config.toml --workspace .

python flow/rag/generate_goldens/scripts/benchmark.py \
  --phase evaluate --limit 3 --config config.toml --workspace .
~~~

- --phase run: execute only cli-agent; DeepEval is not imported.
- --phase evaluate: score only existing responses without running cli-agent.
- --phase all: run then evaluate sequentially (default).
- --limit N: process just first N goldens.
- --timeout 600: limit each agent.ask() to 600 seconds. The start/close
  operations are not included in that timeout.
- --fresh: rerun even if compatible checkpoints exist.
- --approve-tool server__tool: exact-name preapproval, may be repeated;
  the SDK still enforces admin policy and capability restrictions.
- Default output directory: rag-goldens/evaluation.
- Exit code 1: at least one failed/unevaluated case. Low metric scores are
  recorded as failures in summary.json but do not signal an execution error.

Without --config the SDK uses the standard user config, and without
--admin-config it loads the normal machine-wide admin policy. If the admin
file does not exist, the restrictive SDK default policy applies. The agent
is configured with workspace_access="none" for evaluation to avoid granting
arbitrary workspace tool reads; configure the read-only knowledge backend
(OKF or vector) explicitly in the project config.

Each golden is handled by a fresh Agent instance (no conversation, evidence
or prior approval leakage). Failed calls keep an error checkpoint containing
only the error type, never raw exception text.

## Reproducibility and resuming

Compatible response checkpoints are reused automatically. The fingerprint
includes golden content, project and admin config hashes, the optional
workspace .cli-agent/project.toml, workspace path, preapproved tool names
and runner version. Scoring checkpoints additionally track answer hash,
judge identity, threshold and observed retrieval chunks. Use --fresh or
a new output directory after changing the *underlying knowledge corpus*,
model weights or live MCP implementations: these external changes are not
detectable by configuration hashing alone.

Evaluation JSON may contain source-derived or sensitive answers, so keep
the output directory out of public git commits.

## Optional retrieval metrics (not automatic)

AgentResult from cli-agent SDK exposes tool-call names/statuses but not
the exact retrieved RAG passages. Retrieval metrics MUST NOT be calculated
from golden.evidence quotes or deepeval-goldens.json context, as those are
REFERENCE evidence rather than actual results.

If your RAG backend is instrumented, supply a JSON mapping of *observed*
chunks generated for the same run:

~~~json
{
  "b0001-g0001": {
    "runner_sha256": "the full runner fingerprint printed at launch",
    "chunks": [
      "first chunk actually retrieved for this question",
      "second chunk actually retrieved for this question"
    ]
  }
}
~~~

Pass --retrieval-context-file observed.json during --phase evaluate or all.
If the observed retrieval context is empty, only answer metrics are run.
When no such file is provided, faithfulness and contextual retrieval metrics
remain disabled. Each metric in the summary reports a score **and sample
count**, so missing retrieval coverage is visible.

Source hit-rate or MRR needs original source IDs from the retriever; the SDK
tool-call summaries alone do not provide this.

## Interpretation

This evaluates the full question-answering behavior but by default cannot
separate retrieval failures from reasoning failures. Judge scores have
variance; keep the judge model and metric settings stable when comparing
runs. Human review of a subset of goldens and evaluations remains useful.
