Create only the root navigation index after all semantic folder indexes have been created.

Target OKF root: `{{var:okf_root}}`

Project:
{{var:project}}

Semantic structure:
{{var:structure}}

Folder-index results:
{{var:folder_indexes}}

Rules:
- Do not inspect original source/manual material.
- Do not read concept bodies.
- Verify that every declared folder has a corresponding successful folder-index result.
- Write `<okf_root>/index.md` as a compact project/source orientation.
- Link every declared semantic folder through its local `index.md`.
- Do not link normal concepts directly from the root index.
- Do not modify folder indexes or concepts.
- Keep every write inside the OKF root.

Return exactly one JSON object:
{
  "status":"created|needs_attention",
  "root_index":"index.md",
  "folder_indexes":["folder/index.md"],
  "warnings":["string"]
}

Return valid JSON only.
