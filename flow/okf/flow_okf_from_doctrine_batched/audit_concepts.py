"""Audit existing OKF Concept artifacts; optionally quarantine inconsistent ones.

Dry run by default. This script neither modifies source doctrines nor rebuilds
the global document/topic plan. Back up the workspace before applying.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath
import shutil
import tomllib


def _require_safe_path(workspace: Path, path: Path) -> None:
    """Reject paths escaping the workspace or traversing symlinks/junctions.

    Check missing destination ancestors as well as existing sources. This
    validation is performed for the complete recovery plan before any move.
    """
    root = workspace.absolute()
    candidate = path.absolute()
    if (".." in path.parts or not candidate.is_relative_to(root)
            or root.resolve(strict=False) != root
            or candidate.resolve(strict=False) != candidate):
        raise ValueError(f"Symlink or path outside workspace: {path}")
    if not root.is_dir():
        raise ValueError(f"Workspace is not a directory: {root}")
    current = root
    parts = candidate.relative_to(root).parts
    for index, part in enumerate(parts):
        current = current / part
        if current.is_symlink() or (
            callable(getattr(current, "is_junction", None))
            and current.is_junction()
        ):
            raise ValueError(f"Symlink or junction not allowed: {current}")
        # All existing ancestors of source and destination paths must be
        # directories. Otherwise mkdir() could fail after earlier artifacts
        # have already been moved, leaving a partially applied quarantine.
        if index < len(parts) - 1 and current.exists() and not current.is_dir():
            raise ValueError(f"Non-directory artifact path ancestor: {current}")


def _load(path: Path, *, workspace: Path) -> dict:
    _require_safe_path(workspace, path)
    doc = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return doc


def _normalized_reported_concept_path(raw_path: str, output_root: str) -> str | None:
    """Map an untrusted reported path to a safe output-root-relative key.

    Accept both supported report spellings (with or without the output-root
    prefix), collapsing redundant separators, dot segments and in-root '..'.
    Never let a parent traversal escape the selected output root. The result
    is for matching planned owners only, not for filesystem operations.
    """
    if not isinstance(raw_path, str) or not raw_path or "\\" in raw_path:
        return None
    reported = PurePosixPath(raw_path)
    if reported.is_absolute():
        return None
    parts = reported.parts
    prefix = PurePosixPath(output_root).parts
    if parts[:len(prefix)] == prefix:
        parts = parts[len(prefix):]
    elif not parts or parts[0] != "doctrines":
        return None

    normalized: list[str] = []
    for part in parts:
        if part == "..":
            if not normalized:
                return None
            normalized.pop()
        else:
            normalized.append(part)
    if not normalized or normalized[0] != "doctrines":
        return None
    return "/".join(normalized)


def _is_index_reported_path(raw_path: object, output_root: str) -> bool:
    """Recognize safe, normalized index.md paths reported by old checkpoints."""
    if not isinstance(raw_path, str):
        return False
    relative = _normalized_reported_concept_path(raw_path, output_root)
    return relative is not None and PurePosixPath(relative).name.casefold() == "index.md"


def _inside(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise ValueError(f"Invalid artifact path: {relative!r}")
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts or candidate.parts[0] != "doctrines":
        raise ValueError(f"Unsafe or unexpected concept path: {relative!r}")
    path = root.joinpath(*candidate.parts)
    if (path.is_symlink()
            or path.resolve(strict=False) != path.absolute()
            or not path.resolve(strict=False).is_relative_to(root.resolve())):
        raise ValueError(f"Symlink or invalid artifact path: {path}")
    return path


def audit(workspace: Path, output_root: str, *, ignore_index: bool = False) -> dict:
    state = workspace / "okf-batched/state-v3/docs"
    _require_safe_path(workspace, state)
    if not state.is_dir() or state.is_symlink():
        raise ValueError(f"Invalid document state directory: {state}")
    root = workspace / output_root
    findings: list[dict] = []
    affected: dict[str, set[str]] = {}
    scanned = 0

    # First collect EVERY planned concept in the corpus. This makes an
    # erroneous write into another source document visible to its owner.
    corpus_plans: list[tuple[Path, dict[str, str]]] = []
    corpus_owners: dict[str, tuple[str, str]] = {}
    for doc_dir in sorted(state.iterdir()):
        if not doc_dir.is_dir() or doc_dir.is_symlink():
            continue
        plan_path = doc_dir / "group.json"
        if not plan_path.is_file():
            continue
        group = _load(plan_path, workspace=workspace)
        concept_list = group.get("concepts")
        if not isinstance(concept_list, list):
            raise ValueError(f"Invalid concepts in {plan_path}")
        concepts: dict[str, str] = {}
        for obj in concept_list:
            if not isinstance(obj, dict) or not isinstance(obj.get("id"), str):
                raise ValueError(f"Invalid concept in {plan_path}")
            cid, relative = obj["id"], obj.get("path")
            if cid in concepts or not cid or "/" in cid or "\\" in cid:
                raise ValueError(f"Duplicate or invalid planned ID in {plan_path}")
            _inside(root, relative)
            if relative in corpus_owners:
                raise ValueError(f"Duplicate planned concept path across corpus: {relative}")
            concepts[cid] = relative
            corpus_owners[relative] = (doc_dir.name, cid)
        corpus_plans.append((doc_dir, concepts))

    cross_writes: set[tuple[str, str, str, str]] = set()

    def issue_for(slug: str, cid: str, reason: str, detail: str) -> None:
        findings.append({"document": slug, "concept_id": cid,
                         "reason": reason, "detail": detail})
        affected.setdefault(slug, set()).add(cid)

    def mark_owner(writer_slug: str, writer_id: str, raw_path: str, step: str) -> None:
        canonical = _normalized_reported_concept_path(raw_path, output_root)
        owner = corpus_owners.get(canonical) if canonical is not None else None
        if owner is not None and owner != (writer_slug, writer_id):
            issue_for(owner[0], owner[1], "potentially_overwritten",
                      f"{writer_slug}/{writer_id}/{step} references this concept's path")
            cross_writes.add((writer_slug, writer_id, owner[0], owner[1]))

    for doc_dir, concepts in corpus_plans:
        def issue(cid: str, reason: str, detail: str) -> None:
            issue_for(doc_dir.name, cid, reason, detail)

        for cid, expected in concepts.items():
            scanned += 1
            checkpoints = {}
            for step in ("build", "verify", "repair"):
                file = doc_dir / f"concept-{cid}-{step}.json"
                if file.exists():
                    checkpoints[step] = _load(file, workspace=workspace)
            manifest = doc_dir / "manifests" / f"concept-{cid}.json"
            if manifest.is_file():
                checkpoints["manifest"] = _load(manifest, workspace=workspace)

            if not checkpoints:
                continue
            for step, data in checkpoints.items():
                if step == "manifest":
                    entries = data.get("concepts")
                    if not isinstance(entries, list) or len(entries) != 1 or not isinstance(entries[0], dict):
                        issue(cid, "invalid_manifest", str(manifest))
                        continue
                    actual = entries[0].get("path")
                else:
                    actual = data.get("path")
                    if data.get("concept_id") != cid:
                        issue(cid, "wrong_id", f"{step}: {data.get('concept_id')!r}")

                if (actual not in (expected, f"{output_root}/{expected}")
                        and not (ignore_index and _is_index_reported_path(actual, output_root))):
                    issue(cid, "wrong_path", f"{step}: {actual!r} (expected {expected!r})")
                    if isinstance(actual, str):
                        mark_owner(doc_dir.name, cid, actual, step)

                for reported in data.get("changed_paths", ()) if step == "repair" else ():
                    if (reported not in (expected, f"{output_root}/{expected}")
                            and not (ignore_index and _is_index_reported_path(reported, output_root))):
                        issue(cid, "cross_write", f"{step} changed {reported!r}")
                        if isinstance(reported, str):
                            mark_owner(doc_dir.name, cid, reported, "repair.changed_paths")

            if "build" in checkpoints and not _inside(root, expected).is_file():
                issue(cid, "missing_markdown", expected)

    return {"scanned_concepts": scanned, "findings": findings,
            "affected": {key: sorted(value) for key, value in sorted(affected.items())},
            "cross_writes": [
                {"writer_document": src_doc, "writer_concept": src_id,
                 "target_document": dst_doc, "target_concept": dst_id}
                for src_doc, src_id, dst_doc, dst_id in sorted(cross_writes)
            ]}


def quarantine(
    workspace: Path, output_root: str, report: dict,
    selected: dict[str, set[str]],
) -> list[str]:
    """Move explicitly selected invalid concepts and their downstream state."""
    affected = {slug: set(ids) for slug, ids in report["affected"].items()}
    if not selected or any(not ids for ids in selected.values()):
        raise ValueError("Explicit nonempty concept selection required.")
    for slug, ids in selected.items():
        unknown = ids - affected.get(slug, set())
        if unknown:
            raise ValueError(f"Concepts are not flagged by the audit: {slug}:{sorted(unknown)}")
    for edge in report.get("cross_writes", []):
        writer_selected = edge["writer_concept"] in selected.get(edge["writer_document"], set())
        target_selected = edge["target_concept"] in selected.get(edge["target_document"], set())
        if writer_selected != target_selected:
            raise ValueError(
                "Select both the writer and affected target of a cross-document write: "
                f"{edge['writer_document']}:{edge['writer_concept']} -> "
                f"{edge['target_document']}:{edge['target_concept']}"
            )
    sources: list[Path] = []
    docs = workspace / "okf-batched/state-v3/docs"
    generated = workspace / output_root
    for slug, ids in selected.items():
        folder = docs / slug
        group = _load(folder / "group.json", workspace=workspace)
        planned = {item["id"]: item["path"] for item in group["concepts"]}
        for cid in ids:
            if cid not in planned:
                raise ValueError(f"Unknown affected ID: {slug}/{cid}")
            for step in ("build", "verify", "repair"):
                sources.append(folder / f"concept-{cid}-{step}.json")
            sources.append(folder / "manifests" / f"concept-{cid}.json")
            sources.append(_inside(generated, planned[cid]))
        # Document-wide coverage/navigation must be recalculated after repair.
        sources.extend(folder / name for name in (
            "coverage.json", "module-index.json",
            "manifests/coverage.json", "manifests/navigation.json",
            "manifest-inventory.json", "final-manifest-inventory.json",
        ))
        sources.extend(folder.glob("folder-*-index.json"))
        sources.extend(folder.glob("folder-*-inventory.json"))

    # Validate *all* proposed sources, even missing optional checkpoints.
    # In particular, an ancestor such as docs/a/manifests must not redirect
    # reads or moves outside the workspace.
    for path in sources:
        _require_safe_path(workspace, path)
        if path.exists() and not path.is_file():
            raise ValueError(f"Expected a regular artifact file: {path}")
    distinct = sorted({path for path in sources if path.exists()})
    base = workspace / "okf-batched/recovery-v3"
    _require_safe_path(workspace, base)
    targets: list[tuple[Path, Path]] = []
    for path in distinct:
        if path.is_symlink():
            raise ValueError(f"Refusing symlink artifact: {path}")
        if path.is_relative_to(docs):
            target = base / "state" / path.relative_to(docs)
        elif path.is_relative_to(generated):
            target = base / "generated" / path.relative_to(generated)
        else:
            raise ValueError(f"Unexpected artifact outside scoped recovery: {path}")
        _require_safe_path(workspace, target)
        if target.exists() or target.is_symlink():
            raise FileExistsError(f"Recovery file already exists: {target}")
        targets.append((path, target))

    for source, target in targets:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(target))
    return [path.relative_to(workspace).as_posix() for path, _ in targets]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path("."))
    parser.add_argument("--apply", action="store_true", help="Quarantine only explicitly selected checkpoints")
    parser.add_argument(
        "--ignore-index", action="store_true",
        help="Ignore findings caused by reported index.md paths (not other concept errors).",
    )
    parser.add_argument("--select", action="append", default=[],
                        metavar="SOURCE_SLUG:CONCEPT_ID",
                        help="Select a flagged concept for quarantine (repeatable).")
    args = parser.parse_args(argv)
    workspace = args.workspace.resolve()
    config = workspace / "flow/okf/flow_okf_from_doctrine_batched/flow.toml"
    with config.open("rb") as handle:
        root = tomllib.load(handle)["vars"]["okf_root"]
    if (not isinstance(root, str) or not root or Path(root).is_absolute()
            or "\\" in root or ".." in Path(root).parts):
        raise ValueError("Unsafe OKF output root.")
    report = audit(workspace, root, ignore_index=args.ignore_index)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.apply:
        selected: dict[str, set[str]] = {}
        if not args.select:
            parser.error("--apply requires at least one --select SOURCE_SLUG:CONCEPT_ID.")
        for spec in args.select:
            slug, sep, cid = spec.rpartition(":")
            if not sep or not slug or not cid or "/" in slug or ".." in slug or "/" in cid or ".." in cid:
                parser.error(f"Invalid --select: {spec!r}")
            selected.setdefault(slug, set()).add(cid)
        moved = quarantine(workspace, root, report, selected)
        print(f"Quarantined {len(moved)} files in okf-batched/recovery-v3.")
    else:
        print("Dry run: no files were changed. Review findings before --apply with explicit --select.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
