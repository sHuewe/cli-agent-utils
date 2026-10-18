Route exactly ONE completed manual chunk inventory to ONE semantic OKF folder.

Chunk descriptor:
{{var:chunk}}

Target folder:
{{var:folder}}

Complete structure:
{{var:structure}}

Completed scan inventory supplied by the runner:
{{var:scan}}

Rules:
- Use only the supplied scan JSON. Do not read flow state files, original manuals, or other scans. Check document_id and chunk_id against the descriptor; report discrepancies.
- For EVERY candidate concept, function and configuration option in that chunk, choose its single best folder from the complete semantic structure.
- Include an item only if that folder is the target folder. Break ties by structure.folders order.
- Preserve evidence and local IDs, but prefix EVERY item ID with the chunk ID (e.g. c001:fn001, c001:cfg001, c001:topic001). Downstream uses document_id:chunk_id:local-id for global uniqueness.
- Do not synthesize new evidence or drop partially understood items; report ambiguities as warnings.
- It is valid for the target folder to contain no items. Do not modify files.

Return JSON only:
{
 "document_id":"m001","chunk_id":"c001","folder_id":"string",
 "candidate_concepts":[{"id":"c001:topic001","name":"string","description":"string","evidence_ranges":[{"manual":"string","start_line":1,"end_line":10,"reason":"string"}]}],
 "external_functions":[{"id":"c001:fn001","name":"string","kind":"string","description":"string","evidence_ranges":[{"manual":"string","start_line":1,"end_line":10,"reason":"string"}]}],
 "configuration_options":[{"id":"c001:cfg001","name":"string","description":"string","evidence_ranges":[{"manual":"string","start_line":1,"end_line":10,"reason":"string"}]}],
 "warnings":["string"]
}
