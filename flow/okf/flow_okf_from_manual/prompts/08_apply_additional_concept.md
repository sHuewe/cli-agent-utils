Apply exactly one assessed additional-concept action to the manual-derived OKF.

Target OKF root: `{{var:okf_root}}`
Assessment:
{{var:assessment}}

Rules:
- If action is `covered` or `not_applicable`, do not modify any file.
- For action `extend` or `create`, evidence must come only from `assessment.evidence_ranges`.
- For manual files, NEVER call `read_file` without both `start_line` and `end_line`. Never scan or fully read a manual in this step.
- If action is `extend`, read the target concept first, read the bounded evidence ranges, then add only the missing knowledge while preserving correct existing content and frontmatter.
- If action is `create`, read the bounded evidence ranges and create exactly one new OKF concept at `target_path` with valid frontmatter and a `## Manual references` section containing path/line citations.
- If action is `extend` or `create` but no usable evidence range is supplied, do not invent content; return `unchanged` with a warning.
- Keep every write below the OKF root. Reject absolute paths or paths containing `..`.
- Do not modify manuals or other original source material.
- Do not add `verified` or imply human review.
- If a new concept is created, update the nearest appropriate `index.md` when one exists and is the natural navigation parent. Read that index before changing it.
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
