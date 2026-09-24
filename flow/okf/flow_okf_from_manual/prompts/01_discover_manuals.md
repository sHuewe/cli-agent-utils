Discover the manual files that form the complete source scope for this OKF generation flow.

Configured manual path: `{{var:manual_path}}`

Rules:
- Treat `manual_path` as the complete source boundary for this step. Do not inspect files outside it.
- `manual_path` may point either to one readable text manual or to a directory containing one or more manuals.
- If it is a directory, enumerate readable text/manual files recursively below it in deterministic path order.
- The manuals are line-oriented text inputs. Do not include PDF files. If a PDF or unsupported/binary file is encountered, skip it and report it in `warnings`.
- Do not read an entire manual in this step. If content is needed to infer a human-readable title, use only a small bounded line read with both `start_line` and `end_line`.
- Assign stable IDs `m001`, `m002`, ... in deterministic path order. IDs must match `[A-Za-z0-9_-]+`.
- Every returned path must be workspace-relative and remain inside the configured manual path.
- Do not write or modify files.

Return exactly one JSON object:
{
  "project": {
    "name":"string",
    "summary":"short description of the knowledge source"
  },
  "manuals":[
    {
      "id":"m001",
      "name":"human-readable manual title or filename",
      "path":"workspace-relative/path"
    }
  ],
  "warnings":["string"]
}

Return valid JSON only.
