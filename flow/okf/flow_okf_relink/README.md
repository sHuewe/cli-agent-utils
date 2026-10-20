# Relink existing OKF

This flow only adds inline links to existing OKF Markdown concepts. It does not create, split, rename, delete or rewrite concepts or indexes.

Set input `okf_root` to a workspace-relative OKF root. The first `filesystem_operation.inventory` recursively discovers every folder under the root. For each discovered folder, a non-recursive inventory returns its directly contained Markdown concept files (excluding `index.md` and `log.md`). The flow then iterates directly over `inventory.directories` and `inventory.files`; **there is no LLM planning or JSON regrouping step**. Concept paths remain workspace-relative throughout, matching the inventory output.

Each concept has independent checkpointed snapshot, link and read-only verification steps. Only the link step may modify a concept, by wrapping up to three existing plain-text phrases in Markdown links. The original text must be reconstructible character-for-character. Link verification is per concept, not a repository-wide audit.

The inventory is refreshed each run; existing concept checkpoints are reused. Remove the corresponding checkpoints when explicitly relinking a previously processed concept. The root's own Markdown concepts are not iterated because the top-level iteration uses `directories`; place concepts in folders or extend the flow if root-level concepts must also be processed. Recursive inventory is bounded to 10,000 entries.
