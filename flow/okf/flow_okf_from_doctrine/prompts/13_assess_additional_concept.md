Assess one proposed additional doctrine concept against current OKF.
Doctrine root: {{var:doctrine_path}}
OKF root: {{var:okf_root}}
Structure: {{var:structure}}
Known doctrines: {{var:doctrines}}
Request: {{var:requested_concept}}

Inspect OKF first. If evidence is needed, search_text only under doctrine_path then read bounded relevant line ranges; never rescan whole doctrines. Choose covered|not_applicable|extend|create. New concepts must belong to existing semantic folders. Preserve normative force and source attribution. Never modify files. Return JSON only:
{"request":{"id":"string","name":"string","description":"string"},"action":"covered|not_applicable|extend|create","folder_id":"string","target_path":"relative/path.md","type":"string","title":"string","description":"string","tags":["string"],"evidence_ranges":[{"doctrine":"path.md","start_line":1,"end_line":20,"reason":"string"}],"reason":"string"}
