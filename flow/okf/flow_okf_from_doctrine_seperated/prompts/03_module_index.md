Write or update ONLY the index.md in this doctrine's folder. No other file may be changed.
Folder: {{var:folder}}
OKF root: {{var:okf_root}}
Fresh non-recursive folder inventory: {{var:inventory}}
Authoritative source-coverage result: {{var:coverage}}

Require coverage.status == "ok" or return needs_attention without writing.
Require inventory.directory == okf_root + "/" + folder.path. Compare actual
normal .md concepts from inventory.files (exclude index.md and log.md), not
just any planned filenames. Read at most the initial 50 lines per concept
to obtain title and description. Keep the index concise and link EVERY
actual concept using ordinary relative Markdown paths, exactly once.
Explain what this doctrine covers. Do not link arbitrary external files,
and do not modify any concept.

Return JSON only:
{"status":"ok|needs_attention","index_path":"workspace-relative index.md","concept_paths":["workspace-relative concept.md"],"warnings":[]}
