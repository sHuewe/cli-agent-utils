Verify the complete externally observable coverage for one source unit using the plan and independently verified/repaired concept results.

Unit:
{{var:unit}}

Plan:
{{var:plan}}

Concept results:
{{var:concept_results}}

Rules:
- Do not read source or OKF files and do not modify anything.
- Treat `plan.coverage` as the complete expected set produced from the exhaustive inventory.
- Every `plan.coverage[].item_id` must occur in at least one concept result's `documented_item_ids`.
- Every `plan.uncovered_item_ids` entry is an error.
- Any concept result with non-empty `remaining_item_ids` is an error.
- Distinguish external functions from configuration options in the counts.
- Do not silently drop warnings.

Return exactly one JSON object:
{
  "status":"ok|needs_attention",
  "unit_id":"string",
  "expected_external_functions":0,
  "expected_configuration_options":0,
  "documented_external_functions":0,
  "documented_configuration_options":0,
  "missing_item_ids":["string"],
  "warnings":["string"]
}

Return valid JSON only.
