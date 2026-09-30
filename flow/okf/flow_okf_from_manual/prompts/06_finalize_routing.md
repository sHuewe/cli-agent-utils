Return a compact completion record for routing one manual.

Manual:
{{var:manual}}

Semantic structure:
{{var:structure}}

Rules:
- Do not read or modify files.
- Do not include routed content; it is persisted in dedicated route state files.

Return exactly one JSON object:
{"manual_id":"string","routed_folder_ids":["folder-id"],"status":"routed"}

Return valid JSON only.
