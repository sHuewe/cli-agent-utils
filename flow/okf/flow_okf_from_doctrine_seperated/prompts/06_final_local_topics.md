Construct one compact, COMPLETE local concept-topic registry for this doctrine.
Folder: {{var:folder}}
Reduced bounded suggestions: {{var:suggestions}}

Merge duplicates and overlapping labels without dropping genuinely distinct
subtopics. Choose unique IDs t001, t002...; every topic path MUST be directly
under folder.path, lowercase kebab-case and unique. Type must be a meaningful
OKF type; keep titles/descriptions compact. Include semantic local tags, but
do not invent GLOBAL cross-doctrine topic tags in this stage. Do not read
files, create concepts, or copy source evidence. If any reduction returned
needs_attention or is malformed, return warnings and do not pretend complete.
Downstream deterministic group_items validates paths, IDs and assigned coverage.

JSON only:
{"folder":{"id":"same folder id","path":"same folder path","title":"same folder title"},
"topics":[{"id":"t001","path":"folder-path/topic.md","type":"concept","title":"title","description":"one sentence","tags":[]}],"warnings":[]}
