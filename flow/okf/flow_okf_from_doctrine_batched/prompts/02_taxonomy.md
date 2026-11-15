# Choose a small semantic folder taxonomy for ONE document

Source identity: {{var:source}}
Compact deterministic topic profile: {{var:profile}}

No tools, no original source reads. This is folder navigation only;
knowledge extraction and topic grouping are separate steps. Decide based
ONLY on the profile's candidate_count, tags and sample_titles.

When candidate_count <=15 output folders=[] (flat doctrine layout).
When >15 choose 2-8 meaningful, distinct semantic subfolders based on
the actual subject matter. These are NOT the final concept clusters.
No generic or catch-all folders. Folder IDs are stable safe lowercase
kebab-case. Each folder has a title and short description. No paths.

Return JSON ONLY:
{"status":"ok","folders":[
 {"id":"one-semantic-area","title":"Meaningful area",
  "description":"Focused scope"}
],"warnings":[]}

Return needs_attention and warnings instead of guessing when sample metadata
is insufficient for plausible folder names. Do not use source paths as
folder names or assume fixed military/technical taxonomies.
