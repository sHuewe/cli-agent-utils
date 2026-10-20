Add at most THREE meaningful INLINE Markdown links in exactly one existing OKF concept, without rewriting any of its original content.

Inventory concept object: {{var:concept}}
Inventory folder object: {{var:folder}}
OKF root (workspace-relative): {{var:okf_root}}
Full pre-link snapshot: {{var:snapshot}}

Use concept.path directly as a WORKSPACE-relative source path. Require snapshot.status == "captured", snapshot.concept_path == concept.path, and complete nonempty snapshot.content; otherwise return needs_attention without writing. Re-read the ENTIRE source before editing and require an exact character-for-character match to snapshot.content.

Find candidate targets only among existing Markdown concepts under the OKF root, using indexes and targeted searches. Targets must exist and must not be index.md, log.md, or the source. No invented paths, no links outside the OKF root. Relative Markdown URLs must resolve from the source file's parent directory to the target. Do not add a second link to a target already linked in the original file. Zero links is valid.

STRICT EDIT CONTRACT:
- The source concept is the ONLY file that may be modified. Do not create, delete, rename or move any file.
- Only wrap an existing contiguous plain-text phrase in [EXACT ORIGINAL PHRASE](relative/url.md). Never add, remove, rephrase, reorder or normalize any original text, spacing, headings, frontmatter, references or links.
- Only link normal prose; never touch existing links, code fences, inline code, HTML, frontmatter, headings, anchors or reference sections. Link text cannot contain newlines, brackets, backslashes or existing markup.
- Before writing, reconstruct the original by replacing each newly proposed link token with its original phrase exactly once. The reconstructed complete text MUST equal snapshot.content character for character. No overlapping, nested or ambiguous replacements. Each proposed token must occur exactly once and not exist in the original snapshot.
- Use os__write_file only after a complete source read and successful reconstruction. Read the full file back and repeat the reconstruction check. If a check cannot be completed, leave the file unchanged or return needs_attention with an explicit warning.
- At most three DISTINCT targets; only evidence-supported relationships naturally discussed in existing prose. Do not append a Related concepts section.

Report target_path as a WORKSPACE-relative path (the same format as inventory.files[].path). Report only links actually inserted.

Return valid JSON only:
{"status":"ok|needs_attention","source_path":"workspace-relative concept.path","changed":false,"links_added":[{"link_text":"exact original phrase","target_path":"workspace-relative target.md","relative_url":"../target.md"}],"warnings":[]}
