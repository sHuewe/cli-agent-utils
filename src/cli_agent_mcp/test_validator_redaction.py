from __future__ import annotations

import io
import re
import tarfile
from collections.abc import Iterable
from pathlib import Path

_SENSITIVE_KEY = re.compile(
    r"(?i)(?:password|passwd|secret|token|api[_-]?key|access[_-]?key|"
    r"private[_-]?key|credential)"
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


def _secret_values_from_line(line: str) -> tuple[str, ...]:
    colon = line.find(":")
    equals = line.find("=")
    delimiters = [index for index in (colon, equals) if index >= 0]
    if not delimiters:
        return ()

    index = min(delimiters)
    key = line[:index].strip().strip("'\"{}[] ")
    if key.casefold().startswith("export "):
        key = key[7:].strip()
    if not key or not _SENSITIVE_KEY.search(key):
        return ()

    value = line[index + 1 :].strip()
    if not value:
        return ()

    if value[0] in {"'", '"'}:
        quote = value[0]
        value = value[1:]
        end = value.find(quote)
        if end >= 0:
            value = value[:end]
    else:
        for separator in (" #", ";", ",", "}", "]"):
            position = value.find(separator)
            if position >= 0:
                value = value[:position]

    value = value.strip().strip("'\"")
    if len(value) < 4:
        return ()
    return (value,)


def discover_secret_values(
    archive: bytes,
    *,
    max_file_bytes: int = 16 * 1024 * 1024,
) -> tuple[str, ...]:
    values: set[str] = set()
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as tar:
        for member in tar:
            path = Path(member.name)
            if not member.isfile() or not _candidate_config_file(path):
                continue
            if member.size > max_file_bytes:
                continue
            extracted = tar.extractfile(member)
            if extracted is None:
                continue
            content = extracted.read(max_file_bytes + 1)
            if len(content) > max_file_bytes:
                continue
            text = content.decode("utf-8", errors="replace")
            for line in text.splitlines():
                values.update(_secret_values_from_line(line))
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
