from __future__ import annotations

import io
import json
import re
import tarfile
from collections import deque
from collections.abc import Iterable, Iterator
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
)
_PRIVATE_KEY_BEGIN = "-----BEGIN "
_PRIVATE_KEY_SUFFIX = "PRIVATE KEY-----"
_PRIVATE_KEY_END_PREFIX = "-----END "
_TEXT_CONFIG_SUFFIXES = {".env", ".properties", ".yaml", ".yml", ".json", ".toml"}
_MAX_DISCOVERED_SECRET_VALUES = 4096
_MAX_DISCOVERED_SECRET_CHARS = 1024 * 1024
_SUPPRESSED_OUTPUT = (
    "[Testausgabe unterdrückt: Die Secret-Erkennung hat ihr Sicherheitslimit "
    "erreicht. Der Test wurde ausgeführt, aber seine Ausgabe wird nicht an "
    "das Modell zurückgegeben.]"
)


class SecretDiscoveryLimitError(ValueError):
    """Raised when bounded secret discovery cannot safely retain more values."""


def _candidate_config_file(path: Path) -> bool:
    name = path.name.casefold()
    if name == ".env" or name.startswith(".env."):
        return True
    return path.suffix.casefold() in _TEXT_CONFIG_SUFFIXES


def _iter_secret_values_from_line(line: str) -> Iterator[str]:
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
                value_end = value_start
                escaped = False
                while value_end < length:
                    current = line[value_end]
                    if current == quote and not escaped:
                        break
                    if current == "\\" and not escaped:
                        escaped = True
                    else:
                        escaped = False
                    value_end += 1
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
                yield value
            index = max(
                index + 1,
                value_end + (1 if quote is not None and value_end < length else 0),
            )
            continue

        index += 1


def _secret_values_from_line(line: str) -> tuple[str, ...]:
    """Best-effort parser for simple assignment-style text configuration."""
    return tuple(_iter_secret_values_from_line(line))


def _iter_json_secret_values(value: object) -> Iterator[str]:
    stack = [value]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            for key, item in current.items():
                if isinstance(key, str) and _SENSITIVE_KEY.search(key):
                    if isinstance(item, str) and len(item) >= 4:
                        yield item
                if isinstance(item, (dict, list)):
                    stack.append(item)
        elif isinstance(current, list):
            stack.extend(
                item for item in current if isinstance(item, (dict, list))
            )


def discover_secret_values(
    archive: bytes,
    *,
    max_file_bytes: int = 16 * 1024 * 1024,
    max_secret_values: int = _MAX_DISCOVERED_SECRET_VALUES,
    max_secret_chars: int = _MAX_DISCOVERED_SECRET_CHARS,
) -> tuple[str, ...]:
    if max_file_bytes <= 0 or max_secret_values <= 0 or max_secret_chars <= 0:
        raise ValueError("Secret-Erkennungsgrenzen müssen positiv sein.")

    values: set[str] = set()
    total_secret_chars = 0

    def add(candidate: str) -> None:
        nonlocal total_secret_chars
        if len(candidate) < 4 or candidate in values:
            return
        if (
            len(values) >= max_secret_values
            or total_secret_chars + len(candidate) > max_secret_chars
        ):
            raise SecretDiscoveryLimitError(
                "Zu viele bzw. zu große Secret-Werte für sichere Redaction."
            )
        values.add(candidate)
        total_secret_chars += len(candidate)

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

            if path.suffix.casefold() == ".json":
                try:
                    parsed = json.loads(text)
                except (json.JSONDecodeError, RecursionError):
                    parsed = None
                if parsed is not None:
                    for candidate in _iter_json_secret_values(parsed):
                        add(candidate)
                    continue

            for line in text.splitlines():
                for candidate in _iter_secret_values_from_line(line):
                    add(candidate)

    return tuple(sorted(values, key=len, reverse=True))


