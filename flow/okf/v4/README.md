# OKF V4 – Migration, Phase B and Phase C

## Scope: Phase A vs. global topics

**Phase A consists exclusively of the original doctrine-specific concepts**
under `doctrines/<slug>/...`, plus structured provenance metadata and
snapshots of their source doctrines. It contains **no** `index.md`,
no generated thematic pages, no summaries and no V3 checkpoints.

Cross-doctrine topics are *derived views*, not duplicate source concepts.
Phase B creates and improves the concept corpus, then certifies a refreshed
LLM-written inventory. Phase C builds cross-doctrine links and all navigation
deterministically from this final inventory. Themes are navigation pages,
not new doctrine knowledge assertions.

The migration contract is intentionally independent of the B and C workflows,
so this corpus can be reused without preserving old generator checkpoints.

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
`--destination`. The location of the **original source documents** can
be configured separately using `--document-root` (default: `doctrines`).

If the source document paths in V3 `sections.json`, scan evidence and
concept evidence are rooted in `md/` instead of `doctrines/`, run:

```powershell
py .\flow\okf\v4\migrate_v3.py --workspace . --document-root md
py .\flow\okf\v4\migrate_v3.py --workspace . --document-root md --apply
```

This option only selects the **existing, original input Markdown**. Generated
V3 concept paths and the new Phase-A concept layout intentionally remain
under `doctrines/<slug>/...`, and source snapshots remain under
`sources/<slug>.md`. The V3 metadata paths must continue to match their
actual source files; the migration does not silently rewrite original evidence.
The destination may not overlap source documents, V3 generated files or V3 state.

The importer accepts incomplete V3 coverage when the original section
scans and grouped concept files are available. It reads V3
`sections.json`, `scan-<section>.json`, `group.json`, `coverage.json`,
optional `concept-<id>-repair.json` and existing concept Markdown.
It reconciles every grouped item against the authoritative scan payload.
For older V3 scan files, missing or blank routing fields `document_id`,
`folder_id` and `chunk_id` are inferred from the V3 state-directory slug
and the matching `sections.json` section ID **in memory only**.
Historical nonempty `document_id` and `folder_id` aliases are also
accepted when both the legacy and canonical slugs have the **same exact
16-character hexadecimal document hash** and one descriptive slug prefix
is a bounded, whole-token extension of the other. These aliases are recorded
in the Phase-A catalog as `legacy_scan_route_aliases`.
Different hashes, unrelated prefixes, conflicting `chunk_id`, and
section/source mismatches still fail closed with a field-specific error.
The V3 scan checkpoint is never rewritten.
Unassigned scan items, incomplete repair statuses and V3 warnings are retained
in the catalog for a required pre-inventory source repair in B. Legacy
`concept-<id>-repair.json` reports are LLM-produced **diagnostics**, not
authoritative evidence: mismatched IDs, paths, reported item coverage or
remaining findings are recorded in each concept's
`legacy_repair_diagnostics`, setting `source_repair_required` for B.
The original V3 scans, grouped Knowledge Items and Markdown files are
still checked strictly; modified or invented source-item identities,
unsafe evidence and missing source files fail closed.

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
stable, document-scoped IDs, source snapshot hashes, **all** original
scan Knowledge Items, pending assignments, V3 diagnostics and source evidence.
These records are structured metadata in catalog.json, not copied checkpoints.

Legacy concept Markdown may also link back to an original source document,
for example `../../../../md/Some_Source.md` from within the old generated V3
tree. When the relative path resolves to a source document present in the
V3 migration catalog, the importer retains its visible link label as text
without creating a dangling hyperlink. The exact original Markdown is kept
as a source snapshot in Phase A and its original path remains in catalog
provenance. Source snapshots are deliberately not published in C.
Other unknown `.md` targets still fail closed.

Legacy concept Markdown may contain relative navigation references such as
`../index.md`. Phase A preserves those references without copying any V3
index files. Phase C generates its own index pages and validates all
deferred navigation links against the generated output; an index link to
a page that C does not generate is still an error. Unresolved links to
ordinary concept Markdown continue to fail during migration.

**Prohibited in Phase A:** any `index.md`, `themen/`, legacy manifests,
Build/Verify/Repair JSON checkpoints, schema/prompt files, backups and
temporary files. Existing V3 `index.md` files are intentionally ignored,
never copied. `phase_a_contract.py` rejects **any** uncontracted file,
including an accidentally added index.

The importer stages output and replaces an existing V4 Phase-A destination
only after all documents have passed validation. Original V3 data and
checkpoints remain untouched. Previously imported phases can be regenerated
from V3; B only accepts a complete, unmodified Phase-A snapshot.

## B – Inventory, quality, split/merge, final verification

Phase B requires `PyYAML>=6.0,<7` in the interpreter running the Flow Python-script steps (`python -m pip install 'PyYAML>=6.0,<7'`). This dependency is declared in the workspace `pyproject.toml` and installed for repository CI tests.

Phase B consumes the **immutable**, checked Phase-A artifact. It may modify
and restructure concept content only in separately staged B trees. No LLM
writes source Markdown directly and **B creates zero `index.md` pages**.

```powershell
cli-agent-flow validate flow/okf/v4/phase-b.toml --workspace .
cli-agent-flow run flow/okf/v4/phase-b.toml --workspace .
```

The B Flow runs in this order:

