Assign global themes to exactly one doctrine's concepts.
Manifest: {{var:manifest}}
Existing global themes: {{var:themes}}

Only use manifest.concepts and the given stable theme IDs. Match semantic
scope, not merely similar words. Allow zero or multiple themes per concept.
Output EVERY concept from the manifest, using a distinct stable assignment id
derived from its module-local concept filename, without path traversal. Keep
exact workspace-relative path and current theme ID list. Do not copy concept
bodies, invent new global topics, or read files. Preserve a clearly identified
needs_attention on malformed input or invalid registry.

Return JSON only:
{"status":"ok|needs_attention","assignments":[{"id":"stable-filename","path":"workspace-relative concept.md","theme_ids":["known-theme-id"]}],"warnings":[]}
