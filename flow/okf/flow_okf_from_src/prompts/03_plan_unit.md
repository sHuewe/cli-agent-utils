Create the OKF plan for exactly one analyzed unit.

Target OKF root: `{{var:okf_root}}`
Unit inventory:
{{var:inventory}}

Rules:
- Design knowledge by coherent concepts, not one Markdown file per source file.
- Keep all concept paths below the unit's `okf_path` from the inventory.
- Prefer 3-20 concepts for a normal unit. Split only when the source supports distinct concepts.
- Concept paths are relative to the OKF root, use `/`, end in `.md`, contain no `..`, and must not be `index.md` or `log.md`.
- `id` is only local orchestration metadata; use `c001`, `c002`, ... within this unit.
- Every concept must be grounded in source evidence from this unit.
- `related` contains only planned concept paths.
- Include every directory needed for the unit below `directories`, shallowest first.

Return exactly one JSON object:
{
  "unit": {
    "name":"string",
    "source_path":"workspace-relative/path",
    "okf_path":"relative/path"
  },
  "directories": [
    {"path":"relative/path","title":"string","description":"string"}
  ],
  "concepts": [
    {
      "id":"c001",
      "path":"relative/concept.md",
      "type":"string",
      "title":"string",
      "description":"string",
      "tags":["string"],
      "source_hints":["workspace-relative/path"],
      "related":["relative/concept.md"]
    }
  ],
  "warnings":["string"]
}

Return valid JSON only.
