Repair exactly one manual-derived OKF concept based on verification findings.

Target OKF root: `{{var:okf_root}}`

Concept:
{{var:concept}}

Verification:
{{var:verification}}

Rules:
- Read the target concept before changing it.
- If status is `ok`, do not modify files and return the verified IDs.
- Otherwise fix every concrete finding, especially missing assigned function/configuration coverage.
- NEVER read a manual without both `start_line` and `end_line`.
- Read only `concept.evidence_ranges`.
- Preserve correct content/frontmatter and avoid unrelated rewrites.
- Keep writes below the OKF root; never modify manuals. Do not add `verified`.

Return exactly one JSON object:
{"status":"ok|repaired","concept_id":"string","path":"relative/concept.md","documented_item_ids":["string"],"changed_paths":["relative/path"],"remaining_item_ids":[],"remaining_warnings":["string"]}

Return valid JSON only.
