Independently verify inline cross-links for exactly one existing OKF concept. READ ONLY.

Inventory concept object: {{var:concept}}
OKF root (workspace-relative): {{var:okf_root}}
Link result: {{var:link_result}}
Full pre-link snapshot: {{var:snapshot}}

Use concept.path as the WORKSPACE-relative source path. Require snapshot.status == "captured", snapshot.concept_path == concept.path, link_result.source_path == concept.path and link_result.status == "ok". Read the FULL current source, including exact whitespace and line endings. Require link_result.changed to match whether links_added is nonempty, and at most THREE distinct links.

If unchanged, require current content to equal snapshot.content exactly. If changed, replace each newly introduced [link_text](relative_url) token exactly once with its original link_text; require the reconstructed FULL current text to equal snapshot.content character for character. No other modifications are allowed. Reject ambiguous or overlapping replacements, nested links, changes to original markup or references, and edits in frontmatter, headings or code.

For every new link, resolve relative_url from the source file's directory. It MUST resolve to the reported workspace-relative target_path, a normal existing Markdown concept within the OKF root, not index.md/log.md and not the source. Reject duplicates, pre-existing links to the same target, absolute paths, fragments and root escapes. A no-op is valid. Never modify files.

Return valid JSON only:
{"status":"ok|needs_attention","source_path":"workspace-relative concept.path","checked_links":0,"findings":[{"severity":"error|warning","target_path":"workspace-relative target.md","problem":"string"}],"warnings":[]}
