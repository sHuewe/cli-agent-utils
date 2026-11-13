# Plan up to TWO distinct additional cross-document knowledge questions

Original source group: {{var:group}}
Original draft (may be rejected): {{var:draft}}
Original review: {{var:review}}

No tools or extra source reads. Based solely on this bounded source-group
metadata, identify up to TWO substantially different, independently
answerable facets that could require evidence from at least TWO DIFFERENT
source paths already present in the group. Each will be verified against the
original source text later. If there is insufficient evidence or the group
is unrelated, return an EMPTY variants array. Do not fabricate a relation
or target a fact already asked by the original draft.

A facet MUST elicit technical/operational knowledge, not where to find it.
NEVER plan questions like "which document describes", "where is this stated",
"in welchem Dokument", "welche Quelle/Datei" or "compare the documents".
Different paraphrases of one question are NOT distinct facets. Prefer at most
two well-founded questions over forcing a quota. Keep original exact source
ranges unchanged; no new documents.

Return JSON only:
{"group_id":"<exact group.id>","variants":[
 {"id":"v0001","focus":"specific independent knowledge target <=240 characters"},
 {"id":"v0002","focus":"another truly different knowledge target <=240 characters"}
]}
IDs are consecutive from v0001; 0, 1 or 2 variants are valid.
