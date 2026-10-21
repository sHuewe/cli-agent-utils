Route one manual scan into exactly one already planned semantic OKF folder.

Manual scan:
{{var:scan}}

Complete semantic folder structure:
{{var:structure}}

Current target folder:
{{var:folder}}

Rules:
- Do not read or modify files.
- For each scan item, compare all declared folders and determine its single best semantic home from their descriptions/routing guidance.
- Include the item in this result only when the current target folder is that best home.
- If two folders appear equally suitable, break the tie deterministically by the order in `structure.folders`: the earlier folder wins.
- Preserve IDs and evidence ranges exactly.
- The same decision rule must be applied to candidate concepts, external functions and configuration options.
- It is valid for the current folder to receive no items.
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
