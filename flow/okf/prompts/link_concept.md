Apply meaningful, evidence-supported INLINE Markdown links to exactly ONE existing source concept. Candidate discovery is ALREADY completed separately per target folder by read-only steps. There is NO FIXED MAXIMUM number of links; quality and natural placement determine how many to add.

Source concept path (workspace-relative): {{var:concept_path}}
Folder status: {{var:folder_status}}
Folder ID: {{var:folder_id}}
Folder context: {{var:structure}}
OKF root (workspace-relative): {{var:okf_root}}
Full pre-link snapshot: {{var:snapshot}}
Per-target-folder discoveries: {{var:discoveries}}

Use concept_path directly as the WORKSPACE-relative source. Require folder_status == "ok", snapshot.status == "captured", snapshot.concept_path == concept_path, and complete nonempty snapshot.content. EVERY folder discovery must have status "ok" and a valid candidates list. If any folder failed, is malformed or missing, report needs_attention WITHOUT WRITING; do not mistake incomplete discovery for zero relevant links.

Use ONLY candidate targets from the folder discoveries; do NOT perform another repository-wide search. Deduplicate candidate targets across all folders. Validate each actual target against the OKF root and its own file before using it. A candidate's reason or index presence alone is not proof of relevance; check that the target meaningfully relates to the existing source prose. Reject weak associations and targets without suitable natural phrases. Add at most ONE link per target in the source concept; skip targets already linked in the original. Zero links is valid. Never link the source itself or index.md/log.md, invent paths, or link outside the OKF root.

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
