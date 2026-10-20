Deterministic folder inventory (workspace-relative paths):
{{var:inventory}}

Use inventory.files as the complete file list; do not list the directory again. Convert to OKF-root-relative concept paths by stripping the {{var:okf_root}} prefix; exclude index.md and log.md. Sort paths and assign stable positional IDs c001, c002, etc.

Discover the normal OKF concepts directly contained in exactly one semantic folder.

Target OKF root: `{{var:okf_root}}`

Folder:
{{var:folder}}

Rules:
- Inspect only the direct contents of `<okf_root>/<folder.path>`.
- Do not descend recursively.
- Include normal Markdown concepts only.
- Exclude `index.md` and `log.md`.
- Do not read concept bodies in this step.
- Sort deterministically by relative path.
- Assign short stable positional IDs `c001`, `c002`, ... in the sorted list. Do not use the filename as an ID: long concept names can exceed Windows output-path limits. Keep the complete original concept filename in `path`.
- Do not modify files.

Return exactly one JSON object:
{
  "folder_id":"string",
  "concepts":[
    {"id":"concept-name","path":"folder/concept-name.md"}
  ]
}

Return valid JSON only.
