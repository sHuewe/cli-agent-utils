# RAG Golden Generator: cross-doctrine, source-grounded questions

Produces reference questions and answers from the **original Markdown
doctrines** without querying the RAG being evaluated. Semantic processing is
performed by a checkpointed `cli-agent-flow`; the Python standard-library
exporter does only deterministic validation and output formatting.

## Architecture

1. **Inventory** all `.md` / `.markdown` source files in `doctrines/`.
   Document identities are stable path-derived slugs.
2. **Analyze each document** with `markdown_sections` (12,000 characters per
   logical section, preferentially split at headings after at least two-thirds
   of the target; <=512 sections). Each
   section, including short direct documents, runs a *three-stage subflow*:
   a very short LLM discovery of at most 12 topic titles and their source
   line ranges; independent, checkpointed LLM enrichment of **one topic
   per call** (read only its <=50-line source span); and a tool-free assembly
   call that produces the unchanged downstream scan JSON schema. The later
   consolidation layers still handle cross-topic semantic reasoning.
3. **Consolidate per document** in two layers of JSON batches (4 scans at
   most and 32 KB per batch, then 4 partial summaries and 30 KB). Each
   final reduction writes a separate, checkpointed topic-profile **shard**
   with evidence. Before reduction, `batch_arrays` deterministically
   fragments oversized merge results at complete topic/warning boundaries
   (12 KB target, 30 KB maximum batch) without dropping evidence or warnings.
   Short documents have one direct profile. A deterministic
   file inventory collects profile paths, not topic contents. Crucially,
   there is no unbounded all-shards LLM consolidation at document level.
   The consolidation prompt propagates upstream `needs_attention` statuses and
   unresolved warnings at **both** layers, even when no topics remain.
4. **Relate topics across documents** via batches of four profile fragments
   (<=32 KB), then three further rounds of bounded grouping (two fragments / 12 KB). Large profiles are split at complete topic and
   warning boundaries; later cross-document proposals are split at complete
   group and warning boundaries. The FINAL step also batches its fragments
   (two per batch / 12 KB) and produces separately checkpointed registries
   per shard.
   Preserve singleton topics between batches to allow matching a
   concept against other documents at a later stage. Fragments retain
   source/status metadata; individual groups and their evidence are atomic.
   An indivisible oversized group still raises an explicit size error. Each registry shard
   selects up to 15 independently examinable document groups.
   There is deliberately no unbounded all-shard LLM aggregation.
5. **Generate the baseline question and up to two additional independently
   targeted questions per group**. A lightweight model call plans genuinely
   distinct answer targets from the group metadata; each variant reads ONLY
   authorized original source ranges and receives its own independent review.
   An empty variant plan is valid when the evidence supports no additional
   distinct knowledge question. All questions must assess domain knowledge,
   NOT where or in which document a fact is stated. The exporter additionally
   blocks common German/English document-identification and source-location
   formulations, even if an LLM reviewer accepted them. Baseline drafts/reviews
   remain checkpointed at their original paths; variants use separate paths.
6. **Export**, without another LLM call. `export.py` verifies approved
   reviewers, accepted checks, exact quotations within the cited original
   line ranges, valid document paths and at least two different source files.
   It generates `goldens.json` and `deepeval-goldens.json`, including source
   SHA-256 hashes computed at export time.

**The tested RAG gets only `input`**. Do not supply original passages,
`context` or the expected answer as its `retrieval_context`. For DeepEval,
collect the RAG's own answer and retrieved context, and compare these against
the reference answer, including contextual metrics where applicable.

## Run

From the workspace containing `doctrines/` and the flow files:

```bash
cli-agent-flow validate flow/rag/generate_goldens/flow.toml --workspace .
cli-agent-flow run flow/rag/generate_goldens/flow.toml --workspace .
python flow/rag/generate_goldens/scripts/export.py --workspace .
```

Set `[vars].doctrine_path` in `flow.toml` if the corpus is elsewhere in
the workspace. Python 3.11+ and cli-agent with the existing `inventory`,
`markdown_sections`, nested flows, conditional steps, and
`json_operation=batch` are required. No external Python dependencies
are needed for export. The flow does not install or run DeepEval, and the
generated data should be inspected before using it as ground truth.

## Output locations

- `rag-goldens/state/source-inventory.json`
- `rag-goldens/state/docs/<slug>/...`: unfinished sections retain
  `discovery-*.json` and `evidence-*.json` checkpoints for resumption.
  Successfully assembled sections discard those intermediates, retaining
  `scan-*.json` or `profiles/direct.json` as appropriate; final
  `profiles/*.json` shards and `profile-inventory.json` remain intact
- `rag-goldens/state/topics/...`: bounded cross-doctrine candidate batches,
  `reduce3-*.json`, `registry-batches.json` and `registry-b0001.json` etc.
- `rag-goldens/state/draft-b0001-g0001.json`,
  `review-b0001-g0001.json`, etc. (baseline, preserved)
