Verify the result of one concept-granularity evaluation/split.

Target OKF root: `{{var:okf_root}}`
Original concept path: `{{var:concept_path}}`

Assessment:
{{var:assessment}}

Applied change:
{{var:change}}

Rules:
- Do not inspect original source code or manuals and do not modify files.
- If the assessment did not request a split, return `not_changed` and preserve any `needs_attention` warning.
- For a split, read the overview, every `change.new_paths` concept, and the direct folder `index.md`.
- Verify:
  - the original path still exists as a concise overview;
  - every planned part exists directly in the same semantic folder;
  - every part has valid frontmatter with non-empty `type`;
  - the overview links all new parts;
  - the folder index links the overview and every new part;
  - each planned scope from `assessment.parts` is materially represented in the corresponding part;
  - the overview/parts remain semantically focused and the split did not merely create arbitrary fragments;
  - existing source/manual references needed by the redistributed claims are still present somewhere appropriate;
  - no obvious substantial topic named by the assessment disappeared during redistribution.
- Do not require a particular line count after splitting.

Return exactly one JSON object:
{
  "status":"ok|not_changed|needs_attention",
  "overview_path":"relative/concept.md",
  "verified_paths":["relative/path"],
  "findings":[
    {"severity":"error|warning","path":"relative/path","problem":"string"}
  ]
}

Return valid JSON only.
