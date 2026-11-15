# Assign every coverage item to exactly one planned local topic

Source: {{var:source}}
Section ID: {{var:section_id}}
Route: {{var:route}}
Topic plan: {{var:topics}}

No tools. Route is an array with one object. For EACH knowledge item, the
globally qualified item_id must be EXACT:
<source.slug>:<section_id>:<original-local-item-id>
For example document_id=doc, route id=s001:rule001 => doc:s001:rule001.
Choose exactly ONE existing topic ID for each item. Copy no descriptions,
evidence, or source text. Return a JSON ARRAY with exactly ONE object:
[
 {"batch_id":"<section_id>",
  "assignments":[{"item_id":"doc:s001:rule001","topic_id":"s001t001"}],
  "warnings":[]}
]
No missing/duplicate/unknown item IDs; group_items deterministically checks
the full assignment. If no items, assignments=[].

