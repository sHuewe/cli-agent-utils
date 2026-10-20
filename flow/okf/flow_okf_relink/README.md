# Relink existing OKF

This workflow **only** updates inline cross-links in existing Markdown concepts. It does not generate, split, rename or delete concepts or indexes.

Run from the workspace root with input `okf_root` set to the workspace-relative OKF directory. The first step performs a deterministic recursive inventory. A planning step groups the inventory's Markdown concepts by their actual parent folder; nested folders are supported. The workflow then iterates over folders and individual concepts.

Each concept has independent, checkpointed snapshot, link and read-only verification steps. The link step is restricted to wrapping existing text in up to three Markdown links; it cannot rewrite concept content or edit indexes. The pre-link snapshot and verification rules are shared with the doctrine workflow. The planning output and per-concept checkpoints are stored under `flow/okf/flow_okf_relink/state/`. Delete these checkpoints to explicitly re-run linking on the same repository; a resumed run intentionally reuses them.

**Limits:** The recursive inventory is bounded to 10,000 encountered entries; the planning step must fit the complete inventory in model context. The workflow's plan is LLM-generated rather than a deterministic transformation. Use an appropriately sized model and inspect the plan for large repositories. The inventory is refreshed on each run but an existing plan checkpoint is reused; remove `state/plan.json` when the repository's file structure has changed. Link verification is per concept, not a final repository-wide audit.
