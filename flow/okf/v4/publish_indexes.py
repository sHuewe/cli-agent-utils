"""Publish complete, deterministic V4 navigation from LLM concept summaries.

No LLM writes Markdown indexes. Validate every Phase-A concept, each LLM
summary and all generated links before atomically swapping published output.
The immutable Phase-A artifact is never changed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import posixpath
import re
import shutil
import sys
import tempfile

from migrate_v3 import safe_path, slugify
from phase_a_contract import checked_phase_a


def _summary(workspace: Path, state_root: str, item: dict) -> dict:
    path = safe_path(workspace, state_root + "/summaries/" + item["key"] + ".json")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("id") != item["id"]:
        raise ValueError(f"Missing/mismatched LLM summary: {item['id']}")
    summary = data.get("summary")
    if not isinstance(summary, str) or not 20 <= len(summary.strip()) <= 600:
        raise ValueError(f"Invalid LLM summary for {item['id']}")
    tags = data.get("tags")
    if not isinstance(tags,list) or len(tags) > 5:
        raise ValueError(f"Invalid LLM tags for {item['id']}")
    cleaned = []
    for tag in tags:
        if not isinstance(tag,str) or not 2 <= len(tag.strip()) <= 80:
            raise ValueError(f"Invalid LLM tag for {item['id']}")
        tag = tag.strip()
        slugify(tag)
        if tag.casefold() not in {t.casefold() for t in cleaned}:
            cleaned.append(tag)
    return {"id": item["id"], "summary":summary.strip(), "tags":cleaned}


def _relative(current: str, target: str) -> str:
    return posixpath.relpath(target, posixpath.dirname(current) or ".")


def _escape_label(value: str) -> str:
    return value.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]").replace("\n", " ").strip()


def render(catalog: dict, tasks: list[dict], summaries: dict[str, dict]) -> tuple[dict[str, bytes], dict]:
    concepts = catalog["concepts"]
    documents = catalog["documents"]
    identity = {c["id"]: c for c in concepts}
    if len(identity) != len(concepts) or set(identity) != set(summaries):
        raise ValueError("Inventory does not exactly cover Phase-A concept IDs.")
    artifacts: dict[str, bytes] = {}
    links: dict[str, list[str]] = {}
    inventory = []
    for c in sorted(concepts,key=lambda x:x["path"]):
        info = summaries[c["id"]]
        inventory.append({
            "id":c["id"], "path":c["path"], "title":c["title"],
            "summary":info["summary"], "tags":info["tags"],
            "document_id":c["document_id"],
            "knowledge_item_ids":c["knowledge_item_ids"],
            "source_path":c["source_path"],
        })

    def index(path: str, header: str, entries: list[tuple[str,str,str]]) -> None:
        if path in artifacts:
            raise ValueError(f"Index collision: {path}")
        rows = [f"# {header}", ""]
        links[path] = []
        for target, title, description in entries:
            links[path].append(target)
            rows.append(f"- [{_escape_label(title)}]({_relative(path,target)})"
                        + (f" – {description}" if description else ""))
        if not entries:
            rows.append("_Keine Einträge._")
        rows.append("")
        artifacts[path] = ("\n".join(rows)).encode("utf-8")

    # Each concept appears exactly once in its owning folder index.
    folders: dict[str, list[dict]] = {}
    for c in concepts:
        folder = posixpath.dirname(c["path"])
        folders.setdefault(folder, []).append(c)
    for folder, members in sorted(folders.items()):
        ix = folder+"/index.md"
        if ix in {c["path"] for c in concepts}:
            raise ValueError(f"Concept path collides with index: {ix}")
        index(ix, folder.split("/")[-1].replace("-", " ").title(),
              [(c["path"],c["title"],summaries[c["id"]]["summary"])
               for c in sorted(members,key=lambda x:x["title"].casefold())])

    # Doctrine index links directly to folders or root-level concepts via the
    # appropriate folder index. Each doctrine must contain at least one concept.
    doc_entries = []
    for doc in sorted(documents,key=lambda d:d["id"]):
        slug = doc["id"]
        own = [f for f in folders if f == f"doctrines/{slug}" or f.startswith(f"doctrines/{slug}/")]
        if not own:
            raise ValueError(f"Doctrine has no concepts: {slug}")
        page = f"doctrines/{slug}/index.md"
        if page in artifacts:
            # Flat doctrine already got its index in the folder pass; reuse it.
            # A flat layout has no other semantic folder by contract.
            if len(own) != 1 or own[0] != f"doctrines/{slug}":
                raise ValueError(f"Conflicting flat and nested doctrine layout: {slug}")
        else:
            index(page, slug.replace("-", " ").title(),
                  [(folder+"/index.md",folder.split("/")[-1].replace("-", " ").title(),
                    f"{len(folders[folder])} Konzepte")
                   for folder in sorted(own)])
        doc_entries.append((page,slug.replace("-", " ").title(),
                            f"{sum(len(folders[f]) for f in own)} Konzepte"))
    index("doctrines/index.md","Doktrinen",doc_entries)

    # LLM tags are semantic labels only. Membership and all paths are generated
    # deterministically from the complete inventory, including global views.
    themes: dict[str,dict] = {}
    for entry in inventory:
        for tag in entry["tags"]:
            key=slugify(tag)
            group=themes.setdefault(key,{"title":tag,"members":[],"member_ids":set()})
            # Distinct labels can normalize to one filename (e.g. an umlaut
            # and its transliteration). Preserve one link per concept ID.
            if entry["id"] not in group["member_ids"]:
                group["members"].append(entry)
                group["member_ids"].add(entry["id"])
    theme_entries=[]
    for key,group in sorted(themes.items()):
        page=f"themen/{key}.md"
        entries=[(item["path"],item["title"],item["summary"])
                 for item in sorted(group["members"],key=lambda x:x["title"].casefold())]
        index(page,group["title"],entries)
        theme_entries.append((page,group["title"],f"{len(entries)} Konzepte"))
    index("themen/index.md","Themen",theme_entries)
    index("index.md","OKF – Wissensübersicht",[
        ("doctrines/index.md","Doktrinen",f"{len(documents)} Dokumente"),
        ("themen/index.md","Themen",f"{len(themes)} thematische Gruppen"),
    ])

    # Source and source snapshots never enter the published tree. Only
    # Phase-A concepts, derived indexes, and the semantic inventory are allowed.
    expected_concepts={c["path"] for c in concepts}
    all_paths=set(artifacts)|expected_concepts|{"inventory.json"}
    for page, targets in links.items():
        if len(set(targets))!=len(targets):
            raise ValueError(f"Duplicate navigation link: {page}")
        for target in targets:
            if target not in all_paths:
                raise ValueError(f"Broken generated link {page} -> {target}")
    reachable={"index.md"}
    queue=["index.md"]
    while queue:
        for target in links.get(queue.pop(),[]):
            if target not in reachable:
                reachable.add(target)
                queue.append(target)
    if not expected_concepts.issubset(reachable):
        raise ValueError("Not every concept is reachable from root index.")
    for folder, members in folders.items():
        if set(links[folder+"/index.md"]) != {c["path"] for c in members}:
            raise ValueError(f"Folder index is not complete: {folder}")
    artifact_inventory={"schema":"okf.inventory.v1","status":"complete","concepts":inventory}
    artifacts["inventory.json"]=(json.dumps(artifact_inventory,ensure_ascii=False,indent=2)+"\n").encode("utf-8")
    report={
        "status":"ok","concept_count":len(concepts),
        "document_count":len(documents),"theme_count":len(themes),
        "index_count":len(links),"reachable_concepts":len(expected_concepts),
        "inventory_path":"inventory.json",
    }
    return artifacts,report


def publish(workspace: Path, *, phase_a: str, state_root: str,
            destination: str, tasks: dict) -> dict:
    workspace=workspace.resolve()
    _,catalog,base=checked_phase_a(workspace,phase_a)
    if tasks.get("schema")!="okf.inventory-tasks.v1" or tasks.get("status")!="ok":
        raise ValueError("Missing validated inventory task result.")
    items=tasks.get("concepts")
    if not isinstance(items,list) or len(items)!=len(catalog["concepts"]) or tasks.get("count")!=len(items):
        raise ValueError("Inventory task count differs from Phase A.")
    expected={c["id"]:c for c in catalog["concepts"]}
    seen=set()
    summaries={}
    for item in items:
        if not isinstance(item,dict) or item.get("id") not in expected or item["id"] in seen:
            raise ValueError("Unknown/duplicate inventory task.")
        c=expected[item["id"]]
        if (item.get("title")!=c["title"] or item.get("path")!=phase_a+"/"+c["path"]
                or item.get("source")!=phase_a+"/"+c["source_path"]
                or item.get("knowledge_item_count")!=len(c["knowledge_item_ids"])):
            raise ValueError("Inventory task metadata does not match Phase A.")
        seen.add(c["id"])
        key=c["id"].replace(":","--") + "--" + c["sha256"][:16]
        if item.get("key") != key or not re.fullmatch(r"[a-z0-9_-]+",key):
            raise ValueError("Invalid inventory task key.")
        summaries[c["id"]]=_summary(workspace,state_root,item)
    artifacts,report=render(catalog,items,summaries)
    for c in catalog["concepts"]:
        artifacts[c["path"]]=(base/c["path"]).read_bytes()
    target=safe_path(workspace,destination+"/.placeholder",must_exist=False).parent
    if target.exists() and (target.is_symlink() or not (target/"inventory.json").is_file()):
        raise ValueError("Refusing to overwrite non-B publication.")
    if target==base or base in target.parents or target in base.parents:
        raise ValueError("Publication root overlaps Phase A.")
    target.parent.mkdir(parents=True,exist_ok=True)
    staging=Path(tempfile.mkdtemp(dir=target.parent,prefix=".phase-b-stage-"))
    backup=target.with_name("."+target.name+".previous")
    if backup.exists() or backup.is_symlink():
        raise ValueError("Previous publication backup still exists.")
    try:
        for name,raw in artifacts.items():
            target_file=staging.joinpath(*name.split("/"))
            target_file.parent.mkdir(parents=True,exist_ok=True)
            target_file.write_bytes(raw)
        observed={p.relative_to(staging).as_posix() for p in staging.rglob("*") if p.is_file()}
        if observed!=set(artifacts):
            raise ValueError("Incomplete publication output.")
        prior=target.exists()
        if prior:
            os.replace(target,backup)
        try:
            os.replace(staging,target)
        except BaseException:
            if prior:
                os.replace(backup,target)
            raise
        if prior:
            shutil.rmtree(backup)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return {**report,"published_root":destination}


def main(argv: list[str]|None=None)->int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace",type=Path,default=Path("."))
    parser.add_argument("--phase-a",default="okf-v4/phase-a")
    parser.add_argument("--state-root",default="okf-v4/state-b")
    parser.add_argument("--destination",default="okf-v4/published")
    args=parser.parse_args(argv)
    envelope=json.load(sys.stdin)
    data=envelope.get("inputs",{}).get("tasks")
    if not isinstance(data,dict):
        raise ValueError("Python step requires verified json_inputs.tasks.")
    result=publish(args.workspace,phase_a=args.phase_a,state_root=args.state_root,
                   destination=args.destination,tasks=data)
    print(json.dumps(result,ensure_ascii=False))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
