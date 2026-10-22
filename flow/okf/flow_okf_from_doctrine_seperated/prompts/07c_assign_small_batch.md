Assign knowledge items from ONE SMALL batch to existing doctrine topics.

Doctrine folder: {{var:folder}}
Canonical topic registry: {{var:topics}}
Current batch: {{var:batch}}

This is an ID-only classification task. Each object in batch.items is a
routed fragment, containing document_id and knowledge_items. For EACH
knowledge item, form item_id = document_id + ":" + knowledge_item.id.
E.g. document_id=doc1 and knowledge_item.id=c001:rule001 results in
doc1:c001:rule001. Emit exactly one assignment per knowledge item using an
existing topics.topics[].id. Never invent a topic ID or copy evidence,
descriptions, or candidate_concepts into the output. Ignore candidate_concepts
for item count. Do not browse, read files, or use any tools.
Use only the current batch and the supplied topic registry. The runner
checks for every missing, duplicate and unknown assignment. Do not silently
omit difficult items; choose the best supported topic and note ambiguity
briefly in warnings. Keep output minimal, no explanations or extra keys.

Return one compact JSON object only:
{"batch_id":"same batch.id","assignments":[{"item_id":"doc1:c001:rule001","topic_id":"t001"}],"warnings":[]}
