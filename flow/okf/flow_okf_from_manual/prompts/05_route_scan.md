Route one manual scan into exactly one already planned semantic OKF folder.

Manual scan:
{{var:scan}}

Target folder:
{{var:folder}}

Rules:
- Do not read or modify files.
- Select only candidate concepts, external functions and configuration options whose best semantic home is this folder.
- Preserve IDs and evidence ranges exactly.
- Do not duplicate an item merely because it is related; select one best semantic home.
- It is valid for this folder to receive no items from this manual.
- Keep the result compact and omit unrelated scan data.

Return exactly one JSON object:
{
  "manual":{"id":"string","name":"string","path":"workspace-relative/path"},
  "folder_id":"string",
  "candidate_concepts":[{"id":"topic001","name":"string","description":"string","evidence_ranges":[{"manual":"string","start_line":1,"end_line":2,"reason":"string"}]}],
  "external_functions":[{"id":"fn001","name":"string","kind":"string","description":"string","evidence_ranges":[{"manual":"string","start_line":1,"end_line":2,"reason":"string"}]}],
  "configuration_options":[{"id":"cfg001","name":"string","description":"string","evidence_ranges":[{"manual":"string","start_line":1,"end_line":2,"reason":"string"}]}],
  "warnings":["string"]
}

Return valid JSON only.
