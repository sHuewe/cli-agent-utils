# Construct ONE bounded shard of global OKF theme registry

Batch: {{var:batch}}
No tools. Preserve source path and source_slug for every member. Only
create themes with members from at least TWO distinct doctrine slugs.
A related singleton is a valid unresolved proposal but NOT a theme.
Topic descriptions and membership must remain grounded in batch items.
Never guess concept filenames. At most 12 themes in this one batch.
Use namespaced stable IDs: <batch.id>-<semantic-kebab-name>.
No collisions between shards; no path traversal. Path MUST be
themen/<theme-id>.md. Do not truncate theme memberships silently.
Preserve upstream needs_attention and warnings monotonically.

JSON OBJECT:
{"status":"ok|needs_attention",
 "themes":[{"id":"b0001-focused-name",
            "path":"themen/b0001-focused-name.md",
            "title":"Focused topic","description":"one sentence",
            "members":[{"path":"doctrines/doc/concept.md","source_slug":"doc"}]}],
 "warnings":[]}

