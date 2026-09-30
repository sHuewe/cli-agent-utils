Partition the configured source tree into independently analyzable units for scalable OKF generation.

Source root: `{{var:source_root}}`

Rules:
- Treat `source_root` as the complete scope. Do not inspect files or directories outside it.
- This step discovers analysis boundaries only. Do not attempt a complete architecture analysis.
- Inspect directory structure and only a small amount of representative source when necessary.
- Prefer natural units such as applications, services, major packages, subprojects, stable components, or a small shared/bootstrap/configuration unit.
- A unit may contain one or more non-overlapping `source_paths`; each path may be a file or directory below `source_root`.
- Every relevant source/configuration/bootstrap file below `source_root` must belong to exactly one unit. Do not silently lose root-level configuration or startup files merely because most code lives in subdirectories.
- Do not overlap units. If one unit owns a directory recursively, another unit must not own a child path of that directory.
- A unit must be small enough that one downstream inventory pass can exhaustively enumerate its externally observable functions and configuration possibilities.
- If a candidate contains roughly 50-100 or more relevant files, explicitly test whether a meaningful further split exists. File count is only a signal.
- Split large heterogeneous candidates along stable boundaries; avoid over-fragmentation of cohesive code.
- `id` must be stable, unique, filesystem-safe and match `[A-Za-z0-9_-]+`.
- Do NOT decide OKF directory placement here.

Return exactly one JSON object:
{
  "source_root":"{{var:source_root}}",
  "project":{"name":"string","summary":"short summary based only on the configured source tree"},
  "units":[
    {
      "id":"backend",
      "name":"Backend",
      "kind":"package|component|application|service|subproject|shared|other",
      "source_paths":["workspace-relative/path"],
      "description":"why these paths form one independent analysis unit"
    }
  ],
  "warnings":["string"]
}

Return valid JSON only.
