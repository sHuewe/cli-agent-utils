Verify, using only the resulting OKF, whether exactly one question is now adequately answered.

Target OKF root: `{{var:okf_root}}`
Question:
{{var:question}}

Applied change:
{{var:change}}

Rules:
- Do not inspect original source/manual material and do not modify files.
- Start at the root index and follow only relevant navigation.
- Determine whether a reader can answer the question adequately from the OKF as it now exists.
- If the change was unsupported, preserve that fact rather than treating unsupported information as a documentation defect.
- List the concepts that support the answer.
- Keep the result concise.

Return exactly one JSON object:
{
  "question":"string",
  "status":"covered|still_missing|unsupported",
  "covered_by":["relative/concept.md"],
  "remaining_gaps":["string"]
}

Return valid JSON only.
