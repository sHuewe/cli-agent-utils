# OKF from manual flow

This flow generates an OKF repository from one or more line-oriented text manuals.

## Configuration

Set the global variables in `flow.toml`:

```toml
[vars]
manual_path = "manuals"
okf_root = "okf-generated"
```

`manual_path` is workspace-relative and may point to one readable text manual or to a directory containing multiple manuals. PDFs are deliberately excluded because this flow depends on stable 1-based source line numbers.

## Pipeline and evidence strategy

The key design goal is that only the early scan phase traverses the manuals broadly. Even there, manuals are never loaded with an unrestricted full-file `read_file`: each manual is scanned through bounded `start_line`/`end_line` reads.

1. `discover_manuals` finds the configured text manuals without reading them in full.
2. `scan_manuals` iterates over the manuals and extracts candidate concepts plus exact relevant line ranges.
3. `plan_concepts` merges overlapping topics across manuals and produces the final concept list. Every concept carries its complete `evidence_ranges`.
4. `build_concepts` iterates over concepts and reads only those recorded line ranges.
5. `verify_concepts` and `repair_concepts` keep the same evidence ranges and therefore never need to reread complete manuals.
6. `additional_concepts` creates a human-editable list of topics that should be checked.
7. `assess_additional_concepts` first uses the existing concept/evidence map. For genuinely new manually requested topics it may use text search to locate evidence, but still reads only bounded ranges around matches.
8. `apply_additional_concepts` reads only the evidence ranges returned by the assessment.
9. The shared root-index and final-verification prompts finish the OKF structurally.

The important intermediate state is `state/plan.json`. For every concept it contains source evidence like:

```json
{
  "id": "c001",
  "title": "Connection configuration",
  "evidence_ranges": [
    {
      "manual": "manuals/admin-guide.md",
      "start_line": 420,
      "end_line": 487,
      "reason": "Connection properties and defaults"
    }
  ]
}
```

These ranges are 1-based and inclusive, matching the OS MCP `read_file(path, start_line, end_line)` semantics.

## Coverage

The scan explicitly inventories outward-facing functions and configuration possibilities. The planning step must map every discovered function/configuration item to at least one planned concept; concept count is not capped.

## Additional concept requests

`state/additional-concepts.json` uses `overwrite_output = false`, so it can be edited manually between runs. Each requested topic is assessed as `covered`, `not_applicable`, `extend`, or `create`.

Delete the file when you want the model to regenerate the candidate list from the current plan/results.

## Shared OKF material

`flow/okf/okf-format.md` defines the OKF format for all OKF flows. Prompts that are genuinely source-independent are stored in `flow/okf/prompts/` and reused by both the source-code and manual flows.

## Run

With the flow directory inside the workspace:

```text
cli-agent-flow run flow/okf/flow_okf_from_manual/flow.toml --workspace <workspace-root>
```

All paths are workspace-relative. The fixed `--workspace` remains the hard filesystem boundary.
