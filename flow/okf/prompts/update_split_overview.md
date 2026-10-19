Update ONLY the original OKF concept into a concise split overview, AFTER focused parts have been created. Do not touch the folder index.

Target OKF root: {{var:okf_root}}
Original concept path: {{var:concept_path}}
Assessment: {{var:assessment}}
Pre-split snapshot status: {{var:snapshot_status}}
Complete original concept text:
{{var:original_content}}
Per-part creation results:
{{var:parts}}

Rules:
- For assessment.action == "keep" or "skip", do not read or modify any file; return unchanged.
- For action "needs_attention", return needs_attention without modifying files.
- For action "split", require snapshot_status == "captured" and complete nonempty original_content, and exactly one completed per-part result for every assessment.parts entry. Each result must have the exact requested part path and status created or already_present. No errors, missing or duplicate entries; otherwise return needs_attention without writing.
- Read the original concept completely. If it has already been transformed into a valid overview that links to every requested new part and retains all original headings/anchors, do not modify it; return already_present. This is required for safely resuming previously completed splits.
- Otherwise require the entire currently read original text to equal original_content exactly before any write. If changed from snapshot and not an already-complete valid overview, stop with needs_attention (never overwrite a partially modified file).
- Rewrite ONLY the original concept path as a concise overview/entry point explaining the original topic and linking all planned parts. Do not modify new part files or the folder index.
- Keep ALL ORIGINAL Markdown headings at the same path, with exactly their original texts, levels, order, and duplicate-heading slug suffix behavior. Preserve original explicit HTML anchors/IDs and existing fragment URLs, including those not visible from current links. Leave a short navigation stub under any relocated section heading; keep all required fragment targets. Do not add headings that alter generated anchor IDs.
- Preserve valid YAML frontmatter at byte zero, original type, source attribution and all other applicable original metadata; do not claim human verification.
- Retain legitimate overview-level knowledge and meaningful original links; rely on newly created parts for relocated detail. Do not invent or drop statements outside the planned part scopes. Maintain working relative URLs and link to all parts.
- Re-read and validate the overview after writing. If original headings, anchors or metadata cannot be preserved, report needs_attention and do not claim success.
- Never create, rename, move or delete files.

Return valid JSON only:
{"status":"updated|already_present|unchanged|needs_attention","overview_path":"relative/original.md","changed_paths":["relative/original.md"],"warnings":["string"]}
For already_present or unchanged, changed_paths must be []; include only actual writes otherwise.
