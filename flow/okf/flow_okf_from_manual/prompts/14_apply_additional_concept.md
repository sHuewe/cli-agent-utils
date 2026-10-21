Apply exactly one assessed additional-concept action to the manual-derived OKF.

Target OKF root: `{{var:okf_root}}`

Assessment:
{{var:assessment}}

Rules:
- If action is `covered` or `not_applicable`, do not modify files.
- For changes, use only `assessment.evidence_ranges`; NEVER read a manual without bounded line arguments.
- For `extend`, read the target concept first and add only missing supported knowledge.
- For `create`, create one concept at the assessed target with valid frontmatter and `## Manual references`.
- If no usable evidence range is supplied, do not invent content.
- Keep the target inside an already planned semantic folder. Do not create new top-level folders.
- Do not update indexes; the later navigation step rebuilds them.
- Keep writes below the OKF root; never modify manuals. Do not add `verified`.

Return exactly one JSON object:
{"status":"unchanged|extended|created","request_id":"string","folder_id":"string","target_path":"relative/path.md or empty string","changed_paths":["relative/path"],"warnings":["string"]}

Return valid JSON only.
