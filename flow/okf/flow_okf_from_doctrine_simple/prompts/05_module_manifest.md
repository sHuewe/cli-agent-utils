# Compact manifest of a generated doctrine module

Plan: {{var:plan}}
Navigation result: {{var:navigation}}
OKF root: {{var:okf_root}}

NO file or tool access. Do not invent or extend the planned concepts.
The manifest is for document-wide topic discovery: preserve only
identity, brief descriptions, source path, existing concept paths and
local semantic tags. DO NOT copy evidence_ranges, original text or
detailed coverage objects.
Status is ok only when BOTH plan and navigation say ok.
Paths under concepts must be the root-relative planned paths, not
absolute paths or another doctrine's files.
Return JSON only:
{"status":"ok|needs_attention","source_path":"original.md",
"module_path":"doctrines/stable-slug",
"title":"module title","description":"one-sentence scope",
"concepts":[{"path":"doctrines/stable-slug/concept.md","title":"title",
"description":"one sentence","tags":["domain"]}],"warnings":[]}
