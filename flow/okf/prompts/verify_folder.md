Perform a read-only structural verification of exactly one semantic OKF folder.

Semantic structure:
{{var:structure}}

Folder:
{{var:folder}}

Rules:
- Target root is `structure.okf_root`; inspect only this declared folder below it.
- Verify `<okf_root>/<folder.path>/index.md` exists and is readable.
- List the folder directly and identify every normal `.md` concept next to `index.md`. Return their exact OKF-root-relative paths as a sorted, unique `concept_paths` array (exclude `index.md` and `log.md`).
- Do not read full concept bodies. For each concept, read only a small leading range sufficient to validate YAML frontmatter (normally at most the first 60 lines).
- Verify each concept starts with frontmatter containing a non-empty `type`.
- Verify the folder index links every directly contained concept and that its relative links do not escape the OKF root.
- `concept_count` MUST equal the length of `concept_paths`; report duplicate or ambiguous paths as errors.
- Report unexpected nested directories because these flows intentionally generate one semantic folder layer with concepts directly inside it.
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
