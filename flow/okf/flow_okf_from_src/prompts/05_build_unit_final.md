Finalize the current unit after all concept conversation turns have completed.

Target OKF root: `{{var:okf_root}}`
Unit plan:
{{var:unit_plan}}

Rules:
- Inspect the concept files created for this unit.
- Create or update the unit's local `index.md` under its `okf_path` so it links to the unit's concepts and any planned child indexes.
- The index must use relative Markdown links and remain concise.
- Do not alter source code.
- Do not edit concepts unless an immediately obvious formatting/link defect prevents the unit index from being valid.
- Never write outside the target OKF root.

Return exactly one JSON object:
{
  "status":"built",
  "unit": {
    "name":"string",
    "source_path":"workspace-relative/path",
    "okf_path":"relative/path"
  },
  "index_path":"relative/path/index.md",
  "concept_paths":["relative/concept.md"],
  "warnings":["string"]
}

Return valid JSON only.
