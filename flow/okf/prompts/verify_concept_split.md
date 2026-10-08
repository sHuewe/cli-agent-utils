Verify the result of one concept-granularity evaluation/split.

Target OKF root: `{{var:okf_root}}`
Original concept path: `{{var:concept_path}}`

Assessment:
{{var:assessment}}

Applied change:
{{var:change}}

Full pre-split concept snapshot:
{{var:snapshot}}

Rules:
- Do not inspect original source code or manuals and do not modify files.
- If `assessment.action` is `needs_attention`, return `status: needs_attention` with an error finding that preserves the assessment reason/warnings; this is not a successful no-op.
- If `assessment.action` is `keep` or `skip`, return `not_changed` unless the apply step itself reported `needs_attention`.
- If `change.status` is `needs_attention`, or a requested split was not successfully applied, return `needs_attention` and report the problem rather than presenting it as `not_changed`.
- If any verification finding has `severity: error`, return `status: needs_attention`.
- Always set `overview_path` to the original `concept_path`, including when the decision was keep, skip or needs_attention. For a successful split, `verified_paths` must include the original overview path and EVERY successfully checked new part path. For a non-split, do not list invented new paths.
- Before certifying a split, require snapshot.status == "captured", non-empty complete snapshot.content and snapshot.index_content, and matching snapshot.concept_path and snapshot.index_path. If absent or incomplete, return needs_attention with an error finding.
- For a split, read the overview, every change.new_paths concept, and the direct folder index.md.
- Independently compare the FULL original Markdown stored in snapshot.content with the combined new overview and all focused concepts. Do not rely on assessment.parts as an exhaustive inventory.
- Check preservation of every substantial original claim, option, default, limitation, prerequisite, example, procedure, link and source/manual reference. Verify references stay with the corresponding claims.
- If any material is lost, materially altered, or cannot be checked against the snapshot, return needs_attention and provide specific error findings. Do not treat a semantic omission as merely a warning.
- Verify:
  - the original path still exists as a concise overview;
  - every planned part exists directly in the same semantic folder;
  - the rewritten ORIGINAL overview also begins at byte zero with parseable `---`-delimited YAML frontmatter and a non-empty string `type`, with no YAML parsing errors; check this independently of the new parts;
  - the overview retains the original `type` and applicable original metadata, with no newly invented human-verification claim; report removed/corrupted required metadata as an error;
  - every part has valid frontmatter with non-empty `type`;
  - every original Markdown heading and explicit fragment anchor from snapshot.content still resolves at the ORIGINAL overview path, even if its full section moved to a new concept; compare exact heading text, level, order, duplicate-heading slug suffixes, and explicit IDs against the snapshot;
  - moved sections leave short heading stubs with links to the new concepts rather than breaking inbound `original.md#fragment` links; report missing, renamed, ambiguous, or displaced fragment anchors as errors;
  - the overview links all new parts;
  - the folder index links the overview and every new part;
  - the folder index links EVERY direct normal Markdown concept in the folder (exclude index.md and log.md), including all unrelated existing concepts; list the folder directly and compare exact paths, not just the proposed split parts;
  - every pre-existing link destination in snapshot.index_content remains present in the updated index, especially links to unrelated concepts and any other original navigation destinations; report lost links as errors;
  - no concept path has duplicate entries in the folder index;
  - each planned scope from `assessment.parts` is materially represented in the corresponding part;
  - the overview/parts remain semantically focused and the split did not merely create arbitrary fragments;
  - existing source/manual references needed by the redistributed claims are still present somewhere appropriate;
  - no obvious substantial topic named by the assessment disappeared during redistribution.
- Do not require a particular line count after splitting.

Return exactly one JSON object:
{
  "status":"ok|not_changed|needs_attention",
  "overview_path":"relative/concept.md",
  "verified_paths":["relative/path"],
  "findings":[
    {"severity":"error|warning","path":"relative/path","problem":"string"}
  ]
}

Return valid JSON only.
