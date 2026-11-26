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

## Legacy scan route metadata

Older `scan-sNNN.json` checkpoints can lack `document_id`, `folder_id` or
`chunk_id` even though the scan prompt requests them. Such checkpoints
can be accepted by the old schema and later fail at `group_items` with
`route.document_id must be a nonempty string`.

Stop the Flow and back up `okf-batched/state-v3/`, then run the narrow
normalizer in the workspace root (use the real document slug pattern):

```powershell
py .\flow\okf\flow_okf_from_doctrine_batched\normalize_legacy_scan_route_ids.py --workspace . --document "DOCUMENT_SLUG"
```

Inspect the dry run, then apply:

```powershell
py .\flow\okf\flow_okf_from_doctrine_batched\normalize_legacy_scan_route_ids.py --workspace . --document "DOCUMENT_SLUG" --apply
```

The script uses the matching `sections.json` to validate `section_id`,
`source_path`, `start_line` and `end_line`; the documented state-directory
slug supplies `document_id` and `folder_id`; the planned section supplies
`chunk_id`. It fills **only missing/blank identity values** and rejects
conflicting existing values, unrelated schema errors, unsafe paths and
preexisting backups. Every update saves an original copy beside the file
(`.bak-pre-route-ids`). Existing scan content, items, outlines, consolidation
and assignment checkpoints are retained. `jsonschema` is required.

New scan outputs must include all three route identity fields because
`schemas/scan.schema.json` now requires them.

## Readable filenames: standalone utils publication

The generic `cli-agent-flow` remains unchanged and completes all
doctrine concepts, local `index.md` pages, global themes, and root
navigation in the checkpoint-bound `okf-batched-generated-v3/` tree.
**Only after the normal Flow succeeds** does the separate
`publish_named_okf.py` utility generate `okf-batched-published-v3/`.
This is a repository-specific postprocessing operation, not a new
`cli-agent` Flow operation and not an additional model call.

**Recommended one-command workflow** (from the workspace root):

```powershell
py .\flow\okf\flow_okf_from_doctrine_batched\run_and_publish.py --workspace .
```

The wrapper runs the original `cli-agent-flow run`, checks the process
exit status, then runs the publisher. To publish an already completed
generation without invoking the Flow again, use `--skip-flow`.

**Standalone publisher, dry-run first**:

```powershell
py .\flow\okf\flow_okf_from_doctrine_batched\publish_named_okf.py --workspace .
```

To create/replace the published tree after reviewing the preflight:

```powershell
py .\flow\okf\flow_okf_from_doctrine_batched\publish_named_okf.py --workspace . --apply
```

The script uses the existing `group.json` concept plans to identify
source files and stable concept IDs. It derives readable filenames from
scalar YAML frontmatter titles, falling back to the already planned
`group.json` titles, handles umlauts and collisions, and writes
`concept-path-map.json` with the complete original-to-published mapping.
It rewrites relative Markdown links in concepts, the local and root
`index.md` files, and the global thematic pages. Internal broken links,
unsafe source paths, duplicate destinations, and missing concept files
abort publication. Validation takes place in a separate staging directory
before the finished output directory is replaced.

**Existing generated Markdown and every source/model checkpoint remain
untouched.** The original technical filenames are retained exclusively in
`okf-batched-generated-v3/`, so Flow resume keeps working. The final
consumer-facing tree is `okf-batched-published-v3/`. Publication can
be repeated without re-running any LLM steps. Python 3.11+ and the
standard library suffice; no additional parser dependency is required.

The standalone publisher may be run after the completed Flow regardless
of whether the Flow was started via the wrapper. Never run publication
concurrently with a still-writing generation Flow.

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

The bounded section scan is **text-only**. Image-only diagrams and symbol
plates are outside its extraction scope and must be described as deferred
visual content in `warnings`, not treated as failed text sweeps when all
readable Markdown is completely extracted. A failed source read, truncated
output or omitted readable text still requires `needs_attention` and
blocks `outline_tasks`. This prompt adjustment does not add an image
processing step to this flow; visual coverage must be supplied by the
separate image-analysis workflow.

Existing `scan-sNNN.json` checkpoints remain unchanged and are reused on
resume. For a previously blocked image-only scan, back up and move only
its affected `scan-sNNN.json` out of the active state before restarting,
so the model can regenerate it under the updated prompt.

## Unused candidate aliases during source assignment

Section-level outlines may contain candidate topics without corresponding
`knowledge_items`, such as legacy placeholder topics. The semantic
consolidation retains those candidates, but the `assign` JSON join now
permits unused **mapping aliases** (`require_all_aliases = false`). The
generic join still fails on missing mappings for **any actual Knowledge
Item**, duplicate source IDs, duplicate alias declarations or missing
source records. This allows a full scan to advance without creating
unsupported knowledge from unused candidates. Later concept grouping
skips canonical topics with no assigned Knowledge Items.

Existing scan, outline, consolidation and validation checkpoints need not
be regenerated. Restart the Flow after updating this config; the failed
`assign` step can recompute from those checkpoints.

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

## Legacy root-prefixed concept manifests

Some concept manifests written before strict JSON Schema output bindings store
`concepts[*].path` with the configured OKF root prefixed, e.g.
`okf-batched-generated-v3/doctrines/<slug>/<concept>.md`, instead of the
canonical `doctrines/<slug>/<concept>.md`. These JSON checkpoints are structurally
valid but will now fail the canonical manifest path enum.

**Do not delete the concept build/verify/repair checkpoints or loosen the
canonical manifest schema.** The global topic reduction expects relative
paths without the OKF output root.

Stop the flow and back up your full state directory first. From the
repository workspace, inspect a dry run:

