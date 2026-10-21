Discover meaningful cross-link CANDIDATES from exactly ONE target OKF folder. READ ONLY. Never edit a concept or index.

Source concept (workspace-relative): {{var:concept_path}}
OKF root (workspace-relative): {{var:okf_root}}
Current target folder (workspace-relative): {{var:target_folder_path}}
Pre-link snapshot: {{var:snapshot}}

Require snapshot.status == "captured", snapshot.concept_path == concept_path and complete nonempty snapshot.content. Otherwise return needs_attention without guessing.

Inspect only the CURRENT target folder: read its index.md for candidate titles/paths AND independently perform targeted text searches restricted to that folder for meaningful terms, synonyms and relevant phrases from the source snapshot. Index navigation is useful but not sufficient. Consult candidate file contents selectively to establish relevance. Never search other target folders in this iteration; the orchestrator processes them separately.
Do not invent concepts. Return only normal, existing .md concepts directly in target_folder_path, excluding index.md, log.md and the source. Every candidate must be an existing target under the OKF root and have a substantiated semantic relationship to a phrase that ALREADY occurs naturally in the original source prose. Do not generate new source wording. Zero candidates are valid; there is no fixed limit. Do not emit the full source text or full target text.

Return only compact valid JSON:
{"status":"ok|needs_attention","target_folder":"workspace-relative target folder","candidates":[{"target_path":"workspace-relative existing concept.md","link_text":"exact existing source prose phrase","reason":"specific semantic relationship"}],"warnings":[]}
