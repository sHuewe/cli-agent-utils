Review and compact link candidates from ONE bounded batch of OKF folder discoveries. READ ONLY: never modify any source, target, or index file.

Source concept path (workspace-relative): {{var:concept_path}}
OKF root (workspace-relative): {{var:okf_root}}
Complete original pre-link snapshot: {{var:snapshot}}
Current batch of folder discoveries: {{var:batch}}

Require snapshot.status == "captured", snapshot.concept_path == concept_path, and complete nonempty snapshot.content. Require the batch to have a valid id and a nonempty items list. Each item MUST be a completed folder discovery with status "ok", target_folder and a candidates list. If any result is missing, needs_attention or malformed, return needs_attention and DO NOT report partial success.

Individually examine every candidate in this batch:
- Reject nonexistent or outside-root paths; accept only normal .md target concepts, not index.md, log.md, or the source itself. Use targeted READ-ONLY checks to confirm target content and relevance where needed.
- Verify link_text is an exact contiguous existing phrase in normal prose of snapshot.content, not inside an existing link, code, HTML, headings, frontmatter, or reference sections. Never invent or edit source text.
- Keep only concrete, evidence-supported semantic relationships. Reject already linked targets, weak associations, unsuitable phrases, and duplicates by target within the batch.
- Report concise accepted proposals ONLY. Do not repeat the full snapshot, candidate inventories, rejected candidates, or target content. No fixed number of links; compactness comes from filtering, NOT arbitrarily discarding relevant relationships.
- The final link step resolves conflicts/overlaps across batches; do not write anything here.

Return valid JSON only:
{"status":"ok|needs_attention","batch_id":"batch id from input","reviewed_count":0,"proposals":[{"target_path":"workspace-relative target.md","link_text":"exact original phrase"}],"warnings":[]}