```powershell
python flow/okf/flow_okf_from_doctrine_batched/normalize_legacy_manifests.py --workspace .
```

To apply the *exact* plan-based path correction after reviewing the preview:

```powershell
python flow/okf/flow_okf_from_doctrine_batched/normalize_legacy_manifests.py --workspace . --apply
```

The script derives the OKF root from the existing flow's
`[vars].okf_root` (or `--okf-root` if explicitly supplied). It reads
`group.json` from each document state as the authoritative mapping of
concept IDs to canonical paths. For a manifest, it accepts only that exact
canonical path or the same path prefixed by that one configured OKF root;
anything else fails closed before changes begin. It rewrites **only**
`concepts[0].path`, preserving all other JSON values, and creates a
`.json.bak-pre-root-normalize` copy next to each modified file. No
other checkpoint files, Markdown sources or generated concept files are
modified. Re-running is idempotent.

Run the main OKF flow **after** the migration (not concurrently). Existing
checkpoints remain available for normal reuse. Since only the manifest path
changes, the old generated Markdown is untouched.

## Legacy verify findings with empty item IDs

Older `concept-*-verify.json` checkpoints can contain
`findings[*].item_id: ""`. The current concept verify JSON Schema permits
an omitted `item_id` but forbids empty strings. To keep other verified work,
stop the Flow and back up `okf-batched/state-v3/`. Preview the narrowly
scoped normalization from the workspace root:

```powershell
py .\\flow\\okf\\flow_okf_from_doctrine_batched\\normalize_legacy_verify_findings.py --workspace .
```

After reviewing the changes, apply them:

```powershell
py .\\flow\\okf\\flow_okf_from_doctrine_batched\\normalize_legacy_verify_findings.py --workspace . --apply
```

The script requires the Python `jsonschema` package. It inspects every
`concept-*-verify.json` in the existing document state and removes **only**
`item_id` keys whose value is exactly `""` from the `findings` array.
It validates every changed checkpoint against the current
`schemas/concept-verify.schema.json` before writing any files. Other schema
violations abort the migration rather than being silently fixed. On apply,
each original JSON file is preserved next to the checkpoint with suffix
`.bak-pre-empty-item-id-normalize`, and updates are written using a temporary
file followed by an atomic replacement. Existing backups block applying any
changes. Rerunning after successful migration is a no-op. The procedure
does not touch concept Markdown, build/repair checkpoints or source doctrines.

## Scoped concept writes and deterministic state recovery

Requires the Flow step tool-policy support from
[cli-agent](https://github.com/sHuewe/cli-agent) (separate feature PR).
Build and repair now offer ONLY `os__read_file`, `os__write_file`
(and `os__make_directory` for build). The OS server enforces a
single exact write target: `<okf_root>/<concept.path>`. The build
step may create only the target's parent directory. The verify step
only receives `os__read_file`. Other tools are not advertised and
are rejected even if the model attempts an unadvertised call.
The existing model step IDs, output paths, and JSON checkpoints are
unchanged.

Historical runs may already have written a different concept's
file. A JSON-schema-valid response alone cannot prove the generated
Markdown is correct. Stop the Flow and **back up the workspace** before
auditing existing state:

```powershell
py .\flow\okf\flow_okf_from_doctrine_batched\audit_concepts.py --workspace .
```

The dry-run report compares the planned group concept IDs/paths with
build, verify, repair, manifest and repair.changed_paths values,
checks for missing generated Markdown and marks cross-written target
owners as potentially overwritten.

If historical repair results frequently claim changes to navigation
`index.md` files (including the root `okf-batched-generated-v3/index.md`),
add `--ignore-index` to omit findings caused solely by valid reported
index paths within the configured OKF output root:

```powershell
py .\\flow\\okf\\flow_okf_from_doctrine_batched\\audit_concepts.py --workspace . --ignore-index
```

This is an **audit filtering option only**: it does not modify or protect
`index.md`, does not suppress unrelated problems on the same concept,
and is not proof that historical index writes were harmless. If applying
quarantine based on this filtered report, also pass `--ignore-index`
alongside `--apply` and the explicit `--select` arguments.

After inspecting the report, optionally move ONLY affected concept
checkpoints, affected canonical Markdown files and document-level
dependent coverage/navigation checkpoints into
`okf-batched/recovery-v3/`:

```powershell
py .\flow\okf\flow_okf_from_doctrine_batched\audit_concepts.py --workspace . --apply --select "<SOURCE_SLUG>:s003-t001" --select "<SOURCE_SLUG>:s006-t001" --select "SOURCE_SLUG:s003-t001" --select "SOURCE_SLUG:s006-t001"
```

The selection must include all affected IDs for a cross-concept incident (such as both `s003-t001` and `s006-t001`); otherwise the script refuses to proceed. Replace `SOURCE_SLUG` with the document directory name reported by the audit.\n\nThe source slug must match the audit report; the example IDs must be reviewed and adjusted. Both IDs involved in a cross-concept incident are required.\n\nThis is a **quarantine**, not a deletion. It refuses conflicting
recovery destinations. A historical malformed concept directory such as
`s013-t006.md/s013-t006.md` can also be quarantined as a unit, but only
if the outer `.md` directory contains exactly one regular file with
the same basename. Symlinks, unrelated files and complex directory
contents fail closed before any moves; inspect such cases manually.
All other per-concept checkpoints, group plans
and initial document analysis remain unchanged. The relocated
checkpoints are absent for the next resume, so the affected concepts
are generated again using the scoped writes.

**Important:** The audit checks structural evidence and path consistency,
not semantic correctness. A concept that was overwritten but never
reported its writes in JSON may require an additional semantic audit.
If global theme reduction has already completed, invalidate dependent
global artifacts separately before publishing them.

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
