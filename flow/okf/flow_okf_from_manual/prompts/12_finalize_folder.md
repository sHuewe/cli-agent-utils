Create a compact parent-facing result for one processed semantic folder.

Folder:
{{var:folder}}

Plan:
{{var:plan}}

Coverage:
{{var:coverage}}

Concept results:
{{var:concept_results}}

Rules:
- Do not read or modify files.
- Keep the result compact; detailed routed evidence and plans remain in state files.
- Include concept paths/titles and coverage counts/status only.
- Do not copy evidence ranges or full coverage-item descriptions.

Return exactly one JSON object:
{
  "folder_id":"string","folder_path":"string","status":"ok|needs_attention",
  "concepts":[{"id":"c001","path":"folder/concept.md","title":"string"}],
  "coverage":{"external_functions":{"expected":0,"documented":0},"configuration_options":{"expected":0,"documented":0},"missing_item_ids":["string"]},
  "warnings":["string"]
}

Return valid JSON only.
