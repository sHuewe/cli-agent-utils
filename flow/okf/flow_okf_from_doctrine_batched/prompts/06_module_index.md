# Write the doctrine root index after COMPLETE document-level coverage

Source: {{var:source}}
Root: {{var:okf_root}}
Actual compact concept manifests: {{var:manifest_inventory}}
Declared semantic subfolders: {{var:folders}}
Completed semantic folder indices: {{var:folder_indexes}}
Deterministic document-wide coverage: {{var:coverage}}

Require coverage.status=ok. For each declared folder require an index
result whose status=ok, exact path and folder identity match. Never claim
success on missing or incomplete index/coverage results.
This is a small navigation task: read only the declared concept manifests,
bounded frontmatter, and actual target module files; do not read doctrines.
Write ONLY <root>/doctrines/<source.slug>/index.md.

If folders is nonempty, link each actual semantic subfolder's index.md
using correct relative Markdown links; do not flatten nested concepts.
If folders is empty, link every actual concept in this module exactly
once from the module index using relative links. Never invent filenames.
Do not edit concept bodies. If the module has too many concepts for
a single bounded response, return needs_attention rather than omit links.
No source text or external calls.

Return JSON:
{"status":"ok|needs_attention",
 "index_path":"workspace-relative module/index.md",
 "concept_count":0,"warnings":[]}
