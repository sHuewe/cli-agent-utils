Discover the manual files that form the complete source scope for this OKF generation flow.

Configured manual path: `{{var:manual_path}}`

Rules:
- Treat `manual_path` as the complete source boundary. Do not inspect files outside it.
- It may point to one readable line-oriented text manual or a directory containing several.
- If it is a directory, enumerate readable text/manual files recursively in deterministic path order.
- Do not include PDFs or binary/unsupported files; report them in warnings.
- Do not read an entire manual here. Use only a small bounded line range when a title is needed.
- Assign stable IDs `m001`, `m002`, ... in path order.
- Do not modify files.

Return exactly one JSON object:
{
  "manual_path":"{{var:manual_path}}",
  "project":{"name":"string","summary":"short description of the documentation source"},
  "manuals":[{"id":"m001","name":"human-readable title or filename","path":"workspace-relative/path"}],
  "warnings":["string"]
}

Return valid JSON only.
