Plan source-grounded OKF concepts for one semantic doctrine folder.

Folder: {{var:folder}}
Structure: {{var:structure}}
All documents: {{var:doctrines}}
Document scan profiles (contain authoritative chunk lists): {{var:scans}}
OKF root: {{var:okf_root}}
Routed inventories for this folder (JSON array supplied by runner): {{var:routes}}

Use only the supplied `routes` array. For each chunk in each profile.output.chunks, require exactly one matching route (document_id, chunk_id, folder_id). Do not read flow state files, other folders, or original doctrines. Flag missing, duplicate, or inconsistent entries and never claim full coverage in such cases. Missing/unreadable JSON artifacts cause the runner to fail before prompting.
Merge related topics into coherent concepts, not a one-file-one-concept transcription. Preserve contradictions with source attribution. Every normative AND descriptive knowledge item must be assigned to at least one concept, including exceptions and qualifiers. Prefix each routed local ID with document ID, yielding m001:c001:rule001. Include full assigned objects in coverage_items and enumerate every item in top-level coverage. Each planned concept resides directly in <folder.path>/<kebab-case-name>.md; use folder-local concept IDs c001...; mark unassigned items explicitly. No source modifications.

Return JSON only:
{"folder":{"id":"string","path":"string","title":"string"},
"concepts":[{"id":"c001","folder_id":"string","path":"folder/concept.md","type":"string","title":"string","description":"string","tags":["string"],"related":["folder/other.md"],
"evidence_ranges":[{"doctrine":"path.md","start_line":1,"end_line":20,"reason":"string"}],
"coverage_items":[{"id":"m001:c001:rule001","kind":"rule","name":"string","description":"string","normative":true,"evidence_ranges":[{"doctrine":"path.md","start_line":1,"end_line":20,"reason":"string"}]}]}],
"coverage":[{"item_id":"m001:c001:rule001","kind":"rule","name":"string","covered_by":["c001"]}],"uncovered_item_ids":[],"warnings":["string"]}
