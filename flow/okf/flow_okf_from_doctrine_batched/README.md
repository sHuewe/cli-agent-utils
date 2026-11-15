# Bounded separated OKF generator

Generates the **document + global-theme OKF layout** of
`flow/okf/flow_okf_from_doctrine_seperated`, using document-wide
semantic topic consolidation **before writing** final concepts.

## Prerequisite and usage

Requires the generic Flow operations from
[cli-agent PR #315](https://github.com/sHuewe/cli-agent/pull/315).
These operations work on arbitrary JSON structures: no new OKF-specific
operation is added to the runner by that PR.

```shell
cli-agent-flow validate flow/okf/flow_okf_from_doctrine_batched/flow.toml --workspace .
cli-agent-flow run flow/okf/flow_okf_from_doctrine_batched/flow.toml --workspace .
```

Input: `[vars].doctrine_path = "doctrines"` by default. Output:
`okf-batched-generated-v3/`. Private intermediate checkpoints:
`okf-batched/state-v3/`.

## Exact Golden checkpoint reuse

The new root `inventory` step matches Golden's inventory definition exactly
and reuses its original `rag-goldens/state/source-inventory.json` output.
It invokes the **original** `flow/rag/generate_goldens/flows/analyze-document.toml`
subflow under the original parent step ID `analyze_documents` (NOT `golden_profiles`). Compact completion-marker identities contain that parent namespace; changing the ID invalidates the marker lookup even when output JSON paths are identical. No copies are needed, and the per-document checkpoints are shared
at their original `rag-goldens/state/docs/<slug>/` paths.

Golden profiles serve as existing complementary analyses; they cannot
guarantee exhaustive normative/descriptive knowledge. The new OKF-specific
section sweep therefore keeps independent checkpoints.

## Local document pipeline

1. Generic `markdown_sections(always_sections=true)` builds uniform,
   contiguous source ranges, including one section for small documents.
   Target size is ~5 KB per section.
2. One bounded LLM scan per section emits source-grounded descriptive and
   normative `knowledge_items` and local `candidate_concepts`.
3. Existing `prepare_outline_tasks` and `assemble_section_outlines` run
   a small per-section metadata outline and construct a document topic plan.
   No concept Markdown is written yet.
4. Existing `doctrine_taxonomy_profile`,
   `prepare_doctrine_consolidation` (six candidates per batch) and
   `assemble_doctrine_consolidation` compare similar topics across
   different sections and verify that every original topic appears once.
5. Generic `json_join_aliases` maps each **original knowledge item** to
   its canonical topic via its `topic_key` and the consolidated
   `merged_from` aliases. Generic `json_project` maps the consolidated
   topic plan into the shape accepted by existing `group_items`. The
   latter forms bounded 12-KB concept plans and checks assignment coverage.
6. Each concept is written, verified, repaired and given its own small
   semantic manifest. Existing `verify_coverage` checks that every
   source-grounded item is documented. Concept and semantic-folder indices
   provide local navigation.

No new LLM step receives the entire original doctrine in one prompt.
Semantic grouping is still best effort: unrelated comparison batches may
contain overlapping topics.

## Global thematic pipeline

Compact manifests enter several bounded reduction rounds. Registry inputs
are deterministically limited to **five complete groups**, at most 8 KB.
The model supplies exact references to original groups; generic
`json_validate_partition` proves exhaustive, nonoverlapping coverage and
exact unions of member identities. The OKF domain's requirement of at
least two distinct source doctrines is supplied as `min_distinct=2`
and the relevant JSON paths **in the flow configuration**, not in Python.
Optional configured patterns check safe IDs and relative Markdown paths.

Every valid theme gets its own writing and verification steps. Per-shard
status reports retain unsuccessful registry, theme or navigation results.
No unbounded final LLM aggregation is required.

## Limits and invalidation

- Source/document edits and prompt/model changes require explicit checkpoint
  invalidation; document slugs alone do not detect changed contents.
- Existing `okf-batched/state/` and `state-v2/` data are not reused, because
  their internal contracts are incompatible with v3. Golden state is reused.
- A single oversized source range or JSON array entry fails rather than
  being silently truncated. The 120-second GLM provider limit is not
  guaranteed by batching; real-corpus benchmarking is still necessary.
- Generated Markdown is not automatically pruned after changed topic
  membership. Use a clean output directory for comparative runs.
- Global semantic matching is heuristic and can leave cross-shard duplicates.
- Extremely large indices may require a future deterministic index builder.
