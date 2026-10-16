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
