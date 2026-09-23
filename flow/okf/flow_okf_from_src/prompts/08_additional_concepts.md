Review the generated OKF and propose additional concept requests that should be checked before the repository is finalized.

Target OKF root: `{{var:okf_root}}`
Unit plans:
{{var:unit_plans}}
Unit repair results:
{{var:unit_results}}

This step creates the editable intermediate request list used by the later coverage steps.

Rules:
- Do not modify files.
- Compare the planned coverage with the generated/repaired OKF structure.
- Pay special attention to externally visible application functions and configuration possibilities. Every such capability should be discoverable in at least one concept.
- Add candidates for meaningful omissions, weakly represented capabilities, or useful cross-cutting concepts that are not clearly represented by the current concept set.
- Do not create duplicate requests for concepts that are already obviously covered.
- Keep requests semantic and user-oriented. A request may describe a new concept or a topic that could be added to an existing concept; the next step will decide which.
- This file is intended to be editable by a human between runs. Therefore each request must remain understandable without hidden context.
- `id` must be unique and filesystem-safe. Use `extra001`, `extra002`, ... for generated requests.
- `name` and `description` are mandatory. `unit_hint` and `evidence_hints` are optional aids for the assessment step.

Return exactly one JSON object:
{
  "concepts": [
    {
      "id":"extra001",
      "name":"string",
      "description":"short explanation of what knowledge should be available",
      "unit_hint":"optional unit name/path",
      "evidence_hints":["optional workspace-relative/path"]
    }
  ],
  "warnings":["string"]
}

Return valid JSON only.
