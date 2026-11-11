# RAG Golden Generator: cross-doctrine, source-grounded questions

Produces reference questions and answers from the **original Markdown
doctrines** without querying the RAG being evaluated. Semantic processing is
performed by a checkpointed `cli-agent-flow`; the Python standard-library
exporter does only deterministic validation and output formatting.

## Architecture

1. **Inventory** all `.md` / `.markdown` source files in `doctrines/`.
   Document identities are stable path-derived slugs.
2. **Analyze each document** with `markdown_sections` (12,000 characters per
   logical section, preferentially split at headings; <=96 sections). Each
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
4. **Relate topics across documents** via batches of four profile shards (<=32 KB),
   then two further rounds of bounded grouping (five candidate responses /
   30 KB). The FINAL step also batches its input (three summaries /
   24 KB) and produces separately checkpointed registries per shard.
   Preserve singleton topics between batches to allow matching a
   concept against other documents at a later stage. Each registry shard
   selects up to 15 independently examinable document groups.
   There is deliberately no unbounded all-shard LLM aggregation.
5. **Generate one question per group** by reading ONLY bounded original
   line ranges, never feeding reference passages into the tested RAG.
   The reviewer separately reads the same authorized original passages and
   rejects ungrounded, redundant, ambiguous or single-document questions.
   Each generated question and review has a separate JSON checkpoint.
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
- `rag-goldens/state/docs/<slug>/...`: `discovery-*.json` topic
  inventories, `evidence-*.json` per-topic enrichment checkpoints,
  `scan-*.json` assembled scans and final `profiles/*.json` shards,
  plus `profile-inventory.json` containing paths only
- `rag-goldens/state/topics/...`: bounded cross-doctrine candidate batches,
  `registry-batches.json` and `registry-b0001.json` etc.
- `rag-goldens/state/draft-b0001-g0001.json`,
  `review-b0001-g0001.json`, etc.
- `rag-goldens/goldens.json` and `deepeval-goldens.json`

JSON outputs provide step-level checkpoints. Interrupted runs can be
resumed, but the flow itself is sequential (no parallel calls).

## Evaluate the generated goldens in Jupyter

After generating and exporting goldens with `export.py`, open the
**[SDK + DeepEval benchmark notebook](benchmark.ipynb)** from the workspace
root. Configure the model, paths, number of questions, judge and evaluation
threshold in the notebook's configuration cell. SDK calls and DeepEval scores
run in **separate cells**, making reruns and exploratory analysis convenient.

```bash
python -m pip install cli-agent deepeval jupyterlab ipykernel
jupyter lab flow/rag/generate_goldens/benchmark.ipynb
```

The notebook runs each question in a **fresh cli-agent SDK session**, saves
checkpointed answers and scores per golden, and provides tables for per-case
status and per-metric averages. It sends **only the golden question** to the
agent; source evidence and reference answers remain private to the judge.

DeepEval scores answer correctness and relevance by default. With the
optional Knowledge trace from **cli-agent PR #303**, the notebook
automatically receives verified selected chunks and enables faithfulness and
contextual retrieval metrics without manual instrumentation. It also
calculates deterministic initial/candidate/selection document recall against
the required sources in each golden. Reference quotations are never
substituted for actual retrieved chunks.

See [the notebook instructions](scripts/README-benchmark.md) for
configuration, checkpoint handling, retrieval-context instrumentation
and privacy caveats.

## Limitations and safety considerations

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
