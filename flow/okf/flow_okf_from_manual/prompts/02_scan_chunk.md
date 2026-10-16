Scan exactly ONE bounded chunk of one manual. Complete the local inventory, then stop.

Chunk:
{{var:chunk}}

Rules:
- Read only chunk.document_path, with exactly start_line=chunk.start_line and end_line=chunk.end_line.
- At most one primary read_file call is needed. Never read the entire manual and do not read other chunks.
- A final chunk may end beyond EOF; inventory only lines actually returned.
- Identify every reusable topic, externally visible capability/function, and individually configurable key/option within THIS chunk.
- Do not collapse independent configuration settings. Keep descriptions concise.
- IDs are local to this chunk: topic001..., fn001..., cfg001...
- Every item needs exact workspace-relative source path and 1-based inclusive evidence ranges INSIDE this chunk and inside actual returned content.
- If an item starts/ends at the boundary, record it and warn that adjacent context may be needed later; do not independently read adjacent chunks.
- Never claim to have inspected source not returned by the tool; do not modify files.

Return JSON only:
{
 "document_id":"m001","chunk_id":"c001",
 "manual":{"id":"m001","name":"string","path":"workspace-relative/path"},
 "summary":"string",
 "candidate_concepts":[{"id":"topic001","name":"string","description":"string","evidence_ranges":[{"manual":"workspace-relative/path","start_line":1,"end_line":10,"reason":"string"}]}],
 "external_functions":[{"id":"fn001","name":"string","kind":"string","description":"string","evidence_ranges":[{"manual":"workspace-relative/path","start_line":1,"end_line":10,"reason":"string"}]}],
 "configuration_options":[{"id":"cfg001","name":"string","description":"string","evidence_ranges":[{"manual":"workspace-relative/path","start_line":1,"end_line":10,"reason":"string"}]}],
 "scan_checks":{"function_sweep":"completed","configuration_sweep":"completed"},
 "warnings":["string"]
}
