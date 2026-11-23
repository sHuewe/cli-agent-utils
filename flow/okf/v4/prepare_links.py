"""Prepare semantic link candidates from the certified final B inventory."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

from phase_b_contract import checked_b


def prepare(workspace: Path) -> dict:
    _, catalog, _ = checked_b(workspace, root="okf-v4/phase-b", stage="B")
    concepts=sorted(catalog["concepts"],key=lambda c:c["id"])
    tasks=[]
    for source in concepts:
        s_tags={tag.casefold() for tag in source.get("tags",[])}
        peers=sorted(
            (c for c in concepts if c["id"]!=source["id"]),
            key=lambda c: (
                -len(s_tags & {t.casefold() for t in c.get("tags",[])}),
                c["document_id"]==source["document_id"],
                c["id"],
            ),
        )
        # No unbounded corpus prompt: only candidates with at least one
        # shared semantic tag, max eight per source concept.
        peers=[p for p in peers if s_tags & {t.casefold() for t in p.get("tags",[])}][:8]
        candidates=[{
            "id":p["id"],"title":p["title"],"summary":p["summary"],
            "document_id":p["document_id"],"tags":p["tags"],
        } for p in peers]
        fingerprint=hashlib.sha256(json.dumps(
            {"source":source["id"],"sha":source["sha256"],
             "summary":source["summary"],"candidates":candidates},
            ensure_ascii=False,sort_keys=True
        ).encode()).hexdigest()[:16]
        key=source["id"].replace(":","--")+"--"+fingerprint
        tasks.append({
            "id":source["id"],"key":key,"title":source["title"],
            "summary":source["summary"],"tags":source["tags"],
            "candidates":candidates,
        })
    return {"schema":"okf.link-tasks.v1","status":"ok",
            "count":len(tasks),"concepts":tasks}


def main() -> None:
    json.load(sys.stdin)
    print(json.dumps(prepare(Path(".").resolve()),ensure_ascii=False))


if __name__=="__main__":
    main()
