Summarize a completed doctrine semantic folder.
Folder: {{var:folder}}
Plan: {{var:plan}}
Coverage: {{var:coverage}}
Concept results: {{var:concept_results}}

Do not use tools. Preserve unresolved coverage failures; do not copy evidence arrays. Return JSON only:
{"folder_id":"string","folder_path":"string","status":"ok|needs_attention","concepts":[{"id":"c001","path":"folder/concept.md","title":"string"}],"coverage":{"normative_items":{"expected":0,"documented":0},"descriptive_items":{"expected":0,"documented":0},"missing_item_ids":["string"]},"warnings":["string"]}
