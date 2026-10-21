Independently verify ONE cross-doctrine theme. READ ONLY.
Theme: {{var:theme}}
OKF root: {{var:okf_root}}
Write result: {{var:write}}

Require write.status==ok. Read the thematic document and verify YAML
frontmatter, exact canonical path, real relative internal links, at least two
different doctrine modules, no escapes outside root and no invented links.
Do not infer full global completeness from an LLM search. If source search
was truncated or any member cannot be verified, return needs_attention.
Never write files.

Return JSON only:
{"status":"ok|needs_attention","path":"workspace-relative theme path","checked_members":0,"warnings":[]}
