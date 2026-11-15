# Compact semantic manifest of ONE generated concept

Original source: {{var:source}}
Planned concept, including merged source ranges: {{var:concept}}
Actual repair result: {{var:repair}}

No tools. Do not duplicate full knowledge items or evidence content.
Output exactly one compact object with its source identity and ONE
concept, using concept.path (relative to OKF root) unchanged.
Preserve status=needs_attention if repair is missing, incomplete, does not
match the planned ID/path or contains remaining_item_ids or remaining_warnings.
Otherwise status=ok. Never claim source coverage beyond this one concept.
Summary MUST describe actual planned subject matter in <=180 chars;
do not invent facts from concept filenames.

{"status":"ok|needs_attention","source_path":"<source.path>",
 "source_slug":"<source.slug>","concepts":[
  {"path":"doctrines/<slug>/<folder>/<concept>.md",
   "title":"topic","description":"short supported summary",
   "source_path":"<source.path>","source_slug":"<source.slug>"}],
 "warnings":[]}
