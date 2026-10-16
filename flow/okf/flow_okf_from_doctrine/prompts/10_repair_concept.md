Repair exactly one doctrine concept.
OKF root: {{var:okf_root}}
Concept: {{var:concept}}
Verification: {{var:verification}}

Read target concept before writing. If already ok, make no changes. Otherwise fix coverage, exceptions, normative scope, attribution and factual errors using only bounded concept.evidence_ranges with both line arguments. Never introduce unsupported material or resolve contradictions by guessing. Modify only target concept within OKF root. Return JSON only:
{"status":"ok|repaired","concept_id":"string","path":"relative/concept.md","documented_item_ids":["string"],"changed_paths":["relative/path"],"remaining_item_ids":[],"remaining_warnings":["string"]}
