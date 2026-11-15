# Report local navigation and verification status in global topic inputs

Source: {{var:source}}
Document-wide coverage: {{var:coverage}}
Doctrine module index result: {{var:module_index}}
Declared semantic folder index results: {{var:folder_indexes}}

No tools. Return a compact source status record. status MUST be
needs_attention if ANY coverage, document index, or folder index result
is missing, malformed, does not have status=ok, or has unresolved warnings.
For every listed folder index require an actual output object with status=ok.
Never report that one successful navigation page repairs incomplete
coverage. Preserve concise warning summaries with identifying IDs.
No invented concept files.

Return JSON:
{"status":"ok|needs_attention","source_path":"<source.path>",
 "source_slug":"<source.slug>","concepts":[],"warnings":[]}
