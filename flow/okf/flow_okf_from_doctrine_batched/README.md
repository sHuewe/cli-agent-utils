# Bounded, checkpointed OKF generation from Markdown doctrines

This flow builds the **separated OKF layout** from
`flow/okf/flow_okf_from_doctrine_seperated`, using the small-call analysis
style of `flow/rag/generate_goldens` and a new source-complete extraction
pass. Input documents stay unchanged.

## Run

From the repository workspace:

```sh
cli-agent-flow validate flow/okf/flow_okf_from_doctrine_batched/flow.toml --workspace .
cli-agent-flow run flow/okf/flow_okf_from_doctrine_batched/flow.toml --workspace .
```

Change `[vars].doctrine_path` / `[vars].okf_root` in `flow.toml` as
required. The default generated tree is `okf-batched-generated/`.
Distinct, isolated intermediate state is under `okf-batched/state/`.
The prior separated-flow and Golden-flow files have **not** been altered.

## Exact reuse of Golden checkpoints

The new root uses the Golden generator's **identical inventory** step
(`rag-goldens/state/source-inventory.json`, refreshed each run) and
calls its existing `flows/analyze-document.toml` **without modification**.
The Golden subflow therefore reuses document-specific
`rag-goldens/state/docs/<source.slug>/sections.json`,
`discovery-*.json`, `evidence-*.json`, `scan-*.json` and final
`profiles/*.json` where they exist and satisfy normal checkpoint checks.
There is no copying, renaming, or reconstruction of old checkpoints.

The Golden profiles are **not proof of exhaustive knowledge coverage**:
Golden discovery is capped at 12 major topics per 12 KB section and can
report incomplete coverage. For OKF, a separate, smaller 5,000-character
section sweep extracts normative and descriptive items with exact line
citations. This sweep uses NEW paths, so existing Golden state is safe.
The two analyses currently run separately; Golden profiles are retained
as reusable semantic analysis, not used to assert OKF completeness.

## Processing

1. Stable recursive inventory; Golden analysis resumes from its original
   document-scoped state and keeps its established short-call processing.
2. Each original Markdown document is partitioned into sections of roughly
   5 KB. A fresh LLM scan extracts descriptive and normative knowledge items.
3. Each section produces a local route (array), compact topic plan,
   one knowledge-item assignment per item, deterministic `group_items`,
   one generated/verified/repaired concept per bounded plan, deterministic
   `verify_coverage`, and a compact section manifest.
4. The document index links actual generated concepts. The local layout is
   the original separated-flow **flat module variant**:
   `doctrines/<stable-slug>/index.md` and section-prefixed concept files.
5. Section manifests are fragmented along complete concept/warning
   boundaries. Global candidate discovery is followed by **three bounded
   reduction rounds** and separate registry shards. These preserve
   potentially matchable singleton proposals and never perform an
   unbounded final registry aggregation.
6. A theme belongs under `themen/` only when at least two distinct
   source modules support it. Theme pages link actual concept members;
   their frontmatter receives additive `theme:<id>` tags, retaining
   existing tags. Each theme receives an independent verification.
7. Root `index.md`, `doctrines/index.md` and `themen/index.md`
   provide the two navigation views of the separated OKF.

## Bounds and limitations

* A section is ~5 KB. Every LLM call uses one section, one concept,
  one document's index or a 12 KB maximum consolidation batch.
* Global stages split complete JSON array entries into 4 KB target
  fragments, at most two fragments per 12 KB batch. No content is
  intentionally truncated. An indivisible oversized item raises an error.
* Model provider timeout is 120 seconds; these limits **reduce risk**, but
  do not guarantee completion within 120 seconds. Retries do not fix
  intrinsically oversized source ranges or model outputs.
* Every section's **knowledge-item assignment** and coverage verification
  is deterministic; scan completeness is still an LLM judgment.
  If a scan reports `needs_attention`, its manifest carries that warning.
* A theme may be missed or duplicated across global registry shards.
  No single call sees the entire corpus. Registry batches must be reviewed
  before treating the thematic navigation as complete.
* Source edits, model/prompt changes or altered batching require deliberate
  invalidation of dependent `okf-batched/state/` checkpoints and the
  affected generated files. Shared Golden checkpoints follow the Golden
  flow's own invalidation rules: path slugs alone do not detect source edits.
* Document indexes and root navigation are generated with bounded
  model calls; extremely large module/theme counts can require a separate
  deterministic index-building enhancement.
* The current implementation does **not** semantic-merge separate section
  concepts within a doctrine. Section prefixes avoid name collisions,
  but related concepts from distant sections can be redundant. Its flat
  module structure is a supported variant of the target layout.
* Always inspect `needs_attention` results, source citations and the
  final OKF before using it as an authoritative reference.

