# Consolidate a small, fixed group of concept candidates

Authoritative batch: {{var:batch}}

Return JSON only with shape:
{"status":"ok","groups":[{"member_ids":["candidate-a","candidate-b"],"title":"Coherent final concept","description":"Scope including both source candidates, qualifications and exceptions","folder_id":"procedures"}]}

Every candidate in batch.candidates MUST occur exactly once in one member_ids
array. Merge only genuinely equivalent or closely related topics that can form
a coherent concept, not unrelated rules. Single-member groups are correct
when merging would lose meaning. Use only candidate IDs supplied in this
batch. Preserve all meaning in descriptions, including exceptions and
conditions. Choose folder_id from batch.folders (or null if empty). Do not
invent IDs, paths, extra candidates or source ranges. The runner validates
complete and exclusive coverage. Do not use tools or read other files.
