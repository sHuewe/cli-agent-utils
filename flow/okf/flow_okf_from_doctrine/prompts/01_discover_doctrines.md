Discover Markdown doctrines below {{var:doctrine_path}}.

This path is the complete source boundary (one file or a directory). Recursively enumerate .md/.markdown files in deterministic sorted order. Assign stable IDs m001...; do not read complete documents or modify files. Include unsupported files in warnings.

Return JSON only:
{"doctrine_path":"{{var:doctrine_path}}","project":{"name":"string","summary":"string"},"doctrines":[{"id":"m001","name":"string","path":"workspace-relative/file.md"}],"warnings":["string"]}
