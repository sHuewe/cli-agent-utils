Create the root index for the generated OKF repository after primary generation and additional-concept processing have completed.

Target OKF root: `{{var:okf_root}}`
Project:
{{var:project}}

Primary generation results:
{{var:primary_results}}

Additional concept changes:
{{var:additional_changes}}

Rules:
- Use the supplied results plus the generated OKF indexes/concepts you inspect.
- Ensure the OKF root exists.
- Write `<okf_root>/index.md` as the repository entry point.
- Link to the appropriate top-level indexes and/or concepts with relative Markdown links so all important generated knowledge is reachable.
- Preserve navigation to concepts created by the additional-concept phase; inspect affected indexes when needed.
- Keep the root index compact: project/source summary plus useful top-level navigation. Do not duplicate detailed concept content.
- Never write outside the OKF root and do not modify original source material.

Return exactly one JSON object:
{
  "status":"created",
  "index_path":"index.md",
  "linked_entries":["relative/path"],
  "warnings":["string"]
}

Return valid JSON only.
