Capture the complete original OKF concept immediately before a potential split, without modifying files.

Target OKF root: `{{var:okf_root}}`
Concept path: `{{var:concept_path}}`
Assessment: {{var:assessment}}

Rules:
- Only capture for `assessment.action == "split"`. For other actions, return `not_needed` without reading any concept.
- Read the FULL Markdown content at the exact concept path within the OKF root, including frontmatter, all sections, links, references, and trailing text. Never summarize or omit material.
- Do not read original source code or manuals. Do not modify files.
- If the path is missing, invalid, outside the OKF root, or the full content cannot be read or represented in the result, return `needs_attention` and no partial snapshot.
- Preserve all characters and line breaks in `content`. It must reproduce the original file exactly.
- Do not invent content or silently truncate the document.

Return exactly one JSON object:
{
  "status":"captured|not_needed|needs_attention",
  "concept_path":"relative/concept.md",
  "content":"complete original Markdown text, unchanged",
  "warnings":["string"]
}

Return valid JSON only.
