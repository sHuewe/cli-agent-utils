# Discover cross-doctrine connections from compact manifests

Completed module manifests: {{var:modules}}
OKF root: {{var:okf_root}}

No file or tool access. First check the status of every module. If a
module is incomplete, mark needs_attention and do not invent its
concepts or relationships. For completed modules, reason over their
brief concept descriptions and paths TOGETHER (not separate unrelated
batch reductions). Suggest ONLY focused themes supported by concepts
from AT LEAST TWO DISTINCT doctrines. Never present common words or
one-doctrine concepts as cross-doctrine themes.
Make a small number of genuinely useful theme entry points, not one
per concept; zero themes is valid if none are supported.
Stable, non-reserved lowercase kebab-case IDs; path=themen/<id>.md.
Each theme references EXISTING concept paths from the supplied module
manifests only, with concise explanations of why each relates.
Do not reproduce large source passages; do not claim details absent
from the manifests. Return bounded JSON with max 20 themes; if more
are needed, report needs_attention rather than silently truncate.
Do not edit generated concepts or their theme tags in this experiment;
theme pages provide the explicit cross-doctrine links.

Return JSON only:
{"status":"ok|needs_attention","themes":[
 {"id":"stable-theme","path":"themen/stable-theme.md",
 "title":"Theme","description":"narrow shared scope",
 "concept_paths":["doctrines/a/concept.md","doctrines/b/concept.md"]}
],"warnings":[]}
