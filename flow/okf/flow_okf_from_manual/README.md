# OKF from manual flow

This flow generates an OKF repository from line-oriented text manuals while bounding individual model contexts and enforcing complete function/configuration coverage.

## Pipeline

1. `discover_manuals`: enumerate manuals.
2. `scan_manuals`: partition each manual into bounded, chapter-aware chunks (350-line target, 450-line hard maximum); inventory each chunk independently with its own JSON checkpoint, then create one compact per-manual profile.
3. Compact chunk profiles are consolidated into a small per-manual semantic profile, retaining the authoritative chunk list.
4. `design_structure`: let the LLM choose project-specific semantic top-level folders.
5. `route_manuals`: nested flow per manual and per chunk; route chunk inventories into persisted fragments, one per chunk and semantic folder.
6. `process_folders`: nested flow per semantic folder; read all expected chunk-route fragments for that folder, merge topics across manuals, plan concepts, and invoke a nested build -> verify -> repair flow per concept.
7. Run additional-concept handling, navigation creation, per-folder structural verification and a compact final root check.

The previous per-manual scan consumed entire long source files in one agent session. The new folder-routing stage avoids that: no folder planner receives unrelated scan material, and each routing run sees only one chunk inventory. Detailed evidence remains in state files instead of being repeatedly injected into later parent prompts.

## Folder structure

The folder taxonomy is chosen by the LLM before concept planning. Every normal concept is directly inside one selected semantic folder. Names such as `domain` or `application-context` are examples, not hard-coded categories.

## Coverage

Functions use chunk-local `fn...` IDs and configuration options `cfg...` IDs. Routed item IDs are prefixed with the chunk ID, and global coverage IDs are prefixed with the manual ID, e.g. `m001:c002:fn003`. Routed folder plans map every item to concepts and embed the exact coverage items in the concept plan. Build, verification and repair explicitly handle those items, and folder-level set checks verify that none disappeared.

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

Most generated JSON state outputs use `overwrite_output = false`. A valid checkpoint present at run start is reused. To prevent the chunk-based implementation from loading incompatible pre-chunk results, all schema-dependent manual pipeline outputs use **v2 filenames** (document profile, structure, folder planning, concepts, coverage, folder summaries and downstream verification). The discovery checkpoint `state/manuals.json` is unchanged; delete it if the source document list changes. New v2 checkpoints can be resumed normally.

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

After the existing final verification, the flow now performs an additional split evaluation. The split phase remains after final verification. Pre-chunk planning and concept checkpoints deliberately cannot be reused by the chunk-based pipeline because their coverage IDs are incompatible.

Each semantic folder is processed independently. Its direct concepts are listed, and every concept is evaluated in its own nested flow. Roughly 30-80 Markdown lines is only a soft orientation; semantic retrieval independence determines whether a split is useful.

A useful split keeps the original concept path as a concise overview and creates 2-6 focused sibling concepts in the same semantic folder. No manual is re-read during splitting and no new factual knowledge may be introduced; only already documented content and manual references are reorganized. Folder navigation is updated locally and verified again.

The question follow-up flow applies the same split evaluation to the concept touched by each question after the existing question assessment/evidence/apply/verify sequence. Existing question steps are unchanged.


## Long manual chunks

Chunk boundaries prefer Markdown chapter/section headings when appropriate (target about 350 lines, maximum 450 lines). When no suitable heading can be found, numeric 350-line boundaries are used. Partitioning searches for heading candidates and probes single lines without loading the whole file. Each chunk scan gets a fresh LLM context and its own `state/chunks/scan-<manual>-<chunk>.json` checkpoint; per-chunk routing files live in `state/routes/<manual>-<chunk>-<folder>.json`.

**Resume warning:** if a source file or its line numbering changes, remove its partition/scan/profile/routing checkpoints and derived structure/plan/coverage checkpoints before rerunning. Reusing old valid JSON can otherwise silently preserve stale evidence.

## Migration from the legacy manual flow

The old `state/profile-<manual>.json`, `state/structure.json`, `state/folder-plan-<folder>.json`, `state/concepts/<folder>-<concept>-*.json` and other downstream JSON outputs are **not reused**. This flow now uses `profile-v2-*`, `structure-v2.json`, `folder-plan-v2-*`, `concepts/v2-*` and other correspondingly versioned paths throughout the dependent stages. Existing route files are distinct because the chunk-based variant includes the chunk ID in the filename. Migration therefore recomputes the incompatible stages once; later v2 runs retain resumability.

**Generated OKF Markdown content is not automatically cleaned.** If you want a completely fresh output without orphaned old concepts, choose a new/empty `okf_root` (or back up and clean the existing output manually). Do not delete manually maintained content inadvertently. If source files or partition boundaries change, clear related v2 checkpoints before re-running.

## Fine-grained checkpoints

Every model step, including short chunk/folder-routing and shared index/verification/split stages, now writes an individual JSON checkpoint. Shared steps use pipeline-, phase- and folder-scoped identifiers so pre/post split verification cannot reuse each other's data. Subflow invocation steps are orchestrator operations: their model steps are checkpointed individually, and their combined results are reconstructed on resume.

The shared checkpoints are stored in `flow/okf/state/fine/`; routing-stage checkpoints are stored in this pipeline's `state/fine/`. Both locations are gitignored. The concept-split discovery returns short positional IDs (c001, c002, ...), reducing long filenames even when concept titles are long. When inputs or generated OKF content changes, invalidate dependent checkpoints before rerunning. Earlier stages may otherwise legitimately resume from stale JSON.

If Windows reports a long-path error, note the **exact failing path**: a generated checkpoint file, an OKF concept output, or a `.cli-agent` diagnostic dump require different fixes. Shorter checkpoint filenames cannot by themselves guarantee Windows paths remain below system limits in a deeply nested workspace.
