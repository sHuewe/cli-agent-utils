Create a source-code inventory that will be used to design an OKF knowledge repository.

Source root: `{{var:source_root}}`

Rules:
- Inspect only source material that is relevant to understanding the project below the configured source root. Do not write or modify files.
- Base every finding on files you actually inspected. Do not infer implementation details merely from names.
- Ignore generated/vendor/build artifacts unless they are required to understand how the project is built or run.
- Prefer architectural concepts over a file-by-file listing.
- Identify the main languages, frameworks, build/package systems, entry points, modules/components, public or external interfaces, important data/control flows, configuration, persistence, messaging/integration points, security-relevant mechanisms, operational behavior and testing strategy when present.
- Record uncertainty explicitly in `warnings` instead of inventing missing facts.
- Keep the inventory compact enough to be used by a later planning step.

Return exactly one JSON object with this shape:

{
  "project": {
    "name": "string",
    "summary": "string"
  },
  "languages": ["string"],
  "frameworks": ["string"],
  "build_systems": ["string"],
  "entry_points": [
    {"path": "workspace-relative path", "purpose": "string"}
  ],
  "modules": [
    {
      "name": "string",
      "path": "workspace-relative path",
      "responsibility": "string",
      "key_files": ["workspace-relative path"]
    }
  ],
  "interfaces": [
    {"kind": "string", "name": "string", "evidence": ["workspace-relative path"]}
  ],
  "data_flows": [
    {"name": "string", "summary": "string", "evidence": ["workspace-relative path"]}
  ],
  "cross_cutting_concerns": [
    {"name": "string", "summary": "string", "evidence": ["workspace-relative path"]}
  ],
  "candidate_topics": [
    {"topic": "string", "why": "string", "evidence": ["workspace-relative path"]}
  ],
  "warnings": ["string"]
}

Use workspace-relative paths in all evidence fields. Return valid JSON only.
