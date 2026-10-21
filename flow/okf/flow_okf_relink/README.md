# Relink existing OKF

This flow only adds inline links to existing OKF Markdown concepts. It does not create, split, rename, delete or rewrite concepts or indexes.

The standalone flow uses `okf-generated` as its workspace-relative root. To use a different root with the current runner, change both `filesystem_operation.directory` and `steps.link_folders.input.okf_root` in `flow.toml`; `[vars]` cannot be interpolated into these fields by the current runner. No CLI input is required. The first `filesystem_operation.inventory` recursively discovers every folder under the root. For each discovered folder, a non-recursive inventory returns its directly contained Markdown concept files (excluding `index.md` and `log.md`). The flow then iterates directly over `inventory.directories` and `inventory.files`; **there is no LLM planning or JSON regrouping step**. Concept paths remain workspace-relative throughout, matching the inventory output.

Each concept has independent checkpointed snapshot, link and read-only verification steps. Only the link step may modify a concept, by wrapping existing plain-text phrases in Markdown links to distinct, substantively related concepts (no fixed per-concept link limit). A separate read-only `foreach` discovers candidates for each target folder using its `index.md` **and** targeted text searches restricted to that folder. After folder discovery, deterministic JSON batching groups at most two folder results per batch and caps each batch at 32,000 UTF-8 bytes. Separate read-only LLM steps filter each batch to concise, relevant link proposals. Only these reviewed proposals go to a single write-capable link step, followed by one read-only verifier. An individually oversized folder result fails explicitly rather than silently dropping candidates. The original text must be reconstructible character-for-character. Link verification is per concept, not a repository-wide audit.

The inventory is refreshed each run. Each concept's workspace-relative path determines its own state directory, using versioned `snapshot-v3-relink.json`, `discover-v3-relink/`, `candidate-batches-v3-relink.json`, `review-v3-relink-<batch-id>.json`, `link-v3-relink.json` and `verify-v3-relink.json` checkpoints. Previous v2 checkpoints cannot be reused automatically. Batch grouping is positional: invalidate batch/review/link/verify checkpoints when folder discoveries change; never blindly reuse an old batch ID for different input content. Adding, deleting, or reordering inventory entries no longer changes checkpoint filenames for existing concepts. Remove the three checkpoints in that concept's state directory only when deliberately relinking it. Renaming or moving a concept changes its state directory and therefore invalidates its checkpoints.

**Migration from positional checkpoints:** Older `snapshot-<folder-id>-<concept-id>.json`, `link-<folder-id>-<concept-id>.json`, and `verify-<folder-id>-<concept-id>.json` files are not automatically reused. Before the first rerun, review them and migrate each complete set to the corresponding stable filenames **only after verifying the concept path in the saved JSON**. Otherwise the write-capable link step may run again; do not assume old positional IDs still identify the same concept. The root's own Markdown concepts are not iterated because the top-level iteration uses `directories`; place concepts in folders or extend the flow if root-level concepts must also be processed. Recursive inventory is bounded to 10,000 entries.


## Automatic checkpoint-aware resume (requires new runner)

The shared link-concept flow now begins with a deterministic `checkpoint_status`
step. It checks existing `verify-v2-*.json` and `verify-v3-*.json` results
with `status = "ok"`, an exact workspace-relative `source_path`, and an
existing regular source concept. The check makes **no model call**.

When a matching checkpoint exists, all snapshot, discovery, batching, review,
write and verification steps are skipped. The subflow returns the original
verifier JSON through its primary result selector; this preserves
`status`, `source_path`, and `checked_links` for the parent aggregates.

When no valid verification exists, the concept's protection is released
**only after the first deterministic check has completed with a confirmed
miss**. All existing verification checkpoint files remain protected; the
ordinary link and independent verification stages then execute. The
`result_fallback` selector returns the freshly generated verifier JSON.

This requires the cli-agent runner extensions `release_source_on_miss` and
`result_fallback` from the companion runner PR. Older runners will reject
this configuration during validation. A valid legacy verification does not
prove the source content has remained unchanged; invalidate stale checkpoints
manually when the underlying concepts or link requirements change.
