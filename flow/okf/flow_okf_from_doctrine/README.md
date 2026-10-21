# OKF from doctrine

Creates a source-grounded OKF from one or more large Markdown doctrines containing **normative** and **descriptive** material.

Set in `flow.toml`:
```toml
[vars]
doctrine_path = "doctrines"
okf_root = "okf-generated"
```

Run:
```sh
cli-agent-flow validate flow/okf/flow_okf_from_doctrine/flow.toml --workspace <workspace-root>
cli-agent-flow run flow/okf/flow_okf_from_doctrine/flow.toml --workspace <workspace-root>
```

Each file is partitioned into chapter-aware chunks (target 350 lines, hard maximum 450) and separately scanned using bounded line reads. Each chunk has a JSON checkpoint. The routing flow also handles chunks individually, allowing source inventory to remain in persisted state files. The semantic folder structure and generated concepts combine related material across doctrines.

Knowledge coverage tracks every individually identified normative rule (including scope, constraints, permissions and exceptions) and descriptive fact, definition or explanation. IDs are chunk-local in scan files, prefixed with chunk ID in routing and with document ID in concept coverage.

**Checkpoint invalidation:** Source files, paths and line ranges must remain unchanged during a resumed run. If source files change, clear the corresponding partition/scan/profile/routing checkpoints and downstream derived state. Resume is based on outputs present at run start.

Known limit: initial partitioning uses literal heading search and bounded single-line probes in an LLM step; truncated heading searches fall back to numeric boundaries. Real-world integration testing on large source documents is recommended before production use.

## Fine-grained checkpoints

Every model step, including short chunk/folder-routing and shared index/verification/split stages, now writes an individual JSON checkpoint. Shared steps use pipeline-, phase- and folder-scoped identifiers so pre/post split verification cannot reuse each other's data. Subflow invocation steps are orchestrator operations: their model steps are checkpointed individually, and their combined results are reconstructed on resume.

The link phase now calls `flow/okf/flows/link-concept.toml`, sharing the same snapshot/link/verify prompts with `flow_okf_relink`. Its checkpoint paths changed from the legacy `links-*-v3-*` names; existing legacy link checkpoints are **not** automatically reused. The old files remain untouched, but a resumed run will perform those link stages again unless migrated explicitly. Review this before resuming a partially completed doctrine run.\n\nThe shared checkpoints are stored in `flow/okf/state/fine/`; routing-stage checkpoints are stored in this pipeline's `state/fine/`. Both locations are gitignored. The concept-split discovery returns short positional IDs (c001, c002, ...), reducing long filenames even when concept titles are long. When inputs or generated OKF content changes, invalidate dependent checkpoints before rerunning. Earlier stages may otherwise legitimately resume from stale JSON.

If Windows reports a long-path error, note the **exact failing path**: a generated checkpoint file, an OKF concept output, or a `.cli-agent` diagnostic dump require different fixes. Shorter checkpoint filenames cannot by themselves guarantee Windows paths remain below system limits in a deeply nested workspace.

## Related-concept links

After concept generation, additional-concept processing, navigation creation,
and post-split folder verification, the `link_related_concepts` phase adds
**optional semantic cross-links between existing concepts**. This is distinct
from the root and folder `index.md` navigation: it links concepts directly to
other genuinely related concepts, including across semantic folders.

Processing uses a separate nested flow for **each concept**, rather than
loading a whole folder's contents into a single model context. The
post-split folder verification supplies the final sorted
`concept_paths` inventory, so newly split concepts are included. Each
concept's read-only folder `foreach` discovers candidates using each target
folder's `index.md` AND text searches limited to that folder. After folder discovery, deterministic JSON batching limits the context to at most two
folder results and 32,000 UTF-8 bytes per batch. Read-only batch-review steps
select compact relevant proposals, then one write-capable step adds as many meaningful,
nonduplicated relative Markdown links as naturally fit the existing prose,
without a fixed per-concept cap, and only edits the current concept. The new discovery, candidate-batch, read-only review and link checkpoints use `v3` output names, while new verifier results use `v4` to avoid reusing earlier link-stage outputs. An oversized individual folder result fails explicitly instead of being truncated. A full-content read-only snapshot precedes each write. Linking inserts Markdown links directly around existing phrases in normal prose,
without adding, deleting or rephrasing the original text. A separate read-only
verification step reconstructs the full original content by removing only
reported Markdown link wrappers and comparing it to the snapshot character
for character; it also validates link destinations. Uncertain or unrelated candidates may be left unlinked.

The final `post_split_final_verify` consumes all nested link-verification
results and rejects missing/failed concepts or folder mismatches. Its output
uses a NEW checkpoint filename `state/post-link-final-verification-v4.json`
so an existing pre-link final verification cannot be reused as success.

Per-concept JSON checkpoints for the shared link subflow are stored under
`state/snapshot-<folder-id>-<position>.json`,
`state/link-<folder-id>-<position>.json` and
`state/verify-<folder-id>-<position>.json`; positions come from the
**sorted** final folder concept list. Keep these checkpoints for ordinary
resume. **If the set/order of concept paths changes, invalidate the
`snapshot-*`, `link-*` and `verify-*` checkpoints for each affected
folder** before rerunning. Positional checkpoint IDs must not be reused for
a different concept. If a link-step output must be regenerated, invalidate
the matching link-verification checkpoint too.

