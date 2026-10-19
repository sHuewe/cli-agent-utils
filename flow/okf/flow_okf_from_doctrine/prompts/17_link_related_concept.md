Add a SMALL number of meaningful Markdown links from exactly ONE existing doctrine-derived OKF concept to related concepts. All concept splitting has already finished.

Target OKF root: {{var:okf_root}}
Source concept (OKF-root-relative path): {{var:concept_path}}
Source folder ID: {{var:folder_id}}
Pre-link folder verification status: {{var:folder_status}}
Semantic folder structure: {{var:structure}}

Rules:
- If folder_status is not "ok", report needs_attention and do not write.
- Read the specified source concept. It is the ONLY file you may modify. Never change other concepts, indexes, or doctrine sources.
- Discover possible targets using the root index, folder indexes, and a few targeted literal searches within the OKF root if needed. Read only small initial ranges of promising target concepts; do not enumerate and inject every full concept or the entire repository into context.
- Add a link only where the source and target have a concrete, evidence-supported conceptual relationship (e.g., prerequisite, dependent rule, implementation, exception or meaningful contrast). Mere title similarity is insufficient. Zero new links is a valid result. Prefer quality over density and add at most THREE new target links.
- Every linked target must already exist as a normal Markdown concept inside the OKF root, not index.md/log.md and not the source itself. Verify the target before writing. Do not invent files or heading anchors. Use standard relative Markdown links resolved from the source's DIRECTORY (e.g. [Rule](../operations/rule.md)); never use paths outside the OKF root.
- Before writing, ensure no equivalent link already exists anywhere in the source (including a differently labeled link to the same target). Preserve ALL existing content, original headings, frontmatter and its exact YAML fields, citations, normative scope, and links. Only append a short "## Related concepts" section or add to an existing one; do not rewrite other sections or remove material.
- Read the entire source before replacement. If the file cannot be read completely, do not overwrite it. Re-read after writing and check that all original material and the newly added links are still present. If not, return needs_attention and report the issue.
- Return exact OKF-root-relative source/target paths for links actually written, not proposals. An unchanged concept is a successful no-op. Do not move, delete, rename, or create any files.

Return only JSON:
{"status":"ok|needs_attention","source_path":"{{var:concept_path}}","changed":false,"links_added":[{"target_path":"other-folder/target.md","relative_url":"../other-folder/target.md"}],"warnings":["string"]}
