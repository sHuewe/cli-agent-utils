Evaluate whether exactly one existing OKF concept would be more useful if it were split into several independently retrievable concepts.

Target OKF root: `{{var:okf_root}}`
Concept path: `{{var:concept_path}}`

Rules:
- Do not inspect original source code or manuals and do not modify files.
- If `concept_path` is empty, missing, not a normal Markdown concept, or points to `index.md`/`log.md`, return `skip`.
- Read exactly the target concept and, when needed to avoid filename collisions, list only its direct parent folder.
- Evaluate semantic retrieval granularity, not formatting preferences.
- Prefer a split when two or more substantial parts would commonly be retrieved independently, for example:
  - distinct user questions or independently useful capabilities;
  - different lifecycle concerns such as installation, configuration, operation and troubleshooting;
  - multiple largely independent configuration families;
  - sections that are useful and understandable without most of the rest of the concept;
  - a title that has become so broad that it no longer describes one coherent knowledge topic.
- Length is only a signal. Roughly 30-80 Markdown lines is often a useful size; around 100 lines or more should trigger a deliberate granularity check, but a cohesive 100+ line concept may remain intact.
- Do not split merely to satisfy a line target, and never create artificial `part-1` / `part-2` documents.
- Choose `needs_attention` instead of `split` when the concept appears too broad but a safe semantic split cannot be derived from the existing documented content alone.
- A split must be possible without new factual research. It reorganizes only knowledge already present in the concept.
- Preserve the current concept path as a concise overview/entry point so inbound links remain valid.
- For `split`, propose between 2 and 6 focused part concepts. Every part must live directly in the same semantic folder as the original.
- Proposed paths must be lowercase kebab-case Markdown filenames, must not already exist, and must not be `index.md` or `log.md`.
- Every substantial piece of factual/behavioral/configuration knowledge in the original must be assigned to either the overview or at least one proposed part.
- References already present in the original should be retained and distributed to the relevant part(s); do not invent references.

Return exactly one JSON object:
{
  "concept_path":"relative/concept.md",
  "line_count":0,
  "action":"keep|split|needs_attention|skip",
  "reason":"string",
  "overview":{
    "purpose":"what remains at the existing path after a split",
    "content_scope":["knowledge that should remain in the overview"]
  },
  "parts":[
    {
      "path":"same-folder/focused-concept.md",
      "title":"string",
      "type":"string",
      "description":"string",
      "scope":["specific knowledge moved into this concept"]
    }
  ],
  "warnings":["string"]
}

Return valid JSON only.
