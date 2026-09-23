Verify the generated OKF repository against the source and the explicit plan. This step is read-only.

Source root: `{{var:source_root}}`
Target OKF root: `{{var:okf_root}}`

Plan:
{{var:plan}}

Verification requirements:
- Confirm that `<okf_root>/index.md` exists and is readable.
- Confirm that every successfully planned concept path exists as a Markdown file and begins with valid YAML frontmatter containing a non-empty `type`.
- Check that concept titles/descriptions/content are materially supported by the source. Sample the actual source where necessary; do not treat the plan as proof.
- Check that workspace-relative source references used by concepts point to plausible existing source locations.
- Check relative Markdown links in root/directory indexes and concepts for broken or escaping paths.
- Check that every planned concept is reachable from the root through the index hierarchy.
- Flag duplicate or substantially overlapping concepts.
- Flag concepts that are too implementation-fragmentary to be durable knowledge, or too broad to be useful.
- Flag obvious gaps where the plan itself lists a concept but the generated repository fails to cover its stated purpose.
- Do not invent issues merely to be exhaustive. Findings must be concrete and actionable.

Return exactly one JSON object:

{
  "valid": true,
  "summary": "string",
  "findings": [
    {
      "severity": "error|warning",
      "kind": "missing-file|invalid-frontmatter|broken-link|unreachable-concept|source-mismatch|missing-coverage|duplication|quality",
      "path": "relative path inside OKF root or empty string for repository-wide finding",
      "message": "specific actionable description"
    }
  ],
  "checked_concepts": ["relative/concept.md"],
  "warnings": ["string"]
}

Set `valid` to false if at least one finding has severity `error`; otherwise true. Return valid JSON only.
