# Write ONE cross-doctrine navigation theme

Theme: {{var:theme}}
OKF root: {{var:okf_root}}

Write ONLY <okf_root>/<theme.path>, creating the themen/ directory if
necessary. This is a navigation page connecting previously generated
concepts, NOT a new doctrine or a claim of source-backed synthesis.
Read at most the first 30 lines of each linked concept to verify it
actually exists and has the expected title. If any linked file is
missing, return needs_attention without fabricating a replacement.
The generated theme file is a NORMAL OKF concept, not index.md.
Start at byte zero with YAML frontmatter delimited by --- containing
at least non-empty type: concept, title, description, tags and
status: stable. Do not add verified metadata. Read back the first
30 lines of the generated theme file to confirm valid frontmatter,
type and expected path; return needs_attention on a mismatch, never ok.
Use relative links from themen/ to the concept paths and explain the
shared scope briefly, distinguishing each doctrine's contribution.
The page MUST include exactly one Markdown link to EVERY concept in
`theme.concept_paths`, and no links to unplanned concept files.
After writing, read back the COMPLETE generated theme page (using
bounded successive line ranges if necessary, not just its first 30
lines). Resolve each Markdown link destination relative to `themen/`,
normalize the resulting workspace-relative OKF path, and compare the
set AND count against the full `theme.concept_paths` list. Reject
missing, extra or duplicate concept links, and return needs_attention
if any planned member is absent. Also check that the resulting links
still span at least two distinct doctrine module folders. The reported
`linked_concept_paths` must list exactly those verified planned paths;
never claim success based solely on the file existing or on its header.
Do not edit concept tags or other files. No external claims.
Return JSON only:
{"status":"ok|needs_attention","path":"themen/theme.md",
"linked_concept_paths":["doctrines/a/topic.md"],"warnings":[]}
