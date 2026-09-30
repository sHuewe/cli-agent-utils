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
- Derive a stable filesystem-safe `id` from the filename without `.md`. It must match `[A-Za-z0-9_-]+`.
- Do not modify files.

Return exactly one JSON object:
{
  "folder_id":"string",
  "concepts":[
    {"id":"concept-name","path":"folder/concept-name.md"}
  ]
}

Return valid JSON only.
