Assess exactly one requested additional OKF concept against the current manual-derived OKF.

Configured manual path: `{{var:manual_path}}`
Target OKF root: `{{var:okf_root}}`
Requested concept:
{{var:requested_concept}}

Existing concept map:
{{var:concept_map}}

Known manuals:
{{var:manuals}}

Rules:
- Do not modify files.
- First inspect the current OKF indexes/concepts relevant to the request.
- Prefer existing evidence ranges from the concept map whenever they are relevant.
- If the request is not covered by the existing concept map, you may use `search_text` within the configured manual path to locate likely evidence, then inspect only bounded line ranges around relevant hits.
- For manual files, NEVER call `read_file` without both `start_line` and `end_line`. Never fully read or sequentially rescan a manual in this late step.
- Do not inspect source material outside `manual_path`.
- Choose exactly one action:
  - `covered`: the requested knowledge is already adequately represented; no change is needed.
  - `not_applicable`: the requested knowledge is not supported by the manuals or is not meaningful for this documentation set.
  - `extend`: the knowledge exists and belongs in an existing concept; name that concept in `target_path`.
  - `create`: the knowledge exists and deserves its own concept; provide a new safe `target_path` below the OKF root.
- Prefer `extend` when the request is a natural subsection of an existing concept. Prefer `create` when it is independently discoverable knowledge or would make an existing concept unfocused.
- For `extend` or `create`, return concrete bounded `evidence_ranges` that support the change.
- For `create`, also provide `type`, `title`, `description`, and `tags`.
- Never choose `covered` merely because a similar filename exists; verify the actual concept content.

Return exactly one JSON object:
{
  "request": {
    "id":"string",
    "name":"string",
    "description":"string"
  },
  "action":"covered|not_applicable|extend|create",
  "target_path":"relative/path.md or empty string",
  "type":"string or empty string",
  "title":"string or empty string",
  "description":"string",
  "tags":["string"],
  "evidence_ranges":[
    {"manual":"workspace-relative/path","start_line":1,"end_line":120,"reason":"string"}
  ],
  "reason":"string"
}

Return valid JSON only.
