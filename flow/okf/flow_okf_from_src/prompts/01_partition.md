Partition the configured source tree into independently analyzable units for scalable OKF generation.

Source root: `{{var:source_root}}`

Rules:
- Treat `source_root` as the complete scope of this step. Do not inspect files or directories outside it.
- This step discovers analysis boundaries only. Do not attempt a complete architecture analysis.
- Inspect directory/package structure and only a small amount of representative source when necessary.
- Prefer natural units such as applications, services, major packages, subprojects or stable components.
- A unit must be small enough that one downstream inventory pass can exhaustively enumerate its externally observable functions and configuration possibilities.
- If a candidate contains roughly 50-100 or more relevant source files, explicitly test whether a meaningful further split exists. File count is only a signal, not a rule.
- Split large heterogeneous candidates along stable boundaries. Avoid over-fragmentation of cohesive code.
- Units must cover the relevant source tree without intentional overlap and remain below `source_root`.
- `id` must be stable, unique, filesystem-safe and match `[A-Za-z0-9_-]+`.
- Do NOT decide OKF directory placement here. Semantic OKF folders are chosen in the next dedicated step.

Return exactly one JSON object:
{
  "project":{
    "name":"string",
    "summary":"short summary based only on the configured source tree"
  },
  "units":[
    {
      "id":"backend",
      "name":"Backend",
      "kind":"package|component|application|service|subproject|other",
      "source_path":"workspace-relative/path",
      "description":"why this is an independent analysis unit"
    }
  ],
  "warnings":["string"]
}

Return valid JSON only.
