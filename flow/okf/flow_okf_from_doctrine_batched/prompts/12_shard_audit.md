# Audit ONE bounded global registry shard, independently

Registry shard ID: {{var:batch_id}}
DETERMINISTICALLY VALIDATED Registry object: {{var:registry}}
Per-theme verification results: {{var:theme_results}}

No tools. Verify each registry theme has exactly one corresponding
verification iteration with the same ID and path; there may be zero themes.
If the registry status is missing, unknown, or needs_attention, status MUST
be needs_attention regardless of successful theme verifications. If any
theme verification is missing, duplicate, not status=ok, or names a
different path, mark needs_attention. Preserve unresolved registry
warnings, and add concise warnings for each failed theme. Do not invent
successful verification or discard incomplete results. A successful
empty registry is allowed, but registry status must be ok.

Output one short JSON object:
{"status":"ok|needs_attention","batch_id":"exact shard ID",
 "registry_status":"ok|needs_attention",
 "checked_themes":0,"warnings":[]}
