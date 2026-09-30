Create a compact parent-facing summary for one processed source unit.

Unit:
{{var:unit}}

Plan:
{{var:plan}}

Coverage verification:
{{var:coverage}}

Concept results:
{{var:concept_results}}

Rules:
- Do not read or modify files.
- Keep this result compact; the detailed inventory/plan remain in state files and must not be copied into the parent context.
- Include concept paths and folder IDs so navigation can later be built.
- Preserve coverage counts/status and warnings.
- Do not include full concept objects, source evidence lists or coverage-item descriptions.

Return exactly one JSON object:
{
  "unit_id":"string",
  "unit_name":"string",
  "status":"ok|needs_attention",
  "concepts":[
    {"id":"c001","folder_id":"string","path":"folder/concept.md","title":"string"}
  ],
  "coverage":{
    "external_functions":{"expected":0,"documented":0},
    "configuration_options":{"expected":0,"documented":0},
    "missing_item_ids":["string"]
  },
  "warnings":["string"]
}

Return valid JSON only.
