Create the complete OKF concept plan from the manual scan results.

Target OKF root: `{{var:okf_root}}`
Project:
{{var:project}}

Manual scan iterations:
{{var:manual_scans}}

Rules:
- Use only the supplied scan results. Do not read any manual in this step.
- Merge duplicate/overlapping candidate topics across manuals into coherent concepts while preserving all useful evidence ranges.
- Organize knowledge by meaning, not by manual filename or chapter structure when several manuals describe the same concept.
- Every outward-facing function and every configuration option found by the scans must be assigned to at least one concept.
- Prefer grouping closely related material when that produces a coherent concept. Do not collapse unrelated behavior merely to keep the concept count low.
- There is no fixed concept-count cap. Create as many concepts as required for useful, complete coverage.
- Every planned concept must include concrete `evidence_ranges`. These ranges are the authoritative read plan for later build/verify/repair steps.
- Concept paths are relative to the OKF root, use `/`, end in `.md`, contain no `..`, and must not be `index.md` or `log.md`.
- Use stable IDs `c001`, `c002`, ... in plan order.
- `related` contains only paths of concepts in this plan.
- Preserve manual path and 1-based inclusive line boundaries exactly unless you are merging adjacent/overlapping ranges from the same manual.
- Keep each evidence range reasonably focused; do not replace several precise ranges with an entire-manual range.

Return exactly one JSON object:
{
  "project": {
    "name":"string",
    "summary":"string"
  },
  "concepts":[
    {
      "id":"c001",
      "path":"relative/concept.md",
      "type":"string",
      "title":"string",
      "description":"string",
      "tags":["string"],
      "related":["relative/concept.md"],
      "evidence_ranges":[
        {
          "manual":"workspace-relative/path",
          "start_line":1,
          "end_line":120,
          "reason":"string"
        }
      ]
    }
  ],
  "coverage":[
    {
      "kind":"external_function|configuration_option",
      "name":"string",
      "description":"string",
      "covered_by":["relative/concept.md"],
      "reason":"string"
    }
  ],
  "warnings":["string"]
}

Return valid JSON only.
