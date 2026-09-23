# OKF from source flow

This flow creates an OKF repository from source code in scalable, partitioned stages.

## Design

The first step does not try to understand the whole repository in depth. It partitions `source_root` into independently analyzable units such as Maven/Gradle modules, npm workspaces, Python packages, services, subprojects or stable package/component boundaries.

All expensive downstream work is chained through the aggregated `iterations` output of the previous foreach step. The next step therefore does not need to know the original partition item explicitly; the iteration wrapper carries both the stable iteration `id` and that iteration's `output`.

Pipeline:

1. `partition` -> repository-level unit discovery
2. `inventory_units` -> foreach over `partition.units`
3. `plan_units` -> foreach over `inventory_units.output.iterations`
4. `build_units` -> foreach over `plan_units.output.iterations`; concepts are created as conversation turns inside the unit iteration and the final turn writes the unit index
5. `verify_units` -> foreach over `build_units.output.iterations`
6. `repair_units` -> foreach over `verify_units.output.iterations`
7. `create_root_index` -> creates the mandatory OKF root `index.md` from the aggregated unit results
8. `final_verify` -> read-only structural verification

Because every foreach step reuses `${item.id}` as its own `iteration_id`, the unit identity propagates automatically from one aggregated `iterations` array to the next.

## Configure

Edit the global variables at the top of `flow.toml`:

```toml
[vars]
source_root = "src"
okf_root = "okf-generated"
```

Both values are workspace-relative. `source_root` is a logical analysis scope; the hard filesystem boundary is still the `--workspace` supplied to `cli-agent-flow`.

## Run

When this flow directory is inside the workspace:

```text
cli-agent-flow run flow/okf/flow_okf_from_src/flow.toml --workspace <project-root>
```

For a reusable checkout next to a project, choose a common parent as workspace and set `source_root`/`okf_root` accordingly.

## Scaling behavior

The partition step should keep a small repository as one unit and split a large repository along natural project/module boundaries. If a single natural module is still too large, it may be split further along stable package/component boundaries.

Detailed source analysis is then bounded to one unit per agent iteration. No later step needs the full detailed inventory of all units in one prompt. Unit plans and build/verification results are passed through `iterations`, and the global root-index step consumes only the compact final unit results.

## Generated OKF conventions

- Root marker: lowercase `index.md`.
- Concepts use YAML frontmatter with at least a non-empty `type`; the prompts also request `title`, `description`, `tags`, and `status`.
- Concepts are organized by knowledge topic, not one file per source file.
- Claims should contain concrete workspace-relative source references.
- Internal links are relative Markdown links inside the OKF root.
- The flow does not claim human verification and does not add `verified` metadata.

## State files

Per-run JSON outputs are written below `state/` using iteration IDs, for example `inventory-backend.json`, `plan-backend.json`, `build-backend.json`, and `verify-backend.json`. They are orchestration state and are ignored by this directory's `.gitignore`.

`overwrite_output = true` is intentional so a rerun analyzes the current source rather than accepting stale checkpoints after source changes.
