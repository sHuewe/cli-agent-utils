Verify complete function/configuration coverage for exactly one semantic manual-derived folder.

Folder:
{{var:folder}}

Folder plan:
{{var:plan}}

Concept results:
{{var:concept_results}}

Rules:
- Do not read or modify files.
- Every `plan.coverage[].item_id` must occur in at least one concept result's `documented_item_ids`.
- Any `plan.uncovered_item_ids` entry or non-empty `remaining_item_ids` is an error.
- Count functions and configuration options separately and preserve warnings.

Return exactly one JSON object:
{"status":"ok|needs_attention","folder_id":"string","expected_external_functions":0,"expected_configuration_options":0,"documented_external_functions":0,"documented_configuration_options":0,"missing_item_ids":["string"],"warnings":["string"]}

Return valid JSON only.
