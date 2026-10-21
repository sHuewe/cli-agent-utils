Apply exactly one assessed additional-concept action to the source-derived OKF.

Source root: `{{var:source_root}}`
Target OKF root: `{{var:okf_root}}`

Assessment:
{{var:assessment}}

Rules:
- If action is `covered` or `not_applicable`, do not modify files.
- For `extend`, read the target concept first and inspect only relevant source evidence before adding the missing knowledge.
- For `create`, inspect relevant source evidence and create exactly one concept at the assessed target path with valid frontmatter and source references.
- The target path must remain inside one already declared semantic top-level folder. Do not create new top-level folders here.
- Keep all writes below the OKF root and do not modify source code.
- Do not add `verified`.
- Do not update indexes here; the later navigation step rebuilds all folder indexes from the final generated files.

Return exactly one JSON object:
{
  "status":"unchanged|extended|created",
  "request_id":"string",
  "folder_id":"string",
  "target_path":"relative/path.md or empty string",
  "changed_paths":["relative/path"],
  "warnings":["string"]
}

Return valid JSON only.
