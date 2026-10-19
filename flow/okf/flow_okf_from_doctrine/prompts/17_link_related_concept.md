Add a SMALL number of meaningful Markdown links from exactly ONE existing doctrine-derived OKF concept to related concepts. All concept splitting has already finished.

Target OKF root: {{var:okf_root}}
Source concept (OKF-root-relative path): {{var:concept_path}}
Source folder ID: {{var:folder_id}}
Pre-link folder verification status: {{var:folder_status}}
Semantic folder structure: {{var:structure}}
Full pre-link snapshot: {{var:snapshot}}

Rules:
- If folder_status is not "ok", report needs_attention and do not write.
- REQUIRE snapshot.status == "captured", snapshot.concept_path == source concept path, and nonempty full snapshot.content; otherwise do not write and return needs_attention. An incomplete or truncated snapshot is NEVER a valid write baseline.
- Re-read the complete source BEFORE modifying it and compare the FULL text to snapshot.content. If any byte/character differs, do not modify anything and return needs_attention. Do not silently rewrite or normalize the baseline.
- Read the specified source concept. It is the ONLY file you may modify. Never change other concepts, indexes, or doctrine sources.
- Discover possible targets using the root index, folder indexes, and a few targeted literal searches within the OKF root if needed. Read only small initial ranges of promising target concepts; do not enumerate and inject every full concept or the entire repository into context.
- Add a link only where the source and target have a concrete, evidence-supported conceptual relationship (e.g., prerequisite, dependent rule, implementation, exception or meaningful contrast). Mere title similarity is insufficient. Zero new links is a valid result. Prefer quality over density and add at most THREE new target links.
- Every linked target must already exist as a normal Markdown concept inside the OKF root, not index.md/log.md and not the source itself. Verify the target before writing. Do not invent files or heading anchors. Use standard relative Markdown links resolved from the source's DIRECTORY (e.g. [Rule](../operations/rule.md)); never use paths outside the OKF root.
- Before writing, ensure no equivalent link already exists anywhere in the source (including a differently labeled link to the same target).
- CRITICAL: Preserve snapshot.content EXACTLY as a prefix of the post-write file. Do not reformat, rewrite or delete ANY part of the existing concept. Add only a short "## Related concepts" footer section or append new bullet links at the END of an already final "## Related concepts" section. New material MUST be a pure EOF suffix with no edits to the original text, even whitespace. If adding valid links would require modifying text in the middle, leave the concept unchanged and warn.
- Keep all frontmatter, headings, references, citations, normative scope and existing links unchanged. For the suffix, add a line break as needed; never replace previous trailing characters.
- Read the entire source before replacement. If the file cannot be read completely, do not overwrite it. Re-read after writing and check that the COMPLETE snapshot.content is an exact leading prefix of the new file and that the only suffix contains the newly added links. If not, return needs_attention and report the issue.
- Return exact OKF-root-relative source/target paths for links actually written, not proposals. An unchanged concept is a successful no-op. Do not move, delete, rename, or create any files.

Return only JSON:
{"status":"ok|needs_attention","source_path":"{{var:concept_path}}","changed":false,"links_added":[{"target_path":"other-folder/target.md","relative_url":"../other-folder/target.md"}],"warnings":["string"]}
