Assess exactly one requested additional OKF concept against the current generated OKF.

Source root: `{{var:source_root}}`
Target OKF root: `{{var:okf_root}}`
Requested concept:
{{var:requested_concept}}

Rules:
- Do not modify files.
- First inspect the current OKF indexes/concepts relevant to the request.
- Inspect source code only when necessary to determine whether the requested knowledge actually exists and where it belongs.
- Treat `source_root` as the complete source scope. Do not list, read, search or otherwise inspect source files outside it.
- Choose exactly one action:
  - `covered`: the requested knowledge is already adequately represented; no change is needed.
  - `not_applicable`: the requested capability/configuration does not exist in the source or is not meaningful for this application.
  - `extend`: the knowledge exists and belongs in an existing concept; name that concept in `target_path`.
  - `create`: the knowledge exists and deserves its own concept; provide a new safe `target_path` below the OKF root.
- Prefer `extend` when the request is a natural subsection of an existing concept. Prefer `create` when it is independently discoverable knowledge or would make an existing concept unfocused.
- For `create`, provide `type`, `title`, `description`, `tags` and `source_hints` suitable for the new concept.
- For `extend`, provide source hints and a concise description of the material that must be added.
- Never choose `covered` merely because a similar filename exists; verify the actual content.

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
  "source_hints":["workspace-relative/path"],
  "reason":"string"
}

Return valid JSON only.
