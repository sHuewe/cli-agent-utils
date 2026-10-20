Create a deterministic traversal plan for an EXISTING OKF repository from the supplied filesystem inventory. This is read-only planning: never call tools, inspect source files, or invent paths.

OKF root (workspace-relative): {{var:okf_root}}
Complete recursive inventory (workspace-relative paths): {{var:inventory}}

Use ONLY inventory.files and inventory.directories. Derive the actual set of folder paths containing concept Markdown files. Include the root folder (path ".") when it contains concepts. Exclude index.md and log.md case-insensitively. Only .md regular files in inventory.files are concepts; never invent a file or folder. Strip the OKF root prefix from all paths; every concept_path MUST be relative to the OKF root. Group each concept into its immediate parent folder, including nested folders. Order folders by their path, concepts lexicographically by path. Use IDs f001, f002 etc in that sorted order. Each folder must have status "ok" only when it is a real inventory folder and its concept paths are present; otherwise omit it. Do not add an empty folder. The inventory is authoritative: every eligible concept must occur exactly once, no duplicates. Do not read or verify concept contents in this step.

Keep the JSON minimal to avoid exhausting context on large repositories. Return valid JSON only:
{"okf_root":"{{var:okf_root}}","folders":[{"id":"f001","path":"topic","status":"ok","concept_paths":["topic/example.md"]}]}
