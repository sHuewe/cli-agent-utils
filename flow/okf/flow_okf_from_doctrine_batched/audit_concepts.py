"""Audit existing OKF Concept artifacts; optionally quarantine inconsistent ones.

Dry run by default. This script neither modifies source doctrines nor rebuilds
the global document/topic plan. Back up the workspace before applying.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import tomllib


def _load(path: Path) -> dict:
    if path.is_symlink():
        raise ValueError(f"Symlink not allowed: {path}")
    doc = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return doc


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


def audit(workspace: Path, output_root: str) -> dict:
    state = workspace / "okf-batched/state-v3/docs"
    if not state.is_dir() or state.is_symlink():
        raise ValueError(f"Invalid document state directory: {state}")
    root = workspace / output_root
    findings: list[dict] = []
    affected: dict[str, set[str]] = {}
    scanned = 0

    for doc_dir in sorted(state.iterdir()):
        if not doc_dir.is_dir() or doc_dir.is_symlink():
            continue
        plan_path = doc_dir / "group.json"
        if not plan_path.is_file():
            continue
        group = _load(plan_path)
        concept_list = group.get("concepts")
        if not isinstance(concept_list, list):
            raise ValueError(f"Invalid concepts in {plan_path}")
        concepts = {}
        path_owner = {}
        for obj in concept_list:
            if not isinstance(obj, dict) or not isinstance(obj.get("id"), str):
                raise ValueError(f"Invalid concept in {plan_path}")
            cid, relative = obj["id"], obj.get("path")
            if cid in concepts or not cid or "/" in cid or "\\" in cid:
                raise ValueError(f"Duplicate or invalid planned ID in {plan_path}")
            _inside(root, relative)
            if relative in path_owner:
                raise ValueError(f"Duplicate planned path in {plan_path}")
            concepts[cid] = relative
            path_owner[relative] = cid

        def issue(cid: str, reason: str, detail: str) -> None:
            findings.append({"document": doc_dir.name, "concept_id": cid,
                             "reason": reason, "detail": detail})
            affected.setdefault(doc_dir.name, set()).add(cid)

        for cid, expected in concepts.items():
            scanned += 1
            checkpoints = {}
            for step in ("build", "verify", "repair"):
                file = doc_dir / f"concept-{cid}-{step}.json"
                if file.exists():
                    checkpoints[step] = _load(file)
            manifest = doc_dir / "manifests" / f"concept-{cid}.json"
            if manifest.is_file():
                checkpoints["manifest"] = _load(manifest)

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

                if actual not in (expected, f"{output_root}/{expected}"):
                    issue(cid, "wrong_path", f"{step}: {actual!r} (expected {expected!r})")
                    if isinstance(actual, str):
                        unprefixed = actual[len(output_root)+1:] if actual.startswith(output_root + "/") else actual
                        owner = path_owner.get(unprefixed)
                        if owner is not None and owner != cid:
                            issue(owner, "potentially_overwritten",
                                  f"{cid}/{step} references this concept's path")

                for reported in data.get("changed_paths", ()) if step == "repair" else ():
                    if reported not in (expected, f"{output_root}/{expected}"):
                        issue(cid, "cross_write", f"{step} changed {reported!r}")
                        if isinstance(reported, str):
                            unprefixed = reported[len(output_root)+1:] if reported.startswith(output_root + "/") else reported
                            owner = path_owner.get(unprefixed)
                            if owner is not None and owner != cid:
                                issue(owner, "potentially_overwritten",
                                      f"{cid}/repair reports changed_path")

            if "build" in checkpoints and not _inside(root, expected).is_file():
                issue(cid, "missing_markdown", expected)

    return {"scanned_concepts": scanned, "findings": findings,
            "affected": {key: sorted(value) for key, value in sorted(affected.items())}}


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
    # Refuse half a cross-concept incident: the original owner may have
    # been overwritten, even if its own three JSON outputs look correct.
    for finding in report["findings"]:
        if finding["reason"] in {"cross_write", "wrong_path", "potentially_overwritten"}:
            slug = finding["document"]
            affected_ids = affected.get(slug, set())
            selected_ids = selected.get(slug, set())
            if selected_ids & affected_ids and selected_ids != affected_ids:
                raise ValueError(
                    f"Select all affected IDs for a cross-concept incident in {slug}: "
                    f"{sorted(affected_ids)}"
                )
    sources: list[Path] = []
    docs = workspace / "okf-batched/state-v3/docs"
    generated = workspace / output_root
    for slug, ids in selected.items():
        folder = docs / slug
        group = _load(folder / "group.json")
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

    distinct = sorted({path for path in sources if path.exists()})
    base = workspace / "okf-batched/recovery-v3"
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
    report = audit(workspace, root)
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
