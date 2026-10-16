Partition exactly ONE source document into independent, bounded scan chunks.
Prefer Markdown chapter/section boundaries over rigid line counts without losing source lines.

Document:
{{var:document}}

Goal:
- Every existing source line must be covered by exactly ONE chunk, in source order.
- Chunk length TARGET: approximately 350 lines; HARD MAXIMUM: 450 source lines.
- A chunk is only an analysis unit, NOT a future OKF concept boundary.

Discovery (keep tool data and model context small):
1. Stay exclusively inside document.path; never read the whole document.
2. Call search_text(path=document.path, text="# ", max_results=200) to find potential Markdown ATX heading lines. The search is literal, NOT regex.
3. Use returned line numbers / line excerpts. A candidate must begin with 0-3 spaces, then 1-6 literal # characters followed by whitespace (Markdown ATX heading). Reject inline occurrences, comments, non-heading prose, and headings inside fenced code blocks when identifiable. Prefer meaningful chapter headings (#, ##) over fine-grained subsections (### to ######).
4. If search_text is truncated, those are only partial candidates; fallback numeric chunk boundaries remain valid for the rest of the file. If search_text fails (e.g. file too large to search), proceed with numeric fallback and report a warning. Do NOT compensate by fully reading the document.
5. To establish the source extent, probe ONLY a single line at each chunk start with read_file(document.path, start_line=N, end_line=N). Stop when the result is "(No lines in requested range)" (or "(Empty file)" for N=1). Never use a full-file read.

Chunk selection, repeated from start_line S=1:
- Choose the NEXT chunk start H from verified heading candidates in the inclusive window [S+200, S+450], if any exist.
- Prefer lower heading levels (# before ## before ### etc.) when the boundary remains useful; among similarly suitable headings choose the one closest to S+350. Do not create numerous tiny chunks just to match headings.
- If no eligible heading exists, choose NEXT start S+350 (numeric fallback).
- Emit chunk [S, H-1] and continue with S=H, but FIRST check that the candidate next start actually exists via a single-line probe. If it does not exist, emit one final chunk [S, S+449] instead and stop; its end_line is a safe upper bound beyond EOF.
- This ensures no gaps and no overlaps: each next chunk starts exactly one line after the previous end_line.
- If the chosen heading happens to lie at the source end, a short final chunk is acceptable; avoid it when obvious from a small bounded probe. Never create an empty trailing chunk.
- Every chunk must have 1 <= end_line-start_line+1 <= 450. Do not use variable overlaps or duplicate line coverage.
- If a document has no usable headings, the fallback is regular 350-line chunks, with a final range of at most 450 lines (possibly extending beyond EOF).
- IMPORTANT: Do not inspect or inventory the content here. Individual scan steps own full content extraction.

Output:
- IDs c001, c002, ... strictly follow source order and are unique within the document.
- Preserve document id, name and original workspace-relative path.
- Verify that consecutive chunks satisfy next.start_line = previous.end_line + 1, and the first begins at 1.
- If you could not read the document or could not establish continuous coverage, do not report a successful partial partition; return an explicit warning instead.
- Do not modify any files.

Return exactly one valid JSON object:
{
  "document":{"id":"m001","name":"string","path":"workspace-relative/path"},
  "chunks":[
    {"id":"c001","document_id":"m001","document_path":"workspace-relative/path","start_line":1,"end_line":350},
    {"id":"c002","document_id":"m001","document_path":"workspace-relative/path","start_line":351,"end_line":800}
  ],
  "warnings":["string"]
}

The example ranges only illustrate continuity; actual boundaries must be computed from the real document.
Return valid JSON only.
