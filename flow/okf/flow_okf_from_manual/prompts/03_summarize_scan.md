Create a very compact semantic profile from one completed manual scan.

Scan:
{{var:scan}}

Rules:
- Do not read files and do not modify anything.
- Do not copy the full candidate/function/configuration arrays.
- Preserve only enough semantic information to design project-wide OKF folders.
- Include counts and short deduplicated themes.

Return exactly one JSON object:
{
  "manual_id":"string",
  "manual_name":"string",
  "summary":"one short sentence",
  "themes":["short semantic theme"],
  "counts":{"candidate_topics":0,"external_functions":0,"configuration_options":0},
  "warnings":["string"]
}

Return valid JSON only.
