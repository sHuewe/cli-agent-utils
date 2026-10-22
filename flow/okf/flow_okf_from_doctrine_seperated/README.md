# Independent OKF per doctrine (experimental)

Entry point: `flow/okf/flow_okf_from_doctrine_seperated/flow.toml`.
The original multi-doctrine semantic flow is unchanged. Source Markdown files
under `doctrines/` are inventoried recursively every run. Each is processed
in a separate subflow into `okf-generated/doctrines/<stable-source-slug>/`.
A global `themen/` tree connects relevant concepts through stable
`theme:<id>` YAML frontmatter tags; root/index.md gives two navigation views.

The flow reuses the existing single-chunk extraction and single-concept
build/verify/repair prompts. Local routing uses bounded 2-route / 48 KB
batches; topic summaries are reduced in batches and JSON grouping
enforces 48 KB concept plans. The global phase processes at most two module
manifests per batch. LLMs inspect bounded compact summaries rather than all
source documents. All deterministic JSON operations use existing runner
features; no new OKF MCP API is required.

Run from a workspace containing the flow sources, `doctrines/` and the
target `okf-generated/` tree:

```sh
cli-agent-flow validate flow/okf/flow_okf_from_doctrine_seperated/flow.toml --workspace .
cli-agent-flow run flow/okf/flow_okf_from_doctrine_seperated/flow.toml --workspace .
```

**Incremental-change caveats:** Existing local JSON checkpoints are resumed
for unchanged source paths. Source edits are NOT fingerprint-invalidated by
this flow: explicitly remove the altered doctrine's state directory and
dependent global checkpoint files before rerunning. Remove old generated
concept files only after inspecting the change, otherwise stale concepts can
remain in its folder. Never blindly overwrite previous source-grounded
results. Module path slugs must remain stable; LLM-generated slug collision
is detected only by final directory overlap and is NOT a perfect uniqueness
proof. Rename/move events need manual migration of module folder and
checkpoints. Global topic consolidation is a best-effort LLM operation, not a
deterministic exhaustive similarity search; too many themes or incomplete
candidate discovery must be reported as needs_attention. An excessively large
single module manifest fails JSON batching rather than truncating.

**Important:** Global theme-generation currently depends on a literal
workspace search for topic tags; results beyond the OS-MCP limit of 200 are
reported incomplete. No unbounded cross-repository crawling is attempted.
For large repositories, partition topics by narrower physical paths or
introduce a deterministic index in a future version. Manifests and tag
assignment must be invalidated together if a doctrine changes. Module-level
source verification and resulting change tracking are not fully automatic.

Requires `cli-agent` main at or after [PR #231](https://github.com/sHuewe/cli-agent/pull/231) (merge commit `4a9ec52bf66a5a0748b13d2835703a8a80bb0297`): the root `flow.toml` uses `${var.okf_root}` in both `[steps.input]` blocks, which is only supported after that change. Modify `[vars].okf_root` to choose the generated OKF directory; do not hardcode child inputs.

Requires the current `cli-agent` flow runner with inventory,
`json_operation=batch_routes/group_items/verify_coverage/batch`,
`json_inputs`, nested subflows and `foreach`.

## Semantic subfolders (v2)

From this version the local topic plan may optionally group doctrine concepts
into up to 12 meaningful subfolders, with one level under
`<okf-root>/doctrines/<doctrine-slug>/`. The doctrine `index.md` links to
each semantic subfolder `index.md`, which in turn links to its actual
concept files. Small doctrine topic sets may stay flat. Cross-doctrine
`themen/` and `theme:<id>` tags remain independent of local grouping.

**Migration:** v2 deliberately writes its checkpoints to
`flow/okf/flow_okf_from_doctrine_seperated/state-semantic-v2/`.
Existing `state/` checkpoints are retained untouched but will NOT be
reused by the new flow. This avoids silently loading old flat concept plans.
Do not change the flow implementation while a run is active; finish or stop
the old run before checking out this version. For a clean comparison use a
new `[vars].okf_root`, because generated concept files from the flat layout
in an existing OKF root are not automatically removed/migrated.

Requires cli-agent's semantic subfolder support in
[sHuewe/cli-agent PR #233](https://github.com/sHuewe/cli-agent/pull/233).

## Bounded assignment batches

The doctrine topic-assignment step uses its OWN batches generated from the
original per-chunk routes: at most one route fragment and 12 KB per batch.
Unlike the larger route batches used for topic planning, these smaller batches
bound the model input/JSON output. Each knowledge item retains its stable
document_id + local ID, and deterministic group_items still detects omissions
and duplicate assignments.

Older `assign-b000*.json` checkpoints are preserved and intentionally NOT
reused: new results are `assign-small-b000*.json`. The new grouping output is
`concept-plan-small-assign-v1.json`; coverage reads this new plan. All
`prepare`, `partition`, `scan`, `route`, `suggest`, `reduce` and
`local-topics` checkpoints remain eligible for normal reuse. If a run
reached concept generation under the previous layout, inspect its generated
files/checkpoints before rerunning; this fix does not migrate concept files.
