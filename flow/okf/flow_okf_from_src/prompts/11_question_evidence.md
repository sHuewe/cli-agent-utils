Collect only the source evidence needed to close the documented gap for exactly one question.

Source root: `{{var:source_root}}`
Question:
{{var:question}}

OKF assessment:
{{var:assessment}}

Rules:
- Do not modify files.
- If `assessment.action` is `covered`, do not inspect source and return `not_needed`.
- Otherwise inspect only source files below `source_root`.
- Use targeted listing/search and focused reads based on the question and `assessment.missing_information`; do not perform a new broad architecture inventory.
- Establish the concrete information needed to answer the question, including important prerequisites, options, constraints or behavior when supported.
- Prefer concrete workspace-relative paths plus symbols/keys in references.
- If the source does not support an answer, return `unsupported` rather than guessing.
- Keep `content_to_document` compact but sufficiently complete for the later OKF edit.

Return exactly one JSON object:
{
  "status":"not_needed|supported|unsupported",
  "question":"string",
  "content_to_document":["evidence-backed fact or behavior"],
  "references":["workspace-relative/path#symbol-or-key"],
  "reference_section":"Source references",
  "warnings":["string"]
}

Return valid JSON only.
