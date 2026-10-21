Apply meaningful, evidence-supported INLINE Markdown links to exactly ONE existing source concept. Folder-by-folder candidate discovery and read-only BATCH REVIEW are ALREADY complete. The input contains ONLY compact accepted proposals, not the original discovery payloads. There is NO FIXED MAXIMUM number of links.

Source concept path (workspace-relative): {{var:concept_path}}
Folder status: {{var:folder_status}}
Folder ID: {{var:folder_id}}
Folder context: {{var:structure}}
OKF root (workspace-relative): {{var:okf_root}}
Full pre-link snapshot: {{var:snapshot}}
Per-batch link proposals: {{var:batch_reviews}}

Use concept_path directly as the WORKSPACE-relative source. Require folder_status == "ok", snapshot.status == "captured", snapshot.concept_path == concept_path, and complete nonempty snapshot.content. Require EVERY batch review in the aggregate to contain status "ok", a unique nonempty batch_id, reviewed_count >= 0 and a valid proposals array. If any batch review failed, is malformed, missing, or duplicated, return needs_attention WITHOUT WRITING. Do not mistake partial discovery or review failures for zero relevant links.

Use ONLY the reviewed proposals; do NOT redo repository-wide searches or load the original folder discoveries. Deduplicate target paths across batches. Validate each proposed target is a real, normal Markdown concept under the OKF root and not the source, index.md, or log.md. Check each proposed phrase still occurs in original source prose and that the relationship is genuine, not a superficial topical association. Resolve conflicts where proposals overlap or compete for the same source phrase; skip ambiguous ones rather than changing the prose. Skip targets already linked in the original. At most ONE link per distinct target. Zero links is valid.

STRICT EDIT CONTRACT:
- The source concept is the ONLY file that may be modified. Do not create, delete, rename or move any file.
- Re-read the ENTIRE source before editing and require an exact character-for-character match to snapshot.content.
- Only wrap an existing contiguous plain-text phrase in [EXACT ORIGINAL PHRASE](relative/url.md). Never add, remove, rephrase, reorder or normalize any original text, spacing, headings, frontmatter, references or links.
- Only link normal prose; never touch existing links, code fences, inline code, HTML, frontmatter, headings, anchors or reference sections. Link text cannot contain newlines, brackets, backslashes or existing markup.
- Relative Markdown URLs MUST resolve from the source file's parent directory to the exact reported target. All targets must exist and be normal Markdown concepts below the OKF root.
- Before writing, reconstruct the original by replacing each newly proposed link token with its original phrase exactly once. The reconstructed complete text MUST equal snapshot.content character for character. No overlapping, nested or ambiguous replacements. Each proposed token must occur exactly once and not exist in the original snapshot.
- Use os__write_file only after a complete source read and successful reconstruction. Read the full file back and repeat the reconstruction check. If a check cannot be completed, leave the file unchanged or return needs_attention with an explicit warning.
- Only DISTINCT, evidence-supported targets naturally discussed in existing prose. Do not impose a numerical link limit and do not append a Related concepts section.

Report target_path as a WORKSPACE-relative path. Report only links actually inserted.

Return valid JSON only:
{"status":"ok|needs_attention","source_path":"workspace-relative concept_path","changed":false,"links_added":[{"link_text":"exact original phrase","target_path":"workspace-relative target.md","relative_url":"../target.md"}],"warnings":[]}
