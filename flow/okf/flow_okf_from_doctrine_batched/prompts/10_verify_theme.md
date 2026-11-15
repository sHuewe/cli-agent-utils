# Independent verification of ONE theme concept

Theme descriptor: {{var:theme}}
Write result: {{var:write}}
OKF root: {{var:okf_root}}

READ ONLY the generated theme and bounded headings/frontmatter of each
declared member. Verify actual file exists, frontmatter type is nonempty,
all links resolve inside root, theme:<id> present on all actual member
files, and source_slug count >=2. No directory-wide searches.
Never call an unverified link real or silently accept missing members.
Return {"status":"ok|needs_attention","path":"theme path",
"checked_members":0,"warnings":[]}.

