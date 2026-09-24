# OKF from source flow

This flow creates an OKF repository from source code in scalable, partitioned stages.

## Design

The first step does not try to understand the whole repository in depth. It partitions only the configured `source_root` into independently analyzable units such as applications, services, major packages, subprojects represented below the source root, or stable component boundaries. It is explicitly instructed not to inspect files outside `source_root`.

All expensive downstream work is chained through the aggregated `iterations` output of the previous foreach step. The next step therefore does not need to know the original partition item explicitly; the iteration wrapper carries both the stable iteration `id` and that iteration's `output`.

Pipeline:

1. `partition` -> source-root-local unit discovery
2. `inventory_units` -> foreach over `partition.units`; records external functions and configuration options explicitly
3. `plan_units` -> foreach over `inventory_units.output.iterations`; maps every external function/configuration option to one or more planned concepts
4. `build_units` -> foreach over `plan_units.output.iterations`; concepts are created as conversation turns inside the unit iteration and the final turn writes the unit index
5. `verify_units` -> foreach over `build_units.output.iterations`
6. `repair_units` -> foreach over `verify_units.output.iterations`
7. `additional_concepts` -> creates an editable JSON list of additional concept requests
8. `assess_additional_concepts` -> foreach request: decides `covered`, `not_applicable`, `extend`, or `create`
9. `apply_additional_concepts` -> foreach assessment: performs only the required change
10. `create_root_index` -> shared prompt creates the mandatory OKF root `index.md`
11. `final_verify` -> shared read-only structural verification

Because every foreach step reuses `${item.id}` as its own `iteration_id`, identity propagates automatically through each chained `iterations` array.

## Configure

Edit the global variables at the top of `flow.toml`:

```toml
[vars]
source_root = "src"
okf_root = "okf-generated"
```

Both values are workspace-relative. `source_root` is a logical analysis scope; the hard filesystem boundary is still the `--workspace` supplied to `cli-agent-flow`. The partition/inventory/coverage prompts nevertheless explicitly forbid source inspection outside `source_root`.

## Run

When this flow directory is inside the workspace:

```text
cli-agent-flow run flow/okf/flow_okf_from_src/flow.toml --workspace <project-root>
```

## Scaling and coverage

The partition step should keep a small source tree as one unit and split a large source tree along natural boundaries visible inside `source_root`. File count is only a soft signal; around 50-100 relevant source files the partitioner explicitly checks whether a meaningful split exists.

Within every unit, completeness has priority for outward-facing behavior: every externally visible application function and every configuration possibility discovered by the inventory must be mapped to at least one planned concept. The normal concept-count guidance is not a cap.

## Additional concept requests

`state/additional-concepts.json` uses `overwrite_output = false` and JSON checkpoint semantics. You can edit it manually between runs and add requested topics. Each request is independently assessed against the existing OKF and source and may be classified as covered, not applicable, an extension, or a new concept.

Delete the file when you want the model to regenerate the candidate list.

## Shared OKF material

`flow/okf/okf-format.md` defines the common OKF conventions. Source-independent prompts used by more than one OKF flow live in `flow/okf/prompts/`.

## State files

Per-run JSON outputs are written below `state/` using iteration IDs. Most use `overwrite_output = true`; `additional-concepts.json` is the deliberate human-editable exception.
