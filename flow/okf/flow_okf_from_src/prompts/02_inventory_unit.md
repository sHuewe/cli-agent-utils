Analyze exactly one partitioned source unit in detail.

Source root: `{{var:source_root}}`
Unit:
{{var:unit}}

Rules:
- Treat the unit's `source_path` as the complete scope of this step. Do not list, read, search or otherwise inspect files outside that path.
- Base every claim on files actually inspected.
- Identify responsibilities, entry points, important components, interfaces, data/control flows, persistence/integrations, security-relevant behavior, operations and tests when present.
- Enumerate every function the application exposes outward from this unit when it is visible in the source. Examples include CLI commands/options, HTTP/API endpoints, externally callable service operations, message/event interfaces, plugin/provider hooks, user-facing actions and other explicit integration surfaces.
- Enumerate every configuration possibility visible in the source. Include configuration keys/properties, environment variables, command-line configuration, feature flags, configurable endpoints/paths/timeouts/limits and other user/operator controlled settings when present.
- Prefer architectural knowledge over a file-by-file inventory, but completeness of external functions and configuration takes precedence over compactness.
- Do not omit a function or configuration item merely because it seems small or implementation-specific if a user/operator/integrator can observe or configure it.
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
  "external_functions": [
    {"name":"string","kind":"string","description":"string","evidence":["workspace-relative/path"]}
  ],
  "configuration_options": [
    {"name":"string","description":"string","evidence":["workspace-relative/path"]}
  ],
  "data_flows": [{"name":"string","summary":"string","evidence":["string"]}],
  "cross_cutting_concerns": [{"name":"string","summary":"string","evidence":["string"]}],
  "candidate_topics": [{"topic":"string","why":"string","evidence":["string"]}],
  "warnings": ["string"]
}

Return valid JSON only.
