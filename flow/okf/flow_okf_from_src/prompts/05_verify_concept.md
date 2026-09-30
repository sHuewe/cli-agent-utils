Verify exactly one generated source-derived OKF concept, including its mandatory function/configuration coverage.

Source root: `{{var:source_root}}`
Target OKF root: `{{var:okf_root}}`

Concept plan:
{{var:concept}}

Build result:
{{var:build}}

Rules:
- Read the generated concept file.
- Check that it exists at the planned path, below the planned semantic folder, and starts with valid YAML frontmatter containing non-empty `type`.
- For every object in `concept.coverage_items`, verify that the concept text actually documents that exact function/configuration item. A build-result ID alone is not evidence of coverage.
- Inspect only the relevant source evidence/hints needed to verify factual claims and the assigned coverage items. Do not re-analyze the unit broadly.
- A configuration item is not adequately covered by a vague statement such as "the component is configurable"; the supported key/member/options represented by the inventory item must be discoverable.
- An external function is not adequately covered by merely naming its implementation class; the externally observable capability must be understandable.
- Verify the `## Source references` section and obvious internal links.
- Do not modify files.

Return exactly one JSON object:
{
  "status":"ok|needs_repair",
  "concept_id":"string",
  "path":"relative/concept.md",
  "documented_item_ids":["fn001","cfg001"],
  "missing_item_ids":["string"],
  "findings":[
    {
      "severity":"error|warning",
      "item_id":"optional fn/cfg id or empty string",
      "problem":"string",
      "required_change":"string"
    }
  ],
  "warnings":["string"]
}

Return valid JSON only.
