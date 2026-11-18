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

## Native JSON Schema contracts (checkpoint-compatible)

The OKF pipeline now uses the optional JSON Schema output contracts added
in [cli-agent PR #317](https://github.com/sHuewe/cli-agent/pull/317).
Each model-producing step points to a small workspace-local Draft 2020-12
schema under `schemas/`. The runner includes the schema in the model's
final-answer requirements and validates JSON **before** creating a new model
output checkpoint. Invalid fresh responses can use the existing in-context
JSON correction and configured `json_restart_attempts` mechanisms.

For per-concept build, verify, repair and manifest generation, dynamic schema
enum bindings additionally enforce the **exact** planned `concept_id`,
relative concept `path`, source slug and source path. These values are
forwarded as single-element arrays from existing parent Flow inputs; they are
not inferred by the LLM. The existing deterministic folder-ID membership
validator is retained because it handles both the nonempty taxonomy case
and an explicitly empty taxonomy permitting a null folder ID.

**Resume compatibility**: All prior model step IDs, prompt files, iteration
IDs, output paths and `overwrite_output` settings remain unchanged. All
existing `consolidation-cNNNN.json`, per-concept and Golden checkpoints
stay in place. The runner now checks **reused** JSON model checkpoints against
their declared schemas (and effective dynamic enums), too. Schemas are
deliberately tolerant of previously accepted additional properties and
historical nonstandard status strings. If an old checkpoint is genuinely
incompatible, execution stops with a schema error; it is **never silently
deleted, overwritten or regenerated**. Inspect and selectively repair such
a checkpoint before resuming. No state directory reset is intended.

JSON Schemas validate response shape and identity, **not source semantics,
coverage completeness, file writes, or whether an LLM actually used
`os__read_file`**. The existing deterministic coverage/partition/assignment
checks and reading-based content verification remain necessary.

## Deterministic per-batch membership check and repair

Requires [cli-agent PR #316](https://github.com/sHuewe/cli-agent/pull/316)
in addition to the previously merged generic Flow operations.

The **existing** `consolidate` step, its iteration IDs and
`consolidation-cNNNN.json` files are kept unchanged, so completed model calls
remain cached. A new `validated_batches` subflow checks the result of each
batch against the authoritative `taxonomy.json` using the generic
`json_validate_allowed_values` operation. It compares:

- `allowed_path = "/folders/*/id"` from the taxonomy.
- `values_path = "/groups/*/folder_id"` from the original batch JSON.

When folders are defined, every group must use an allowed folder ID; when
the allowed list is empty, `folder_id: null` is permitted.

A valid batch passes through without a model call. An invalid batch produces
a report with precise errors and the original JSON object. Only that batch
is sent to the small `03b_repair_folders.md` LLM prompt, which must change
**only** invalid folder references. The repaired JSON is checked a second
time with `on_invalid = "raise"`, then passed to the original
`assemble_doctrine_consolidation`. Missing or still-invalid references
stop the flow at the offending batch rather than failing at the end of
the entire document. All checkpoints of prior stages are retained.

For an existing corpus, the additional validation and conditional repair
results are written into separate `validation-cNNNN.json`,
`consolidation-repaired-cNNNN.json` and `revalidation-cNNNN.json` files
under the document's existing `okf-batched/state-v3/docs/<slug>/` directory.
Existing scan and consolidation JSON checkpoints are not overwritten.

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
