Update the direct semantic folder index for ONE already-created concept split, without touching any concept body.

Target OKF root: {{var:okf_root}}
Original concept path: {{var:concept_path}}
Assessment: {{var:assessment}}
Pre-split snapshot status: {{var:snapshot_status}}
Original folder index path: {{var:index_path}}
Complete original index snapshot:
{{var:index_content}}
Per-part creation results:
{{var:parts}}
Overview update result:
{{var:overview}}

Rules:
- When assessment.action is keep or skip, return unchanged without reading or writing. For needs_attention, return needs_attention.
- For split, require a captured snapshot with nonempty complete original index_content and matching index_path to the original concept's parent folder index.md. Also require overview.status updated or already_present and one successful result (created or already_present) per planned part. Any failure, mismatch or omission means needs_attention with no write.
- Read the complete current index and list the normal direct .md concept files within the folder (exclude index.md and log.md). Read only index and filenames; do not load all concept bodies.
- If the index already links EVERY current direct concept exactly once, including the original overview and each new part, and all original link destinations remain present, do not modify it; return already_present. This handles existing completed splits and safe retries.
- Otherwise add only missing links to the new focused parts, preserving EVERY pre-existing destination and unrelated navigation entry from index_content. Never rebuild the index solely from the new split results.
- If current index differs from index_content, it may legitimately contain links from earlier completed splits in this folder. Do NOT overwrite or remove those links. Make a conservative additive edit only if you can prove ALL current links are preserved; otherwise report needs_attention. Do not assume the index is identical to the snapshot.
- Do not add duplicate concept links. All current direct concepts must be linked exactly once, and all previous non-concept links retained. Validate target existence, relative paths and no paths outside the OKF root.
- The ONLY file you may overwrite is the existing folder index. Never create/move/delete files. Read it entirely before writing and re-read after writing.
- Return needs_attention on any loss of original links, unverifiable index coverage, or tool failure.

Return valid JSON only:
{"status":"updated|already_present|unchanged|needs_attention","index_path":"relative/folder/index.md","changed_paths":["relative/folder/index.md"],"warnings":["string"]}
Return [] for changed_paths if no write.
