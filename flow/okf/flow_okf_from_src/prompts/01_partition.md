Partition the configured source tree into independently analyzable units for scalable OKF generation.

Source root: `{{var:source_root}}`

Rules:
- Treat `source_root` as the complete scope of this step. Do not list, read, search or otherwise inspect files or directories outside it, even if repository-level build metadata exists there.
- Do not attempt a detailed architecture analysis yet. This step exists only to discover robust analysis boundaries inside `source_root`.
- Inspect directory/package structure and a small amount of representative source below `source_root` as needed to identify natural units.
- Prefer boundaries visible inside the source tree: distinct applications, services, major packages, subprojects represented below the source root, or clearly separated top-level components.
- A unit should be large enough that closely related functionality can be understood together, but small enough that one downstream inventory pass can completely capture its externally exposed functions, configuration possibilities, and important internal concepts.
- Split a unit when it contains several largely independent functional or technical subsystems with stable boundaries. Do not split merely because the unit contains many source files.
- File count is only a soft signal, not a partitioning rule. If a candidate unit contains roughly 50-100 or more relevant source files, explicitly inspect whether a meaningful further split exists. Keeping such a candidate as one unit is valid when the code is still cohesive and can be analyzed completely in one inventory pass.
- If one natural unit is obviously too broad for a single detailed analysis, split it further along stable package/component boundaries even when there is no formal project/module boundary.
- Avoid over-fragmentation. Small source trees may legitimately produce one unit, and related packages should stay together when separating them would make the later concepts less coherent.
- Every unit must be fully contained below `source_root`.
- Units should cover the relevant source tree without intentional overlap.
- `id` must be stable, unique, filesystem-safe and match `[A-Za-z0-9_-]+`.
- `source_path` is workspace-relative and must point at the unit's analysis root below `source_root`.
- `okf_path` is relative to the configured OKF root, contains no `..`, and should use lowercase kebab-case. It may be `.` only when there is exactly one unit.
- Record uncertain or ambiguous boundaries in `warnings`; do not invent structure from information outside `source_root`.

Return exactly one JSON object:

{
  "project": {
    "name": "string",
    "summary": "short summary based only on the configured source tree"
  },
  "units": [
    {
      "id": "backend",
      "name": "Backend",
      "kind": "package|component|application|service|subproject|other",
      "source_path": "workspace-relative/path",
      "okf_path": "backend",
      "description": "why this is an independent analysis unit"
    }
  ],
  "warnings": ["string"]
}

Return valid JSON only.
