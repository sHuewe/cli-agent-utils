Perform the final compact root-level structural verification of the generated OKF.

Target OKF root: `{{var:okf_root}}`

Semantic structure:
{{var:structure}}

Root-index result:
{{var:navigation}}

Per-folder verification results:
{{var:folder_verifications}}

Rules:
- Do not re-read all concept files and do not analyze original source/manual material.
- Read only the root `<okf_root>/index.md`.
- Verify it links every declared semantic folder index and does not bypass the planned folder layer for normal concepts.
- Check that every per-folder verification result is present and account for its reported errors/warnings.
- Verify no normal generated concept is reported directly below the OKF root.
- Do not modify files.

Return exactly one JSON object:
{
  "status":"ok|needs_attention",
  "checked_folders":["folder-id"],
  "findings":[{"severity":"error|warning","path":"relative/path","problem":"string"}],
  "warnings":["string"]
}

Return valid JSON only.
