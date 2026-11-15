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
Never impose a smaller output group-count cap than the groups/concepts
in batch.items[] can require. Input byte size is bounded by the runner;
the output MUST retain every distinct unmerged topic and singleton. The
group count may equal the number of distinct input topics. Do not create
more groups than there are distinct input concepts/groups. If some groups
cannot be merged, preserve them as separate entries. A needs_attention
warning is NOT a substitute for retaining those source groups.

Keep at most 12 members per group, each description <=180 characters.
If a group requires more members, keep separate supported groups and
mark needs_attention; never truncate members or knowledge coverage.
Preserve all warnings and status information across stages.
