Create one curated OKF index.md for ONE local semantic folder.
Folder: {{var:folder}}
Root: {{var:okf_root}}
Actual nonrecursive inventory: {{var:inventory}}
Completed coverage: {{var:coverage}}

Require coverage.status=="ok" and inventory.directory matches
okf_root + "/" + folder.path; otherwise return needs_attention, without
writing. Inventory lists actual concept files; read at most first 50 lines
per file for title/description. Link every normal Markdown concept exactly
once from folder/index.md. Write no other file, do not invent links and
do not edit concepts. Use relative Markdown links.
Return JSON only:
{"status":"ok|needs_attention","index_path":"workspace-relative/index.md",
"concept_paths":["workspace-relative/concept.md"],"warnings":[]}
