Create the OKF index files after all planned concepts have been written.

Target OKF root: `{{var:okf_root}}`

Plan:
{{var:plan}}

Concept creation results:
{{var:concept_results}}

Rules:
- Do not change source code or concept files in this step.
- Build a lowercase root `index.md` directly in the target OKF root. This file is mandatory.
- Create an `index.md` in each planned directory that contains concepts or child directories where that improves progressive navigation.
- Use only relative Markdown links that remain inside the OKF root.
- Every planned concept that was successfully written must be reachable from the root index through the index hierarchy.
- Prefer concise indexes: title, short purpose, then grouped links with one-line descriptions.
- Do not link to files that were not planned or not reported as written.
- Do not create speculative concepts.
- Never write outside the target OKF root. Reject absolute paths or any path containing `..`.
- If an index file already exists, read it first and then replace it with the complete intended content.

The root index should contain at least:
- repository title and description from the plan,
- links to top-level directory indexes and/or top-level concepts,
- enough context for a retrieval agent to choose where to continue.

Return exactly one JSON object:

{
  "status": "written",
  "indexes": ["index.md", "relative/directory/index.md"],
  "linked_concepts": ["relative/concept.md"],
  "warnings": ["string"]
}

Return valid JSON only.
