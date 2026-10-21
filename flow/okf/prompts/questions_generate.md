Generate a small starter list of useful questions about the project that a reader may reasonably expect the OKF to answer.

Target OKF root: `{{var:okf_root}}`
Source kind: {{var:source_kind}}

Rules:
- This step exists mainly to create an editable checkpoint file. In normal use, a human will usually replace the generated questions with concrete questions that the current OKF did not answer well enough.
- You may inspect the existing OKF starting from `<okf_root>/index.md` to propose useful questions, but do not inspect the original source/manual material.
- Prefer practical reader questions about installation, operation, usage, configuration, architecture, interfaces, constraints, troubleshooting or domain behavior.
- Keep each question self-contained and understandable without hidden context.
- Do not answer the questions.
- Return only the simple question list. Do not add IDs, categories, explanations or warnings.

Return exactly one JSON object:
{
  "questions":[
    "How is the software installed?",
    "How is the software operated?",
    "Which runtime version is required?"
  ]
}

Return valid JSON only.
