Create or update ONE derived thematic OKF concept.
Theme: {{var:theme}}
OKF root: {{var:okf_root}}

Use os search_text ONLY in okf_root/doctrines for the EXACT literal tag
"theme:<theme.id>" to discover candidate concept files. Search results may be
truncated (max 200). If truncated, return needs_attention, NEVER claim complete
membership. Read only matching concept frontmatter plus the shortest relevant
bounded sections. Validate each candidate actually carries the tag. Reject
non-concepts and duplicates. Require at least two distinct doctrine modules.
Do not invent relationships: explain verified complementary roles and any
source-dependent contradictions. Build a focused summary with normal relative
Markdown links to every validated participating concept, without copying
large source paragraphs. The theme page has valid frontmatter (type:
concept, title, description, tags) and preserves the stable path specified
in theme.path. Only write okf_root/theme.path. Treat old theme content as
derived and replace it when membership changes. Do not modify doctrines.

Return JSON only:
{"status":"ok|needs_attention","path":"workspace-relative theme path","members":["workspace-relative concept paths"],"warnings":[]}
