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
    values: list[str] = []
    key_chars = set(
        "abcdefghijklmnopqrstuvwxyz"
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        "0123456789_.-"
    )
    length = len(line)
    index = 0

    while index < length:
        char = line[index]
        if char not in {":", "="}:
            index += 1
            continue

        left = index - 1
        while left >= 0 and line[left].isspace():
            left -= 1
        if left >= 0 and line[left] in {"'", '"'}:
            left -= 1
        key_end = left + 1
        while left >= 0 and line[left] in key_chars:
            left -= 1
        key = line[left + 1 : key_end]

        right = index + 1
        while right < length and line[right].isspace():
            right += 1

        if key and _SENSITIVE_KEY.search(key) and right < length:
            quote = line[right] if line[right] in {"'", '"'} else None
            if quote is not None:
                value_start = right + 1
                value_end = line.find(quote, value_start)
                if value_end < 0:
                    value_end = length
            else:
                value_start = right
                value_end = value_start
                while (
                    value_end < length
                    and not line[value_end].isspace()
                    and line[value_end] not in "#;,}{]["
                ):
                    value_end += 1

            value = line[value_start:value_end].strip()
            if len(value) >= 4:
                values.append(value)
            index = max(index + 1, value_end + (1 if quote is not None else 0))
            continue

        index += 1

    return tuple(values)


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
