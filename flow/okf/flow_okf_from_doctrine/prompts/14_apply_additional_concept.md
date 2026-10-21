Apply one assessed doctrine-concept change.
OKF root: {{var:okf_root}}
Assessment: {{var:assessment}}

If covered or not_applicable, do not write. Otherwise read only assessment.evidence_ranges with bounded read_file, preserve source modality, scope and exceptions. For extend, first read the existing target. For create, write valid frontmatter and ## Doctrine references. Never change doctrines or folder structure; do not claim verified. Return JSON only:
{"status":"unchanged|extended|created","request_id":"string","folder_id":"string","target_path":"relative/path.md","changed_paths":["relative/path"],"warnings":["string"]}
