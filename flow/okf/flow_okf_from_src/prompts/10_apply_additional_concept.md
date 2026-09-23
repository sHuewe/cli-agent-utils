Apply exactly one assessed additional-concept action to the generated OKF.

Source root: `{{var:source_root}}`
Target OKF root: `{{var:okf_root}}`
Assessment:
{{var:assessment}}

Rules:
- If action is `covered` or `not_applicable`, do not modify any file.
- If action is `extend`, read the target concept first, inspect the relevant source evidence, then add only the missing knowledge while preserving correct existing content and frontmatter.
- If action is `create`, inspect the relevant source evidence and create exactly one new OKF concept at `target_path` with valid frontmatter and source references.
- Treat `source_root` as the complete source scope. Do not list, read, search or otherwise inspect source files outside it.
- Keep every write below the OKF root. Reject absolute paths or paths containing `..`.
- Do not modify source code.
- Do not add `verified` or imply human review.
- If a new concept is created, update the nearest appropriate `index.md` so the concept is reachable through OKF navigation. Read that index before changing it.
- If an existing concept is extended, change an index only if navigation is actually missing or broken.

Return exactly one JSON object:
{
  "status":"unchanged|extended|created",
  "request_id":"string",
  "target_path":"relative/path.md or empty string",
  "changed_paths":["relative/path"],
  "warnings":["string"]
}

Return valid JSON only.
