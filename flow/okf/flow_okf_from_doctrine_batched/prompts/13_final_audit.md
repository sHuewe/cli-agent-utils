# Final status of ONE registry shard and the global root navigation

Shard ID: {{var:batch_id}}
Audited registry/theme results: {{var:shard_report}}
Root index writer result: {{var:root_index}}

No tools. This is a status-only step, not a source or concept review.
Status may be ok ONLY when shard_report.status == ok,
shard_report.batch_id exactly matches this shard ID, and
root_index.status == ok. Missing, invalid, or needs_attention upstream
statuses MUST yield needs_attention. Preserve every unresolved warning
from the shard report and root index. Do not infer that a successful root
index repaired any previous source/registry/theme failure.

Return compact JSON:
{"status":"ok|needs_attention","batch_id":"exact shard ID",
 "root_status":"ok|needs_attention","warnings":[]}
