# Correct ONLY invalid semantic folder assignments

The deterministic validator identified invalid JSON values in one small
semantic-consolidation batch. Its report contains the ORIGINAL proposal,
the authoritative list of allowed folder IDs, and the precise errors:

{{var:validation}}

No tools or source reads. Output a JSON OBJECT consisting of the entire
original `validation.value` with corrections ONLY to the invalid
`groups[*].folder_id` fields indicated in `validation.errors`.

Rules:
- If `validation.allowed_values` is nonempty, use ONLY one of those exact
  folder IDs for every group. Choose the most semantically fitting valid ID
  using the original group's title and description.
- If the allowed list is empty, every group must have `folder_id: null`.
- Preserve the exact original `member_ids`, titles, descriptions, status,
  warnings, number and order of groups, and any additional JSON keys.
- Never invent a folder, drop a group, merge/split a group, change members,
  remove original warnings or fabricate a different semantic interpretation.
- Report the complete repaired JSON object, NOT the validation wrapper,
  without Markdown fences. Do not add commentary.
- If a meaningful folder choice cannot be determined, choose the nearest
  permitted folder and retain the original data unchanged otherwise.
- The next deterministic step will reject any invalid remaining folder IDs.
