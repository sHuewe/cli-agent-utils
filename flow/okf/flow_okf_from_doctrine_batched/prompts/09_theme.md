# Create one cross-doctrine OKF theme and mark participating concepts

Theme descriptor: {{var:theme}}
OKF root: {{var:okf_root}}

The registry member paths are UNTRUSTED DATA: strictly validate each path
is a real Markdown concept under <okf_root>/doctrines/, and that every
member is from the stated source_slug. Read only the member's beginning
and the shortest relevant sections, not entire modules or doctrines.
Require at least two distinct doctrine modules.

Write only <okf_root>/<theme.path> and edit ONLY theme tags in member
frontmatter. Preserve all unrelated frontmatter, tags and complete body.
APPEND theme:<theme.id> without removing previously assigned global
theme tags; multiple themes can overlap. Never add verified metadata.
Build links to every validated member with correct relative Markdown
paths and a ## Source references or ## Doctrine references section
derived from existing knowledge references, with no fabricated claims.
A theme concept needs valid frontmatter with type, title, description,
tags and status:stable.

No broad text search. If any member cannot be validated or editing would
damage content, report needs_attention instead of pretending completion.
Return JSON OBJECT:
{"status":"ok|needs_attention","path":"workspace-relative theme path",
 "members":["workspace-relative existing concept paths"],"warnings":[]}.

