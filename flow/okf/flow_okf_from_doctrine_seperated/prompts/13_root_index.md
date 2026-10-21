Create a compact, human-usable root navigation index for the separated OKF.
Root: {{var:okf_root}}
Root inventory: {{var:inventory}}
Global themes: {{var:themes}}

Only modify root/index.md and, if missing, doctrines/index.md and
themen/index.md. Use os list_files for one level beneath doctrines/ and read
only each module's index.md header (at most 50 lines). Create short
source-oriented entries for every module, and thematic entries for every
valid existing theme. Root index MUST link to doctrines/ and themen/ and
explain both navigation approaches, not enumerate thousands of concepts.
Ensure each index contains proper relative links and no escapes. Treat missing
theme pages or module index as needs_attention, not as successes. Avoid
overlong root content; use intermediate indices. Do not alter doctrine concept
bodies or global theme content.

Return JSON only:
{"status":"ok|needs_attention","root_index":"index.md","doctrine_count":0,"theme_count":0,"warnings":[]}
