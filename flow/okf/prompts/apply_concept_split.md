Apply one previously evaluated OKF concept split without adding new factual knowledge.

Target OKF root: `{{var:okf_root}}`
Concept path: `{{var:concept_path}}`

Assessment:
{{var:assessment}}

Pre-split concept snapshot:
{{var:snapshot}}

Rules:
- If the assessment action is `keep`, `needs_attention` or `skip`, do not modify files.
- Before ANY write for a split, require snapshot.status to be captured, a complete non-empty snapshot.content, and matching snapshot.concept_path. Otherwise return needs_attention without writing.
- Re-read the original concept and compare its FULL content to snapshot.content before writing. If it has changed since the snapshot, stop without modifying files and return needs_attention.
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
- Update the existing folder `index.md` so it links the overview and every new part exactly once.
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
