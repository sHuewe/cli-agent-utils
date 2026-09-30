Review the generated OKF at a high level and propose additional concept requests that should be checked before navigation is finalized.

Target OKF root: `{{var:okf_root}}`

Semantic folder structure:
{{var:structure}}

Compact planning/profile state:
{{var:plans}}

Compact generation/coverage results:
{{var:results}}

Rules:
- Do not modify files.
- Use the supplied compact state and, when useful, inspect generated OKF files. Do not perform a fresh broad analysis of the original source material.
- Pay special attention to remaining warnings/gaps from function and configuration coverage.
- Add candidates for meaningful cross-cutting omissions or weakly represented knowledge that is not already clearly represented.
- Do not duplicate requests for topics that are already adequately covered.
- Every proposed request must identify the best existing semantic folder in `folder_id`. Do not propose a concept directly below the OKF root.
- This file is intended to remain human-editable between runs, so each request must be understandable without hidden context.
- `id` must be unique and filesystem-safe. Use `extra001`, `extra002`, ... for generated requests.

Return exactly one JSON object:
{
  "concepts":[
    {
      "id":"extra001",
      "name":"string",
      "description":"short explanation of the knowledge that should be available",
      "folder_id":"one declared folder id",
      "scope_hint":"optional unit/manual/topic hint",
      "evidence_hints":["optional source hint"]
    }
  ],
  "warnings":["string"]
}

Return valid JSON only.
