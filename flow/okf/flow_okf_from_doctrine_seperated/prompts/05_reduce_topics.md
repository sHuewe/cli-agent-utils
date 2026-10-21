Reduce overlapping local topic suggestions from ONE bounded batch.
Input: {{var:batch}}
Do not access files. Require each batch item to be a successful suggestion
object with a topics list; report malformed or missing entries as warnings.
Merge near-duplicates; keep distinct subject matter separate. Return compact
candidate titles and one-sentence descriptions. Never include evidence, full
text or item arrays. Return JSON only:
{"status":"ok|needs_attention","topics":[{"name":"semantic topic","description":"one sentence"}],"warnings":[]}
