Perform compact root-level consistency verification. READ ONLY.
Registry: {{var:registry}}
Root navigation write: {{var:index}}
Per-theme verifications: {{var:theme_results}}
Per-module tag updates: {{var:tag_results}}
OKF root: {{var:okf_root}}

Require index.status==ok and registry.status==ok. Check every reported
theme verification status, every module's nested tag iteration status and
paths. Never accept missing or malformed results as success. Read only the
root index, doctrines/index.md, themen/index.md. Require working navigation
to module index files and actual thematic concept pages. Do not scan all
concepts or doctrine sources; do not claim independently verified coverage.
If any result is incomplete, output needs_attention. Do not modify files.

JSON only:
{"status":"ok|needs_attention","checked_themes":0,"checked_doctrines":0,"warnings":[]}
