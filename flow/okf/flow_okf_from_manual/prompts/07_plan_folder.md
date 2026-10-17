Plan all OKF concepts for exactly one semantic folder by merging routed evidence fragments from all manuals.

Target OKF root: `{{var:okf_root}}`

Folder:
{{var:folder}}

All known manuals:
{{var:manuals}}

Completed per-manual compact scan profiles, including authoritative chunk lists:
{{var:scans}}

Semantic structure:
{{var:structure}}

Routed inventories for this folder (JSON array supplied by runner):
{{var:routes}}

Rules:
- Do not re-scan manuals.
- For EVERY scan in the supplied `scans` array, inspect scan.output.chunks and require exactly one matching entry in the supplied `routes` array (document_id, chunk_id, folder_id).
- Do not read any flow state files, other folders, or original manuals. The runner supplies completed routing JSON.
- Local routed item IDs already include the chunk prefix (e.g. c001:fn003). Prefix each final coverage item ID with document ID (e.g. m001:c001:fn003). Never strip the chunk ID: fn001/cfg001 repeat in separate chunks.
- If a route entry is missing, duplicated, or inconsistent, flag incomplete coverage. Missing/unreadable route files are rejected by the runner before prompting.
- Merge duplicate/overlapping topics across manuals while preserving evidence ranges.
- Every routed external function and configuration option must be assigned to at least one concept.
- Concept paths are exactly `<folder.path>/<kebab-case-name>.md`. No root concepts and no additional directory level.
- Use folder-local concept IDs `c001...`.
- Put exact assigned function/configuration objects into each concept's `coverage_items`.
- Prefix coverage item IDs with the manual ID, e.g. `m001:c001:fn003` or `m002:c002:cfg007`.
- The top-level `coverage` list must contain every routed function/configuration item exactly once by prefixed ID.
- Each concept carries all bounded `evidence_ranges` needed to build it.
- There is no concept-count cap. Complete coverage takes precedence.

Return exactly one JSON object:
{
  "folder":{"id":"string","path":"string","title":"string"},
  "concepts":[
    {
      "id":"c001","folder_id":"string","path":"folder/concept.md","type":"string","title":"string","description":"string","tags":["string"],"related":["folder/other.md"],
      "evidence_ranges":[{"manual":"workspace-relative/path","start_line":1,"end_line":120,"reason":"string"}],
      "coverage_items":[{"id":"m001:c001:fn001|m001:c001:cfg001","kind":"external_function|configuration_option","name":"string","description":"string","evidence_ranges":[{"manual":"workspace-relative/path","start_line":1,"end_line":40,"reason":"string"}]}]
    }
  ],
  "coverage":[{"item_id":"m001:c001:fn001|m001:c001:cfg001","kind":"external_function|configuration_option","name":"string","covered_by":["c001"]}],
  "uncovered_item_ids":[],
  "warnings":["string"]
}

Return valid JSON only.
