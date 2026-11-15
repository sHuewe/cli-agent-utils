# Convert ONE completed source scan to compact per-section topic metadata

Section task: {{var:task}}

No tools. Input task.analysis is the complete source scan verified by the
preceding deterministic section-task generator. Do NOT invent a topic or
discard a candidate. For EACH candidate_concepts entry return exactly one
concept with the SAME topic_key, a grounded title, a short description and
tags (zero or more semantic keywords). Preserve source scope, normative
exceptions and meaning. This step is solely document taxonomy preparation;
the original knowledge items remain unchanged in the scan checkpoint.
Do not include any original source text or knowledge item bodies.

Return JSON object with:
{"status":"ok","section_id":"<exact task.id>",
 "concepts":[{"topic_key":"s001-t001","title":"Descriptive title",
 "description":"Short supported scope","tags":["optional-keyword"]}],
 "warnings":[]}

Missing, duplicate or altered topic keys are unacceptable. If there are
no source candidates, output concepts=[] and status=ok. Do not impose
any smaller topic-count limit than the supplied section analysis.
