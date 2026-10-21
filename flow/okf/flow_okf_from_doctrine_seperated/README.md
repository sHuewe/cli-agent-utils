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
