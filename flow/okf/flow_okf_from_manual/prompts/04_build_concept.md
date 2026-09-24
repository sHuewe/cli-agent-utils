Create exactly one OKF concept from the prepared manual evidence map.

Target OKF root: `{{var:okf_root}}`
Concept plan:
{{var:concept}}

Rules:
- Treat the concept plan as navigation metadata, not as evidence. The actual evidence is in `concept.evidence_ranges`.
- For manual files, NEVER call `read_file` without both `start_line` and `end_line`.
- Read only the manual ranges listed in `concept.evidence_ranges`. Do not scan or fully read a manual and do not inspect unrelated manual ranges.
- If the listed evidence is insufficient for a claim, omit the claim and report a warning rather than searching the rest of the manuals.
- Write exactly one concept file at `<okf_root>/<concept.path>`.
- Never write outside the OKF root. Reject absolute paths and paths containing `..`.
- Create missing parent directories only when required.
- Do not modify manuals or other original source material.
- Start the Markdown file with valid YAML frontmatter containing at least `type`, `title`, `description`, `tags`, and `status: stable`.
- Do not add `verified` or imply human review.
- Keep content concise and durable.
- Include a `## Manual references` section. Cite each relevant evidence range as `<workspace-relative-manual>:L<start>-L<end>`.
- Add relative Markdown links only to concepts listed in `related`.

Return exactly one JSON object:
{
  "status":"created",
  "id":"string",
  "path":"relative/concept.md",
  "title":"string",
  "evidence_ranges":[
    {"manual":"workspace-relative/path","start_line":1,"end_line":120,"reason":"string"}
  ],
  "warnings":["string"]
}

Return valid JSON only.
