Design a concrete OKF repository plan from the source inventory below.

Source root: `{{var:source_root}}`
Target OKF root: `{{var:okf_root}}`

Inventory:
{{var:inventory}}

You may inspect the source tree read-only when the inventory is insufficient, but every planned concept must be grounded in actual source evidence.

Planning rules:
- Organize knowledge by coherent concepts, not one Markdown file per source file.
- Prefer a small number of meaningful directories and concepts over a deep or repetitive hierarchy.
- Cover architecture, important components, externally visible interfaces, central data/control flows, configuration/operations and testing only where the source actually supports them.
- Avoid speculative concepts. If the source does not support a topic, omit it.
- Concept paths are relative to the OKF root, use `/`, end in `.md`, contain no `..`, and should use lowercase kebab-case names.
- Do not use `index.md` or `log.md` as a concept path.
- Every concept path must be unique.
- `id` must be unique and match `c` followed by three decimal digits (`c001`, `c002`, ...). These IDs are orchestration identifiers, not OKF concept IDs.
- `type` must be a short non-empty semantic category such as `architecture`, `component`, `interface`, `data-flow`, `configuration`, `operations`, `testing` or another source-appropriate value.
- `source_hints` must contain workspace-relative files or directories that are useful starting points for the concept writer.
- `related` contains other planned concept paths, not arbitrary prose.
- Keep the plan practical. Normally use 5-40 concepts; exceed that only when the project clearly requires it, and never exceed 100.
- List every parent directory needed by concept paths in `directories`, shallowest first. Do not list the repository root itself.

Return exactly one JSON object:

{
  "repository": {
    "title": "string",
    "description": "string"
  },
  "directories": [
    {
      "path": "relative/directory",
      "title": "string",
      "description": "string"
    }
  ],
  "concepts": [
    {
      "id": "c001",
      "path": "architecture/system-overview.md",
      "type": "architecture",
      "title": "string",
      "description": "string",
      "tags": ["string"],
      "source_hints": ["workspace-relative path"],
      "related": ["relative/concept-path.md"]
    }
  ],
  "warnings": ["string"]
}

Return valid JSON only.
