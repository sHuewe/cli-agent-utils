Add meaningful, evidence-supported INLINE Markdown links to related existing OKF concepts in exactly one source concept, without rewriting any of its original content. There is NO FIXED MAXIMUM number of links: relevance and natural placement determine how many to add.

Source concept path (workspace-relative): {{var:concept_path}}
Folder status: {{var:folder_status}}
Folder ID: {{var:folder_id}}
Folder context: {{var:structure}}
OKF root (workspace-relative): {{var:okf_root}}
Full pre-link snapshot: {{var:snapshot}}

Use concept_path directly as a WORKSPACE-relative source path. Require folder_status == "ok" and snapshot.status == "captured", snapshot.concept_path == concept_path, and complete nonempty snapshot.content; otherwise return needs_attention without writing. Re-read the ENTIRE source before editing and require an exact character-for-character match to snapshot.content.

Discover candidate targets using BOTH index navigation AND targeted text search, restricted to the OKF root:
1. Read the OKF root index.md when present, the source folder's index.md, and relevant linked folder/section index.md files. Follow navigation entries to discover related concepts, including concepts in other folders. Read-only: NEVER edit an index. An index entry alone is not evidence that two concepts are meaningfully related.
2. Independently perform targeted text searches across existing Markdown concepts under the OKF root for distinctive terms, aliases, synonyms and subject-specific phrases from the source concept. Use focused searches instead of blindly loading every file. Do this EVEN IF index navigation already found candidates, because indexes need not list all semantic relationships.
3. Inspect candidate concept contents as needed. Confirm a concrete, meaningful relationship to the source and an existing, naturally suitable plain-text phrase in the source to link. Do not add weak topical associations or links merely to raise the count.

Targets must exist and must not be index.md, log.md, or the source. No invented paths, no links outside the OKF root. Relative Markdown URLs must resolve from the source file's parent directory to the target. Add no more than ONE link per distinct target in this source concept, and do not add a link to a target already linked in the original file. There is no fixed target count or maximum: add all well-supported, nonredundant links that fit naturally, whether few or many. Zero links is valid. If indexes are missing or cannot be read, continue with targeted text searches; never invent index contents.

STRICT EDIT CONTRACT:
- The source concept is the ONLY file that may be modified. Do not create, delete, rename or move any file.
- Only wrap an existing contiguous plain-text phrase in [EXACT ORIGINAL PHRASE](relative/url.md). Never add, remove, rephrase, reorder or normalize any original text, spacing, headings, frontmatter, references or links.
- Only link normal prose; never touch existing links, code fences, inline code, HTML, frontmatter, headings, anchors or reference sections. Link text cannot contain newlines, brackets, backslashes or existing markup.
- Before writing, reconstruct the original by replacing each newly proposed link token with its original phrase exactly once. The reconstructed complete text MUST equal snapshot.content character for character. No overlapping, nested or ambiguous replacements. Each proposed token must occur exactly once and not exist in the original snapshot.
- Use os__write_file only after a complete source read and successful reconstruction. Read the full file back and repeat the reconstruction check. If a check cannot be completed, leave the file unchanged or return needs_attention with an explicit warning.
- Only DISTINCT, evidence-supported targets naturally discussed in existing prose. Do not impose a numerical link limit and do not append a Related concepts section.

Report target_path as a WORKSPACE-relative path (the same format as inventory.files[].path). Report only links actually inserted.

Return valid JSON only:
{"status":"ok|needs_attention","source_path":"workspace-relative concept_path","changed":false,"links_added":[{"link_text":"exact original phrase","target_path":"workspace-relative target.md","relative_url":"../target.md"}],"warnings":[]}
