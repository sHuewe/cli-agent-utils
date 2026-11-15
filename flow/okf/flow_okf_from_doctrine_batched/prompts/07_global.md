# Bounded cross-document topic discovery and reduction

Stage: {{var:stage}}
One small batch: {{var:batch}}

No tools. Input is compact section manifests or previously reduced groups.
Compare semantic equivalences and meaningful complementary knowledge.
Group concepts that address the SAME focused topic across distinct
source_slugs. Preserve each member concept path and source_slug, never invent
a member. Preserve singleton candidates, since a later reduction may find
other documents. Keep genuinely distinct topics separate. Do not invent
cross-doctrine commonality from word overlap alone.

Always propagate needs_attention and warnings monotonically from all input
objects. Never report completeness if any upstream source was incomplete.
An individual group has a bounded set of member paths; do not truncate:
when too large, keep separate groups and report needs_attention.

Output JSON OBJECT:
{"status":"ok|needs_attention",
 "groups":[
  {"topic":"focused semantic name","description":"one sentence",
   "members":[{"path":"doctrines/<slug>/concept.md",
               "source_slug":"<slug>"}]}
 ],
 "warnings":[]}
At most 20 groups per batch, at most 12 members per group, each
description <=180 characters. Preserve ALL singletons and warnings
within the given limits. Never silently drop excess input.

