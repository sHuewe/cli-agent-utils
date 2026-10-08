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
