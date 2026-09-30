Apply the evidence-backed change for exactly one question to the OKF.

Target OKF root: `{{var:okf_root}}`
Question:
{{var:question}}

Assessment:
{{var:assessment}}

Evidence:
{{var:evidence}}

Rules:
- If the assessment action is `covered`, do not modify files and return `unchanged`.
- If evidence status is `unsupported`, do not invent an answer and do not modify files.
- For `extend`, read the existing `assessment.target_path` first and add only the missing knowledge supported by the evidence. Preserve valid frontmatter and correct existing content.
- For `create`, first confirm that `assessment.target_path` still does not exist. If it now exists, read it and extend it only with the missing evidence-backed knowledge rather than overwriting it.
- Otherwise create exactly one concept at `assessment.target_path`. It must remain directly inside the existing semantic folder selected by the assessment.
- A newly created concept must have valid OKF frontmatter with at least `type`, `title`, `description`, `tags`, and `status: stable`. Do not add `verified`.
- Incorporate the evidence in reader-oriented form so the question can be answered from the OKF without consulting the original source material.
- Add the reference section requested by `evidence.reference_section` and include the supplied concrete references.
- When creating a new concept, read and update that folder's `index.md` so the new concept is reachable.
- When extending a concept, change an index only if navigation is actually missing or broken.
- Keep every write inside the OKF root and do not modify original source/manual material.

Return exactly one JSON object:
{
  "status":"unchanged|extended|created|unsupported",
  "question":"string",
  "target_path":"relative/concept.md or empty string",
  "changed_paths":["relative/path"],
  "warnings":["string"]
}

Return valid JSON only.
