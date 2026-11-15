# Normalize one section scan into the existing group_items route contract

Source: {{var:source}}
Section ID: {{var:section_id}}
Scan JSON: {{var:scan}}

No tools. Output a JSON ARRAY containing exactly ONE route object:
[
 {"document_id":"<source.slug>","chunk_id":"<section_id>",
  "folder_id":"<source.slug>",
  "candidate_concepts":[
   {"id":"<section_id>:topic001","name":"name","description":"description",
    "evidence_ranges":[]}
  ],
  "knowledge_items":[
   {"id":"<section_id>:rule001","kind":"fact","name":"name",
    "description":"unchanged assertion","normative":false,
    "evidence_ranges":[]}
  ],
  "warnings":[]
]
Copy ALL scanned knowledge_items, facts, normative flags and evidence ranges
without reinterpreting or omitting anything. Prefix ONLY each local ID
with the section ID. Preserve source paths and evidence literally.
Input status=needs_attention MUST be recorded in warnings with its reason.
A missing or malformed input must not be represented as complete.
Do not transform a candidate into a knowledge item or vice versa.