- `rag-goldens/state/plans/plan-b0001-g0001.json`: optional extra targets
- `rag-goldens/state/variants/b0001-g0001/draft-v0001.json` and
  `review-v0001.json` (similarly for v0002)
- `rag-goldens/goldens.json` and `deepeval-goldens.json`

The root flow opts into a 600 MB startup budget for existing dynamic JSON
checkpoints (`[checkpoint].max_snapshot_bytes`); cli-agent keeps its 200 MB
default for other flows and enforces a 1 GB maximum. The Golden Flow also
raises the separately bounded dynamic-checkpoint discovery limit to 100,000
filesystem entries via `[checkpoint].max_candidates` (default 20,000,
maximum 200,000). Entries include directories and unrelated files. Discovery, evidence,
and assembly steps each permit one fresh agent run if the model still returns
invalid JSON after its normal in-context repair attempts. All other failures
remain terminal, and no completed JSON checkpoint is overwritten.

JSON outputs provide step-level checkpoints. Interrupted runs can be
resumed, but the flow itself is sequential (no parallel calls).

`scan-section.toml` opts into `[checkpoint].retain_intermediate = false`.
Each fully completed section gets a durable marker in
`.cli-agent/flow-checkpoints/`; subsequent runs skip the section without
reconstructing individual discovery/evidence steps. The runner removes only
intermediate step outputs after recording successful completion. The assembled
scan/profile stays on disk for the downstream JSON-input operations. While a
section is incomplete, its intermediate checkpoints remain available. This
feature requires a version of cli-agent supporting compact subflow checkpoints.
Changing the source corpus, prompt or model still requires checkpoint
invalidation as described below; the completion marker is also a checkpoint.

## Extending an already completed benchmark

This revision adds one more global cross-document reduction and optional
independent variants (at most two per registry group, plus the original
question). It **does not guarantee** three accepted questions per group:
unrelated or insufficiently grounded pairs must still be rejected.

To reuse expensive document and source-topic scans, preserve
`rag-goldens/state/docs/`, `profile-batches.json`,
`candidates-*.json`, `candidate-batches.json`,
`reduce1-*.json`, `reduce1-batches.json`, and `reduce2-*.json`.
Before resuming with the new pipeline, back up the existing state and delete
**downstream** `topics/reduce3-batches.json`, `topics/reduce3-*.json`,
`topics/registry-batches.json`, `topics/registry-*.json`, as well as the
old `topics/reduce3-batches.json` if present. The new registry may reassign
batch/group IDs; old baseline drafts and reviews can only be reused when their
group ID **and underlying sources** match. For reliable correctness,
also invalidate `state/draft-*.json`, `state/review-*.json`,
`state/plans/` and `state/variants/` when registry groups change. Keep
the original `goldens.json` backed up separately before re-exporting.

The exporter now reports `total_question_slots` and
`missing_variant_plans` in addition to `accepted`, `reviewed`,
`rejected` and `missing`. Missing plans are tolerated so older completed
benchmarks remain exportable, but are reported as an incomplete extension.
Export deduplicates exact normalized questions across groups and variants.
It cannot prove that two differently worded questions are semantically
distinct; the independent reviewer is responsible for that judgment.

## Evaluate the generated goldens with native DeepEval

The [benchmark notebook](benchmark.ipynb) uses
**`EvaluationDataset.evals_iterator()` to drive target execution and
evaluation**. While the iterator yields a Golden, the optional SDK method
`AgentBuilder.build_deepeval_target()` provides an observed
`target.ask(question, expected_output=...)`; it annotates the native
DeepEval trace without revealing the answer/reference to the target.

```bash
python -m pip install --upgrade cli-agent "deepeval>=4,<5" pandas jupyterlab ipykernel
jupyter lab flow/rag/generate_goldens/benchmark.ipynb
```

