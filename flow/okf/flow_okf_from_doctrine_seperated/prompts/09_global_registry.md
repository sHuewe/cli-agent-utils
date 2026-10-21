Consolidate CROSS-DOCTRINE themes into a compact registry.
Reduced candidate summaries: {{var:reduced}}
OKF root: {{var:okf_root}}

Read the existing themes/index.md and existing theme files using ONLY small
leading ranges if they exist, to preserve existing IDs and meanings. Do not
scan entire repository. Do not create duplicate themes or rename old IDs.
A theme must be meaningful across at least two separate doctrines; candidate
co-occurrence in one batch alone is insufficient. If that relationship cannot
be validated from compact evidence, leave it provisional and exclude it.
Return stable kebab-case IDs and concise descriptions, with unique paths under
themen/. Preserve existing valid themes so incremental doctrine additions do
not silently drop prior theme IDs. If there are too many summaries to reason
about reliably, return needs_attention rather than truncating. No writes.

JSON only:
{"status":"ok|needs_attention","themes":[{"id":"stable-kebab-case","path":"themen/stable-kebab-case.md","title":"title","description":"short scope"}],"warnings":[]}
