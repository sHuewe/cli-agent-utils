Create the semantic folder indexes and root index after primary generation and additional-concept processing have completed.

Target OKF root: `{{var:okf_root}}`

Project:
{{var:project}}

Semantic structure:
{{var:structure}}

Compact primary generation results:
{{var:primary_results}}

Additional concept changes:
{{var:additional_changes}}

Rules:
- Do not re-analyze original source material and do not broadly read concept bodies.
- Use the declared structure plus the compact generation results. You may list files below a declared folder and read only small frontmatter/title ranges when needed to include a generated concept that is not represented in the compact results.
- Ensure the OKF root and every declared semantic folder exist.
- For every declared folder, write `<okf_root>/<folder.path>/index.md`.
- A folder index must link every normal Markdown concept directly contained in that folder. It should provide a concise orientation, not duplicate concept content.
- Write `<okf_root>/index.md` and link every declared folder index from it.
- Do not link normal concepts directly from the root index when the folder index is their navigation parent.
- Do not move or rewrite concept files in this step.
- Never write outside the OKF root.

Return exactly one JSON object:
{
  "status":"created",
  "root_index":"index.md",
  "folder_indexes":[
    {
      "folder_id":"string",
      "path":"relative/folder/index.md",
      "concept_count":0
    }
  ],
  "warnings":["string"]
}

Return valid JSON only.
