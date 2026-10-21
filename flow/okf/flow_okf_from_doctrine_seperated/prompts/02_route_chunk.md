Convert ONE completed doctrine chunk scan to an unmodified-content route for exactly ONE local folder.
Chunk: {{var:chunk}}
Folder: {{var:folder}}
Source scan supplied by runner: {{var:scan}}

No file access. Require scan.document_id and scan.chunk_id to match chunk.
Route ALL candidate_concepts and knowledge_items to the given folder; no
cross-doctrine routing, no omission. Preserve descriptions, evidence, normative
force and qualifiers. Prefix local item IDs with chunk.id (c001:rule001).
Do not duplicate any item. Explicitly warn on malformed scans.

Return valid JSON only:
{"document_id":"matching chunk document_id","chunk_id":"matching chunk.id",
"folder_id":"matching folder.id",
"candidate_concepts":[{"id":"c001:topic001","name":"string","description":"string","evidence_ranges":[]}],
"knowledge_items":[{"id":"c001:rule001","kind":"rule|fact|definition|other","name":"string","description":"exact sourced statement","normative":true,"evidence_ranges":[]}],
"warnings":[]}
