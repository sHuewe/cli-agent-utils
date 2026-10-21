Map EVERY routed doctrine knowledge item in ONE batch to the global folder topics.

Folder: {{var:folder}}
Global topic registry: {{var:topics}}
Batch: {{var:batch}}

Use only IDs from topics.topics, preserving all original source entries implicitly
without copying their descriptions or evidence. For every knowledge_items entry
in every route, construct its unique ID as document_id + ":" + knowledge_item.id
(e.g. m001:c001:rule001). Assign EXACTLY ONE existing topic ID to each unique
knowledge item. Do not omit descriptive items, normative items, exceptions, or
qualifiers. Do not invent items or topic IDs. Do not read files or use tools.
Any missing, duplicate, unknown or ambiguous assignment is an error: report it
as a warning, but still try to provide complete, unique assignments. The runner
independently rejects omissions and duplicate IDs.

Return JSON only:
{"batch_id":"b0001","assignments":[{"item_id":"m001:c001:rule001","topic_id":"t001"}],"warnings":[]}
