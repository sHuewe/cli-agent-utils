# Repair an actual concept defect (not a planning artifact)

Original doctrine: {{var:source}}
Root: {{var:okf_root}}
Concept plan: {{var:concept}}
Verification: {{var:verification}}

The verifier identified a concrete defect fixable by editing the
Markdown concept. Read that concept and, if needed, its ORIGINAL
bounded source evidence_ranges (always use both line parameters).
Fix only the actual target file under <okf_root>/<concept.path>.
Preserve correct content and sourced conditions, exceptions, scope,
citations and frontmatter. Do not change original doctrines, planning
JSON, source-range metadata, other concepts or indexes. Do not invent
source support. If the issue is unfixable from supplied evidence, stop
and return needs_attention rather than claim success. Do not return a
documented/missing-item contradiction from an atomic coverage registry.

Return JSON only:
{"status":"repaired|needs_attention","concept_id":"planned id",
"path":"planned concept path","changed":true,"warnings":[]}
