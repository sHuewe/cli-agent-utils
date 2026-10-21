Collect only the manual evidence needed to close the documented gap for exactly one question.

Configured manual path: `{{var:manual_path}}`
Question:
{{var:question}}

OKF assessment:
{{var:assessment}}

Rules:
- Do not modify files.
- If `assessment.action` is `covered`, do not inspect manuals and return `not_needed`.
- Otherwise inspect source material only below `manual_path`.
- Use `search_text` to locate likely evidence before reading. For manual files, NEVER call `read_file` without both `start_line` and `end_line`.
- Read only bounded ranges around relevant hits; do not sequentially rescan or fully read manuals in this late flow.
- Establish the concrete information needed to answer the question, including prerequisites, options, constraints or procedures when supported.
- Record every supporting range as `<workspace-relative-path>:L<start>-L<end>`.
- If the manuals do not support an answer, return `unsupported` rather than guessing.
- Keep `content_to_document` compact but sufficiently complete for the later OKF edit.

Return exactly one JSON object:
{
  "status":"not_needed|supported|unsupported",
  "question":"string",
  "content_to_document":["evidence-backed fact, procedure or behavior"],
  "references":["manual/path:L10-L35"],
  "reference_section":"Manual references",
  "warnings":["string"]
}

Return valid JSON only.
