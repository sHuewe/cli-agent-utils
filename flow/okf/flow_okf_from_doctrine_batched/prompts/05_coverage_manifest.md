# Preserve deterministic coverage status in one small profile

Source: {{var:source}}
Coverage report from verify_coverage: {{var:coverage}}

No tools. Propagate coverage.status literally. Do NOT infer that a
missing or incomplete verification succeeded. Retain the original
warnings briefly and state which scope was incomplete. No new facts.
Return JSON only:
{"status":"ok|needs_attention","source_path":"<source.path>",
 "source_slug":"<source.slug>","concepts":[],"warnings":[]}

When coverage has nonempty missing_item_ids or status!=ok, status MUST
be needs_attention and warnings identify the missing IDs (or a bounded
sample plus complete missing count). Do not invent concept paths.
