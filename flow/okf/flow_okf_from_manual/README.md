# OKF from manual flow

This flow generates an OKF repository from line-oriented text manuals while bounding individual model contexts and enforcing complete function/configuration coverage.

## Pipeline

1. `discover_manuals`: enumerate manuals.
2. `scan_manuals`: independently scan each manual with bounded line reads and inventory every user-visible function/configuration option.
3. `summarize_scans`: reduce each detailed scan to a compact semantic profile.
4. `design_structure`: let the LLM choose project-specific semantic top-level folders.
5. `route_manuals`: nested flow per manual; split its detailed scan into persisted fragments, one per semantic folder.
6. `process_folders`: nested flow per semantic folder; read only that folder's routed fragments, merge topics across manuals, plan concepts, and invoke a nested build -> verify -> repair flow per concept.
7. Run additional-concept handling, navigation creation, per-folder structural verification and a compact final root check.

The previous global planning step consumed all manual scans at once. The new folder-routing stage avoids that: no folder planner receives unrelated scan material, and each routing run sees only one manual scan. Detailed evidence remains in state files instead of being repeatedly injected into later parent prompts.

## Folder structure

The folder taxonomy is chosen by the LLM before concept planning. Every normal concept is directly inside one selected semantic folder. Names such as `domain` or `application-context` are examples, not hard-coded categories.

## Coverage

Functions use stable `fn...` IDs and configuration options `cfg...` IDs. Routed folder plans map every item to concepts and embed the exact coverage items in the concept plan. Build, verification and repair explicitly handle those items, and folder-level set checks verify that none disappeared.

## Configure

```toml
[vars]
manual_path = "manuals"
okf_root = "okf-generated"
```

PDFs remain excluded because the evidence pipeline relies on stable 1-based source line ranges.

## Run

```text
cli-agent-flow validate flow/okf/flow_okf_from_manual/flow.toml --workspace <workspace-root>
cli-agent-flow run flow/okf/flow_okf_from_manual/flow.toml --workspace <workspace-root>
```
