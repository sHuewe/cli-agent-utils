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
