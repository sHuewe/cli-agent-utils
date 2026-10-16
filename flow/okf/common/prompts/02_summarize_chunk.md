Produce a compact thematic profile for ONE completed source-document chunk.

Chunk inventory:
{{var:scan}}

Rules:
- Do not read or write files.
- Preserve document_id and chunk_id; summarize only what the inventory supports.
- Do not reproduce evidence ranges or item arrays.
- For manuals include counts for candidate_concepts, external_functions and configuration_options.
- For doctrines include counts for candidate_concepts and knowledge_items.
- Keep themes short and deduplicated. Any scan warnings must be retained.

Return exactly one JSON object:
{
 "document_id":"string","chunk_id":"string","summary":"one sentence",
 "themes":["short theme"],
 "counts":{"candidate_concepts":0,"external_functions":0,"configuration_options":0,"knowledge_items":0},
 "warnings":["string"]
}
Return valid JSON only.
