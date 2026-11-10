# Cross-document RAG goldens (experimental)

This tool generates **reference questions from original Markdown doctrines**,
not from the RAG retriever under evaluation. It intentionally creates questions
requiring information from two *different* original documents, including a
grounded expected answer and exact source quotations. The evaluated RAG should
receive **only** `input` (the question). Its retrieval and response are
generated independently for DeepEval.

## Run

Use Python 3.11+ from the repository/workspace root containing `doctrines/`.
The helper scripts use only the Python standard library.

```sh
python flow/rag/generate_goldens/scripts/prepare.py --workspace . \
  --source-dir doctrines --max-packs 24
cli-agent-flow validate flow/rag/generate_goldens/flow.toml --workspace .
cli-agent-flow run flow/rag/generate_goldens/flow.toml --workspace .
python flow/rag/generate_goldens/scripts/export.py --workspace .
```

Outputs:

- `rag-goldens/packs/pack-p*.json`: at most 12 KB each, containing two
  bounded, semantically similar, different-doctrine source excerpts.
- `rag-goldens/manifest.json`: source document SHA-256 fingerprints and pack IDs.
- `rag-goldens/state/draft-*.json` and `review-*.json`: independently
  checkpointed question-generation and adversarial-review steps.
- `rag-goldens/goldens.json`: validated benchmark with question, answer,
  exact source metadata and source hashes.
- `rag-goldens/deepeval-goldens.json`: DeepEval-oriented `input`,
  `expected_output`, `context` (evidence text for offline grading).
  Do **not** pass `context` to your RAG when invoking it.

The pipeline deliberately **does not run RAG or DeepEval**. DeepEval is the
external evaluator; invoke your actual RAG with each golden's `input`, collect
its `actual_output` and `retrieval_context`, then evaluate those with
DeepEval's faithfulness/answer correctness/contextual metrics. The generated
`context` is *reference evidence*, not the retrieved context.

## Bounded execution and reproducibility

- `prepare.py` partitions original Markdown into line-aligned windows
  (default at most 2,400 characters), chooses similar windows from distinct
  documents with deterministic TF-IDF cosine scoring, caps reused windows and
  document-pair counts, and creates at most 24 packs by default.
- Each pack is processed independently by one generator and one reviewer.
  Both see at most one pack, **never the whole corpus**. Both can reject.
- Every JSON result has an independent checkpoint; rerun the flow after a
  timeout to reuse successful prior outputs. Flow retry policy handles transient
  LLM errors. The runner executes sequentially, not in parallel.
- `export.py` deterministically checks pack IDs, two-source citations, quoted
  substrings and original-file hashes; it rejects stale sources, invalid or
  missing reviews, and duplicates. There is no unbounded final LLM reduction.

**Checkpoint invalidation:** Each pack's filename and inventory slug change
when any referenced source file changes. Do not edit the scripts or prompts
during a running flow. On prompt/model changes, remove the existing
`rag-goldens/state/draft-*.json` and `review-*.json` to force regeneration.
The exporter refuses documents changed since preparation, but it is **not**
a proof that a reviewer judged correctly. Human spot-checking of accepted
goldens remains recommended.

The source corpus should be the *original* doctrines, not generated OKF/RAG
chunks, unless you explicitly want to benchmark that downstream representation.
Input supports `.md` and `.markdown` only; convert other document types first.

## Limitations

- Lexical overlap determines candidate pairs; semantically related passages
  without shared terminology may be missed. It is a scalable **candidate
  selection heuristic**, not an oracle for document necessity.
- Very long single lines (> window size), source files over 8 MB, or extremely
  large corpora fail explicitly instead of silently truncating source context.
  For huge corpora, split the corpus into directories and run separately.
- Document necessity is assessed by an LLM reviewer; exact quote matching
  alone cannot prove entailment. Human validation is needed for high-stakes use.
- Not every pair yields a valid multi-document question. A high rejection rate
  can be expected and must not be silently converted into weaker examples.
