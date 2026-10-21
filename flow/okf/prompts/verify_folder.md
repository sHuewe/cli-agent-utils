Perform a read-only structural verification of exactly one semantic OKF folder.

Semantic structure:
{{var:structure}}

Folder:
{{var:folder}}

Authoritative deterministic directory inventory (workspace-relative paths):
{{var:inventory}}

Rules:
- Target root is `structure.okf_root`; inspect only this declared folder below it.
- Verify `<okf_root>/<folder.path>/index.md` exists and is readable.
- Use the provided deterministic inventory as the complete direct-folder file listing. Do NOT list the directory again. Convert each inventory file path from workspace-relative to OKF-root-relative by removing the exact `structure.okf_root/` prefix. Select normal `.md` concepts, excluding `index.md` and `log.md`, and return sorted unique `concept_paths`.
- If the inventory directory or path prefix does not match the declared folder, report `needs_attention` rather than guessing.
- Do not read full concept bodies. For each concept, read only a small leading range sufficient to validate YAML frontmatter (normally at most the first 60 lines).
- Verify each concept starts with frontmatter containing a non-empty `type`.
- Verify the folder index links every directly contained concept and that its relative links do not escape the OKF root.
- `concept_count` MUST equal the length of `concept_paths`; report duplicate or ambiguous paths as errors.
- Report unexpected nested directories from the inventory because these flows intentionally generate one semantic folder layer with concepts directly inside it.
- Do not inspect original source material and do not modify files.

Return exactly one JSON object:
{
  "status":"ok|needs_attention",
  "folder_id":"string",
  "index_path":"relative/folder/index.md",
  "concept_count":0,
  "concept_paths":["relative/folder/concept.md"],
  "findings":[
    {"severity":"error|warning","path":"relative/path","problem":"string"}
  ]
}

Return valid JSON only.
