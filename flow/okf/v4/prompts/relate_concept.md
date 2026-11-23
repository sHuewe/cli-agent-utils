# Select justified semantic links for one verified OKF concept

Task: {{var:concept}}

The source title, summary and tags are grounded in the final reviewed
Phase-B inventory. Candidate concepts (max eight) are bounded and enumerated
in concept.candidates. Use ONLY these source-grounded descriptions.

Return JSON:
{"source_id":"<exact concept.id>","related_ids":[]}

Select 0–5 DIFFERENT candidate IDs only where there is a substantive,
specific semantic relationship. Prefer cross-doctrine connections if equally
meaningful. Do not add generic associations merely because two concepts
share a label. Never propose self-links, a fabricated ID, or a duplicate.

This step must NOT modify Markdown or write files. C's deterministic Python
publisher resolves the IDs to current paths and writes links. JSON only.