class _ExactSecretMatcher:
    """Linear-time exact multi-pattern matcher used for output redaction."""

    def __init__(self, values: Iterable[str]) -> None:
        self._next: list[dict[str, int]] = [{}]
        self._failure: list[int] = [0]
        self._output_len: list[int] = [0]

        for value in values:
            state = 0
            for char in value:
                child = self._next[state].get(char)
                if child is None:
                    child = len(self._next)
                    self._next[state][char] = child
                    self._next.append({})
                    self._failure.append(0)
                    self._output_len.append(0)
                state = child
            self._output_len[state] = max(self._output_len[state], len(value))

        queue: deque[int] = deque()
        for state in self._next[0].values():
            queue.append(state)

        while queue:
            state = queue.popleft()
            for char, child in self._next[state].items():
                queue.append(child)
                fallback = self._failure[state]
                while fallback and char not in self._next[fallback]:
                    fallback = self._failure[fallback]
                self._failure[child] = self._next[fallback].get(char, 0)
                self._output_len[child] = max(
                    self._output_len[child],
                    self._output_len[self._failure[child]],
                )

    def redact(self, value: str) -> str:
        if len(self._next) == 1 or not value:
            return value

        intervals: list[tuple[int, int]] = []
        state = 0
        for index, char in enumerate(value):
            while state and char not in self._next[state]:
                state = self._failure[state]
            state = self._next[state].get(char, 0)
            match_len = self._output_len[state]
            if not match_len:
                continue

            start = index - match_len + 1
            end = index + 1
            while intervals and start <= intervals[-1][1]:
                previous_start, previous_end = intervals.pop()
                start = min(start, previous_start)
                end = max(end, previous_end)
            intervals.append((start, end))

        if not intervals:
            return value

        chunks: list[str] = []
        cursor = 0
        for start, end in intervals:
            chunks.append(value[cursor:start])
            chunks.append("<redacted>")
            cursor = end
        chunks.append(value[cursor:])
        return "".join(chunks)



def _redact_private_keys(value: str) -> str:
    """Redact PEM private-key blocks with one forward marker scan."""
    result: list[str] = []
    cursor = 0
    scan = 0
    active_start: int | None = None
    active_label: str | None = None

    while True:
        marker_start = value.find("-----", scan)
        if marker_start < 0:
            break
        marker_end_start = value.find("-----", marker_start + 5)
        if marker_end_start < 0:
            break
        marker_end = marker_end_start + 5
        marker = value[marker_start:marker_end]

        if active_label is None:
            if marker.startswith(_PRIVATE_KEY_BEGIN):
                label = marker[
                    len(_PRIVATE_KEY_BEGIN) : -5
                ].strip()
                if label.endswith("PRIVATE KEY"):
                    active_start = marker_start
                    active_label = label
        elif marker == f"{_PRIVATE_KEY_END_PREFIX}{active_label}-----":
            assert active_start is not None
            result.append(value[cursor:active_start])
            result.append("<redacted-private-key>")
            cursor = marker_end
            active_start = None
            active_label = None

        scan = marker_end

    result.append(value[cursor:])
    return "".join(result)

class OutputRedactor:
    def __init__(
        self,
        secret_values: Iterable[str] = (),
        *,
        suppress_output: bool = False,
    ) -> None:
        values = {
            value
            for value in secret_values
            if isinstance(value, str) and len(value) >= 4
        }
        self._matcher = _ExactSecretMatcher(values)
        self._suppress_output = suppress_output

    @property
    def suppresses_output(self) -> bool:
        return self._suppress_output

    def redact(self, value: str) -> str:
        if self._suppress_output:
            return _SUPPRESSED_OUTPUT

        text = self._matcher.redact(value)
        text = _GENERIC_PATTERNS[0].sub(r"\1<redacted>", text)
        text = _GENERIC_PATTERNS[1].sub(r"\1<redacted>", text)
        return _redact_private_keys(text)
