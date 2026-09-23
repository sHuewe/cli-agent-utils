Create exactly one OKF concept from source code.

Source root: `{{var:source_root}}`
Target OKF root: `{{var:okf_root}}`

Concept specification:
{{var:concept}}

Rules:
- Treat the concept specification as a plan, not as evidence. Inspect the actual source files needed to substantiate the concept before writing it.
- Stay focused on this one concept. Do not create or edit other concepts or indexes.
- The destination is `<okf_root>/<concept.path>`. It must be relative to the OKF root, must end in `.md`, and must not be `index.md` or `log.md`.
- Never write outside the target OKF root. Reject absolute paths or any path containing `..`.
- Use `source_hints` as starting points, then follow relevant code references when necessary. Do not fabricate implementation details.
- If planned details conflict with the source, follow the source and mention the discrepancy in the returned warnings.
- Write concise, durable knowledge rather than copying large source fragments.
- Include concrete workspace-relative source references in a `## Source references` section. Use paths, and add symbols/classes/functions when useful.
- Include meaningful relationships to planned related concepts using relative Markdown links where appropriate. Do not invent links to concepts not present in `related`.
- Do not claim human review or add a `verified` field.

The Markdown file must start with YAML frontmatter:

---
type: <concept.type>
title: <concept.title>
description: <short source-grounded description>
tags:
  - <tag>
status: stable
---

After the frontmatter, structure the body for the concept rather than following a fixed template. Explain responsibilities, behavior, interactions, constraints and important implementation details that are actually supported by source evidence.

Before writing, if the destination file already exists, read it first. Then write the complete intended file with `write_file`.

Return exactly one JSON object:

{
  "id": "the orchestration id from the concept specification",
  "path": "the concept path relative to the OKF root",
  "status": "written",
  "source_references": ["workspace-relative path"],
  "warnings": ["string"]
}

Return valid JSON only.
