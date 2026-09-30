Create the OKF concept plan for exactly one analyzed source unit.

Target OKF root: `{{var:okf_root}}`

Semantic folder structure:
{{var:structure}}

Unit inventory:
{{var:inventory}}

Rules:
- Use the inventory as planning data; do not read source files in this step.
- Design coherent reusable concepts, not one Markdown file per source file.
- Every concept must belong to exactly one folder declared in `structure.folders`.
- Every concept path is exactly `<folder.path>/<unit-slug>-<concept-slug>.md`, with no additional directory level.
- Derive `unit-slug` deterministically from `inventory.unit.id`: lowercase it and replace underscores with hyphens. This prefix is mandatory so independently processed units cannot overwrite one another's concepts.
- Do not create concepts directly below the OKF root.
- `folder_id` must match the selected declared folder's `id`.
- Paths are relative to the OKF root, contain no `..`, and must not be `index.md` or `log.md`.
- Use local concept IDs `c001`, `c002`, ...
- Assign the best semantic home based on folder routing guidance. Source package/unit boundaries do not determine the folder.
- Coverage is mandatory: every inventory item in `external_functions` and `configuration_options` must be assigned to at least one concept.
- Put the exact assigned inventory objects into each concept's `coverage_items`.
- The top-level `coverage` list must contain every inventory item exactly once by item ID, with one or more concept IDs in `covered_by`.
- Closely related items may share a concept. Do not collapse unrelated behavior merely to reduce concept count.
- There is no concept-count cap. Complete coverage takes precedence.
- `source_hints` should contain the most relevant evidence paths.
- `related` contains only planned concept paths.

Return exactly one JSON object:
{
  "unit":{"id":"string","name":"string","source_path":"workspace-relative/path"},
  "concepts":[
    {
      "id":"c001",
      "folder_id":"declared-folder-id",
      "path":"folder/unit-concept.md",
      "type":"string",
      "title":"string",
      "description":"string",
      "tags":["string"],
      "source_hints":["workspace-relative/path"],
      "related":["folder/unit-other.md"],
      "coverage_items":[
        {"id":"fn001|cfg001","kind":"external_function|configuration_option","name":"string","description":"string","evidence":["workspace-relative/path#symbol-or-key"]}
      ]
    }
  ],
  "coverage":[{"item_id":"fn001|cfg001","kind":"external_function|configuration_option","name":"string","covered_by":["c001"]}],
  "uncovered_item_ids":[],
  "warnings":["string"]
}

Return valid JSON only.
