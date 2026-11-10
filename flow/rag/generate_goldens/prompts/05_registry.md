# Create final bounded registry of cross-document RAG question candidates

Candidate summaries from preceding reductions: {{var:summaries}}

The groups are compact topic relationships discovered across multiple
document batches. Deduplicate overlaps without losing distinct cross-document
connections; do not invent or modify original evidence ranges. No tool calls.
Only candidates that have at least two DISTINCT source paths are eligible
for goldens. Unpaired candidates are not used as questions but their omission
from the goldens is not evidence they were unrelated in the original corpus.

Output at most 60 independent, meaningful pairs or triples. Choose diverse
topics and relationships; favor questions that actually require BOTH original
documents to provide an answer. No speculative extrapolation.
For each group return deterministic-looking unique slug ID g0001, g0002, ...
for stable checkpoint files; ID must match g[0-9]{4}. Sources must contain
original path, inclusive start_line/end_line and claim from the input.
Max 3 source references per group, 600 characters in total for rationale.
If incomplete coverage, status=needs_attention and report warnings; output
groups may still be processed but are not exhaustive.

JSON:
{"status":"ok|needs_attention",
 "groups":[
   {"id":"g0001","topic":"name","relation":"complement|dependency|constraint|conflict",
    "sources":[
     {"path":"original path.md","start_line":1,"end_line":10,
      "claim":"supported by that range"},
     {"path":"other path.md","start_line":5,"end_line":20,
      "claim":"necessary complementary fact"}
    ],
    "rationale":"why both sources may be needed"}
 ],
 "warnings":[]}
