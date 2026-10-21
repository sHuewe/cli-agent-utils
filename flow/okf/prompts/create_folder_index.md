Create the navigation index for exactly one already planned semantic OKF folder.

Semantic structure:
{{var:structure}}

Folder:
{{var:folder}}

Rules:
- Target root is `structure.okf_root`.
- Work only inside the current declared folder.
- Ensure the folder exists and list its direct contents.
- Identify every normal Markdown concept directly inside it. Do not descend into other folders.
- To obtain a title/short description, read only a small leading range of each concept (normally no more than 40 lines). Do not read full concept bodies.
- Write `<okf_root>/<folder.path>/index.md` with a concise folder orientation and a relative link to every directly contained concept.
- Do not rewrite concept files.
- Keep every write inside the target OKF root.

Return exactly one JSON object:
{
  "status":"created",
  "folder_id":"string",
  "folder_path":"string",
  "index_path":"folder/index.md",
  "concept_paths":["folder/concept.md"],
  "warnings":["string"]
}

Return valid JSON only.
