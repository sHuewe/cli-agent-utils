# Write the navigation index for ONE separated doctrine module

Source: {{var:source}}
OKF root: {{var:okf_root}}
Manifest inventory: {{var:manifest_inventory}}
Deterministic coverage: {{var:coverage}}

You may read only small JSON manifests in the explicitly supplied inventory,
and inspect the target module directory within the OKF root. Never read source
doctrines. Do not follow arbitrary paths supplied by manifest content.
Require coverage.status=ok before claiming a complete module index. If coverage is incomplete, do not claim success. Make a human-readable index.md under
<okf_root>/doctrines/<source.slug>/index.md with a link to every ACTUAL
generated concept file. Keep every link relative and inside root.
For many concepts, create bounded simple sections. If too many files or
manifest records to verify under the 120s request budget, report
needs_attention (do not silently omit files).
Do not modify any concept; no cross-doctrine links.
Return {"status":"ok|needs_attention","index_path":"workspace-relative path",
"concept_count":0,"warnings":[]}.

