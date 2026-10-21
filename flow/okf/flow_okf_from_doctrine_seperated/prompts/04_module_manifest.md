Emit a COMPACT, source-grounded module manifest for global theme discovery.
Source: {{var:source}}
Prepared identity: {{var:meta}}
Verified concept summaries: {{var:plan}}
Coverage: {{var:coverage}}
Index result: {{var:index}}

Do not read files or use tools. Require coverage.status=="ok",
index.status=="ok", meta.status=="ok"; if not return needs_attention.
Each concept from plan must occur exactly once, with its FULL workspace-relative
path (prepend the configured OKF root if the plan path is root-relative).
Never invent concepts; keep descriptions to one sentence. Avoid copying source
text, evidence ranges, coverage item objects or other large data. The source
path (not the generated concept path) is the source_path for change tracking.
Keep existing semantic tags separate from global topic membership tags.

JSON only:
{"status":"ok|needs_attention","source_path":"original doctrine source path",
"module_path":"workspace-relative module folder","title":"title","description":"one sentence",
"concepts":[{"path":"workspace-relative concept.md","title":"title","description":"short description","tags":[]}],
"warnings":[]}
