Assess exactly one requested additional source-derived OKF concept.

Source root: `{{var:source_root}}`
Target OKF root: `{{var:okf_root}}`

Semantic structure:
{{var:structure}}

Requested concept:
{{var:requested_concept}}

Rules:
- Do not modify files.
- Inspect the current OKF content relevant to the request first.
- Inspect source only when needed and only inside `source_root`.
- Choose exactly one action: `covered`, `not_applicable`, `extend`, or `create`.
- For `create`, choose exactly one folder declared in `structure.folders`; the target path must be `<folder.path>/<kebab-name>.md`, with no additional directory layer.
- For `extend`, the target must be an existing concept inside a declared semantic folder.
- Never create a normal concept directly below the OKF root.
- Prefer `extend` when the request naturally belongs in an existing focused concept.
- Return concrete source hints for any change.

Return exactly one JSON object:
{
  "request":{"id":"string","name":"string","description":"string"},
  "action":"covered|not_applicable|extend|create",
  "folder_id":"declared folder id or empty string",
  "target_path":"relative/path.md or empty string",
  "type":"string or empty string",
  "title":"string or empty string",
  "description":"string",
  "tags":["string"],
  "source_hints":["workspace-relative/path#symbol-or-key"],
  "reason":"string"
}

Return valid JSON only.
