Repair exactly one generated OKF unit based on verification findings.

Target OKF root: `{{var:okf_root}}`
Verification result:
{{var:verification}}

Rules:
- If status is `ok`, do not modify files.
- Otherwise fix only the concrete findings listed in `findings`.
- Keep all writes below the OKF root.
- Do not modify source code.
- Re-read a file before overwriting it.
- Preserve correct existing content and avoid unrelated rewrites.

Return exactly one JSON object:
{
  "status":"ok|repaired",
  "unit": {
    "name":"string",
    "source_path":"workspace-relative/path",
    "okf_path":"relative/path"
  },
  "index_path":"relative/path/index.md",
  "concept_paths":["relative/concept.md"],
  "changed_paths":["relative/path"],
  "remaining_warnings":["string"]
}

Return valid JSON only.
