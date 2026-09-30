Assess exactly one requested additional concept against the current manual-derived OKF.

Configured manual path: `{{var:manual_path}}`
Target OKF root: `{{var:okf_root}}`

Semantic structure:
{{var:structure}}

Known manuals:
{{var:manuals}}

Requested concept:
{{var:requested_concept}}

Rules:
- Do not modify files.
- Inspect relevant current OKF concepts first.
- If evidence is needed, use `search_text` only inside `manual_path`, then bounded line reads around relevant hits.
- NEVER read a manual without both `start_line` and `end_line`; never fully rescan a manual.
- Choose exactly one action: `covered`, `not_applicable`, `extend`, or `create`.
- For `create`, choose one existing semantic folder; target exactly `<folder.path>/<kebab-name>.md`.
- For `extend`, target an existing concept in a declared folder.
- Return concrete bounded evidence ranges for changes.

Return exactly one JSON object:
{"request":{"id":"string","name":"string","description":"string"},"action":"covered|not_applicable|extend|create","folder_id":"declared folder id or empty string","target_path":"relative/path.md or empty string","type":"string or empty string","title":"string or empty string","description":"string","tags":["string"],"evidence_ranges":[{"manual":"workspace-relative/path","start_line":1,"end_line":120,"reason":"string"}],"reason":"string"}

Return valid JSON only.
