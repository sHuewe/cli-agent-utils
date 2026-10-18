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

The shared checkpoints are stored in `flow/okf/state/fine/`; routing-stage checkpoints are stored in this pipeline's `state/fine/`. Both locations are gitignored. The concept-split discovery returns short positional IDs (c001, c002, ...), reducing long filenames even when concept titles are long. When inputs or generated OKF content changes, invalidate dependent checkpoints before rerunning. Earlier stages may otherwise legitimately resume from stale JSON.

If Windows reports a long-path error, note the **exact failing path**: a generated checkpoint file, an OKF concept output, or a `.cli-agent` diagnostic dump require different fixes. Shorter checkpoint filenames cannot by themselves guarantee Windows paths remain below system limits in a deeply nested workspace.

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

**Minimum cli-agent runner:** Git commit [`d507ca3448c1541f3870c5dea50ba3c8fc71ad46`](https://github.com/sHuewe/cli-agent/commit/d507ca3448c1541f3870c5dea50ba3c8fc71ad46) (merge of [cli-agent PR #223](https://github.com/sHuewe/cli-agent/pull/223)), or a newer commit on `main` that includes it. This revision adds `foreach = "input.<path>"` support, used directly for the doctrine's chunk and folder routing; older runners fail validation.
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
