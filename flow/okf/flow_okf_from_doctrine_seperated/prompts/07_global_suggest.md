Find potential CROSS-DOCTRINE themes from one bounded batch of module manifests:
{{var:batch}}

Use only compact concept descriptions and tags provided. No file tools.
Suggest focused provisional themes even if this batch contains only one doctrine:
relevance across different batches will be decided by the global registry.
Do not discard a strong local candidate merely because its related doctrine
belongs to another batch. Avoid generic
topics such as "technology" or "system". Suggest at most 12 strong proposals,
each with unique short name, focused scope and supporting concept paths. Do not
invent links or source content; no full Concept copies.

Return JSON only:
{"status":"ok|needs_attention","candidates":[{"name":"topic name","description":"one sentence","concept_paths":["workspace-relative concept path"]}],"warnings":[]}
