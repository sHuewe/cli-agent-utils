Capture a complete, read-only snapshot of one existing OKF Markdown concept.

Source concept path (workspace-relative): {{var:concept_path}}
Folder status: {{var:folder_status}}
OKF root (workspace-relative): {{var:okf_root}}

If folder_status != "ok", return needs_attention without reading. Read the ENTIRE file at concept_path, preserving exact YAML frontmatter, whitespace, line endings and trailing characters. Confirm that it is a normal Markdown concept under the OKF root, not index.md or log.md. Never write or modify files. If the full content cannot be captured exactly, return needs_attention with empty content. Do not claim a partial read is complete.

Return valid JSON only:
{"status":"captured|needs_attention","concept_path":"workspace-relative path from concept_path","content":"complete exact text","warnings":[]}
