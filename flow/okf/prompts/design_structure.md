Design the semantic top-level directory structure for the OKF **before** any concept paths are planned.

Target OKF root: `{{var:okf_root}}`
Source kind: {{var:source_kind}}

Project:
{{var:project}}

Compact analysis profiles:
{{var:analysis_profiles}}

Rules:
- Use only the compact profiles supplied here. Do not perform a broad source/manual scan in this step.
- Return `okf_root` exactly as the configured target string shown above. Do not rename or normalize it.
- Decide which semantic knowledge areas are useful for this specific project. Folder names are not predetermined by the flow.
- Examples such as domain, application-context, interfaces, configuration, operations or security are only examples.
- At least one top-level folder is mandatory. For a non-trivial system prefer several focused folders (commonly 2-8), but do not create meaningless empty categories.
- Do not use a source package, module name or manual filename merely because it is available. A technical component name is acceptable only when it is genuinely the semantic category a reader should navigate by.
- Each folder `path` is exactly one lowercase kebab-case path segment matching `[a-z0-9]+(?:-[a-z0-9]+)*`.
- Every normal concept created later must be placed directly below exactly one declared folder. No normal concept may be placed directly below the OKF root.
- `routing_guidance` must be concrete enough that independent downstream planners can consistently choose a folder.
- Keep the output compact. This is a routing/navigation plan, not a detailed concept plan.

Return exactly one JSON object:
{
  "okf_root":"exact configured target",
  "folders":[
    {"id":"domain","path":"domain","title":"Domain","description":"short reader-oriented purpose","routing_guidance":["what belongs here","what should go elsewhere"]}
  ],
  "warnings":["string"]
}

Return valid JSON only.
