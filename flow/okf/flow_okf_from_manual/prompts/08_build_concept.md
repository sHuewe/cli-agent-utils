Create exactly one manual-derived OKF concept from its prepared bounded evidence.

Target OKF root: `{{var:okf_root}}`

Concept:
{{var:concept}}

Rules:
- Factual evidence comes only from `concept.evidence_ranges`.
- NEVER call `read_file` for a manual without both `start_line` and `end_line`.
- Read only the listed ranges. Do not scan or fully read a manual.
- Write exactly one concept at `<okf_root>/<concept.path>`, directly inside its selected semantic folder.
- Start with valid YAML frontmatter containing at least `type`, `title`, `description`, `tags`, and `status: stable`.
- Do not add `verified`.
- Explicitly document every `coverage_items` entry. Configuration families must enumerate the settings/options represented by the item.
- Include `## Manual references` with `<path>:L<start>-L<end>`.
- If evidence is insufficient, report a warning rather than reading elsewhere.
- Keep writes below the OKF root and never modify manuals.

Return exactly one JSON object:
{"status":"created","concept_id":"string","path":"relative/concept.md","documented_item_ids":["m001:fn001","m001:cfg001"],"evidence_ranges":[{"manual":"workspace-relative/path","start_line":1,"end_line":120,"reason":"string"}],"warnings":["string"]}

Return valid JSON only.
