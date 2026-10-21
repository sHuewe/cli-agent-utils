Create exactly ONE focused OKF concept part from a pre-existing split assessment. This is one small stage of a multi-step split; do NOT rewrite the original concept or the folder index.

Target OKF root: {{var:okf_root}}
Original concept path: {{var:concept_path}}
Assessment: {{var:assessment}}
Current planned part: {{var:part}}
Pre-split snapshot status: {{var:snapshot_status}}
Complete original concept content (NOT the folder index):
{{var:original_content}}

Rules:
- Only perform a write when assessment.action == "split", snapshot_status == "captured", original_content is complete and nonempty, and part is exactly one member of assessment.parts. Otherwise do not modify any file and return needs_attention.
- The only file you may create is <okf_root>/<part.path>; keep it directly in the original concept's semantic folder, with a lower-case kebab-case .md filename. Do not modify the original concept, other parts or the folder index. Do not touch doctrine sources.
- First check whether the exact destination part already exists. If it exists, NEVER overwrite or alter it. Read it sufficiently to establish it is a valid focused concept representing the requested part.scope, with proper YAML frontmatter and references. Return already_present only if it matches; otherwise return needs_attention. This also allows completed legacy splits to be resumed without modifying their parts.
- If absent: before writing, read the complete original concept and require it to equal original_content exactly. If it differs, return needs_attention without writing; do not attempt to repair an earlier partial split.
- Transfer only information, examples, normative qualifiers, constraints and original source references actually present in original_content and relevant to this part.scope. Do not invent or infer new facts. Do not copy information that clearly belongs only to another planned part. Give the part sufficient local context to be understandable on its own.
- Include YAML frontmatter at byte zero with at least type, title, description, tags, status: stable. Do not invent verified or alter a human verification claim. Preserve supporting source/manual references for every relocated assertion.
- Keep useful relative Markdown links valid at the new path. Avoid unnecessary new cross-concept links; a dedicated later flow will add those.
- After writing, read back the created part to confirm it exists, has valid frontmatter, and covers this planned scope. Never move, delete, or rename files.
- On any uncertainty or missing source material, return needs_attention rather than silently dropping content or overwriting an existing path. Do not report success if a tool failed.

Return valid JSON only:
{"status":"created|already_present|needs_attention","path":"relative/part.md","changed_paths":["relative/part.md"],"warnings":["string"]}
For already_present, changed_paths must be []; for needs_attention, include concrete warnings and only paths actually written.
