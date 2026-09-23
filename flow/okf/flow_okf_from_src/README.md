# OKF from source flow

This flow creates an OKF repository from source code in several bounded stages instead of asking one agent call to understand and write the complete repository.

## Structure

1. `inventory` explores the source tree and identifies the relevant modules, entry points, interfaces, data flows and cross-cutting concerns.
2. `plan` turns that inventory into an explicit OKF directory/concept plan.
3. `initialize_okf` creates the target directory structure.
4. `create_concepts` runs once per planned concept. Every iteration gets a fresh agent session, inspects the actual source as needed and writes exactly one OKF concept.
5. `create_indexes` builds the mandatory root `index.md` and progressive indexes for planned subdirectories.
6. `verify` checks OKF validity, linkability, plan completeness and source fidelity.
7. `repair` fixes only concrete findings from verification.
8. `final_verify` performs a read-only final check.

The flow uses the global retry policy in `flow.toml` for transient model failures.

## Configure

Edit the global variables at the top of `flow.toml`:

```toml
[vars]
source_root = "src"
okf_root = "okf-generated"
```

Both paths are interpreted relative to the fixed workspace used for `cli-agent-flow`.

`source_root` is deliberately a **prompt-level logical scope**, not an additional filesystem security boundary. `workspace_access = "read"`/`"write"` still exposes the fixed workspace to the built-in OS MCP according to the normal cli-agent rules. For a hard boundary, choose `--workspace` so that it contains only material the agent is allowed to access.

The generated repository root must remain inside that workspace. `okf_root` should not point into this flow's `state` directory.

## Run

When this flow folder is inside the project workspace:

```text
cli-agent-flow run flow/okf/flow_okf_from_src/flow.toml --workspace <project-root>
```

A reusable alternative is to make a common parent the workspace, for example:

```text
work/
  cli-agent-utils/
  project/
```

Then set `source_root = "project"`, choose a suitable workspace-relative `okf_root`, and run:

```text
cli-agent-flow run cli-agent-utils/flow/okf/flow_okf_from_src/flow.toml --workspace work
```

In that arrangement the workspace, not `source_root`, is the technical read/write boundary.

## Generated OKF conventions

The process intentionally creates documentation by **concept**, not one document per source file. A concept must be supported by source evidence and contains YAML frontmatter with at least a non-empty `type`. The prompts also use `title`, `description`, `tags` and `status` where appropriate. They do not claim human verification.

Every concept should include source references using workspace-relative code paths so that claims remain traceable. The root contains lowercase `index.md`, because that file is the OKF repository marker expected by cli-agent. Directory indexes use relative Markdown links so progressive OKF navigation can follow them.

## State files

Intermediate JSON outputs are written below `state/`. They make the individual stages inspectable while keeping the generated OKF separate from orchestration state. They are ignored by the local `.gitignore` in this folder.

The current flow deliberately uses `overwrite_output = true`: rerunning it re-analyzes current source instead of silently accepting stale checkpoints after the code changes.
