Perform a final read-only verification of the generated OKF repository.

Target OKF root: `{{var:okf_root}}`
Root-index result:
{{var:root_index}}

Rules:
- Start at `<okf_root>/index.md` and follow the linked unit indexes.
- Verify that the root `index.md` exists, all unit indexes are reachable, their listed concepts exist, concept frontmatter contains a non-empty `type`, and internal Markdown links remain within the OKF repository.
- Report broken links, missing files, malformed concepts, unreachable generated concepts and obvious structural inconsistencies.
- Include concepts created or extended by the additional-concept phase in the structural check.
- Do not modify files and do not perform another full source-code analysis.

Return exactly one JSON object:
{
  "status":"ok|needs_attention",
  "checked_unit_indexes":["relative/path/index.md"],
  "findings":[
    {"severity":"error|warning","path":"relative/path","problem":"string"}
  ],
  "warnings":["string"]
}

Return valid JSON only.
