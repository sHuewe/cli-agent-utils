Plan doctrine-local concepts and optionally ONE semantic subfolder level.

Doctrine root: {{var:folder}}
Reduced topic suggestions: {{var:suggestions}}

Do not read files. Merge synonymous topics while retaining distinct knowledge.
Use stable and unique topic IDs t001..., short descriptions and unique file
names. For fewer than 8 coherent topics, keep folders=[] and put all topic
files directly under folder.path. For larger documents, choose between 2 and
8 (maximum 12) semantic subfolders based on shared subject matter; put ALL
topics under these folders. Avoid one folder per concept, mirroring chapter
headings and generic catchalls. No source changes or global theme tags.
Each folder ID must be a unique, lowercase kebab-case slug (no Windows device
names con, nul, aux, prn, com1..9, lpt1..9), and each declared folder path
must be folder.path + "/" + folder.id. Exactly ONE subfolder level.
Concept paths must be folder.path + "/" + filename for flat mode, or
declared-subfolder.path + "/" + filename in hierarchical mode.
Do not mix flat and hierarchical topics.

Return valid JSON only:
{"folder":{"id":"existing folder id","path":"doctrines/slug","title":"existing folder title"},
"folders":[{"id":"access-rights","path":"doctrines/slug/access-rights","title":"Access rights"}],
"topics":[{"id":"t001","path":"doctrines/slug/access-rights/topic.md","type":"concept","title":"title","description":"one sentence","tags":[]}],
"warnings":[]}

The deterministic group_items operation verifies all topic paths and IDs.
For flat mode, folders=[] and topic files live directly under folder.path.
