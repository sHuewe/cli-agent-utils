Build a GLOBAL, COMPACT topic registry for one doctrine folder.

Folder: {{var:folder}}
Batch topic suggestions: {{var:suggestions}}

Merge synonymous or overlapping topics across ALL batches, even if they originate
from different doctrines. Keep distinct concepts where their purpose or behavior differs.
Create stable, unique folder-scoped IDs t001, t002..., concise titles and single
destination filenames directly under folder.path. Keep paths unique and kebab-case.
Choose a meaningful type for each concept, short descriptions and tags.
Keep the registry reasonably small: no evidence, full source records, coverage
items, or documents. Do not read files or use tools.
The next stage assigns every source knowledge item to exactly one registry topic.
Do not drop a suggested topic without considering its meaning.

Return JSON only:
{"folder":{"id":"folder-id","path":"folder-path","title":"folder title"},
"topics":[{"id":"t001","path":"folder-path/semantic-topic.md","type":"concept",
"title":"Semantic topic","description":"one sentence","tags":["topic"]}]}
