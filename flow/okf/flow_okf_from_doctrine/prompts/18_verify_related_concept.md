Independently verify INLINE cross-links added to exactly ONE doctrine-derived OKF concept. This step is read-only.

Target OKF root: {{var:okf_root}}
Expected source (OKF-root-relative): {{var:concept_path}}
Source folder ID: {{var:folder_id}}
Link-step result: {{var:link_result}}
Authoritative complete pre-link snapshot: {{var:snapshot}}

Rules:
- Never modify files or read doctrine sources. Require link_result.source_path and snapshot.concept_path to equal the expected source; require link_result.status == "ok", snapshot.status == "captured", and complete nonempty snapshot.content. An incomplete read/snapshot is a blocking error.
- Read the FULL current source concept, including whitespace, line endings and YAML frontmatter. If unable to read it completely, return needs_attention.
- Require link_result.changed to be a boolean equal to whether links_added is nonempty. Require links_added to be a list of at most THREE entries.
- If changed is false, the current file MUST equal snapshot.content character for character.
- If changed is true, perform a FULL reconstruction of snapshot.content by removing ONLY the introduced Markdown-link syntax. For each reported link, require a nonempty plain-text link_text, target_path and relative_url, and the exact new token [link_text](relative_url) to appear ONCE in the current file and not already in snapshot.content. Replace that token with link_text ONCE, without modifying the surrounding text. After processing every reported link, the reconstructed entire current text MUST equal the entire snapshot.content character for character. No lost or rephrased words, spacing, headings, frontmatter, references, punctuation, anchors, old links or other modifications are allowed. If reconstruction fails or is ambiguous, return needs_attention even if URLs resolve.
- Verify the link label is the verbatim original phrase; it must not introduce new wording, span lines, or be placed inside a code fence, inline code, YAML frontmatter, heading, HTML, a pre-existing link or source-reference section. Reject nested/overlapping links.
- Resolve each URL relative to the SOURCE DOCUMENT'S parent directory. Verify it points exactly to reported target_path, exists as a normal Markdown concept within the OKF root and is neither index.md/log.md nor the source. Reject absolute paths, unsupported fragments, directory escapes and duplicates (including previously existing links to the same target).
- An unchanged concept with no links is valid. Any missing evidence or error yields needs_attention with concrete findings; NEVER trust the link step's own fidelity assertion as proof.
- Do not claim the checks were completed if full-content comparison was impossible.

Return valid JSON only:
{"status":"ok|needs_attention","source_path":"{{var:concept_path}}","checked_links":0,"findings":[{"severity":"error|warning","target_path":"other-folder/target.md","problem":"string"}],"warnings":["string"]}
