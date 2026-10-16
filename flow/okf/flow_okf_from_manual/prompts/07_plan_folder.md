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

Rules:
- Do not re-scan manuals.
- For EVERY scan in the supplied `scans` array, inspect scan.output.chunks. For EVERY listed chunk read exactly flow/okf/flow_okf_from_manual/state/routes/<chunk.document_id>-<chunk.id>-<folder.id>.json.
- Read no route files for other folders and do not read original manuals.
- Local routed item IDs already include the chunk prefix (e.g. c001:fn003). Prefix each final coverage item ID with document ID (e.g. m001:c001:fn003). Never strip the chunk ID: fn001/cfg001 repeat in separate chunks.
- If a listed route file is missing or unreadable, flag the folder as incomplete instead of silently dropping coverage.
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
