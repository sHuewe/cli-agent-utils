Build exactly one doctrine-derived OKF concept from its planned evidence.

OKF root: {{var:okf_root}}
Concept: {{var:concept}}

Read only concept.evidence_ranges with both start_line and end_line. Write exactly one concept under <okf_root>/<concept.path>. Frontmatter must start at first byte and contain type,title,description,tags,status:stable, never verified. Cover every coverage_items entry preserving normative strength, scope, conditions, exceptions and descriptive details. Keep disagreements attributed. Include ## Doctrine references with path:Lstart-Lend. Do not modify source files or invent claims. Return valid JSON only:
{"status":"created","concept_id":"string","path":"relative/concept.md","documented_item_ids":["m001:c001:rule001"],"evidence_ranges":[{"doctrine":"path.md","start_line":1,"end_line":20,"reason":"string"}],"warnings":["string"]}
