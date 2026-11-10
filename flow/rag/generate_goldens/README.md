# RAG Golden Generator: cross-doctrine, source-grounded questions

Produces reference questions and answers from the **original Markdown
doctrines** without querying the RAG being evaluated. Semantic processing is
performed by a checkpointed `cli-agent-flow`; the Python standard-library
exporter does only deterministic validation and output formatting.

## Architecture

1. **Inventory** all `.md` / `.markdown` source files in `doctrines/`.
   Document identities are stable path-derived slugs.
2. **Analyze each document** with `markdown_sections` (28,000 characters per
   logical section, preferentially split at headings; <=96 sections). Short
   documents are scanned directly. Each larger section gets its own bounded,
   resumable LLM step. Extract subjects, aliases, concrete claims, qualifiers,
   exact source path and inclusive line intervals.
3. **Consolidate per document** in two layers of JSON batches (4 scans at
   most and 32 KB per batch, then 4 partial summaries and 30 KB). Produce a
   compact per-document topic profile with evidence. No prompt receives all
   section texts of a document. One small final per-document pass follows.
4. **Relate topics across documents** via batches of four profiles (<=32 KB),
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
- `rag-goldens/state/docs/<slug>/...`: per-section scans and consolidated
  doctrine topic profiles
- `rag-goldens/state/topics/...`: bounded cross-doctrine candidate batches,
  `registry-batches.json` and `registry-b0001.json` etc.
- `rag-goldens/state/draft-b0001-g0001.json`,
  `review-b0001-g0001.json`, etc.
- `rag-goldens/goldens.json` and `deepeval-goldens.json`

JSON outputs provide step-level checkpoints. Interrupted runs can be
resumed, but the flow itself is sequential (no parallel calls).

## Limitations and safety considerations

- **Source edits require checkpoint invalidation.** The runner uses stable
  path-based IDs and saved outputs. If original files change or prompts/models
  are changed, delete the affected `rag-goldens/state` before regenerating
  the benchmark. The exporter checks citations against *current* source text
  and stores current SHA-256; it cannot prove unquoted parts of a source
  stayed unchanged during generation.
- **Bounded, not guaranteed exhaustive.** Each scan and each global stage
  imposes limits, reporting `needs_attention` for incomplete coverage.
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
- **Export status.** `needs_attention` in any registry shard is preserved
  in the export summary. A valid registry with zero eligible groups produces
  empty JSON benchmark arrays. Missing registry shards remain hard errors;
  missing/rejected individual questions are counted. Duplicate question texts
  are deduplicated across all shards.
- **Cross-shard scope.** A group created only by combining topics from
  different final registry shards may be missed. This bounded design favors
  reliable completion over a claim of globally exhaustive matching. The
  registry count and `needs_attention` flags should be considered when
  reviewing the resulting benchmark.

There is no TF-IDF pairing stage and no mandatory `prepare.py` step.
