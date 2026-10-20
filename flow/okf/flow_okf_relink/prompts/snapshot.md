Capture a complete, read-only snapshot of one existing OKF Markdown concept.

Inventory concept object (workspace-relative path): {{var:concept}}
OKF root (workspace-relative): {{var:okf_root}}

Read the ENTIRE file at concept.path, preserving exact YAML frontmatter, whitespace, line endings and trailing characters. Confirm that it is a normal Markdown concept under the OKF root, not index.md or log.md. Never write or modify files. If the full content cannot be captured exactly, return needs_attention with empty content. Do not claim a partial read is complete.

Return valid JSON only:
{"status":"captured|needs_attention","concept_path":"workspace-relative path from concept.path","content":"complete exact text","warnings":[]}
