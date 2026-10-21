Prepare ONE source doctrine for independent OKF generation. READ ONLY.

Source inventory record: {{var:source}}
OKF root: {{var:okf_root}}

Do not read the entire source or inspect any other doctrine. Derive one stable,
lowercase, kebab-case slug from the FULL workspace-relative path (not just the
basename); identical paths must always receive the same slug. Distinct paths
must have distinct slugs. Do not use positional IDs. Do not include slashes,
dots, or path traversal in the slug. If safe uniqueness is uncertain, return
needs_attention and no fabricated result; do not reuse another module.
Keep document.id equal to slug. The physical module path must be
"doctrines/" + slug. Avoid generic semantic folder names. Never change an
existing completed module's slug casually; stable links depend on it.

Return valid JSON only:
{"status":"ok|needs_attention","document":{"id":"slug","name":"source filename","path":"original workspace-relative source path"},"folder":{"id":"slug","path":"doctrines/slug","title":"human-readable doctrine title"},"warnings":[]}
