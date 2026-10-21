Add up to THREE meaningful INLINE Markdown links within exactly ONE existing doctrine-derived OKF concept. All concept splitting has finished. Do not add a generic Related concepts footer.

Target OKF root: {{var:okf_root}}
Source concept (OKF-root-relative path): {{var:concept_path}}
Source folder ID: {{var:folder_id}}
Pre-link folder verification status: {{var:folder_status}}
Semantic folder structure: {{var:structure}}
Full pre-link snapshot: {{var:snapshot}}

Preconditions:
- If folder_status != "ok", return needs_attention without writing.
- Require snapshot.status == "captured", snapshot.concept_path equal to the source concept path, and complete, nonempty snapshot.content. If any condition fails, return needs_attention without writing.
- Re-read the ENTIRE source before editing; require its content to match the COMPLETE snapshot.content exactly (all characters, newlines and trailing whitespace). If it differs or cannot be read fully, do not write.
- The source concept is the ONLY file you may modify. Never modify its index, other concepts or doctrine sources. Do not move, rename, delete or create files.

Target selection:
- Find plausible target concepts through the OKF root/folder indexes and a few targeted searches. Examine small leading portions of promising targets, not complete folders or the entire repository.
- Add a link only when there is a concrete, evidence-supported relationship in the existing sentence or paragraph (for example a prerequisite, rule, exception, dependency or meaningful contrast). Similar titles are insufficient; zero links is a valid result.
- Targets must already exist as normal Markdown concepts within the OKF root, not index.md or log.md and not the source. Check each target exists. Resolve relative URLs from the SOURCE FILE'S DIRECTORY; reject absolute URLs, traversal outside the root, fragments and invented files.
- Never add a second link to a target already linked anywhere in the original source, even with different link text. Add at most three DISTINCT target paths.

STRICT EDIT CONTRACT (required to protect doctrine content):
- Place links naturally INSIDE the existing concept, at the sentence/paragraph that actually discusses the target. Do not add a Related concepts section or new explanatory claims.
- The ONLY permitted edit is wrapping a contiguous, already-existing plain-text phrase in a standard Markdown link. The exact original phrase must become the link label: ORIGINAL => [ORIGINAL](relative/path.md). No other text may be added, removed, reworded, reordered, reformatted or normalized.
- Each link_text is a nonempty, human-readable plain-text phrase already present verbatim in snapshot.content; it must not contain a newline, Markdown-sensitive square brackets, backslashes, or existing markup. Do not touch links, code fences, inline code, HTML, YAML frontmatter, headings, anchors or source-reference sections. Link only normal prose.
- Preserve all original headings, frontmatter, claims, normative modality, exceptions, references, links, spacing, line endings and trailing characters EXACTLY. Do not insert blank lines or modify a sentence beyond the new link markup.
- Before any write, derive the full proposed text from snapshot.content. Reconstruct the original exactly by replacing EACH proposed newly inserted [link_text](relative_url) with link_text, exactly once. The reconstruction must match snapshot.content character for character. If not, do not write: return needs_attention.
- No proposed link's exact [link_text](relative_url) syntax may already occur in snapshot.content; each must occur exactly once in the proposed result. Avoid ambiguous, overlapping or nested insertions.
- Use os__write_file only after reading the complete existing file; afterward read back the complete file and repeat the exact reconstruction check. If any change other than the declared link wrappers is observed, return needs_attention with a warning.
- If the concept is too long or exact reconstruction cannot be proven, leave it UNCHANGED and report needs_attention; do not guess or silently truncate.

Report only links actually inserted. For each added link provide the exact original label text, target path relative to the OKF root, and Markdown URL relative to the source's directory. A no-op with no valid links uses status ok, changed false and links_added [].

Return valid JSON only:
{"status":"ok|needs_attention","source_path":"{{var:concept_path}}","changed":false,"links_added":[{"link_text":"exact original phrase","target_path":"other-folder/target.md","relative_url":"../other-folder/target.md"}],"warnings":["string"]}
