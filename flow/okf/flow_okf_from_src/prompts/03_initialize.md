Initialize the directory structure for the planned OKF repository.

Target OKF root: `{{var:okf_root}}`

Plan:
{{var:plan}}

Rules:
- Do not change source code.
- Create the target OKF root if it does not exist.
- Create every directory listed in `directories`, including intermediate parents, in shallow-to-deep order.
- Use only paths below the target OKF root. Reject any plan entry containing an absolute path or `..` instead of trying to normalize it.
- Do not create concept or index files in this step.
- If a required directory already exists, leave it unchanged.
- Do not delete or overwrite anything.

Return exactly one JSON object:

{
  "status": "initialized",
  "okf_root": "string",
  "created_directories": ["string"],
  "existing_directories": ["string"],
  "warnings": ["string"]
}

Return valid JSON only.
