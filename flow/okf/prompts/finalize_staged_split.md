Summarize the completed staged split steps; do not read files or use tools.

Original concept path: {{var:concept_path}}
Assessment: {{var:assessment}}
Part creation results:
{{var:parts}}
Original overview result:
{{var:overview}}
Folder index result:
{{var:index}}

Rules:
- If assessment.action is keep or skip, require no error in overview/index results, then return unchanged with new_paths=[], changed_paths=[].
- If assessment.action is needs_attention, return needs_attention.
- For split, require 2-6 unique assessed parts and EXACTLY one result for each planned part, each with status created or already_present, and overview.status and index.status each updated or already_present.
- If ANY result is missing, malformed, needs_attention, has an unexpected path, duplicate path or unknown status, return needs_attention. Do NOT infer success from the original assessment alone.
- For successful split, return status split, overview_path exactly the original concept path, and new_paths containing exactly the planned part paths. Combine changed_paths only from actual stage writes, without duplicates. Preserve warnings from all stages; treat blocking problems as needs_attention.
- Do NOT copy the full original concept, folder index or source evidence into this compact report.

Return valid JSON only:
{"status":"unchanged|split|needs_attention","overview_path":"relative/concept.md","new_paths":["relative/part.md"],"changed_paths":["relative/path.md"],"warnings":["string"]}
