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


## Resume/checkpoint behavior

All generated JSON state outputs use `overwrite_output = false` by default. A valid state file that already exists at flow start is therefore used as a checkpoint instead of being regenerated. Delete the relevant state JSON when you intentionally want that analysis step to run again.

Every flow file also has a root-level `exclude_paths = []` entry so project-specific exclusions can be configured in one obvious place and are inherited by nested flows.

## Question-driven gap flow

`flow_questions.toml` is a standalone follow-up flow for questions that the generated OKF should answer better.

The first step produces only the editable checkpoint:

```json
{"questions":["How is the software installed?","How is it operated?","Which runtime version is required?"]}
```

Normally, create or edit `state/questions.json` yourself before running. Because the first step uses `overwrite_output = false`, your questions are consumed unchanged.

Each question runs in its own nested child flow:

1. assess answerability from the existing OKF only;
2. if incomplete, locate evidence with `search_text` inside `manual_path` and read only bounded line ranges;
3. extend an existing concept or create a new concept in an existing semantic folder;
4. verify from the updated OKF alone that the question is now answerable.

Per-question state lives below `state/questions/` and is resumable. Question IDs are positional; after changing/reordering the question list, delete the corresponding per-question JSON checkpoints before rerunning.

Run it with:

```text
cli-agent-flow validate flow/okf/flow_okf_from_manual/flow_questions.toml --workspace <workspace-root>
cli-agent-flow run flow/okf/flow_okf_from_manual/flow_questions.toml --workspace <workspace-root>
```

## Post-generation concept granularity pass

After the existing final verification, the flow now performs an additional split evaluation. The phase is appended after the previous steps so existing JSON checkpoints remain reusable and a completed older run can simply continue into this new phase.

Each semantic folder is processed independently. Its direct concepts are listed, and every concept is evaluated in its own nested flow. Roughly 30-80 Markdown lines is only a soft orientation; semantic retrieval independence determines whether a split is useful.

A useful split keeps the original concept path as a concise overview and creates 2-6 focused sibling concepts in the same semantic folder. No manual is re-read during splitting and no new factual knowledge may be introduced; only already documented content and manual references are reorganized. Folder navigation is updated locally and verified again.

The question follow-up flow applies the same split evaluation to the concept touched by each question after the existing question assessment/evidence/apply/verify sequence. Existing question steps are unchanged.

