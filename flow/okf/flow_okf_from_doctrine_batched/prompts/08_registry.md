# Construct ONE lossless, small global OKF registry shard

One bounded batch: {{var:batch}}

No tools. Input batch.items[] contains a few source-preserving topic
proposal fragments, each with groups[]. Each source group is identified
by its EXACT 1-based position within this batch:
i0001-g0001 = batch.items[0].groups[0]
i0002-g0003 = batch.items[1].groups[2], etc.

For every group whose members span at least TWO distinct source_slug values,
include it in exactly ONE theme, preserving ALL its concept memberships.
You may merge synonymous eligible groups into one theme, listing ALL
contributing group_refs and the exact UNION of their members.
A group from only ONE source_slug is ineligible; explicitly report it
in excluded_group_refs. Do not exclude an eligible group or invent a member.
Theme IDs must be unique lower-case kebab-case, prefixed with batch.id:
e.g. b0001-requirements. Themes live only at themen/<id>.md.

NO arbitrary number-of-themes cap. Batching already limits the input to
at most five complete groups. Never silently drop or truncate a group.
Never invent a theme from a singleton. Preserve upstream incomplete
statuses/warnings monotonically: any input status needs_attention or
unresolved warnings means registry.status=needs_attention. Emit warnings
for missing or ambiguous evidence, but retain all group refs.

JSON only:
{"status":"ok|needs_attention",
 "themes":[
  {"id":"b0001-focused-topic","path":"themen/b0001-focused-topic.md",
   "title":"Focused topic","description":"Short grounded scope",
   "group_refs":["i0001-g0001"],
   "members":[
    {"path":"doctrines/doc-a/alpha.md","source_slug":"doc-a"},
    {"path":"doctrines/doc-b/beta.md","source_slug":"doc-b"}
   ]}
 ],
 "excluded_group_refs":["i0001-g0002"],
 "warnings":[]}

The runner independently rejects missing/duplicate/unknown group refs,
omitted or invented members, and exclusion of eligible groups.
