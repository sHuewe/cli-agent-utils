"""Source repair must safely quote only an exact malformed YAML title."""
from pathlib import Path
import sys

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "flow/okf/v4"))
from source_repair import _source_repair_markdown


TITLE = "Document front matter: TOC structure and page classification"
SUBSTANTIVE_TEXT = (
    "# Document front matter\n\n"
    "This concept specifies the structure and page classification "
    "requirements for the document's table of contents and metadata.\n"
)


def test_repairs_exact_unquoted_colon_title_without_changing_body():
    proposal = (
        "---\ntype: concept\n"
        f"title: {TITLE}\n"
        "tags: []\n---\n" + SUBSTANTIVE_TEXT
    )
    fixed = _source_repair_markdown(TITLE, proposal).decode("utf-8")
    assert fixed.startswith(
        '---\ntype: concept\ntitle: "Document front matter: '
        'TOC structure and page classification"\ntags: []\n---\n'
    )
    assert fixed.endswith(SUBSTANTIVE_TEXT)
    assert yaml.safe_load(fixed.split("---", 2)[1])["title"] == TITLE


def test_preserves_already_valid_quoted_title_and_unicode():
    title = 'Führung: Qualitätsprüfung "A"'
    proposal = (
        "---\ntype: concept\n"
        "title: " + __import__("json").dumps(title, ensure_ascii=False)
        + "\n---\n" + SUBSTANTIVE_TEXT
    )
    assert _source_repair_markdown(title, proposal) == proposal.encode("utf-8")


@pytest.mark.parametrize("title_line", [
    "title: Another: Title",  # Not the exact proposal title
    "title: Something else",
    "  title: Document front matter: TOC structure and page classification",
])
def test_refuses_nonmatching_title_lines(title_line):
    proposal = f"---\ntype: concept\n{title_line}\n---\n" + SUBSTANTIVE_TEXT
    with pytest.raises(ValueError, match="frontmatter"):
        _source_repair_markdown(TITLE, proposal)


def test_refuses_other_invalid_yaml_even_with_matching_title():
    proposal = (
        "---\ntype: [concept\n"
        f"title: {TITLE}\n"
        "---\n" + SUBSTANTIVE_TEXT
    )
    with pytest.raises(ValueError, match="invalid YAML frontmatter"):
        _source_repair_markdown(TITLE, proposal)


def test_preserves_strict_type_requirement():
    proposal = (
        "---\ntype: [concept]\n"
        f"title: {TITLE}\n"
        "---\n" + SUBSTANTIVE_TEXT
    )
    with pytest.raises(ValueError, match="nonempty string type"):
        _source_repair_markdown(TITLE, proposal)
