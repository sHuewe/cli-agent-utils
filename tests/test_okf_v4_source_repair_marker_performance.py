from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "flow/okf/v4"))
from source_repair import _same_except_replacement_escape

def test_many_adjacent_markers():
    path = "$.knowledge_items[1].description"
    expected = "\\ufffd" * 12 + "!"
    assert not _same_except_replacement_escape("a" * 36 + "?", expected, path)
    assert _same_except_replacement_escape("a" * 36 + "!", expected, path)
    assert not _same_except_replacement_escape("a" * 73 + "!", expected, path)

def test_literally_unchanged_spans():
    path = "$.knowledge_items[1].description"
    expected = "prefix\\ufffdmiddle\\ufffdsuf"
    assert _same_except_replacement_escape("prefixXYZmiddleQsuf", expected, path)
    assert not _same_except_replacement_escape("prefixXYZMIDDLEQsuf", expected, path)
