Capture a complete, read-only, pre-link snapshot of exactly ONE existing doctrine-derived OKF concept.

OKF root: {{var:okf_root}}
Concept (OKF-root-relative): {{var:concept_path}}
Pre-link folder verification status: {{var:folder_status}}

Rules:
- If folder_status is not "ok", return needs_attention without reading or modifying files.
- Read the ENTIRE concept at <okf_root>/<concept_path>, including exact YAML frontmatter, headings, all original text, links, references, line endings, and trailing whitespace. Do not summarize or omit any text.
- Never inspect doctrine sources or modify ANY file.
- If the complete content cannot be read and represented exactly in JSON, or is missing, outside the OKF root, or empty, return needs_attention with empty content. Do not make a partial snapshot appear valid.
- Capture the path and full content without normalization. The downstream mutating and read-only verifying steps use this as their immutable baseline.
- A successful snapshot MUST have status captured, an exact matching concept_path, and complete nonempty content.

Return valid JSON only:
{"status":"captured|needs_attention","concept_path":"{{var:concept_path}}","content":"full exact original Markdown text","warnings":["string"]}
