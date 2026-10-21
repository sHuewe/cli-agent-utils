Verify complete doctrine knowledge-item coverage for one folder.
Folder: {{var:folder}}
Plan: {{var:plan}}
Concept results: {{var:concept_results}}

Compare exact global IDs of EVERY plan.coverage item against actual documented_item_ids in concept_results. Missing expected route files, uncovered_item_ids, or remaining_item_ids prohibit status ok. Distinguish normative=true and descriptive=false item counts. Do not use tools. Return JSON only:
{"status":"ok|needs_attention","folder_id":"string","expected_normative_items":0,"documented_normative_items":0,"expected_descriptive_items":0,"documented_descriptive_items":0,"missing_item_ids":["string"],"warnings":["string"]}
