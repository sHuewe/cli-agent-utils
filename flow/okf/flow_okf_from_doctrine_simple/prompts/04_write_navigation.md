# Write navigable indexes for ONE doctrine

Source-grounded plan: {{var:plan}}
OKF root: {{var:okf_root}}

If plan.status is not ok, return needs_attention WITHOUT writing files.
The plan is a navigation contract, not proof that files were generated.
For each planned concept, verify the actual file exists with a small
bounded os__read_file (e.g. lines 1..30), and inspect the frontmatter.
If any target is missing or unreadable, return needs_attention and list
it explicitly. Do not silently omit it.
Do not modify normal concept files.

Create index.md in the doctrine root and in EVERY declared semantic
subfolder. For each subfolder, link every concept belonging to it once
using relative Markdown paths (with a short description).
Root doctrine index links to all subfolder indexes, not to a giant
flat list of nested concepts. In flat mode it links directly to the
normal concept files. Explain source scope briefly.
Use only relative links inside the OKF root; never fabricate paths
or external references. Write ONLY the planned index.md files; parent
directories may be created when needed. Do not touch global indexes.
Do not label any generated concepts as human verified.

Return JSON only:
{"status":"ok|needs_attention","module_path":"root-relative doctrine folder",
"index_paths":["root-relative/index.md"],"missing_paths":[],"warnings":[]}
