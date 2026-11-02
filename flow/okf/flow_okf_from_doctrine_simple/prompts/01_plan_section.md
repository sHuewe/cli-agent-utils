# Design concepts from one bounded doctrine section

Source inventory descriptor: {{var:source}}
Authoritative section task: {{var:task}}

Create a concise list of **concept candidates for this single section**. Do
not attempt to design the entire document's navigation or inspect other
section analyses.

If task.direct=true, read the complete short source document
task.source_path with bounded os__read_file requests. Otherwise use ONLY
task.analysis, including its topics and warnings. Do not use file tools
for non-direct tasks. Never invent information or source references.

Each concept must have a stable lowercase kebab-case topic_key describing
its semantics, not its location or section number. Identical conceptual
topics across separate sections MUST use the same topic_key so they can
be joined by the runner. Prefer established domain terminology and
specific keys; distinguish genuinely different concepts. Aim for a
small number of substantive, self-contained concepts, not one per
paragraph or atomic rule. Preserve definitions, important conditions,
exceptions and procedures in descriptions.

The runner assigns the definitive concept id and path from topic_key.
You must not invent paths or folders. Every local outline must be
complete for its section, without pretending to cover other sections.

Output compact valid JSON only:
{
  "status": "ok",
  "section_id": "s001",
  "concepts": [
    {
      "topic_key": "approval-procedure",
      "title": "Approval procedure",
      "description": "Specific coherent concept and its qualifications",
      "tags": ["approval"]
    }
  ],
  "warnings": []
}

Set section_id to task.id (including "direct" for a short document).
If the source analysis is incomplete, use status=needs_attention and
explain the missing evidence. Never guess or silently drop a section.
