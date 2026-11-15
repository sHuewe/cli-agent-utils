# Bounded OKF generation with cross-section semantic consolidation

This flow produces the separated OKF layout used by
`flow/okf/flow_okf_from_doctrine_seperated`, with **document-wide semantic
topic consolidation BEFORE writing concepts**. The original Markdown
source documents and earlier OKF implementations remain unchanged.

## Requirements / run

- An installed `cli-agent` containing the opt-in Flow operations in
  [cli-agent PR #315](https://github.com/sHuewe/cli-agent/pull/315).
- The unchanged `flow/rag/generate_goldens` resources in this repository.
- Markdown doctrines below `doctrines/` (or adjust `[vars].doctrine_path`).
- A model configured for the CLI; all semantic tasks are deliberately small,
  but a 120-second per-request timeout is not mathematically guaranteed.

```sh
cli-agent-flow validate flow/okf/flow_okf_from_doctrine_batched/flow.toml --workspace .
cli-agent-flow run flow/okf/flow_okf_from_doctrine_batched/flow.toml --workspace .
```

The output repository defaults to `okf-batched-generated-v2/`. New intermediate
checkpoints reside at `okf-batched/state-v2/`; this isolates the revised
document pipeline from `okf-batched/state/` and from the older separated flow.

## Reuse existing Golden checkpoints

The root's `inventory` step is the exact same definition as in the Golden
flow, including its `rag-goldens/state/source-inventory.json` path. The
`golden_profiles` step calls the **unchanged**
`flow/rag/generate_goldens/flows/analyze-document.toml` subflow, so existing
per-document `sections.json`, `discovery-*.json`, `evidence-*.json`,
`scan-*.json` and `profiles/*.json` checkpoints can be reused at their
original paths without copying or migration.

The Golden profiles are not complete normative/descriptive coverage. A
separate ~5,000-character OKF section sweep therefore uses fresh v2
checkpoints. Golden scans are retained as independent, reusable semantic
analysis; the normative OKF sweep remains authoritative for concept coverage.
Source edits do NOT automatically invalidate path-based checkpoints; follow
the Golden flow's documented invalidation rules and remove affected v2
downstream checkpoints when sources/prompt/model change.

## Document pipeline

1. Deterministic `markdown_sections` (5,000 chars target) and
   `prepare_okf_scan_tasks` produce exact 1-based source ranges for all
   sections, including a single `direct` task for small documents.
2. An independent source-bounded LLM scan inventories EVERY normative and
   descriptive knowledge item. Each item has a source citation and a unique
   local `topic_key`. Failed/incomplete scans block later publication.
3. `assemble_okf_outline` checks full section coverage and constructs a
   compact source-local topic catalog; no concepts are written yet.
4. A compact taxonomy profile is used to choose optional semantic subfolders.
   `prepare_doctrine_consolidation` groups **six related topic candidates
   per LLM call**. The model merges semantically coherent topics from
   DIFFERENT sections; `assemble_doctrine_consolidation` deterministically
   checks that every original topic ID appears once.
5. `group_consolidated_items` maps all ORIGINAL source knowledge items onto
   their consolidated canonical topic, preserving evidence and normative
   qualifiers. Existing `group_items` splits any oversized concept into
   bounded parts (12 KB JSON evidence plan), with complete item ID mapping.
6. Each final concept is generated, reviewed and repaired independently using
   the original OKF concept prompts. `verify_coverage` checks complete
   source-item coverage; its status is also saved in a compact manifest.
7. Each concept has one tiny semantic manifest for global matching. The
   document index links actual generated concepts. Larger documents may have
   one level of semantic subfolders planned by the taxonomy.

This is a **bounded, best-effort semantic** clustering pass. Distinct
clusters that never meet in a consolidation batch may remain separate; the
deterministic checks guarantee no *identified* source topic or item is
silently discarded, not that an LLM discovers every possible synonym.

## Global themes

- Read only compact concept / coverage manifests.
- Candidate discovery and three independent reduction rounds use loss-aware
  `batch_arrays` fragmentation.
- The final registry uses `max_fragment_items=5`, `batch_size=1` and
  bounded JSON bytes. Earlier reduction rounds limit complete array entries to six per fragment. This cap counts COMPLETE group/warning entries; none
  are truncated or silently omitted to satisfy a prompt limit.
- Registry proposals cite every source group by positional
  `iNNNN-gNNNN` reference. `validate_theme_registry` rejects missing,
  duplicate, ineligible or invented groups/members. Single-source groups
  must be explicitly recorded as excluded.
- Each validated multi-document theme is built, tagged and verified in
  separate calls. The final result contains shard-level status reports,
  including navigation/registry/theme failures.

## Limitations and checkpoints

* Missing or malformed source content, overlarge indivisible knowledge
  records, incomplete coverage or invalid registry assignments fail
  explicitly rather than inventing success.
* The 120-second GLM timeout remains a provider limit. Smaller calls and
  checkpointed retries reduce its impact but cannot guarantee avoidance.
* Large indices may still need a deterministic index writer.
* Global semantic duplicates can remain across registry shards; the
  model cannot obtain a whole-corpus view in one bounded call.
* Existing v1 intermediate checkpoints are intentionally not reused:
  the new section/consolidation/generation output contracts differ.
* Generated documents are not automatically removed when a source or
  grouping changes. Use a fresh output root for a clean comparison.
