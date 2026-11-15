# Semantic merge of ONE SMALL BATCH of candidate concepts

Bounded batch containing up to six related candidate topics: {{var:batch}}

No tools. Only merge genuinely identical/complementary local concepts that
can be written as ONE coherent OKF concept. Preserve distinctions of scope,
obligation, permissions, exceptions and qualifiers. A concept from ANY
document section may join another when semantically appropriate.
Do not merge unrelated concepts merely to reduce file count.

Return EXACTLY ONE group membership for EACH batch.candidates[].id.
Group.member_ids must partition the candidate IDs: no missing, duplicate or
invented IDs. Preserve singleton groups when no meaningful relation exists.
No unsupported facts. The runner deterministically checks completeness.

If batch.folders is empty, folder_id must be null.
Otherwise folder_id MUST be an existing batch.folders[].id. Choose the most
appropriate declared folder for each group. No new folders or concepts.
Use a short meaningful title and 1-sentence description per group.

JSON only:
{"status":"ok","groups":[
 {"member_ids":["s001-t001","s004-t002"],
  "title":"Coherent combined topic","description":"Short scope",
  "folder_id":null}
]}

If cannot make an evidence-backed decision, do not omit candidates:
preserve them as singleton groups or return needs_attention (which fails
closed rather than falsely publishing incomplete knowledge).
