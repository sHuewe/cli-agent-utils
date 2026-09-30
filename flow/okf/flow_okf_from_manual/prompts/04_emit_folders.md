Expose the already planned semantic folders for one routing child flow.

Semantic structure:
{{var:structure}}

Rules:
- Do not read or modify files.
- Return the folder objects unchanged and in the same order.
- Do not add, remove or rename folders.

Return exactly one JSON object:
{"folders":[{"id":"string","path":"string","title":"string","description":"string","routing_guidance":["string"]}]}

Return valid JSON only.
