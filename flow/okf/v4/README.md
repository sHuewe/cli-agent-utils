# OKF V4 – Migration and Phase B

## Scope: Phase A vs. global topics

**Phase A consists exclusively of the original doctrine-specific concepts**
under `doctrines/<slug>/...`, plus structured provenance metadata and
snapshots of their source doctrines. It contains **no** `index.md`,
no generated thematic pages, no summaries and no V3 checkpoints.

Cross-doctrine topics are *derived views*, not duplicate source concepts.
Phase B creates an LLM-supported per-concept inventory with concise
summaries and thematic tags; deterministic scripts build local, root and
cross-doctrine topic navigation from the complete inventory. Themes are
navigation pages under `themen/`, not new doctrine knowledge assertions.

This is an initial, standalone Phase B implementation. A later quality
workflow can perform semantic review, concept splitting/merging and source
coverage maintenance before publishing, without changing the import contract.

## A – strict contract, V3 import

Run from the workspace root. Python 3.11+ standard library only:

```powershell
py .\flow\okf\v4\migrate_v3.py --workspace .
```

This is a **dry-run** by default. Apply the migration after checking the
validation report:

```powershell
py .\flow\okf\v4\migrate_v3.py --workspace . --apply
```

Defaults: V3 generated tree `okf-batched-generated-v3/`, V3 state
`okf-batched/state-v3/docs/`, V4 destination `okf-v4/phase-a/`.
All paths can be overridden with `--source-root`, `--state-root` and
`--destination`.

The importer fails closed if any existing document group is incomplete.
It reads V3 `sections.json`, `group.json`, `coverage.json`,
`concept-<id>-repair.json` and the planned Markdown concept for each
group member. It verifies complete Knowledge Item membership against
repair reports and deterministic coverage status.

**Exact Phase-A permitted file set:**

```text
okf-v4/phase-a/
  phase-a.json
  catalog.json
  sources/<slug>.md                     # or .markdown, as supplied
  doctrines/<slug>/<named-concept>.md
  doctrines/<slug>/<folder>/<named-concept>.md
```

Only the *original source Markdown*, the planned concept Markdown files
(with descriptive slugs and corrected inter-concept links), and these two
structured metadata files are copied or created. The catalog preserves
stable, document-scoped IDs, source snapshot hashes, complete original
Knowledge Item objects and their evidence ranges.

**Prohibited in Phase A:** any `index.md`, `themen/`, legacy manifests,
Build/Verify/Repair JSON checkpoints, schema/prompt files, backups and
temporary files. Existing V3 `index.md` files are intentionally ignored,
never copied. `phase_a_contract.py` rejects **any** uncontracted file,
including an accidentally added index.

The importer stages output and replaces an existing V4 Phase-A destination
only after all documents have passed validation. Original V3 data and
checkpoints remain untouched. Previously imported phases can be regenerated
from V3; B only accepts a complete, unmodified Phase-A snapshot.

## B – LLM inventory, deterministic indexes

After importing Phase A, use the generic Python subprocess step provided
by cli-agent PR #324 (now merged):

```powershell
cli-agent-flow validate flow/okf/v4/phase-b.toml --workspace .
cli-agent-flow run flow/okf/v4/phase-b.toml --workspace .
```

Flow B has three stages:

1. **`inventory_tasks`** – A trusted Python script checks the complete
   Phase-A file contract and fingerprints, then lists every concept.
2. **`summarize`** – An independent read-only LLM step per concept reads
   the actual concept Markdown, writes a content-based German summary and
   1–5 semantic tags. Outputs are checkpointed separately as
   `okf-v4/state-b/summaries/<key>.json`; no model can write an index.
3. **`publish_indexes`** – Another trusted Python script verifies that
   every concept has exactly one matching LLM inventory entry. It copies
   only Phase-A concept pages into `okf-v4/published/` and deterministically
   generates all indexes, the global thematic navigation and an
   `inventory.json`.

The resulting published tree contains all actual concept Markdown plus:

```text
index.md
doctrines/index.md
doctrines/<slug>/index.md
doctrines/<slug>/<folder>/index.md
themen/index.md
themen/<semantic-tag>.md
inventory.json
```

The script checks that every generated link resolves and every concept is
reachable from the root index. No concepts can silently disappear from the
navigation; an invalid/missing model summary aborts publication. Source
snapshots stay inside Phase A, not the published tree.

The final publishing step has `overwrite_output = true` because it also
validates and recreates filesystem side effects. The individual LLM summary
steps reuse their checkpoints, avoiding unnecessary model calls.

### Limitations and next stages

- The current importer requires complete V3 documents and complete
  deterministic repair/coverage records. It does not attempt to repair
  missing documents, produce summaries itself, or invent source evidence.
- Global thematic tags are an initial cross-doctrine classification, not
  the later semantic merge/split and quality-review pipeline.
- Phase A remains immutable during any B run. When concepts are reimported
  with changed Markdown, the inventory step includes the concept SHA-256 in
  each per-concept summary checkpoint filename, automatically invalidating
  summaries for changed content while reusing those for unchanged concepts.
- Future incremental update flows should use the catalog's original
  Knowledge Item identities and source snapshots for change-impact analysis.
