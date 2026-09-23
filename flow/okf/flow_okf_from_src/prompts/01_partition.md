Partition the configured source tree into independently analyzable units for scalable OKF generation.

Source root: `{{var:source_root}}`

Rules:
- Do not attempt a detailed architecture analysis yet. This step exists only to discover robust analysis boundaries.
- Inspect repository structure, build/package metadata and a small amount of representative source as needed to identify natural units.
- Prefer existing project/module boundaries such as Maven/Gradle modules, npm workspaces, Python packages, services, applications or clearly separated top-level components.
- If one natural module is still obviously too large for a single detailed analysis, split it further along stable package/component boundaries.
- Avoid over-fragmentation. Small repositories should normally produce one unit.
- Every unit must be fully contained below source_root.
- Units should cover the relevant source tree without intentionally overlapping. Shared root-level build/configuration material may be represented as one dedicated unit when it materially affects the project.
- `id` must be stable, unique, filesystem-safe and match `[A-Za-z0-9_-]+`.
- `source_path` is workspace-relative and must point at the unit's analysis root.
- `okf_path` is relative to the configured OKF root, contains no `..`, and should use lowercase kebab-case. It may be `.` only when there is exactly one unit.
- Record uncertain or ambiguous boundaries in `warnings`; do not invent structure.

Return exactly one JSON object:

{
  "project": {
    "name": "string",
    "summary": "short repository-level summary"
  },
  "units": [
    {
      "id": "backend",
      "name": "Backend",
      "kind": "gradle-module",
      "source_path": "workspace-relative/path",
      "okf_path": "backend",
      "description": "why this is an independent analysis unit"
    }
  ],
  "warnings": ["string"]
}

Return valid JSON only.
