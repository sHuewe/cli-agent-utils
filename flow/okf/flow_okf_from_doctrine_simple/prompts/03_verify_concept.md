# Verify ONE created concept against its source

Original doctrine: {{var:source}}
Root: {{var:okf_root}}
Planned concept: {{var:concept}}
Build outcome: {{var:build}}

BEFORE reading a concept file, enforce this build gate:
build.status MUST equal "created"; build.concept_id MUST equal concept.id;
build.path MUST equal concept.path. If any check fails, do NOT read an
existing (possibly stale) concept file, do NOT return ok/needs_repair;
return needs_attention with an explicit failed-build finding.
The build JSON is not proof that the file exists; still inspect the file
after the gate succeeds.

Read the actual Markdown concept and ONLY the original source intervals
listed under concept.evidence_ranges, using BOTH start_line and end_line.
Do not read unrelated source files or write anything.
Verify: file exists at the planned path; frontmatter includes type and
is well-formed; information and normative force match source; relevant
conditions/exceptions from the evidence are not silently omitted;
sources are cited accurately; links stay within the OKF root.
A concept may cover multiple sections coherently; do not require a
one-to-one mapping between sentences and fabricated atomic item IDs.
A planning reference pointing to unrelated source text is a SOURCE PLAN
problem, not a concept-writing problem: report it as needs_attention
without instructing a writer to change immutable planning metadata.
Categorize issues precisely. Do not flag an issue already correctly
handled in the actual Markdown file. No fabricated findings.

Use status=needs_repair ONLY when an error in the generated concept can
be fixed by editing that concept alone. Otherwise return needs_attention
for unfixable plan/source problems, or ok for a satisfactory concept.
Return JSON only:
{"status":"ok|needs_repair|needs_attention","concept_id":"planned id",
"path":"planned concept path",
"findings":[{"kind":"concept_error|source_plan_error","severity":"error|warning",
"problem":"specific issue","required_change":"only if actionable"}],
"warnings":[]}
