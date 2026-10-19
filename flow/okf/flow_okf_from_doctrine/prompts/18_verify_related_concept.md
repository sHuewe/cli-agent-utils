Independently verify the cross-links added to exactly ONE doctrine-derived OKF concept. This is a read-only step.

Target OKF root: {{var:okf_root}}
Expected source (OKF-root-relative): {{var:concept_path}}
Source folder ID: {{var:folder_id}}
Link-step result: {{var:link_result}}

Rules:
- Do not modify any files or read original doctrine sources.
- Require link_result.source_path to equal the expected source and link_result.status to be "ok"; mismatches and partial/failed writes are errors.
- Require link_result.changed to match whether links_added is nonempty.
- Read the source concept (also when no links were added) and check it exists with valid YAML frontmatter at the first byte. Reject truncated, missing or malformed concepts; do not claim to verify content fidelity you cannot establish.
- For each link_result.links_added entry, verify that the exact relative Markdown URL is present in the source and resolves relative to the source document's directory to exactly target_path. Resolve within the OKF root; reject traversal outside it, absolute paths, non-concept targets (index.md/log.md), missing targets, self-links and unsupported fragments.
- Check that no reported link is duplicated elsewhere in the source and that at most three target links were added. An empty list is legitimate and must not be treated as a failure.
- For potential integrity issues or an incomplete verification, report "needs_attention" with a concrete finding. Never report "ok" just because the model's result claimed success.

Return JSON only:
{"status":"ok|needs_attention","source_path":"{{var:concept_path}}","checked_links":0,"findings":[{"severity":"error|warning","target_path":"other-folder/target.md","problem":"string"}],"warnings":["string"]}
