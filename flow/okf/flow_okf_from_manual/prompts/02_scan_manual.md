Scan exactly one manual and create a complete evidence inventory for later OKF generation.

Manual:
{{var:manual}}

Rules:
- Read only `manual.path`; do not inspect other manuals or unrelated files.
- NEVER read this manual without both `start_line` and `end_line`.
- Scan sequentially using bounded ranges. Prefer roughly 200-350 lines per first-pass read and continue until beyond EOF.
- Keep the model output compact even when the manual is long; do not quote manual prose.
- Completeness is mandatory: identify coherent reusable topics, every user-visible/externally observable function, and every configuration possibility described by the manual.
- Configuration includes individual keys/options/settings, modes, flags, endpoints, paths, timeouts, limits and toggles. Do not collapse multiple independently configurable settings into a vague "configuration" entry.
- Assign `fn001...` to functions/capabilities and `cfg001...` to configuration options.
- Every candidate/function/configuration item must have concrete 1-based inclusive evidence ranges. Prefer focused ranges <=200 lines where possible.
- Do not use the entire manual as one evidence range.
- Do not modify files.

Return exactly one JSON object:
{
  "manual":{"id":"string","name":"string","path":"workspace-relative/path"},
  "summary":"string",
  "candidate_concepts":[{"id":"topic001","name":"string","description":"string","evidence_ranges":[{"manual":"workspace-relative/path","start_line":1,"end_line":120,"reason":"string"}]}],
  "external_functions":[{"id":"fn001","name":"string","kind":"string","description":"string","evidence_ranges":[{"manual":"workspace-relative/path","start_line":1,"end_line":40,"reason":"string"}]}],
  "configuration_options":[{"id":"cfg001","name":"string","description":"string","evidence_ranges":[{"manual":"workspace-relative/path","start_line":1,"end_line":40,"reason":"string"}]}],
  "scan_checks":{"function_sweep":"completed","configuration_sweep":"completed"},
  "warnings":["string"]
}

Return valid JSON only.
