# Relink existing OKF

This flow only adds inline links to existing OKF Markdown concepts. It does not create, split, rename, delete or rewrite concepts or indexes.

The standalone flow uses `okf-generated` as its workspace-relative root. To use a different root with the current runner, change both `filesystem_operation.directory` and `steps.link_folders.input.okf_root` in `flow.toml`; `[vars]` cannot be interpolated into these fields by the current runner. No CLI input is required. The first `filesystem_operation.inventory` recursively discovers every folder under the root. For each discovered folder, a non-recursive inventory returns its directly contained Markdown concept files (excluding `index.md` and `log.md`). The flow then iterates directly over `inventory.directories` and `inventory.files`; **there is no LLM planning or JSON regrouping step**. Concept paths remain workspace-relative throughout, matching the inventory output.

Each concept has independent checkpointed snapshot, link and read-only verification steps. Only the link step may modify a concept, by wrapping existing plain-text phrases in Markdown links to distinct, substantively related concepts (no fixed per-concept link limit). A separate read-only `foreach` discovers candidates for each target folder using its `index.md` **and** targeted text searches restricted to that folder. After folder discovery, deterministic JSON batching groups at most two folder results per batch and caps each batch at 32,000 UTF-8 bytes. Separate read-only LLM steps filter each batch to concise, relevant link proposals. Only these reviewed proposals go to a single write-capable link step, followed by one read-only verifier. An individually oversized folder result fails explicitly rather than silently dropping candidates. The original text must be reconstructible character-for-character. Link verification is per concept, not a repository-wide audit.

The inventory is refreshed each run. Each concept's workspace-relative path determines its own state directory, using versioned `snapshot-v3-relink.json`, `discover-v3-relink/`, `candidate-batches-v3-relink.json`, `review-v3-relink-<batch-id>.json`, `link-v3-relink.json` and `verify-v3-relink.json` checkpoints. Previous v2 checkpoints cannot be reused automatically. Batch grouping is positional: invalidate batch/review/link/verify checkpoints when folder discoveries change; never blindly reuse an old batch ID for different input content. Adding, deleting, or reordering inventory entries no longer changes checkpoint filenames for existing concepts. Remove the three checkpoints in that concept's state directory only when deliberately relinking it. Renaming or moving a concept changes its state directory and therefore invalidates its checkpoints.

**Migration from positional checkpoints:** Older `snapshot-<folder-id>-<concept-id>.json`, `link-<folder-id>-<concept-id>.json`, and `verify-<folder-id>-<concept-id>.json` files are not automatically reused. Before the first rerun, review them and migrate each complete set to the corresponding stable filenames **only after verifying the concept path in the saved JSON**. Otherwise the write-capable link step may run again; do not assume old positional IDs still identify the same concept. The root's own Markdown concepts are not iterated because the top-level iteration uses `directories`; place concepts in folders or extend the flow if root-level concepts must also be processed. Recursive inventory is bounded to 10,000 entries.


## Legacy v2/v3 verification precheck (not yet wired into relink)

The shared, model-free subflow at `flow/okf/flows/link-resume-status.toml`
checks whether a concept has an existing successful `verify-v2-*.json` or
`verify-v3-*.json` result with an exact matching `source_path`.
It uses the runner's `filesystem_operation.kind = "checkpoint_status"`
and requires the source concept to exist.

This is currently only a **read-only integration building block**. It is
**not** called from `link-concept.toml`, and the main flow does not yet
skip successfully linked concepts automatically.

Two runner limitations prevent safe in-flow integration:

1. `checkpoint_status` permanently protects its `expected_source_path`
   from subsequent writes in the same flow run. A new or invalid
   verification must allow the linker to edit that concept; otherwise the
   resumed flow would abort with a protected-path collision.
2. The subflow `result` points to one fixed step. Selecting an existing
   v2/v3 verification result *or* a newly produced v3 verifier result needs
   a deterministic result-selection mechanism. Skipped concepts must still
   appear in the final per-folder and doctrine verification aggregates.

Do not wire the precheck directly before the write-capable `link` step
until both protections and result semantics have been implemented and tested
in `cli-agent`. Do not infer success solely from the existence of a JSON
checkpoint filename.
