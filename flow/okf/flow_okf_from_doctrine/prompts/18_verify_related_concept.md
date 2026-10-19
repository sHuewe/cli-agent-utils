Independently verify the cross-links added to exactly ONE doctrine-derived OKF concept. This is a read-only step.

Target OKF root: {{var:okf_root}}
Expected source (OKF-root-relative): {{var:concept_path}}
Source folder ID: {{var:folder_id}}
Link-step result: {{var:link_result}}
Authoritative pre-link snapshot: {{var:snapshot}}

Rules:
- Do not modify any files or read original doctrine sources.
- Require link_result.source_path to equal the expected source and link_result.status to be "ok"; mismatches and partial/failed writes are errors.
- Require link_result.changed to match whether links_added is nonempty.
- REQUIRE snapshot.status == "captured", snapshot.concept_path == the expected source, and snapshot.content be complete, nonempty, and untruncated. Any missing, wrong-path, incomplete or malformed snapshot is a blocking needs_attention finding. Do not trust link_result's self-report about preservation.
- Read the FULL current source concept, even when no links were added. Reject truncated reads, missing or malformed concepts or invalid frontmatter.
- Independently compare complete snapshot.content against the FULL current file. For changed==false, the entire current file MUST be exactly identical to snapshot.content. For changed==true, the current file MUST start with the EXACT complete snapshot.content, unchanged byte-for-byte/character-for-character; only an EOF suffix consisting of the newly reported Related concepts link lines is permitted. Treat any lost or modified existing text, headings, citations, YAML fields, anchors, or links as a blocking error even if all reported links resolve. If the complete comparison cannot be carried out, return needs_attention, never ok.
- Check that the newly added footer/suffix contains only up to three link entries and optional related-concepts heading/blank lines, with no unrelated substantive changes.
- For each link_result.links_added entry, verify that the exact relative Markdown URL is present in the source and resolves relative to the source document's directory to exactly target_path. Resolve within the OKF root; reject traversal outside it, absolute paths, non-concept targets (index.md/log.md), missing targets, self-links and unsupported fragments.
- Check that no reported link is duplicated elsewhere in the source and that at most three target links were added. An empty list is legitimate and must not be treated as a failure.
- For potential integrity issues or an incomplete verification, report "needs_attention" with a concrete finding. Never report "ok" just because the model's result claimed success.

Return JSON only:
{"status":"ok|needs_attention","source_path":"{{var:concept_path}}","checked_links":0,"findings":[{"severity":"error|warning","target_path":"other-folder/target.md","problem":"string"}],"warnings":["string"]}
