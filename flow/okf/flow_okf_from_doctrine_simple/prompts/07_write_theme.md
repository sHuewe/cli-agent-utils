# Write ONE cross-doctrine navigation theme

Theme: {{var:theme}}
OKF root: {{var:okf_root}}

Write ONLY <okf_root>/<theme.path>, creating the themen/ directory if
necessary. This is a navigation page connecting previously generated
concepts, NOT a new doctrine or a claim of source-backed synthesis.
Read at most the first 30 lines of each linked concept to verify it
actually exists and has the expected title. If any linked file is
missing, return needs_attention without fabricating a replacement.
Use relative links from themen/ to the concept paths and explain the
shared scope briefly, distinguishing each doctrine's contribution.
Do not edit concept tags or other files. No external claims.
Return JSON only:
{"status":"ok|needs_attention","path":"themen/theme.md",
"linked_concept_paths":["doctrines/a/topic.md"],"warnings":[]}
