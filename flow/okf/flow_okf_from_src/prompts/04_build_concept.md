Create exactly one source-derived OKF concept.

Source root: `{{var:source_root}}`
Target OKF root: `{{var:okf_root}}`

Concept plan:
{{var:concept}}

Rules:
- The concept plan is navigation/planning metadata, not factual evidence. Inspect the actual source needed for the concept.
- Limit source inspection to the evidence/source hints required for this concept; do not broadly analyze the whole source tree.
- Write exactly one concept file at `<okf_root>/<concept.path>`.
- The path must already be inside one planned semantic folder. Never write a normal concept directly below the OKF root.
- Never write outside the OKF root and never modify source code.
- Create the missing semantic parent directory only when needed.
- Start with valid YAML frontmatter containing at least `type`, `title`, `description`, `tags`, and `status: stable`.
- Do not add `verified`.
- Explicitly document every entry in `concept.coverage_items`. For configuration families, enumerate the individual supported keys/members/options represented by that item rather than merely saying that configuration exists.
- For externally observable functions, document what the caller/user/operator can do, the relevant inputs/options and important observable behavior supported by the evidence.
- Keep implementation details secondary to durable behavior, but do not drop configuration/function details required for coverage.
- Include `## Source references` with concrete workspace-relative paths and symbols/keys.
- Add relative links only to paths listed in `related`.

Return exactly one JSON object:
{
  "status":"created",
  "concept_id":"string",
  "path":"relative/concept.md",
  "documented_item_ids":["fn001","cfg001"],
  "source_references":["workspace-relative/path#symbol-or-key"],
  "warnings":["string"]
}

Return valid JSON only.
