Merge synonymous cross-doctrine theme candidates from exactly this bounded batch:
{{var:batch}}

No file access. Keep distinct scopes apart; do not infer relationships from
shared broad words. Prefer stable human-understandable names. Keep at most 15
proposals; if more meaningfully distinct topics are required, report
needs_attention rather than discarding them silently. Keep only names,
descriptions and sparse path examples, not full concept content.

Return JSON only:
{"status":"ok|needs_attention","themes":[{"name":"topic","description":"one sentence","concept_paths":["path"]}],"warnings":[]}
