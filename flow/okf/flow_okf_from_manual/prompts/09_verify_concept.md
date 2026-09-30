Verify exactly one manual-derived OKF concept against its bounded evidence and assigned coverage items.

Target OKF root: `{{var:okf_root}}`

Concept:
{{var:concept}}

Build result:
{{var:build}}

Rules:
- Read the generated concept and check its planned path/frontmatter.
- NEVER read a manual without both `start_line` and `end_line`.
- Re-read only `concept.evidence_ranges`.
- For every `concept.coverage_items` entry, verify the actual concept text documents that exact function/configuration item. Build-result IDs alone do not prove coverage.
- Configuration coverage must make the supported setting/key/options discoverable; generic "configurable" wording is insufficient.
- Verify important factual claims, manual references and obvious internal links.
- Do not modify files.

Return exactly one JSON object:
{"status":"ok|needs_repair","concept_id":"string","path":"relative/concept.md","documented_item_ids":["string"],"missing_item_ids":["string"],"findings":[{"severity":"error|warning","item_id":"optional id or empty string","problem":"string","required_change":"string"}],"warnings":["string"]}

Return valid JSON only.
