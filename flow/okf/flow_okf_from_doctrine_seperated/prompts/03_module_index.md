Write the doctrine ROOT index only, using the real generated concepts.

Doctrine: {{var:folder}}
OKF root: {{var:okf_root}}
Declared semantic folders: {{var:folders}}
Semantic index results: {{var:folder_indexes}}
Verified coverage: {{var:coverage}}

Require coverage.status=="ok". When folders are declared, require a successful
semantic index result for EVERY declared folder. Link all semantic folder
index.md pages from the doctrine index using ordinary relative Markdown links.
Provide a short navigation overview; do NOT flatten the concepts into the
doctrine index or overwrite any subfolder indices.
When no semantic folders are declared, use the existing flat layout: list
actual concept files in this doctrine's directory via os list_files or read
the concept plan, and link every normal concept. Never invent filenames.
Only write <okf_root>/<folder.path>/index.md.
Return JSON only:
{"status":"ok|needs_attention","index_path":"workspace-relative/index.md",
"concept_paths":["workspace-relative paths if flat"],"warnings":[]}
