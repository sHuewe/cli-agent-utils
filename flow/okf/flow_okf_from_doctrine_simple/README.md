# Experimental simplified doctrine → OKF flow

Entrypoint: flow/okf/flow_okf_from_doctrine_simple/flow.toml

Created as an **independent experiment alongside**
flow_okf_from_doctrine_seperated. This workflow does NOT consume or
rewrite the older flow's checkpoints. It deliberately avoids atomic
knowledge-item extraction, forced 350/450-line partitioning, route
batches, topic assignment, and per-item coverage counting.

Stages:
1. Deterministically inventory Markdown doctrines.
2. Per doctrine, the runner determines contiguous, heading-aware source sections.
   Doctrines up to 30,000 characters use the original direct whole-document
   planning route. Longer doctrines receive a compact section analysis per
   approximately 30,000-character range (no atomic knowledge-item routing);
   each analysis reads the exact original source lines and has an independent
   JSON checkpoint. Instead of one large global outline request, a bounded
   model request proposes concepts for each section. The runner merges repeated
   semantic topic_keys into a flat, document-wide concept outline without another
   model call. A deterministic step divides these concepts into groups of three. Each group gets its own evidence-planning model call and
   checkpoint. The runner combines complete, validated groups into the
   original plan.json without another model call. Missing/inconsistent evidence
   blocks subsequent writing.
3. Build each planned concept from bounded original evidence. Verify every
   concept; repair **only** actionable concept defects. Planning/evidence
   defects are reported separately, not silently treated as missing text.
4. Write doctrine/subfolder navigation indexes, then create one compact manifest
   **deterministically** from the validated plan and successful navigation.
   No extra LLM is used to recopy or omit planned concepts.
5. Use manifests from all doctrines in one global theme-planning step.
   Write cross-doctrine theme navigation pages and root/index.md.

Output: okf-simple/doctrines/<source-slug>/... and okf-simple/themen/...
The experiment intentionally does NOT mutate concept frontmatter to add
reverse theme tags; themes link to concepts instead. This difference is
important when comparing it to the existing separated flow.

Example:
```sh
cli-agent-flow validate flow/okf/flow_okf_from_doctrine_simple/flow.toml --workspace .
cli-agent-flow run flow/okf/flow_okf_from_doctrine_simple/flow.toml --workspace .
```

Configure [vars] in flow.toml: doctrine_path and okf_root.

The runner must contain the following already-merged changes:

- [cli-agent PR #236](https://github.com/sHuewe/cli-agent/pull/236): deterministic inventory slugs.
- [cli-agent PR #237](https://github.com/sHuewe/cli-agent/pull/237): pre-write OKF plan validation.
- [cli-agent PR #238](https://github.com/sHuewe/cli-agent/pull/238): deterministic manifest creation.
- [cli-agent PR #239](https://github.com/sHuewe/cli-agent/pull/239): binding source path/slug to inventory and validating theme links against current manifests.
- [cli-agent PR #273](https://github.com/sHuewe/cli-agent/pull/273): deterministic heading-aware Markdown section ranges.

The adaptive version requires the runner containing PR #273 in addition to those previous changes.

The inventory source.slug is authoritative; unlike LLM kebab normalization
it distinguishes source paths such as `a/b.md` and `a-b.md`.
The simplified flow passes completed concept verification/repair outcomes
to navigation and manifest creation; incomplete concepts must not be
reported as successfully published. Theme pages require OKF frontmatter.
Workspace must contain the flow sources, the source Markdown files
and any shared OKF format context. Do not point okf_root at the existing
generated repository during experiments. The new independent state is
under flow/okf/flow_okf_from_doctrine_simple/state/.

## Limitations and evaluation

* A model may still hit tool/model token limits for a long individual section.
  The deterministic section operation fails rather than silently truncating
  documents exceeding its supported range and size limits. Section analysis
  returns needs_attention rather than silently claiming full coverage.
  A long global plan may also be expensive when many section summaries accrue.
* A concept plan is intentionally NOT a formally exhaustive registry of
  every independent normative statement. Compare completeness via actual
  domain questions, source-section sampling and reference checks.
* Resume uses path-keyed checkpoints, not content hashes of the original
  sources. On edits to doctrine contents, remove that doctrine's new flow
  state and dependent global state after careful review. Existing generated
  files may need manual migration/cleanup.
* Failure in verification must not cause invented source fixes. The
  conditional repair returns the verify result when no repair was needed.
  Navigation and manifests may return needs_attention; inspect those before
  using the OKF as complete.
* The independent test should compare answer quality, topic coverage,
  traceability, number of concept files, model calls, errors and runtime.

This is a test workflow, not a replacement for the existing flow or
for a formal compliance audit. No live end-to-end run was performed when
this implementation was authored.

## Batched planning checkpoints

The newly introduced intermediate outputs are `outline.json`,
`plan-batches.json` and `plan-detail-b0001.json` (one per group). The final
`plan.json` and every downstream checkpoint path are unchanged. For
preexisting `plan.json` checkpoints the runner still reuses that file,
but the newly introduced preceding stages may be executed unless their
own checkpoints already exist. Do not assume that a resumed run skips
all newly introduced upstream work. Do not merge the utils PR before
its companion cli-agent PR adds the deterministic JSON operations.

## Section-local outline consolidation

The single expensive outline LLM request is replaced by checkpointed
`local_outlines` calls (one per existing section analysis, or one for a short
direct document). The runner assembles `outline.json` deterministically
using exact `topic_key` matches. **Different keys referring to the same
semantic topic are not automatically recognized as duplicates.** This is
a deliberate trade-off to eliminate the document-wide model call; review
the output for near-duplicates and missed cross-section relationships.

The existing final `outline.json`, `plan.json`, validation and concept
checkpoints retain their locations. New intermediates are
`outline-tasks.json` and `local-outline-s001.json` (one per section).
The core extension is required before this flow can run.

## Migration from the flat local-outline result

The original `sections.json`, `section-*.json`, `outline-tasks.json` and
`local-outline-*.json` remain valid and should **not** be deleted. After
upgrading cli-agent and this flow, delete the affected doctrine's stale
`outline.json`, `plan-batches.json`, `plan-detail-*.json`, `plan.json`,
`validated-plan.json`, `navigation.json` and `manifest.json` if present.
The new `outline-candidates.json`, `taxonomy-profile.json`, `taxonomy.json`,
`consolidation-batches.json` and `consolidation-c*.json` are created by
the new implementation. Remove them too when intentionally resetting a
failed consolidation.

**Never automatically remove user-authored OKF files.** If concepts or index
files were already written from the old plan, review/backup the affected
`okf-simple/doctrines/<source-slug>/` directory separately: removing
only JSON checkpoints does not revert those actual generated files or
per-concept subflow checkpoints. Restarting with these outputs still present
can reuse stale concepts or produce path collisions.
