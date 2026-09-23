Create exactly one OKF concept for the current unit.

Target OKF root: `{{var:okf_root}}`
Unit plan:
{{var:unit_plan}}
Current concept:
{{var:concept}}

Rules:
- Treat the plan as guidance, not evidence. Inspect the actual source needed for this concept.
- Write exactly one concept file at `<okf_root>/<concept.path>`.
- Never write outside the OKF root. Reject absolute paths and paths containing `..`.
- Create missing parent directories only when required.
- Do not edit source code or other concept files.
- Start the Markdown file with valid YAML frontmatter containing at least `type`, `title`, `description`, `tags`, and `status: stable`.
- Do not add `verified` or imply human review.
- Keep content concise and durable. Include a `## Source references` section with concrete workspace-relative paths and symbols when useful.
- Add relative Markdown links only to concepts listed in `related`.

Return exactly one JSON object:
{
  "status":"created",
  "path":"relative/concept.md",
  "title":"string",
  "source_references":["workspace-relative/path"],
  "warnings":["string"]
}

Return valid JSON only.
