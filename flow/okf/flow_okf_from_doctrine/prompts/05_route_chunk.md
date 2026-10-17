Route ONE doctrine chunk's inventory to ONE semantic folder.

Chunk: {{var:chunk}}
Folder: {{var:folder}}
Complete semantic structure: {{var:structure}}
Completed scan inventory supplied as JSON by the runner: {{var:scan}}

Use only the supplied scan JSON. Do not read flow state files, original sources, or other chunks. Check document_id and chunk_id against the descriptor; report discrepancies as warnings. For each candidate_concepts and knowledge_items item choose the single best folder considering all structure.folders; break ties by folder order. Only emit items assigned to this folder. Preserve ALL content, evidence, normative flags and kinds. Prefix local IDs with chunk ID (c001:rule001, c001:topic001); downstream prefixes document ID. Never omit unresolved items without warning. Do not modify files.

Return JSON only:
{"document_id":"m001","chunk_id":"c001","folder_id":"string",
"candidate_concepts":[{"id":"c001:topic001","name":"string","description":"string","evidence_ranges":[{"doctrine":"path.md","start_line":1,"end_line":20,"reason":"string"}]}],
"knowledge_items":[{"id":"c001:rule001","kind":"rule|obligation|prohibition|permission|condition|exception|procedure|definition|model|fact|dependency|other","name":"string","description":"string","normative":true,"evidence_ranges":[{"doctrine":"path.md","start_line":1,"end_line":20,"reason":"string"}]}],"warnings":["string"]}
