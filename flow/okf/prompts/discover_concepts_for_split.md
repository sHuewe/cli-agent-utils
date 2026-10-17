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