Concept generation's `build` and `repair` steps also preapprove
`os__move_file`, `os__delete_file` and `os__copy_file` in addition to their existing tool
approvals. These are tool-wide approvals within each step, not
path-limited approvals; the runner's workspace and protected-path
restrictions still apply.

## Resumable concept splitting

The shared `flow/okf/flows/split-concept.toml` no longer makes one large
`split.apply` model call that creates all parts, rewrites the original and
updates the index. Instead it runs:

1. `assess` and `snapshot`, with the **existing checkpoint paths**.
2. `parts`, with a separate `split-part-create-v2-*.json` checkpoint for
   each of 2–6 planned focused parts (one concept per model invocation).
3. `overview`, rewriting only the original concept while preserving its
   original heading/fragment targets.
4. `index`, conservatively adding missing links without discarding prior
   navigation.
5. `apply`, now a short JSON **summary**, using the original
   `split-concept-apply-*.json` path and response schema.
6. The existing read-only `verify` checks full coverage and structure.

**Resume:** Existing `assess`, `snapshot`, `apply`, and `verify`
checkpoints are retained; do not delete them. Previously created parts
are treated as existing and never overwritten, and completed overview/index
files can be recognized by their individual stages. Newly created stage
checkpoints are independent for each concept/part. If an older `apply`
checkpoint already exists, the new stages must only accept valid existing
outputs, not recreate them. The runner remains based on immutable
run-start checkpoints; edits to checkpoint files or new files after run start
can cause an intentional safety rejection.

**Important:** Changing the split plan, its part ordering or the source
concept invalidates the corresponding new part/overview/index checkpoints.
Manual intervention is required for incomplete legacy splits whose existing
files cannot be validated against the original snapshot. Splitting large
individual parts may still hit provider limits; this change reduces per-model
scope, but cannot override gateway timeouts.

## Dynamic folder planning (v3)

The former monolithic `process_folders.<folder>.plan` step has been replaced
with bounded deterministic batches and a global compact topic registry.

1. `batch_routes` reads **the existing verified routing artifacts**, splits oversized route records at complete `candidate_concepts`,
   `knowledge_items` and `warnings` boundaries and then groups the fragments
   into batches with at most 3 records and 60,000 UTF-8 bytes per batch.
   Batch count is dynamic (one for a small folder, many for a large folder).
2. `suggest_topics` analyzes each bounded batch, producing *short* topic hints
   without copying evidence. `consolidate_topics` merges topic hints globally,
   so related knowledge from different batches can share one OKF concept.
3. `assign_topics` assigns each original, globally prefixed knowledge-item ID
   to precisely one global topic; it never copies the full item objects.
4. A deterministic `group_items` JSON operation reads the original route
   checkpoints and the assignments, rejects unknown/missing/duplicate item IDs,
   and constructs source-grounded concept plans. Oversized topics are split
   into parts at **whole-item** boundaries, capped at 60,000 bytes per concept.
5. Each concept uses the existing build/verify/repair subflow. Deterministic
   `verify_coverage` compares the planned IDs to completed repair results.
   Finalization receives compact concept summaries and coverage counts only.

**Minimum cli-agent runner:** Git commit [`efa22cd18eae8ff00d4797d3964918cbe6f8047f`](https://github.com/sHuewe/cli-agent/commit/efa22cd18eae8ff00d4797d3964918cbe6f8047f) (merge of [cli-agent PR #230](https://github.com/sHuewe/cli-agent/pull/230)), or a newer commit on `main` that includes it. The shared concept-link flow now requires `result_fallback` and `filesystem_operation.release_source_on_miss` to resume verified concepts without LLM calls and safely unlock sources after a checkpoint miss. Earlier runner capabilities, including `foreach = "input.<path>"` from PR #223, are also required; older installations may fail flow validation.
This flow requires all five deterministic JSON operations: `batch`, `flatten`,
`group_items`, `verify_coverage`, **and `batch_routes`**. PRs #220 and #221
alone do not provide `batch_routes`; versions preceding PR #222 will fail
validation with an unsupported JSON operation. Ensure your installed
`cli-agent-flow` executable uses the updated cli-agent package before running
`validate` or `run`; updating only cli-agent-utils is insufficient.

**Resume:** Routing, scanning and partitioning artifacts retain their names.
The new batching, topic, group-plan, coverage and folder-finalization checkpoints
are all `v3`-scoped. Do not reuse the earlier `folder-plan-<id>.json` as the
new plan. A changed source or route still requires invalidating its dependent
checkpoints; a checkpoint is not a live dependency tracker.

**Limits:** An individually oversized knowledge item or required route metadata fails
closed rather than being truncated. A very high number of distinct topic
suggestions can still exceed a single consolidation context; that stage
handles compact hints, not the full doctrine inventory.