1. `source_repair_tasks` validates immutable A and identifies incomplete
   V3 concept repairs and unassigned original scan Knowledge Items. Bounded,
   read-only `source_repair_review` LLM tasks propose corrected content or
   additional source-bound concepts. `apply_source_repairs` deterministically
   checks identities, provenance and **complete original scan coverage** before
   publishing `okf-v4/b-source-repaired/`. A remains untouched. When V3 is
   complete, no source-repair LLM tasks are needed.
2. `inventory_tasks` validates the fully reconciled B-source corpus.
   `summarize` reads every actual source concept and creates its initial
   German LLM summary and 1–5 thematic tags.
3. `quality_review` reads the same concept plus its complete, trusted source
   Knowledge Items. It chooses **keep**, **rewrite**, or **split** (2–8 pieces)
   and proposes complete Markdown texts as JSON, without file write rights.
4. `apply_quality` is a deterministic Python step. It enforces stable IDs,
   title/path consistency, **exact one-to-one Knowledge Item preservation**
   and source evidence retention before writing `okf-v4/b-reviewed/`.
5. `merge_candidates` creates bounded, same-doctrine concept neighborhoods
   using the inventory tags. `merge_review` reads at most four concepts per
   group and either skips or proposes a merge. `apply_merges` validates and
   writes the outcome to `okf-v4/b-merged/`, preserving the primary concept
   ID and path. Removed IDs/paths are retained as redirects/aliases.
6. `final_inventory_tasks` is computed from the actual revised/merged corpus,
   not the initial list. `summarize_final` reads and summarizes *every*
   resulting concept again, including new split children.
7. `verify_final` reads every merged concept, checking the actual
   Markdown against all assigned source Knowledge Items. Valid, unchanged
   concepts are retained as verified.
8. **Bounded repair loop (maximum two attempts):** The deterministic
   `repair_candidates_1` step selects *only* concepts with concrete
   `needs_revision` findings. `repair_review_1` creates complete,
   structured replacement Markdown via a read-only LLM; `apply_repair_1`
   validates original IDs, title and complete Knowledge Item assignments
   before writing `okf-v4/b-repair-1/`. Only changed concepts are checked
   again by `verify_repair_1`. If still defective, round two repeats this
   process into `okf-v4/b-repair-2/`. Both intermediate trees retain exact
   source evidence and may contain **no indexes**.
9. `certify_repairs` reconciles initial verification and both repair
   rounds, reusing a successful verdict only for the exact same concept
   and Knowledge Item fingerprint. Any unresolved error after two attempts
   stops B **before** publication. Zero failures incur zero repair LLM calls.
10. `final_inventory_tasks` then generates the inventory from the actual,
    fully verified final corpus. `summarize_final` creates the final LLM
    summaries. `complete_b` rechecks the full certification and publishes
    `okf-v4/phase-b/`: `phase-b.json`, `catalog.json`,
    `inventory.json`, original source snapshots and final concept Markdown.
    **No navigation files are generated in B.**

All deterministic transformations are generic Python script steps provided
by cli-agent PR #324, with JSON stdin/stdout and independent checkpoints.
LLM outputs are strictly structured suggestions. Changed concept content
and semantic merge candidates use content-sensitive checkpoint keys.
A failure preserves the immutable A snapshot and the last completed stage.

Important: a split or merge is never accepted solely because an LLM asserts
that it is complete; Python checks all source-item identities and unchanged
provenance, and the final LLM checks substantive claim coverage. Source
identities and evidence are never invented or reassigned.

## C – Semantic links, deterministic indexes, publication

Run C **only after B has completed successfully**:

```powershell
cli-agent-flow validate flow/okf/v4/phase-c.toml --workspace .
cli-agent-flow run flow/okf/v4/phase-c.toml --workspace .
```

1. `link_candidates` validates certified B and produces bounded candidates
   (maximum eight per concept) from shared semantic tags.
2. `relate` selects semantic links **by existing concept IDs only**;
   no model can create or change Markdown in this step.
3. `publish_indexes` validates links/IDs, resolves removed-concept path
   aliases, updates internal Markdown links and generates all navigation
   pages deterministically from the complete final B inventory. It checks
   complete folder membership, valid targets, and root-to-concept reachability
   before atomically publishing `okf-v4/published/`.

The published tree contains all final concept Markdown and:

```text
index.md
doctrines/index.md
doctrines/<slug>/index.md
doctrines/<slug>/<folder>/index.md
themen/index.md
themen/<semantic-tag>.md
inventory.json
```

Overarching thematic pages are *derived navigation*, **not additional
primary concepts**. Both flows are separately resumable. Source snapshots
remain in the certified B corpus, not the published navigation tree.

## Limitations and further development

- Migration requires authoritative V3 section scans, grouped concept
  records and source files. Documents without those inputs still fail closed;
  missing original Knowledge Items are never manufactured.
- Source recovery handles known scan items and incomplete concept repairs.
  New Knowledge Items never arise from LLM output. B's later semantic
  verification remains the final content-quality gate.
- Phase B supports local rewrite/split and same-doctrine merge. It does not
  perform cross-doctrine concept merges, which risk changing provenance;
  C can instead link concepts across doctrines.
- Semantic verification is fail-closed after at most two automatic
  source-grounded repair attempts. Errors not resolved in those attempts
  still require manual inspection or explicit changes; repeated retries are
  intentionally not unbounded.
- Future incremental-update flows should use stable concept identities,
  source snapshots, exact Knowledge Item records and the retirement mapping
  to limit reprocessing to affected concepts.

