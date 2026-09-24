Verify exactly one generated OKF concept against its recorded manual evidence.

Target OKF root: `{{var:okf_root}}`
Build result:
{{var:build}}

Rules:
- Read the generated concept at `build.path`.
- Check that it exists below the OKF root and has valid YAML frontmatter with a non-empty `type`.
- For manual files, NEVER call `read_file` without both `start_line` and `end_line`.
- Re-read only the ranges listed in `build.evidence_ranges`. Never read or scan an entire manual.
- Check important factual claims against those ranges and check that the `## Manual references` section accurately cites the relevant ranges.
- Check internal Markdown links for obvious invalid/out-of-root targets.
- Do not modify files.

Return exactly one JSON object:
{
  "status":"ok|needs_repair",
  "id":"string",
  "path":"relative/concept.md",
  "evidence_ranges":[
    {"manual":"workspace-relative/path","start_line":1,"end_line":120,"reason":"string"}
  ],
  "findings":[
    {"severity":"error|warning","problem":"string","required_change":"string"}
  ],
  "warnings":["string"]
}

Return valid JSON only.
