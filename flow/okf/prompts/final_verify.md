Perform a final read-only structural verification of the generated OKF repository.

Target OKF root: `{{var:okf_root}}`
Root-index result:
{{var:root_index}}

Rules:
- Start at `<okf_root>/index.md` and follow the internal OKF navigation.
- Verify that the root `index.md` exists, linked indexes/concepts are reachable, concept files exist, concept frontmatter contains a non-empty `type`, and internal Markdown links remain within the OKF repository.
- Report broken links, missing files, malformed concepts, unreachable generated concepts and obvious structural inconsistencies.
- Include concepts created or extended by the additional-concept phase in the structural check.
- Do not modify files.
- Do not perform another broad analysis of the original source material; this is a structural/navigation verification pass.

Return exactly one JSON object:
{
  "status":"ok|needs_attention",
  "checked_indexes":["relative/path/index.md"],
  "findings":[
    {"severity":"error|warning","path":"relative/path","problem":"string"}
  ],
  "warnings":["string"]
}

Return valid JSON only.
