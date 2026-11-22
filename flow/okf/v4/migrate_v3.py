"""One-time, checkpoint-preserving V3 -> V4 Phase-A migration.

Phase A contains ONLY doctrine concepts, their source snapshots and a
machine-readable catalog/completion marker. Indexes, themes, manifests and
legacy checkpoints are never copied. Dry-run is the default.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import posixpath
import re
import shutil
import tempfile
import unicodedata

SCHEMA = "okf.phase-a.v1"
RESERVED = {"index", "con", "prn", "aux", "nul", *{f"com{i}" for i in range(1, 10)}, *{f"lpt{i}" for i in range(1, 10)}}


def safe_path(workspace: Path, relative: str, *, must_exist: bool = True) -> Path:
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise ValueError(f"Unsafe workspace path: {relative!r}")
    parts = relative.split("/")
    windows = PureWindowsPath(relative)
    if (windows.drive or windows.is_absolute() or relative.startswith("/")
            or any(part in ("", ".", "..") for part in parts)):
        raise ValueError(f"Unsafe workspace path: {relative!r}")
    current = workspace
    for part in parts:
        current /= part
        if current.is_symlink() or (hasattr(current, "is_junction") and current.is_junction()):
            raise ValueError(f"Symlink/junction refused: {current}")
    if must_exist and not current.is_file():
        raise ValueError(f"Required file missing: {current}")
    return current


def read_json(path: Path) -> dict:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Required JSON missing or unsafe: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return data


def slugify(title: str) -> str:
    if not isinstance(title, str) or not title.strip():
        raise ValueError("Concept title missing.")
    translit = {"Ä":"Ae","Ö":"Oe","Ü":"Ue","ä":"ae","ö":"oe","ü":"ue","ß":"ss"}
    text = "".join(translit.get(c,c) for c in title)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")[:72].rstrip("-")
    if not text or text in RESERVED:
        raise ValueError(f"Unusable concept title: {title!r}")
    return text


def title_from_frontmatter(raw: str) -> str | None:
    lines = raw.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    for line in lines[1:101]:
        if line.strip() == "---":
            return None
        m = re.fullmatch(r"title:\s*(.+?)\s*", line)
        if m:
            value = m.group(1)
            if value.startswith('"') and value.endswith('"'):
                try:
                    value = json.loads(value)
                except ValueError:
                    return None
            elif value.startswith("'") and value.endswith("'"):
                value = value[1:-1].replace("''", "'")
            elif value.startswith(("[", "{", "|", ">", "!", "*", "&")):
                return None
            return value.strip() if isinstance(value, str) and value.strip() else None
    return None


def checksum(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def assert_parent(path: str, document_slug: str) -> None:
    parts = path.split("/")
    if len(parts) not in (3, 4) or parts[0:2] != ["doctrines", document_slug] or not parts[-1].endswith(".md"):
        raise ValueError(f"Unexpected doctrine concept path: {path!r}")
    if any(not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", x) for x in parts[1:-1]):
        raise ValueError(f"Invalid doctrine/semantic folder: {path!r}")


def _markdown_links(body: str, old: str, new: str, mapping: dict[str, str]) -> str:
    """Update explicitly linked old concept paths; leave nonconcept links alone.

    This scans inline links and reference definitions, while shielding fenced
    code and code spans. External/anchor links are left as-is. Unexpected
    internal .md targets fail rather than silently publish a broken link.
    """
    from urllib.parse import unquote, quote, urlsplit
    pattern = re.compile(r"(?P<before>\]\(\s*|\[[^\]\n]+\]:[ \t]*)(?P<url><[^>\n]+>|[^\s()]+)", re.M)
    codes = re.compile(r"(?<!\x60)(?P<t>\x60+)(?!\x60).*?(?<!\x60)(?P=t)(?!\x60)", re.S)
    fences = re.compile(r"^[ ]{0,3}(\x60{3,}|~{3,})(.*)$")
    def rewrite(segment: str) -> str:
        def transform(match: re.Match) -> str:
            value = match["url"]
            enclosed = value.startswith("<") and value.endswith(">")
            target = value[1:-1] if enclosed else value
            parsed = urlsplit(target)
            if parsed.scheme or parsed.netloc or not parsed.path or parsed.path.startswith("/"):
                return match.group()
            decoded = unquote(parsed.path)
            original = posixpath.normpath(posixpath.join(posixpath.dirname(old), decoded))
            if original in mapping:
                relative = posixpath.relpath(mapping[original], posixpath.dirname(new))
                fixed = quote(relative, safe="/-._~")
                if parsed.query:
                    fixed += "?" + parsed.query
                if parsed.fragment:
                    fixed += "#" + parsed.fragment
                return match["before"] + ("<"+fixed+">" if enclosed else fixed)
            if decoded.lower().endswith(".md"):
                raise ValueError(f"Unresolved concept Markdown link in {old}: {target!r}")
            return match.group()
        result = []
        prev = 0
        for m in codes.finditer(segment):
            result.append(pattern.sub(transform, segment[prev:m.start()]))
            result.append(m.group())
            prev = m.end()
        result.append(pattern.sub(transform, segment[prev:]))
        return "".join(result)
    lines = body.splitlines(keepends=True)
    chunk, result = [], []
    fenced = None
    for line in lines:
        m = fences.match(line.rstrip("\r\n"))
        marker, tail = (m.group(1),m.group(2)) if m else (None,None)
        valid_open = marker and (marker[0] == "~" or "\x60" not in tail)
        if fenced is None and valid_open:
            result.append(rewrite("".join(chunk)))
            chunk = []
            fenced = (marker[0],len(marker))
            result.append(line)
        elif fenced:
            result.append(line)
            if marker and marker[0] == fenced[0] and len(marker) >= fenced[1] and not tail.strip():
                fenced = None
        else:
            chunk.append(line)
    result.append(rewrite("".join(chunk)))
    return "".join(result)


def prepare(workspace: Path, *, source_root: str, state_root: str) -> tuple[dict, dict[str, bytes]]:
    generated = safe_path(workspace, source_root+"/.placeholder", must_exist=False).parent
    state = safe_path(workspace, state_root+"/.placeholder", must_exist=False).parent
    if not generated.is_dir() or not state.is_dir():
        raise ValueError("V3 generated root or state directory missing.")
    groups = sorted(p for p in state.iterdir() if p.is_dir())
    if not groups:
        raise ValueError("No V3 doctrine state directories.")
    documents, concepts, outputs = [], [], {}
    paths, ids, ki_ids = set(), set(), set()
    original_paths: dict[str,str] = {}
    pending: list[tuple[str,str,str,bytes]] = []
    for doc_dir in groups:
        if doc_dir.is_symlink() or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", doc_dir.name):
            raise ValueError(f"Unsafe document state directory: {doc_dir}")
        slug = doc_dir.name
        group_path, cover_path, section_path = (doc_dir / n for n in ("group.json","coverage.json","sections.json"))
        if not group_path.is_file() or not cover_path.is_file() or not section_path.is_file():
            raise ValueError(f"Incomplete V3 document: {slug}")
        group, cover, sections = (read_json(p) for p in (group_path,cover_path,section_path))
        if cover.get("status") != "ok" or cover.get("missing_item_ids") or cover.get("warnings"):
            raise ValueError(f"Source coverage incomplete: {slug}")
        source_path = sections.get("source_path")
        source = safe_path(workspace, source_path)
        source_bytes = source.read_bytes()
        src_output = f"sources/{slug}{source.suffix.lower()}"
        if src_output in outputs:
            raise ValueError("Duplicate source output")
        outputs[src_output] = source_bytes
        planned = group.get("concepts")
        if (not isinstance(planned,list) or not planned
                or group.get("folder",{}).get("id") != slug
                or group.get("folder",{}).get("path") != f"doctrines/{slug}"):
            raise ValueError(f"Invalid group or empty concepts: {slug}")
        listed_items = set()
        for concept in planned:
            cid, old, title = concept.get("id"), concept.get("path"), concept.get("title")
            if not all(isinstance(x,str) and x for x in (cid,old,title)):
                raise ValueError(f"Incomplete planned concept: {slug}")
            if not re.fullmatch(r"[a-z][a-z0-9_-]*", cid):
                raise ValueError(f"Invalid concept identifier: {cid!r}")
            assert_parent(old,slug)
            qualified_id = f"{slug}:{cid}"
            if qualified_id in ids or old in original_paths:
                raise ValueError(f"Duplicate concept ID or path: {qualified_id}")
            ids.add(qualified_id)
            old_file = safe_path(workspace,source_root+"/"+old)
            raw_bytes = old_file.read_bytes()
            raw = raw_bytes.decode("utf-8")
            final_title = title_from_frontmatter(raw) or title
            target_folder = posixpath.dirname(old)
            stem = slugify(final_title)
            target = target_folder+"/"+stem+".md"
            if target.casefold() in paths:
                suffix = re.sub(r"[^a-z0-9-]+","-",cid.lower()).strip("-")[:24]
                target = target_folder+"/"+stem[:52].rstrip("-")+"-"+suffix+".md"
            if target.casefold() in paths or target.endswith("/index.md"):
                raise ValueError(f"Unresolvable concept filename collision: {target}")
            paths.add(target.casefold())
            original_paths[old] = target
            items = concept.get("coverage_items")
            if not isinstance(items,list) or not items:
                raise ValueError(f"Concept has no source Knowledge Items: {cid}")
            item_ids = []
            for item in items:
                kid = item.get("id") if isinstance(item,dict) else None
                if not isinstance(kid,str) or not kid or kid in ki_ids:
                    raise ValueError(f"Duplicate/invalid Knowledge Item ID: {kid}")
                ki_ids.add(kid); listed_items.add(kid); item_ids.append(kid)
            repair = read_json(doc_dir / f"concept-{cid}-repair.json")
            documented = repair.get("documented_item_ids")
            if (repair.get("status") not in ("ok","repaired") or repair.get("concept_id") != cid
                    or repair.get("remaining_item_ids") or repair.get("remaining_warnings")
                    or not isinstance(documented,list) or set(documented) != set(item_ids)):
                raise ValueError(f"Incomplete repair or Knowledge Item coverage: {cid}")
            pending.append((old,target,cid,raw_bytes))
            concepts.append({
                "id": f"{slug}:{cid}", "legacy_id":cid, "document_id":slug,
                "title":final_title,"path":target,"source_path":src_output,
                "source_original_path":source_path,
                "knowledge_item_ids":item_ids,
                "evidence_ranges":concept.get("evidence_ranges",[]),
                "sha256":None,
            })
        total=group.get("total_items")
        if total != len(listed_items) or (
            cover.get("expected_normative_items",0)+cover.get("expected_descriptive_items",0)
        ) != len(listed_items):
            raise ValueError(f"Group/coverage item count mismatch: {slug}")
        documents.append({
            "id":slug,"source_snapshot":src_output,
            "original_path":source_path,"sha256":checksum(source_bytes),
            "concept_ids":[x["id"] for x in concepts if x["document_id"]==slug],
        })
    by_path = {x["path"]:x for x in concepts}
    for old, target, cid, data in pending:
        fixed = _markdown_links(data.decode("utf-8"),old,target,original_paths).encode("utf-8")
        outputs[target] = fixed
        by_path[target]["sha256"] = checksum(fixed)
    catalog={"schema":SCHEMA,"documents":documents,"concepts":concepts}
    outputs["catalog.json"] = (json.dumps(catalog,ensure_ascii=False,indent=2)+"\n").encode("utf-8")
    contract={
        "schema":SCHEMA, "stage":"A","status":"completed","origin":"v3_migration",
        "catalog":"catalog.json","concept_count":len(concepts),
        "document_count":len(documents),"knowledge_item_count":len(ki_ids),
        "catalog_sha256":checksum(outputs["catalog.json"]),
        "allowed_files":sorted([*outputs,"phase-a.json"]),
    }
    outputs["phase-a.json"] = (json.dumps(contract,ensure_ascii=False,indent=2)+"\n").encode("utf-8")
    return contract,outputs


def migrate(workspace: Path, *, source_root: str, state_root: str,
            destination: str, apply: bool = False) -> dict:
    workspace=workspace.resolve()
    target=safe_path(workspace,destination+"/.placeholder",must_exist=False).parent
    if any(target == parent or target in parent.parents for parent in (
        safe_path(workspace,source_root+"/.placeholder",must_exist=False).parent,
        safe_path(workspace,state_root+"/.placeholder",must_exist=False).parent,
    )):
        raise ValueError("Phase A destination overlaps V3 sources/state.")
    contract,outputs=prepare(workspace,source_root=source_root,state_root=state_root)
    if target.exists():
        if target.is_symlink() or not (target/"phase-a.json").is_file():
            raise ValueError("Refusing to replace a non-V4 Phase-A directory.")
    if not apply:
        return {**contract, "dry_run":True,"destination":destination}
    target.parent.mkdir(parents=True,exist_ok=True)
    staging=Path(tempfile.mkdtemp(dir=target.parent,prefix=".phase-a-stage-"))
    backup=target.with_name("."+target.name+".previous")
    if backup.exists() or backup.is_symlink():
        raise ValueError(f"Unremoved previous migration backup: {backup}")
    try:
        for name,data in outputs.items():
            out=staging.joinpath(*name.split("/"))
            out.parent.mkdir(parents=True,exist_ok=True)
            out.write_bytes(data)
        actual={p.relative_to(staging).as_posix() for p in staging.rglob("*") if p.is_file()}
        if actual != set(contract["allowed_files"]):
            raise ValueError("Phase A contract: output files mismatch.")
        existing=target.exists()
        if existing:
            os.replace(target,backup)
        try:
            os.replace(staging,target)
        except BaseException:
            if existing:
                os.replace(backup,target)
            raise
        if existing:
            shutil.rmtree(backup)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return {**contract,"dry_run":False,"destination":destination}


def main(argv: list[str]|None=None)->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--workspace",type=Path,default=Path("."))
    p.add_argument("--source-root",default="okf-batched-generated-v3")
    p.add_argument("--state-root",default="okf-batched/state-v3/docs")
    p.add_argument("--destination",default="okf-v4/phase-a")
    p.add_argument("--apply",action="store_true")
    args=p.parse_args(argv)
    print(json.dumps(migrate(args.workspace,source_root=args.source_root,state_root=args.state_root,
                             destination=args.destination,apply=args.apply),ensure_ascii=False,indent=2))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
