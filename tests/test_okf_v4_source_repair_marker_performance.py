"""Long source descriptions must not control repair task identity."""
from pathlib import Path
import sys
import copy

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "flow/okf/v4"))
from source_repair import _reconcile_tasks


def test_many_markers_and_large_description_are_advisory():
    expected = {"schema": "okf.source-repair-tasks.v1", "status": "ok",
                "count": 1, "concepts": [{
                    "key": "stable-key", "id": "example:a", "kind": "missing",
                    "title": "", "path": None, "source": "source.md",
                    "knowledge_item_ids": ["example:k1"],
                    "knowledge_items": [{
                        "id": "example:k1",
                        "description": r"\\ufffd" * 3000,
                        "evidence_ranges": [{
                            "doctrine": "source.md",
                            "start_line": 10, "end_line": 11,
                        }],
                    }],
                    "feedback": {"status": "none"},
                }]}
    incoming = copy.deepcopy(expected)
    incoming["concepts"][0]["knowledge_items"][0]["description"] = "text" * 1000
    incoming["concepts"][0]["feedback"]["status"] = "transport-change"
    assert _reconcile_tasks(incoming, expected) == expected
    incoming["concepts"][0]["knowledge_items"][0]["evidence_ranges"][0]["start_line"] = 30
    with pytest.raises(ValueError, match="identity/provenance mismatch"):
        _reconcile_tasks(incoming, expected)
