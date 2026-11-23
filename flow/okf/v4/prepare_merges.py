"""Prepare bounded, non-overlapping same-doctrine merge candidate groups."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import sys

from migrate_v3 import theme_slug
from phase_b_contract import checked_b


def prepare(workspace: Path) -> dict:
    _,catalog,_ = checked_b(workspace,root="okf-v4/b-reviewed",stage="B-draft")
    concepts = sorted(catalog["concepts"],key=lambda c:(c["document_id"],c["id"]))
    buckets: dict[tuple[str,str],list[dict]]={}
    for c in concepts:
        for tag in c.get("tags",[]):
            buckets.setdefault((c["document_id"],theme_slug(tag)),[]).append(c)
    used=set()
    groups=[]
    for (doc,theme),members in sorted(buckets.items(),key=lambda pair:pair[0]):
        unique=[c for c in members if c["id"] not in used]
        if len(unique)<2:
            continue
        # Up to four complete concepts per LLM call. No concept appears
        # in more than one merge decision; order is reproducible.
        for pos in range(0,len(unique),4):
            batch=unique[pos:pos+4]
            if len(batch)<2:
                continue
            ids=[c["id"] for c in batch]
            digest=hashlib.sha256(json.dumps(
                [(c["id"],c["sha256"]) for c in batch],
                sort_keys=True
            ).encode()).hexdigest()[:16]
            key=f"{doc}--{theme[:32]}--{digest}"
            if not re.fullmatch(r"[a-z0-9_-]+",key):
                raise ValueError("Unsafe merge batch identifier.")
            groups.append({
                "key":key,"document_id":doc,"theme":theme,
                "members":[{
                    "id":c["id"],"title":c["title"],
                    "path":"okf-v4/b-reviewed/"+c["path"],
                    "sha256":c["sha256"],
                    "summary":c.get("summary",""),
                    "knowledge_item_ids":c["knowledge_item_ids"],
                } for c in batch]
            })
            used.update(ids)
    return {"schema":"okf.merge-tasks.v1","status":"ok",
            "count":len(groups),"groups":groups}


def main() -> None:
    json.load(sys.stdin)
    print(json.dumps(prepare(Path(".").resolve()),ensure_ascii=False))


if __name__=="__main__":
    main()
