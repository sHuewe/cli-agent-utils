Summarize a completed doctrine semantic folder from COMPACT, verified metadata.

Folder: {{var:folder}}
Concept summaries (IDs, paths and titles only): {{var:plan}}
Deterministic coverage result: {{var:coverage}}
Coverage verification details: {{var:concept_results}}

Do not use tools or read state files. Do not copy evidence, knowledge items, or
large plan structures. Do not claim full coverage unless coverage.status is
exactly "ok"; preserve all missing_item_ids and warnings. Preserve the concept
summaries without inventing extra files. The verification is computed from
actual repair results, not claimed LLM plan coverage.

Return JSON only:
{"folder_id":"string","folder_path":"string","status":"ok|needs_attention",
"concepts":[{"id":"t001","path":"folder/concept.md","title":"Title"}],
"coverage":{"normative_items":{"expected":0,"documented":0},
"descriptive_items":{"expected":0,"documented":0},
"missing_item_ids":["string"]},"warnings":["string"]}
