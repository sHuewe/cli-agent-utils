Create the OKF plan for exactly one analyzed unit.

Target OKF root: `{{var:okf_root}}`
Unit inventory:
{{var:inventory}}

Rules:
- Design knowledge by coherent concepts, not one Markdown file per source file.
- Keep all concept paths below the unit's `okf_path` from the inventory.
- Concept paths are relative to the OKF root, use `/`, end in `.md`, contain no `..`, and must not be `index.md` or `log.md`.
- `id` is only local orchestration metadata; use `c001`, `c002`, ... within this unit.
- Every concept must be grounded in source evidence from this unit.
- `related` contains only planned concept paths.
- Include every directory needed for the unit below `directories`, shallowest first.
- Coverage is mandatory: every item in `external_functions` and every item in `configuration_options` from the inventory must be assigned to at least one planned concept.
- Prefer grouping closely related functions/configuration in one concept when that produces a coherent document. Do not collapse unrelated externally visible behavior merely to keep the concept count low.
- Treat 3-20 concepts only as a rough size guideline, not as a cap. Create more concepts when required for complete coverage.
- For each externally visible function/configuration item, record which concept(s) will cover it in `coverage`.
- If an inventory item cannot be meaningfully documented, keep it in `coverage` with an empty `covered_by` and explain why in `reason`; this should be exceptional.

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
  "coverage": [
    {
      "kind":"external_function|configuration_option",
      "name":"string",
      "description":"string",
      "covered_by":["relative/concept.md"],
      "reason":"string"
    }
  ],
  "warnings":["string"]
}

Return valid JSON only.
