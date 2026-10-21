Verify exactly one doctrine-derived concept.
OKF root: {{var:okf_root}}
Concept: {{var:concept}}
Build result: {{var:build}}

Read actual generated concept and only bounded evidence_ranges using start_line AND end_line. Check every coverage_items entry against actual text, not merely build JSON. Verify modal force, conditions, permissions, exceptions, descriptive fidelity, contradictions, references and frontmatter. Do not modify files. Return valid JSON only:
{"status":"ok|needs_repair","concept_id":"string","path":"relative/concept.md","documented_item_ids":["string"],"missing_item_ids":["string"],"findings":[{"severity":"error|warning","item_id":"string","problem":"string","required_change":"string"}],"warnings":["string"]}
