Perform a read-only structural verification of exactly one semantic OKF folder.

Semantic structure:
{{var:structure}}

Folder:
{{var:folder}}

Rules:
- Target root is `structure.okf_root`; inspect only this declared folder below it.
- Verify `<okf_root>/<folder.path>/index.md` exists and is readable.
- List the folder directly and identify every normal `.md` concept next to `index.md`.
- Do not read full concept bodies. For each concept, read only a small leading range sufficient to validate YAML frontmatter (normally at most the first 60 lines).
- Verify each concept starts with frontmatter containing a non-empty `type`.
- Verify the folder index links every directly contained concept and that its relative links do not escape the OKF root.
- Report unexpected nested directories because these flows intentionally generate one semantic folder layer with concepts directly inside it.
- Do not inspect original source material and do not modify files.

Return exactly one JSON object:
{
  "status":"ok|needs_attention",
  "folder_id":"string",
  "index_path":"relative/folder/index.md",
  "concept_count":0,
  "findings":[
    {"severity":"error|warning","path":"relative/path","problem":"string"}
  ]
}

Return valid JSON only.
