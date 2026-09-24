Review the generated OKF and propose additional concept requests that should be checked before the repository is finalized.

Target OKF root: `{{var:okf_root}}`

Planning state:
{{var:plans}}

Generation/repair results:
{{var:results}}

This step creates the editable intermediate request list used by the later coverage steps.

Rules:
- Do not modify files.
- Use the supplied planning/results data and, when useful, inspect the generated OKF. Do not perform a fresh broad analysis of the original source material in this step.
- Pay special attention to outward-facing functions/capabilities and configuration possibilities identified by the planning state. Every such capability should be discoverable in at least one concept.
- Add candidates for meaningful omissions, weakly represented capabilities, or useful cross-cutting concepts that are not clearly represented by the current concept set.
- Do not create duplicate requests for concepts that are already obviously covered.
- Keep requests semantic and user-oriented. A request may describe a new concept or a topic that could be added to an existing concept; the next step will decide which.
- This file is intended to be editable by a human between runs. Therefore each request must remain understandable without hidden context.
- `id` must be unique and filesystem-safe. Use `extra001`, `extra002`, ... for generated requests.
- `name` and `description` are mandatory. `scope_hint` and `evidence_hints` are optional aids for the later assessment step.

Return exactly one JSON object:
{
  "concepts": [
    {
      "id":"extra001",
      "name":"string",
      "description":"short explanation of what knowledge should be available",
      "scope_hint":"optional unit/manual/topic hint",
      "evidence_hints":["optional source hint"]
    }
  ],
  "warnings":["string"]
}

Return valid JSON only.
