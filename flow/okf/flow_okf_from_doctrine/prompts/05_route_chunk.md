Route ONE doctrine chunk's inventory to ONE specified semantic folder.

Chunk: {{var:chunk}}
Target folder: {{var:folder}}
Complete semantic structure: {{var:structure}}
Completed scan inventory supplied as JSON by the runner: {{var:scan}}

Use only the supplied scan JSON. Do not read flow state files, original sources, or other chunks. Check whether the scan's document_id and chunk_id match the chunk descriptor; report discrepancies as warnings.

For each candidate_concepts and knowledge_items entry, choose the single best semantic folder considering all structure.folders; break ties by folder order. Output ONLY the entries assigned to the specified target folder. Never output entries belonging to another folder, and never change folder_id to represent a different folder. If no entries belong to the target folder, return empty candidate_concepts and knowledge_items arrays.

The three top-level identifiers in the response are FIXED and must be reproduced exactly as shown in the JSON template below. In particular, folder_id is the requested target folder ID, not a folder that the model selects. Preserve ALL assigned content, evidence, normative flags and kinds. Prefix local item IDs with chunk ID (for example, c001:rule001 or c001:topic001); downstream processing prefixes document ID. Never omit unresolved items without a warning. Do not modify files.

Return valid JSON only, with these exact top-level identifier values:
{"document_id":"{{var:document_id}}","chunk_id":"{{var:chunk_id}}","folder_id":"{{var:folder_id}}",
"candidate_concepts":[{"id":"{{var:chunk_id}}:topic001","name":"string","description":"string","evidence_ranges":[{"doctrine":"path.md","start_line":1,"end_line":20,"reason":"string"}]}],
"knowledge_items":[{"id":"{{var:chunk_id}}:rule001","kind":"rule|obligation|prohibition|permission|condition|exception|procedure|definition|model|fact|dependency|other","name":"string","description":"string","normative":true,"evidence_ranges":[{"doctrine":"path.md","start_line":1,"end_line":20,"reason":"string"}]}],
"warnings":["string"]}
