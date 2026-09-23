Perform the final read-only verification of the generated OKF repository after repair.

Source root: `{{var:source_root}}`
Target OKF root: `{{var:okf_root}}`

Plan:
{{var:plan}}

Repair result:
{{var:repair}}

Checks:
- `<okf_root>/index.md` exists and is readable.
- Every planned concept exists and has valid YAML frontmatter with a non-empty `type`.
- All repository-internal Markdown links resolve inside the OKF root.
- Every planned concept is reachable from the root index through the index hierarchy.
- The generated knowledge remains materially consistent with the actual source; inspect source files where needed.
- No concept claims human verification unless that fact is independently present in the source material.
- No obvious duplicate concepts or unresolved plan gaps remain.
- Do not modify any file.

Return exactly one JSON object:

{
  "valid": true,
  "summary": "string",
  "remaining_findings": [
    {
      "severity": "error|warning",
      "kind": "missing-file|invalid-frontmatter|broken-link|unreachable-concept|source-mismatch|missing-coverage|duplication|quality",
      "path": "relative path inside OKF root or empty string",
      "message": "specific actionable description"
    }
  ],
  "checked_concepts": ["relative/concept.md"],
  "warnings": ["string"]
}

Set `valid` to false if at least one remaining finding has severity `error`; otherwise true. Return valid JSON only.
