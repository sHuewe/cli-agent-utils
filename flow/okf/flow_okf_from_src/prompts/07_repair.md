Repair the generated OKF repository using only the concrete findings from verification.

Source root: `{{var:source_root}}`
Target OKF root: `{{var:okf_root}}`

Plan:
{{var:plan}}

Verification result:
{{var:verification}}

Rules:
- Do not change source code.
- If verification contains no findings, do not modify the OKF repository.
- Repair only findings that can be resolved deterministically from the source and plan.
- Re-read any existing OKF file before overwriting it.
- For source-mismatch or quality findings, inspect the cited/relevant source and correct the concept without inventing unsupported facts.
- For broken links or unreachable concepts, fix index/concept links while preserving the planned concept paths.
- For missing files that are present in the plan, create the missing planned file from source evidence. Do not create concepts that are absent from the plan.
- If a required parent directory is missing, create it before writing the file.
- Preserve valid YAML frontmatter and ensure every concept has a non-empty `type`.
- Never write outside the target OKF root. Reject absolute paths or any path containing `..`.
- Do not claim human verification or add a `verified` field.
- If a finding cannot be safely repaired, leave it unchanged and report it in `unresolved`.

Return exactly one JSON object:

{
  "status": "repaired|no_changes",
  "modified_files": ["relative/path.md"],
  "created_directories": ["relative/directory"],
  "unresolved": [
    {
      "path": "relative path or empty string",
      "message": "string"
    }
  ],
  "warnings": ["string"]
}

Return valid JSON only.