**Requires the companion [cli-agent SDK PR #312](https://github.com/sHuewe/cli-agent/pull/312).**
Upgrade cli-agent after merging that PR (or install its branch) before opening
the notebook. The SDK import itself does not depend on DeepEval.

The notebook configures its judge via independent `JUDGE_PROVIDER`,
`JUDGE_MODEL` and optional `JUDGE_BASE_URL`. Target model settings are not
passed to the judge. Responses are checkpointed separately from DeepEval
scoring; changing the judge replays cached answers into a native observed
trace rather than repeating expensive target questions.

DeepEval runs answer correctness/relevance inside the iterator, with optional
follow-up contextual retrieval metrics for actual, verified selected
Knowledge passages. Reference quotations from the golden dataset are NEVER
used as observed retrieval context. Initial/candidate/selection source
recall remains a deterministic, cli-agent-specific diagnostic.

See [benchmark instructions](scripts/README-benchmark.md) for architecture,
provider setup, data handling, checkpoint freshness, and limitations.

## Limitations and safety considerations

- **When switching to smaller global-reduction batches:** Existing
  `rag-goldens/state/topics/candidates-*.json` files remain usable. The
  previous `candidate-batches.json` and all downstream global reduction,
  registry, draft and review checkpoints must be invalidated because the
  batch IDs are reused with different contents. Do NOT delete
  `profile-batches.json`, `candidates-*.json`, or document profiles.
  For a safe fresh reduction, first back up `rag-goldens/state/topics/`,
  then remove `candidate-batches.json`, `reduce1-*.json`,
  `reduce1-batches.json`, `reduce2-*.json`,
  `registry-batches.json`, and `registry-*.json`, plus dependent
  `rag-goldens/state/draft-*.json` and `review-*.json` if present.
  These are **only downstream caches**, not the completed document scans.
- **Generic splitting operation.** The Flow JSON `batch_arrays` operation
  accepts configurable JSON Pointer array paths, here `/topics` and
  `/warnings`. All other fields are copied without interpretation.
  Other flows can apply it to different object-array structures.
- **Existing merge checkpoints can be reused.** The new
  `batch_topic_profiles` operation consumes existing `merged-*.json` files
  unchanged. If a previous `reduce-batches.json` checkpoint exists,
  remove just that checkpoint and downstream `profiles/reduced-*.json`
  before resuming, so the new operation runs. This avoids rerunning the
  expensive scan and merge LLM steps.
- **Scan configuration changes require checkpoint invalidation.** This
  release changes the per-section step graph and output contracts: old
  `sections.json`, `scan-*.json` and `profiles/*.json` checkpoints may
  no longer match the discovery/enrichment pipeline. Before the first run
  after upgrading, delete `rag-goldens/state`; this removes intermediate
  progress but leaves the original doctrines untouched. Do the same when
  changing `target_chars`, source files or prompts.
- **Source edits require checkpoint invalidation.** The runner uses stable
  path-based IDs and saved outputs. If original files change or prompts/models
  are changed, delete the affected `rag-goldens/state` before regenerating
  the benchmark. The exporter checks citations against *current* source text
  and stores current SHA-256; it cannot prove unquoted parts of a source
  stayed unchanged during generation.
- **Bounded, not guaranteed exhaustive.** Discovery reports at most 12
  distinct major topics and at most 50 source lines per candidate. If
  relevant topics or dispersed evidence exceed those bounds, it must
  report `needs_attention` rather than inventing missing information.
  The assembly step must propagate any such status and unresolved warnings.
  More small LLM calls may incur more cost and latency overall; this design
  aims to reduce per-request generation time, not guarantee that the
  provider can never time out. Each global stage also imposes limits.
  Large individual model JSON outputs may exceed the 30–32 KB batch bound:
  this is a hard failure to investigate, not silently truncated data.
  Topic discovery is heuristic and may miss distant connections, even with
  the later reductions. The reviewer is an LLM, not a correctness oracle.
- **Large or abnormal documents.** `markdown_sections` rejects oversized
  sources (>8 MB), huge lines and >96 sections. Documents that cannot fit
  under the section limits need an explicit split, not an unbounded context.
- **Review isolation.** Generated answers are evaluated with ORIGINAL source
  ranges, not retrieval results. Source passages are untrusted and should
  never be interpreted as executable instructions. Prompts limit tool access.
- **Aggregate manifest size.** `registry-batches.json` contains the
  complete bounded batch inventory and may legitimately exceed the 4 MB
  limit used for individual JSON results. Its dedicated export limit is
  32 MB (up to 1,000 batches), while each individual registry input batch
  remains limited to 24 KB. An oversized aggregate still fails explicitly.
- **Export status.** `needs_attention` and warnings from the final
  reduction inputs are carried through by prompt and checked deterministically
  against the `registry-batches.json` artifact at export. The export summary
  records `registry_status`, the number of incomplete upstream batches and a
  bounded sample of warnings. A valid registry with zero eligible groups
  produces empty JSON benchmark arrays **but retains the incomplete status**
  if any upstream input was incomplete. Missing registry shards remain hard
  errors; missing/rejected questions are counted, and duplicate questions
  are deduplicated across all shards.
- **Cross-shard scope.** Themes in different per-document profile shards
  and final registry shards may not be fully deduplicated or paired. This
  bounded design favors reliable completion over a claim of globally
  exhaustive matching. Review the resulting candidate diversity and
  `needs_attention` status, and invalidate stale outputs on source changes.
  The profile directory is scanned afresh each run: old, unproduced shard
  files are deliberately not accepted by the flow's secure JSON-input reads.

There is no TF-IDF pairing stage and no mandatory `prepare.py` step.

The scan assembly checkpoint template is anchored under `rag-goldens/state/docs/`
(instead of an unconstrained output-path placeholder), so it cannot match
static global-topic checkpoint paths. Existing per-document scan/profile
checkpoint filenames remain unchanged and reusable.
