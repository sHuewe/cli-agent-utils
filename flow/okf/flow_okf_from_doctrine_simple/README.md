# Experimental simplified doctrine → OKF flow

Entrypoint: flow/okf/flow_okf_from_doctrine_simple/flow.toml

Created as an **independent experiment alongside**
flow_okf_from_doctrine_seperated. This workflow does NOT consume or
rewrite the older flow's checkpoints. It deliberately avoids atomic
knowledge-item extraction, forced 350/450-line partitioning, route
batches, topic assignment, and per-item coverage counting.

Stages:
1. Deterministically inventory Markdown doctrines.
2. Per doctrine, **read/understand the whole source in one model step**
   when feasible, or read successive bounded ranges within that SAME
   conversation when necessary. Return a concise source-grounded concept plan
   and optional semantic subfolders.
3. Build each planned concept from bounded original evidence. Verify every
   concept; repair **only** actionable concept defects. Planning/evidence
   defects are reported separately, not silently treated as missing text.
4. Write doctrine/subfolder navigation indexes, then one compact manifest.
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

Configure [vars] in flow.toml: doctrine_path and okf_root.\nRequires `cli-agent` with deterministic validation of model-generated OKF plans\nfrom [sHuewe/cli-agent PR #237](https://github.com/sHuewe/cli-agent/pull/237),\nin addition to optional deterministic inventory slugs from\n[sHuewe/cli-agent PR #236](https://github.com/sHuewe/cli-agent/pull/236).\nThe inventory source.slug is authoritative; unlike LLM kebab normalization\nit distinguishes source paths such as `a/b.md` and `a-b.md`.\nThe simplified flow passes completed concept verification/repair outcomes\nto navigation and manifest creation; incomplete concepts must not be\nreported as successfully published. Theme pages require OKF frontmatter.
Workspace must contain the flow sources, the source Markdown files
and any shared OKF format context. Do not point okf_root at the existing
generated repository during experiments. The new independent state is
under flow/okf/flow_okf_from_doctrine_simple/state/.

## Limitations and evaluation

* A model may still hit file/tool/model token limits on unusually long
  documents. No blanket promise to fit all sources in one prompt.
  In that case it must read bounded successive ranges or return
  needs_attention; it must never silently claim full coverage.
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
