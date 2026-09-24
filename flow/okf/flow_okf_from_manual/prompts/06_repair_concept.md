Repair exactly one generated OKF concept based on verification findings and the recorded manual evidence.

Target OKF root: `{{var:okf_root}}`
Verification result:
{{var:verification}}

Rules:
- If status is `ok`, do not modify files.
- Otherwise read the target concept before changing it and fix only the concrete findings listed in `findings`.
- For manual files, NEVER call `read_file` without both `start_line` and `end_line`.
- Read only the ranges listed in `verification.evidence_ranges`. Never read or scan an entire manual.
- Keep all writes below the OKF root and do not modify manuals/original source material.
- Preserve correct existing content and frontmatter; avoid unrelated rewrites.
- Do not add `verified` or imply human review.

Return exactly one JSON object:
{
  "status":"ok|repaired",
  "id":"string",
  "path":"relative/concept.md",
  "evidence_ranges":[
    {"manual":"workspace-relative/path","start_line":1,"end_line":120,"reason":"string"}
  ],
  "changed_paths":["relative/path"],
  "remaining_warnings":["string"]
}

Return valid JSON only.
