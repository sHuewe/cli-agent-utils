Assess whether the existing OKF adequately answers exactly one question.

Target OKF root: `{{var:okf_root}}`
Question:
{{var:question}}

Rules:
- Do not inspect original source code or manuals and do not modify files.
- Start at `<okf_root>/index.md` and follow only the navigation/concepts relevant to the question.
- Judge the actual concept content, not filenames alone.
- Choose exactly one action:
  - `covered`: the question can already be answered adequately and unambiguously from the existing OKF.
  - `extend`: relevant knowledge exists in the OKF, but one existing concept needs additional information.
  - `create`: the question exposes a meaningful knowledge gap best represented by a new concept.
- For `covered`, list the concepts that provide the answer and summarize why coverage is sufficient.
- For `extend`, select exactly one existing concept as `target_path` and describe the missing information.
- For `create`, select the best existing semantic top-level folder and propose a safe `target_path` directly inside that folder. Confirm that this target does not already exist; if it exists, use `extend` instead.
- Do not invent a new top-level folder.
- Never classify a question as covered merely because related terminology appears.
- If the question is ambiguous, state the ambiguity in `missing_information` and choose the action that would make the OKF useful without inventing facts.

Return exactly one JSON object:
{
  "question":"string",
  "action":"covered|extend|create",
  "covered_by":["relative/concept.md"],
  "target_path":"relative/concept.md or empty string",
  "folder_path":"semantic-folder or empty string",
  "coverage_summary":"what the existing OKF already establishes",
  "missing_information":["specific information still required"]
}

Return valid JSON only.
