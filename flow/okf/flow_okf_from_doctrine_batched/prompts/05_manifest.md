# Emit one small, source-grounded SECTION manifest for global discovery

Source: {{var:source}}
Section ID: {{var:section_id}}
Original scan: {{var:scan}}
Compact concept summaries: {{var:plan}}
Deterministic coverage: {{var:coverage}}

No tools. Return ONLY compact concept metadata, NOT full original text.
A path from plan is relative to the OKF root; preserve that relative path,
do not invent or prepend an unknown root. Every concept must appear once.
Describe each concept using the scan's supported topic labels or short
knowledge items, preserving the source. At most 200 characters per summary.
Do NOT imply coverage=ok if scan.status!=ok or coverage.status!=ok.
Propagate every unresolved scan and coverage warning.

JSON object:
{"status":"ok|needs_attention","source_path":"<source.path>",
 "source_slug":"<source.slug>","section_id":"<section_id>",
 "concepts":[
  {"path":"doctrines/<source.slug>/s001-topic.md","title":"topic",
   "description":"concise supported facts","source_path":"original.md",
   "source_slug":"source slug"}],
 "warnings":[]}

