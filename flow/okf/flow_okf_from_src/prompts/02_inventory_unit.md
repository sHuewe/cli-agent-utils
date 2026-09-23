Analyze exactly one partitioned source unit in detail.

Source root: `{{var:source_root}}`
Unit:
{{var:unit}}

Rules:
- Restrict detailed analysis to the unit's `source_path`. Read repository-level build/config files outside that path only when required to understand this unit.
- Base every claim on files actually inspected.
- Identify responsibilities, entry points, important components, interfaces, data/control flows, configuration, persistence/integrations, security-relevant behavior, operations and tests when present.
- Prefer architectural knowledge over a file-by-file inventory.
- Keep the result compact enough to feed the next planning iteration.
- Do not write or modify files.

Return exactly one JSON object:
{
  "unit": {
    "name": "string",
    "kind": "string",
    "source_path": "workspace-relative/path",
    "okf_path": "relative/path"
  },
  "summary": "string",
  "entry_points": [{"path":"string","purpose":"string"}],
  "components": [{"name":"string","responsibility":"string","evidence":["string"]}],
  "interfaces": [{"kind":"string","name":"string","evidence":["string"]}],
  "data_flows": [{"name":"string","summary":"string","evidence":["string"]}],
  "cross_cutting_concerns": [{"name":"string","summary":"string","evidence":["string"]}],
  "candidate_topics": [{"topic":"string","why":"string","evidence":["string"]}],
  "warnings": ["string"]
}

Return valid JSON only.
