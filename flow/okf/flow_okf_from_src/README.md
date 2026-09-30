# OKF from source flow

This flow creates an OKF repository from source code with nested flows, bounded per-concept contexts, an LLM-designed semantic folder layer, and explicit completeness tracking for externally observable behavior and configuration.

## Design

The top-level flow stays deliberately small:

1. `partition` discovers independently analyzable source units.
2. `design_structure` chooses the semantic top-level OKF folders for this project. The taxonomy is not hard-coded.
3. `process_units` invokes a nested child flow once per source unit.
4. Coverage gaps and optional additional concepts are handled after the unit runs.
5. Navigation is created from compact unit results.
6. Each semantic folder is structurally verified in its own nested flow.
7. A compact final verification checks the root/navigation aggregate.

Inside each unit child, the source is inventoried exhaustively and concepts are planned against the shared semantic folder structure. Each concept is then processed by a **separate nested child flow** (build -> verify -> repair). This replaces the previous multi-turn conversation that accumulated all concepts of one unit in a single model context.

## Context-size strategy

No downstream concept run receives the full project inventory. Each concept child receives only its own plan object, including its assigned source hints and coverage items. Build, verification and repair are separate fresh agent instances.

The parent receives only a compact unit result. Large detailed inventories/plans remain in `state/` and are not copied into the later root/navigation prompts.

This design is intended to stay below the previous per-run context pressure rather than moving the same large context to a later step.

## Semantic OKF folders

The flow always creates at least one semantic folder below `okf_root`. Before concept planning, the LLM decides which folders make sense for the project and supplies routing guidance. Examples such as `domain`, `application-context`, `interfaces`, `configuration`, `operations` or `security` are examples only.

Every normal concept is placed directly below exactly one selected folder:

```text
okf-generated/
  index.md
  <semantic-folder>/
    index.md
    <concept>.md
```

Source packages/units do not determine the OKF directory layout.

## Complete function/configuration coverage

For every source unit the inventory performs an explicit sweep for:
- externally observable/callable functions and integration surfaces;
- every configuration possibility visible in the source.

Each item receives a stable ID (`fn...` / `cfg...`). The planner must assign every item to at least one concept. The item is embedded into that concept's `coverage_items`, the concept builder must document it, and the independent concept verifier checks the actual generated text. The unit coverage step then checks the item-ID set end-to-end.

This makes small configuration options and less prominent application functions first-class coverage obligations rather than optional candidate topics.

## Configure

```toml
[vars]
source_root = "src"
okf_root = "okf-generated"
```

Both are workspace-relative.

## Run

```text
cli-agent-flow validate flow/okf/flow_okf_from_src/flow.toml --workspace <project-root>
cli-agent-flow run flow/okf/flow_okf_from_src/flow.toml --workspace <project-root>
```

## State

Detailed per-unit and per-concept JSON state is kept below `flow/okf/flow_okf_from_src/state/`. It is intentionally not fed wholesale into later parent steps.


## Resume/checkpoint behavior

All generated JSON state outputs use `overwrite_output = false` by default. A valid state file that already exists at flow start is therefore used as a checkpoint instead of being regenerated. Delete the relevant state JSON when you intentionally want that analysis step to run again.

Every flow file also has a root-level `exclude_paths = []` entry so project-specific exclusions can be configured in one obvious place and are inherited by nested flows.

## Question-driven gap flow

`flow_questions.toml` is a standalone follow-up flow for questions that the generated OKF should answer better.

The first step produces only this editable checkpoint format:

```json
{"questions":["How is the software installed?","How is it operated?","Which runtime version is required?"]}
```

In normal use, create or edit `state/questions.json` yourself before running the flow. Because the first step uses `overwrite_output = false`, your list is consumed unchanged.

Each question then runs in its own nested child flow:

1. assess the answerability from the existing OKF only;
2. if coverage is incomplete, collect targeted evidence from `source_root`;
3. extend an existing concept or create a new concept in an existing semantic folder;
4. verify from the updated OKF alone that the question is now answerable.

Per-question state is stored under `state/questions/` and is resumable as well. Question iteration IDs are positional, so if you change or reorder `state/questions.json` after some questions have already been processed, delete the corresponding `state/questions/*.json` files before rerunning.

Run it with:

```text
cli-agent-flow validate flow/okf/flow_okf_from_src/flow_questions.toml --workspace <project-root>
cli-agent-flow run flow/okf/flow_okf_from_src/flow_questions.toml --workspace <project-root>
```
