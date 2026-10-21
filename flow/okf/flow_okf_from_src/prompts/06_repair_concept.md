Repair exactly one generated source-derived OKF concept based on its verification result.

Source root: `{{var:source_root}}`
Target OKF root: `{{var:okf_root}}`

Concept plan:
{{var:concept}}

Verification:
{{var:verification}}

Rules:
- Read the target concept before changing it.
- If verification status is `ok`, do not modify files and return all verified `documented_item_ids`.
- Otherwise fix every concrete verification finding. In particular, no assigned `coverage_items` may remain undocumented when source evidence supports them.
- Inspect only the source evidence needed for the listed findings; do not broadly re-analyze the unit.
- Preserve correct content and frontmatter and avoid unrelated rewrites.
- Keep all writes below the OKF root and never modify source code.
- Do not add `verified`.

Return exactly one JSON object:
{
  "status":"ok|repaired",
  "concept_id":"string",
  "path":"relative/concept.md",
  "documented_item_ids":["fn001","cfg001"],
  "changed_paths":["relative/path"],
  "remaining_item_ids":[],
  "remaining_warnings":["string"]
}

Return valid JSON only.
