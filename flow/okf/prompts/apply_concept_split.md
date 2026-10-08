Apply one previously evaluated OKF concept split without adding new factual knowledge.

Target OKF root: `{{var:okf_root}}`
Concept path: `{{var:concept_path}}`

Assessment:
{{var:assessment}}

Pre-split concept snapshot:
{{var:snapshot}}

Rules:
- If the assessment action is `keep`, `needs_attention` or `skip`, do not modify files.
- Before ANY write for a split, require snapshot.status to be captured, complete non-empty snapshot.content and snapshot.index_content, and matching snapshot.concept_path and snapshot.index_path. Otherwise return needs_attention without writing.
- Re-read the original concept and the direct folder index, comparing their FULL contents to snapshot.content and snapshot.index_content before writing. If either has changed since the snapshot, stop without modifying files and return needs_attention.
- Use the complete snapshot as the authoritative pre-split baseline; the assessment scope is not a complete inventory of knowledge.
- For `split`, read the current target concept and its direct folder `index.md`.
- Before writing, confirm every proposed part path is still absent. If a proposed target already exists, do not overwrite it; return `needs_attention` without modifying files.
- Use only information already present in the original concept. Do not inspect source code/manuals and do not introduce new factual claims.
- Preserve the original path as a concise overview/entry point. It should explain the overall topic and link to all new focused concepts.
- Create every planned part directly in the same semantic folder.
- Redistribute the original content so no substantial documented behavior, configuration option, constraint, procedure or reference is lost.
- Avoid needless duplication: shared orientation may remain in the overview, while detailed material belongs in the focused part.
- Preserve valid YAML frontmatter. Every new part needs at least `type`, `title`, `description`, `tags`, and `status: stable`. Do not introduce `verified`.
- Preserve the original source/manual reference style and place existing references in the part(s) whose claims they support.
- Preserve useful links to other OKF concepts. Adjust relative links only when necessary.
- Update the existing folder `index.md` conservatively: preserve every pre-existing link destination and existing links to unrelated concepts from snapshot.index_content. Add only the links needed for the focused new concepts; never rebuild the index from just the split results.
- Before finishing, list the direct Markdown concepts in the folder (excluding `index.md` and `log.md`) and ensure the resulting index links EVERY concept exactly once, including unrelated existing concepts, the original overview, and the new concepts. Preserve pre-existing non-concept navigation links too.
- If preserving the original index links or full folder coverage is not possible, return `needs_attention` and describe the problem instead of reporting a successful split.
- Do not create directories, remove files, or write outside the OKF root.

Return exactly one JSON object:
{
  "status":"unchanged|split|needs_attention",
  "overview_path":"relative/concept.md",
  "new_paths":["relative/new-concept.md"],
  "changed_paths":["relative/path"],
  "warnings":["string"]
}

Return valid JSON only.
