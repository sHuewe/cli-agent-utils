Verify the answerability of exactly one question AGAINST THE OKF AFTER the concept split, and incorporate the split's verification result.

Target OKF root: `{{var:okf_root}}`
Question:
{{var:question}}

Applied question change:
{{var:change}}

Question verification performed BEFORE the split (not authoritative for the current OKF):
{{var:prior_verification}}

Concept split verification:
{{var:split_verification}}

Rules:
- Do not inspect original source code/manuals and do not modify files.
- Start at the root OKF index and follow only relevant navigation.
- Independently verify whether a reader can adequately answer the question from the current, post-split OKF. Do not reuse the old `covered_by` list without verifying its paths/content.
- Set `question_status` to `covered`, `still_missing`, or `unsupported`. Preserve an evidence-backed `unsupported` result when the applied question change was unsupported.
- Inspect `split_verification.status` and every `split_verification.findings` entry. A split status of `needs_attention`, any error finding, or a missing/malformed split verification is a BLOCKING issue, even when the question itself is still answerable.
- Set the overall `status` to `needs_attention` whenever the split has a blocking issue; otherwise set it to `question_status`. An earlier `covered` result must never conceal a post-split problem.
- Preserve all split findings and their paths in `findings`; provide a clear error finding when the split verification is missing or invalid. Warnings should remain visible.
- For `not_changed` (no split), retain the question answerability status unless there is a blocking split finding.
- Keep the result concise.

Return exactly one JSON object:
{
  "question":"string",
  "status":"covered|still_missing|unsupported|needs_attention",
  "question_status":"covered|still_missing|unsupported",
  "split_status":"ok|not_changed|needs_attention",
  "covered_by":["relative/concept.md"],
  "remaining_gaps":["string"],
  "findings":[{"severity":"error|warning","path":"relative/path","problem":"string"}]
}

Return valid JSON only.
