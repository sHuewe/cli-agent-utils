Summarize independently completed chunk profiles into one compact document profile.

Document partition and authoritative chunk list:
{{var:partition}}

Completed chunk profiles:
{{var:profiles}}

Rules:
- Do not use tools or inspect source text.
- Copy partition.chunks EXACTLY into chunks. This list is required by later chunk routing.
- All partition chunks must have exactly one completed chunk profile. On mismatch, explicitly warn; do not assert complete coverage.
- Merge themes and aggregate category counts from chunk profiles.
- Do not include original chunk inventories or evidence arrays.
- Retain document identity and report any warnings.

Return exactly one JSON object:
{
 "document_id":"string","document_name":"string","document_path":"workspace-relative/path",
 "summary":"one sentence","themes":["short theme"],
 "counts":{"candidate_concepts":0,"external_functions":0,"configuration_options":0,"knowledge_items":0},
 "chunks":[{"id":"c001","document_id":"m001","document_path":"workspace-relative/path","start_line":1,"end_line":350}],
 "warnings":["string"]
}
Return valid JSON only.
