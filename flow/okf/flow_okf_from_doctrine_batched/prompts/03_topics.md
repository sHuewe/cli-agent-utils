# Plan bounded local concepts for ONE section

Source with stable slug: {{var:source}}
Section ID: {{var:section_id}}
Route ARRAY (one entry): {{var:route}}

Do not use tools. Plan 1-8 coherent topics to hold ALL knowledge_items
in this route. Topics can combine related claims but no claim may be
discarded. For a long heterogeneous section, use several small topics.
Names and filenames must be stable, lowercase safe kebab-case. Do not
reuse concept filenames or IDs across sections: prefix topic IDs and
filenames with the section ID. No thematic subfolders: generated files
are directly in doctrines/<source.slug>/, maintaining the separated-OKF
flat-module variant. Use a short, descriptive filename suffix after prefix.
If route has no knowledge items, topics may be []. If >8 topics are needed,
use eight coherent groups and report ambiguity in warnings.

Return a JSON OBJECT in the exact group_items plan schema:
{"folder":{"id":"<source.slug>","path":"doctrines/<source.slug>",
 "title":"Source document filename"},
 "folders":[],
 "topics":[
  {"id":"s001t001","path":"doctrines/<source.slug>/s001-example-topic.md",
   "type":"concept","title":"Meaningful topic title",
   "description":"short scope","tags":[]}
 ],
 "warnings":[]}
NEVER generate path traversal, Windows reserved file names or root-level
concepts. All topic IDs must match ^[a-z][a-z0-9_-]*$ and be unique.
Use directt001 for direct sections.

