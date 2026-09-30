# Open Knowledge Format (OKF) authoring guide

This file defines the shared OKF conventions for flows under `flow/okf/`.
It is intended to be used as `add_file_context` by planning, generation,
verification and repair steps.

## 1. Repository root and semantic navigation

An OKF repository is a directory tree of Markdown knowledge documents.

The repository root **must contain a readable lowercase `index.md`**. This file
is the repository marker and the first navigation entry point. A directory is
not accepted as an OKF repository merely because an `index.md` exists somewhere
below it.

For the generated repositories in these flows, the root is intentionally only
an orientation/navigation layer. **Normal concepts must not be written directly
below the OKF root.** Before concept generation starts, the LLM plans one or
more semantic top-level folders and every concept is assigned to exactly one of
them. The folder names are project-specific and must be chosen from the actual
knowledge structure; examples such as `domain`, `application-context`,
`interfaces`, `configuration`, `operations` or `security` are illustrative,
not a fixed taxonomy.

The generated layout therefore has at least this depth:

```text
<okf-root>/
  index.md
  <semantic-folder>/
    index.md
    <concept>.md
```

Keep generated concepts directly inside their selected semantic top-level
folder unless a future flow explicitly plans another navigation level. This
keeps navigation predictable and makes completeness checks cheap.

Navigation is progressive. Therefore:

- keep the root `index.md` concise and link it to every declared top-level folder;
- every declared top-level folder has a curated local `index.md`;
- every generated concept must be linked from its folder index;
- important concepts may link to closely related concepts;
- use normal relative Markdown links for internal navigation;
- do not use paths that escape the OKF root.

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
classes, functions, modules or symbols.

For manual-derived OKF repositories, include a `## Manual references` section
with the bounded source ranges used for the concept.

## 3. Complete externally observable coverage

The OKF should not document only the architectural highlights. When the source
material exposes behavior or configuration to users, operators, callers or
integrators, that knowledge must be discoverable somewhere in the OKF.

Generation flows therefore maintain explicit coverage items for:

- externally observable functions/capabilities, including APIs, commands,
  user actions, jobs, messages, import/export behavior, extension hooks and
  other integration surfaces;
- every discovered configuration option or configuration family, including
  keys/properties, environment variables, command-line options, feature flags,
  modes/profiles, endpoints, paths, timeouts, limits and comparable controls.

Several related coverage items may be documented in one coherent concept. The
important invariant is that every discovered item is mapped to a concept and
then checked against the generated concept text. Merely mentioning an item in a
plan does not count as documentation.

## 4. Required frontmatter

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
- `title` — optional human-readable title;
- `description` — optional short summary;
- `tags` — optional list used for concept summaries;
- `status` — optional status value; defaults to `stable` when absent;
- `stale_after` — optional date-like value used to flag stale knowledge;
- `verified` — optional verification metadata used for trust classification.

Do not add `verified` merely because an LLM generated or checked a document.
Human verification must only be recorded when such verification actually
occurred. Keep frontmatter simple YAML and do not use aliases or anchors.

## 5. Special documents and links

`index.md` and `log.md` are special readable OKF Markdown documents and are not
parsed as normal concepts. Use `index.md` for navigation and orientation. Only
create `log.md` when a flow explicitly needs a log/changelog document.

Use standard relative Markdown links, for example:

```markdown
[Authentication](authentication.md)
[Runtime lifecycle](../operations/runtime-lifecycle.md)
```

Links should resolve inside the OKF root.

## 6. Source-grounded generation

When an OKF is generated from source code:

1. Treat plans, inventories and filenames as navigation hints, not as evidence.
2. Inspect the relevant source before stating implementation facts.
3. Prefer architectural or behavioral knowledge over file-by-file summaries.
4. Record concrete source references for important claims.
5. Do not copy large source fragments into the OKF.
6. Do not state inferred behavior as fact when the source does not support it.
7. Keep generated knowledge inside the configured OKF root and never modify the
   source tree.

## 7. Verification checklist

A generated OKF should be considered structurally valid only when all of the
following hold:

- the repository root contains readable `index.md`;
- at least one semantic top-level folder exists;
- no normal generated concept is located directly below the OKF root;
- every declared top-level folder contains `index.md`;
- every generated concept is linked from its folder index;
- every concept starts with valid YAML frontmatter containing non-empty `type`;
- `index.md`/`log.md` are treated as special documents rather than concepts;
- internal links stay inside the repository and important navigation links resolve;
- source-derived claims are consistent with the source material inspected;
- every discovered function/configuration coverage item is actually represented
  in concept content;
- no unsupported `verified` claim is introduced.

Verification and repair steps should distinguish parser/structure errors from
content-quality warnings. Repair only concrete defects supported by the
available evidence.
