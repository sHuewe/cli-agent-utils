# Open Knowledge Format (OKF) authoring guide

This file defines the shared OKF conventions for flows under `flow/okf/`.
It is intended to be used as `add_file_context` by planning, generation,
verification and repair steps.

## 1. Repository root and navigation

An OKF repository is a directory tree of Markdown knowledge documents.

The repository root **must contain a readable lowercase `index.md`**. This file
is the repository marker and the first navigation entry point. A directory is
not accepted as an OKF repository merely because an `index.md` exists somewhere
below it.

Navigation is progressive. The knowledge reader starts at the root index and
can follow Markdown links exposed by indexes or other OKF documents. Therefore:

- keep the root `index.md` concise;
- link from it to the important top-level directories or concepts;
- use local `index.md` files for larger subtrees where they improve navigation;
- make important concepts reachable through the index/link structure;
- use normal relative Markdown links for internal navigation;
- do not use paths that escape the OKF root.

A subdirectory does not technically require its own `index.md`: the OKF reader
can synthesize a directory index. Explicit indexes are nevertheless recommended
when they provide a clearer curated navigation path.

`index.md` is a navigation document, not a normal concept, and does not require
concept frontmatter.

## 2. Concepts

A concept is a Markdown file other than `index.md` or `log.md` that represents a
coherent piece of reusable knowledge. Organize concepts around architecture,
components, interfaces, workflows, configuration, operations, domain behavior,
or other meaningful topics rather than mirroring source files one-to-one.

Concepts should be:

- focused enough to be selected independently;
- durable rather than a transcription of implementation details;
- grounded in the actual source or other authoritative input;
- explicit about uncertainty instead of inventing missing information;
- linked to closely related OKF concepts when that improves navigation.

For source-derived OKF repositories, include a `## Source references` section
with concrete workspace-relative source paths and, where useful, relevant
classes, functions, modules or symbols. This is a generation convention for
traceability; it is not required by the OKF parser itself.

## 3. Required frontmatter

Every concept file must begin at the first byte with YAML frontmatter delimited
by `---` lines.

The only parser-required metadata field is a non-empty string `type`:

```yaml
---
type: component
---
```

For generated knowledge, prefer the richer form:

```yaml
---
type: component
title: Request processing
description: How incoming requests are validated, routed and executed.
tags:
  - request
  - routing
status: stable
---
```

Recognized metadata includes:

- `type` — required, non-empty string;
- `title` — optional human-readable title; the filename stem is used when absent;
- `description` — optional short summary;
- `tags` — optional list used for concept summaries;
- `status` — optional status value; defaults to `stable` when absent;
- `stale_after` — optional date-like value used to flag stale knowledge;
- `verified` — optional verification metadata used for trust classification.

Do not add `verified` merely because an LLM generated or checked a document.
Human verification must only be recorded when such verification actually
occurred. Flows that have no external verification evidence should normally
omit `verified` entirely.

Keep frontmatter simple YAML. Do not use aliases or anchors.

## 4. Special documents

`index.md` and `log.md` are special readable OKF Markdown documents and are not
parsed as normal concepts.

Use `index.md` for navigation and orientation. Do not plan it as a concept and
do not give it concept frontmatter merely to satisfy concept rules.

Only create `log.md` when a flow explicitly needs a log/changelog document; it
is not required for a valid repository.

## 5. Internal links

Use standard Markdown links:

```markdown
[Authentication](security/authentication.md)
[Sibling concept](../runtime/lifecycle.md)
```

Relative links are preferred because the repository may be moved as a unit.
Links should resolve to files or directories inside the OKF root. Avoid broken
links and avoid linking to non-OKF Markdown as though it were an OKF concept.

For a curated index, every linked concept should be a valid OKF document. Keep
indexes reasonably small and use additional directory indexes when a single
index would become unwieldy.

## 6. Source-grounded generation

When an OKF is generated from source code:

1. Treat plans, inventories and filenames as navigation hints, not as evidence.
2. Inspect the relevant source before stating implementation facts.
3. Prefer architectural or behavioral knowledge over file-by-file summaries.
4. Record concrete source references for important claims.
5. Do not copy large source fragments into the OKF.
6. Do not state inferred behavior as fact when the source does not support it.
7. Keep generated knowledge inside the configured OKF root and never modify the
   source tree unless the flow explicitly requests a separate source change.

## 7. Verification checklist

A generated OKF should be considered structurally valid only when all of the
following hold:

- the repository root contains readable `index.md`;
- every planned concept exists as UTF-8 Markdown;
- every concept starts with valid YAML frontmatter containing non-empty `type`;
- `index.md`/`log.md` are treated as special documents rather than concepts;
- internal links stay inside the repository and important navigation links resolve;
- important concepts are reachable through the progressive navigation structure;
- source-derived claims are consistent with the source material inspected;
- no unsupported `verified` claim is introduced.

Verification and repair steps should distinguish parser/structure errors from
content-quality warnings. Repair only concrete defects that are supported by
the available evidence.
