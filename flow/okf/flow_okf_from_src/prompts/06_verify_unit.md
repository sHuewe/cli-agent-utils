Verify exactly one generated OKF unit.

Target OKF root: `{{var:okf_root}}`
Build result:
{{var:build}}

Rules:
- Read the unit index and every concept listed by the build result.
- Check that all files exist below the OKF root, each concept has valid YAML frontmatter with non-empty `type`, and relative Markdown links stay inside the OKF repository.
- Check that the unit index makes all listed concepts reachable.
- Spot-check source references and key claims against the source. Do not re-analyze unrelated units.
- Do not modify files.

Return exactly one JSON object:
{
  "status":"ok|needs_repair",
  "unit": {
    "name":"string",
    "source_path":"workspace-relative/path",
    "okf_path":"relative/path"
  },
  "index_path":"relative/path/index.md",
  "concept_paths":["relative/concept.md"],
  "findings":[
    {"severity":"error|warning","path":"relative/path","problem":"string","required_change":"string"}
  ],
  "warnings":["string"]
}

Return valid JSON only.
