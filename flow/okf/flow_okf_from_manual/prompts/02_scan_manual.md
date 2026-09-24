Scan exactly one manual and extract a compact evidence map for later OKF planning.

Manual:
{{var:manual}}

Rules:
- Read only the manual at `manual.path`. Do not inspect other manuals or unrelated workspace files.
- The manual is line-oriented text. NEVER call `read_file` for this manual without both `start_line` and `end_line`.
- Scan the manual sequentially using bounded line ranges. A practical first-pass window is about 300-500 lines. Continue until a requested range is beyond the end of the file.
- Identify coherent knowledge topics, outward-facing/user-visible functions, configuration possibilities, procedures/workflows, constraints, operational behavior, interfaces/integrations and other reusable knowledge described by the manual.
- Completeness matters: do not omit a function or configuration option merely because it is small.
- Every candidate concept, outward-facing function and configuration option must carry one or more concrete evidence ranges.
- Refine coarse scan windows into useful evidence ranges. Prefer ranges no larger than about 200 lines when the relevant material can be isolated more narrowly. Multiple ranges are allowed when a topic is distributed across the manual.
- Evidence ranges are 1-based and inclusive. They must refer to lines actually inspected and must contain the information described.
- Do not use the whole manual as one evidence range merely for convenience.
- Keep summaries compact; later steps will re-read only the recorded ranges.
- Do not write or modify files.

Return exactly one JSON object:
{
  "manual": {
    "id":"string",
    "name":"string",
    "path":"workspace-relative/path"
  },
  "summary":"string",
  "candidate_concepts":[
    {
      "name":"string",
      "description":"string",
      "evidence_ranges":[
        {
          "manual":"workspace-relative/path",
          "start_line":1,
          "end_line":120,
          "reason":"what relevant information is contained here"
        }
      ]
    }
  ],
  "external_functions":[
    {
      "name":"string",
      "kind":"string",
      "description":"string",
      "evidence_ranges":[
        {"manual":"workspace-relative/path","start_line":1,"end_line":40,"reason":"string"}
      ]
    }
  ],
  "configuration_options":[
    {
      "name":"string",
      "description":"string",
      "evidence_ranges":[
        {"manual":"workspace-relative/path","start_line":1,"end_line":40,"reason":"string"}
      ]
    }
  ],
  "warnings":["string"]
}

Return valid JSON only.
