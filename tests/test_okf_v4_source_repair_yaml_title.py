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


def test_repairs_unquoted_description_colon_and_preserves_markdown():
    proposal = (
        "---\ntype: concept\n"
        "title: Mission command guidelines\n"
        "description: Required by mission command: NATO-wide definition\n"
        "---\n" + SUBSTANTIVE_TEXT
    )
    result = _source_repair_markdown("Mission command guidelines", proposal)
    fixed = result.decode("utf-8")
    assert (
        'description: "Required by mission command: NATO-wide definition"'
        in fixed
    )
    assert fixed.endswith(SUBSTANTIVE_TEXT)
    assert yaml.safe_load(fixed.split("---", 2)[1])["description"] == (
        "Required by mission command: NATO-wide definition"
    )


def test_repairs_title_and_description_together():
    proposal = (
        "---\ntype: concept\n"
        f"title: {TITLE}\n"
        "description: Priority context: commander selection\n"
        "---\n" + SUBSTANTIVE_TEXT
    )
    fixed = _source_repair_markdown(TITLE, proposal).decode("utf-8")
    assert 'title: "Document front matter: TOC structure' in fixed
    assert 'description: "Priority context: commander selection"' in fixed
    assert fixed.endswith(SUBSTANTIVE_TEXT)


def test_refuses_duplicate_unsafe_description_and_other_invalid_yaml():
    proposal = (
        "---\ntype: concept\n"
        "title: Mission command guidelines\n"
        "description: Mission command: commander selection\n"
        "description: Mission command: mission outcome\n"
        "---\n" + SUBSTANTIVE_TEXT
    )
    with pytest.raises(ValueError, match="invalid YAML frontmatter"):
        _source_repair_markdown("Mission command guidelines", proposal)

    proposal = (
        "---\ntype: [concept\n"
        "title: Mission command guidelines\n"
        "description: Mission command: commander selection\n"
        "---\n" + SUBSTANTIVE_TEXT
    )
    with pytest.raises(ValueError, match="invalid YAML frontmatter"):
        _source_repair_markdown("Mission command guidelines", proposal)


def test_does_not_rewrite_nested_yaml_or_structured_description():
    proposal = (
        "---\ntype: concept\n"
        "title: Mission command guidelines\n"
        "description: [Mission command: commander selection\n"
        "---\n" + SUBSTANTIVE_TEXT
    )
    with pytest.raises(ValueError, match="invalid YAML frontmatter"):
        _source_repair_markdown("Mission command guidelines", proposal)

    proposal = (
        "---\ntype: concept\n"
        "title: Mission command guidelines\n"
        "metadata:\n"
        "  description: Mission command: commander selection\n"
        "---\n" + SUBSTANTIVE_TEXT
    )
    with pytest.raises(ValueError, match="invalid YAML frontmatter"):
        _source_repair_markdown("Mission command guidelines", proposal)


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
