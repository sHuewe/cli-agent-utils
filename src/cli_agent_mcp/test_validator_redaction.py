from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

_SENSITIVE_KEY = re.compile(
    r"(?i)(?:password|passwd|secret|token|api[_-]?key|access[_-]?key|"
    r"private[_-]?key|credential)"
)
_ASSIGNMENT = re.compile(
    r"""(?ix)
    ["']?([A-Za-z0-9_.-]*(?:password|passwd|secret|token|api[_-]?key|
    access[_-]?key|private[_-]?key|credential)[A-Za-z0-9_.-]*)["']?
    \s*[:=]\s*
    (?:
        ["']([^"'\r\n]{4,})["']
        |
        ([^\s#;,}{\]\[][^\r\n#;,}{\]\[]*)
    )
    """
)
_GENERIC_PATTERNS = (
    re.compile(r"(?i)(Authorization\s*:\s*Bearer\s+)[^\s]+"),
    re.compile(
        r"(?i)((?:password|passwd|secret|token|api[_-]?key|access[_-]?key|"
        r"credential)\s*[:=]\s*)[^\s,;]+"
    ),
    re.compile(
        r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?"
        r"-----END [A-Z0-9 ]*PRIVATE KEY-----",
        re.DOTALL,
    ),
)
_TEXT_CONFIG_SUFFIXES = {".env", ".properties", ".yaml", ".yml", ".json", ".toml"}


def _candidate_config_file(path: Path) -> bool:
    name = path.name.casefold()
    if name == ".env" or name.startswith(".env."):
        return True
    return path.suffix.casefold() in _TEXT_CONFIG_SUFFIXES


def discover_secret_values(
    project: Path,
    files: Iterable[Path],
    *,
    max_file_bytes: int = 1_000_000,
) -> tuple[str, ...]:
    values: set[str] = set()
    for path in files:
        if not _candidate_config_file(path):
            continue
        try:
            if path.stat().st_size > max_file_bytes:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for match in _ASSIGNMENT.finditer(text):
            key = match.group(1)
            if not _SENSITIVE_KEY.search(key):
                continue
            value = (match.group(2) or match.group(3) or "").strip().strip("'\"")
            if len(value) >= 4:
                values.add(value)
    return tuple(sorted(values, key=len, reverse=True))


class OutputRedactor:
    def __init__(self, secret_values: Iterable[str] = ()) -> None:
        self._secret_values = tuple(
            sorted(
                {
                    value
                    for value in secret_values
                    if isinstance(value, str) and len(value) >= 4
                },
                key=len,
                reverse=True,
            )
        )

    def redact(self, value: str) -> str:
        text = value
        for secret in self._secret_values:
            text = text.replace(secret, "<redacted>")
        text = _GENERIC_PATTERNS[0].sub(r"\1<redacted>", text)
        text = _GENERIC_PATTERNS[1].sub(r"\1<redacted>", text)
        text = _GENERIC_PATTERNS[2].sub("<redacted-private-key>", text)
        return text
