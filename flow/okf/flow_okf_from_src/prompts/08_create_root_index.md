Create the root index for the generated OKF repository after all unit iterations have completed.

Target OKF root: `{{var:okf_root}}`
Project:
{{var:project}}

Unit results:
{{var:units}}

Rules:
- Use only unit results supplied above plus the generated unit indexes you inspect.
- Ensure the OKF root exists.
- Write `<okf_root>/index.md` as the repository entry point.
- Link to each unit index with relative Markdown links.
- Keep the root index compact: project summary plus navigation to units. Do not duplicate detailed unit documentation.
- Never write outside the OKF root and do not modify source code.

Return exactly one JSON object:
{
  "status":"created",
  "index_path":"index.md",
  "unit_indexes":["relative/path/index.md"],
  "warnings":["string"]
}

Return valid JSON only.
