Perform the final root-level structural and concept-split integrity verification of the generated OKF.

Target OKF root: `{{var:okf_root}}`

Semantic structure:
{{var:structure}}

Root-index result:
{{var:navigation}}

Post-split per-folder structural verification results:
{{var:folder_verifications}}

Split verification results (one outer iteration per semantic folder, with nested concept iterations):
{{var:split_verifications}}

Rules:
- Do not re-read all concept files or inspect original source/manual material. Read only the root `<okf_root>/index.md`.
- Verify the root index links every declared semantic folder index and does not bypass the folder layer for normal concepts.
- Verify that every expected folder structural verification is present; account for its errors, warnings, and status.
- Verify no normal concept is reported directly below the OKF root.
- Inspect EVERY split result: for each outer folder iteration, inspect its nested `output.iterations`, then each concept's `output.status` and `output.findings`.
- Each declared folder must have a split iteration with a valid nested result (an empty concept iteration list is valid for an empty folder). Treat missing, malformed, or unrecognized verification results as `needs_attention`, never as success.
- Reconcile EXACT concept paths separately for EACH folder. Extract the current direct concept paths from the matching post-split folder verification's `concept_paths` array; reject absent, duplicate, or inconsistent `concept_paths` / `concept_count` as `needs_attention`.
- Extract every original concept path from the matching split iteration's discovery/foreach items, and every newly created part path from each concept verification's `verified_paths` (only for successful `split` actions). Do not treat the original overview path as an additional new concept; do not count `index.md` or `log.md`. Ensure a successful split's new paths are actually reported and validated. If necessary inspect the nested iteration's `input.concept_path` and verification output to establish the exact mapping.
- Require a ONE-TO-ONE match: current concept paths must equal the union of distinct original evaluated concept paths and the newly created concept paths. Every original concept must have exactly one corresponding completed split-verification iteration, and every new path must belong to exactly one successful split result. Missing evaluations, extra unverified concepts, duplicate paths, missing results or mismatched folder IDs are errors; return `needs_attention`.
- Checking only the number of split iterations is insufficient, since splitting legitimately adds new files. Never infer coverage from counts alone.
- If ANY concept split has `status: needs_attention` or any finding has `severity: error`, the final status MUST be `needs_attention`, even if all later structural checks report `ok`. Never downgrade or discard those findings.
- A split result of `not_changed` is acceptable only when it carries no blocking finding. Preserve reported warnings in the final report.
- If ANY folder structural verification reports `needs_attention` or a blocking finding, the final status MUST be `needs_attention`.
- Include every blocking split or structural finding in the final `findings` array, retaining its affected concept/folder path where possible. Do not replace an error with a generic success message.
- Return `ok` only when every required check is present and no blocking result or finding exists.
- Do not modify files.

Return exactly one JSON object:
{
  "status":"ok|needs_attention",
  "checked_folders":["folder-id"],
  "findings":[{"severity":"error|warning","path":"relative/path","problem":"string"}],
  "warnings":["string"]
}

Return valid JSON only.
