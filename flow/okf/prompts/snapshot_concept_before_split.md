Capture the complete original OKF concept immediately before a potential split, without modifying files.

Target OKF root: `{{var:okf_root}}`
Concept path: `{{var:concept_path}}`
Assessment: {{var:assessment}}

Rules:
- Only capture for `assessment.action == "split"`. For other actions, return `not_needed` without reading any concept.
- Read the FULL Markdown content at the exact concept path within the OKF root, including frontmatter, all sections, links, references, and trailing text. Never summarize or omit material.
- Also read the FULL `index.md` in the concept's direct parent folder. Preserve its exact content as `index_content` and its OKF-root-relative path as `index_path`; this is the baseline for protecting links to unrelated concepts and other previously documented navigation.
- Do not read original source code or manuals. Do not modify files.
- If either file is missing, invalid, outside the OKF root, or either full content cannot be read or represented in the result, return `needs_attention` and no partial snapshot.
- Preserve all characters and line breaks in `content` and `index_content`. They must reproduce both original files exactly.
- Do not invent content or silently truncate the document.

Return exactly one JSON object:
{
  "status":"captured|not_needed|needs_attention",
  "concept_path":"relative/concept.md",
  "content":"complete original Markdown text, unchanged",
  "index_path":"relative/folder/index.md",
  "index_content":"complete original folder index text, unchanged",
  "warnings":["string"]
}

Return valid JSON only.
