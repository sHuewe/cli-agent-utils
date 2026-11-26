# Summarize ONE existing OKF concept for the concept inventory

Concept to inspect (trusted inventory metadata): {{var:concept}}

Use the read-only `os__read_file` tool to read the complete Markdown file
at `concept.path`. If the file is not readable or its content contradicts
the expected concept identity, do not guess; fail rather than inventing facts.

Return exactly one JSON object with:
- `id`: exactly the given `concept.id` (unchanged).
- `summary`: a concise but informative English summary (60–350 characters),
  based **only** on the actual Markdown content, conveying the concept's
  meaning, boundaries and main statements; no filler, invented claims, or
  generic phrasing based on filenames.
- `tags`: 1–5 concise English thematic labels (2–80 characters each),
  reflecting the actual content. Choose labels that can group related
  concepts across different doctrines. Avoid overly generic labels.

No file writes, index creation, or source modifications. No Markdown fences,
no commentary outside the JSON. Do not use information from other concepts
unless explicitly contained in the read concept itself.
