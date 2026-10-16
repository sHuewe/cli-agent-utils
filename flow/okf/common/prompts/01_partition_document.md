Partition exactly one line-oriented source document into bounded scan chunks.

Document:
{{var:document}}

Rules:
- This is a METADATA operation, not a content inventory. Do not read the whole document.
- Read only the configured document.path. Probe a SINGLE line at positions 1, 351, 701, 1051, ... using read_file(path, start_line=N, end_line=N) until the first "(No lines in requested range)". "(Empty file)" means no chunks.
- Each nonempty probe yields one chunk, with start_line=N and end_line=N+349 (the final end_line is a safe upper bound; it may pass EOF). Never skip a probe or omit a nonempty interval.
- Do not interpret document content or collect topic/function/rule inventories here. Never read the entire file.
- IDs must be c001, c002, ... in ascending order; preserve the exact document ID/path. A chunk must contain at most 350 lines.
- If the configured document is unreadable, report a warning and do not claim it was scanned.
- Do not modify files.

Return JSON only:
{
  "document":{"id":"m001","name":"string","path":"workspace-relative/path"},
  "chunks":[{"id":"c001","document_id":"m001","document_path":"workspace-relative/path","start_line":1,"end_line":350}],
  "warnings":["string"]
}
