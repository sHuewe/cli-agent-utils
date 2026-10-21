Update ONLY the YAML frontmatter tags of ONE source doctrine concept.
Assignment: {{var:assignment}}
OKF root: {{var:okf_root}}

Read the entire target first. Require its path to be an actual normal .md
concept UNDER okf_root/doctrines/, with correct YAML frontmatter; do not
follow arbitrary paths. Preserve the Markdown body byte-for-byte and preserve
other YAML metadata and non-global tags. Global membership tags MUST use
"theme:<theme-id>" exactly. Replace the PREVIOUS "theme:" tags with precisely
assignment.theme_ids. Preserve unrelated tags, including source-specific tags.
No fabricated topic IDs, prose edits or updates to other files.
If anything cannot be done without changing non-tag content return
needs_attention without writing. On rerun, no-op if tags already match.

Return JSON only:
{"status":"ok|needs_attention","path":"same concept path","theme_ids":["assigned-id"],"changed":false,"warnings":[]}
