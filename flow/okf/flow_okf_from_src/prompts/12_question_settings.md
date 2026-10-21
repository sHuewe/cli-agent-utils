Expose the configured roots for the question-processing child flow.

Configured source root: `{{var:source_root}}`
Configured OKF root: `{{var:okf_root}}`

Rules:
- Do not read or modify files.
- Return both configured values exactly as supplied.
- This is only a configuration bridge; do not add other fields.

Return exactly one JSON object:
{
  "source_root":"{{var:source_root}}",
  "okf_root":"{{var:okf_root}}"
}

Return valid JSON only.
