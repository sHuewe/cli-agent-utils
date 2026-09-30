Expose the configured roots for the question-processing child flow.

Configured manual path: `{{var:manual_path}}`
Configured OKF root: `{{var:okf_root}}`

Rules:
- Do not read or modify files.
- Return both configured values exactly as supplied.
- This is only a configuration bridge; do not add other fields.

Return exactly one JSON object:
{
  "manual_path":"{{var:manual_path}}",
  "okf_root":"{{var:okf_root}}"
}

Return valid JSON only.
