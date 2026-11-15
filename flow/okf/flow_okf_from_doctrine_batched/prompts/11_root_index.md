# Build concise separated OKF root navigation

OKF root: {{var:okf_root}}

Write root/index.md, doctrines/index.md and themen/index.md ONLY.
Read top-level subdirectory listings and their index.md headings; do not
read all concept files or sources. Root index must link doctrines/ and
themen/, explain document-oriented versus thematic navigation.
doctrines/index.md links to each actual module index.md; themen/index.md
links to every actual theme page. Do not invent entries. If the number
of modules or themes makes a complete index infeasible in this model
request, return needs_attention. No unbounded list of all concepts.
Use safe relative Markdown links. Return:
{"status":"ok|needs_attention","root_index":"index.md",
"doctrine_count":0,"theme_count":0,"warnings":[]}

