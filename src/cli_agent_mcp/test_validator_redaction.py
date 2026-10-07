from __future__ import annotations

import io
import json
import re
import tarfile
import tomllib
from collections import deque
from collections.abc import Iterable, Iterator, Mapping
from pathlib import Path
from typing import Any

import javaproperties
import yaml
from dotenv import dotenv_values

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
_PRIVATE_KEY_END_PREFIX = "-----END "
_TEXT_CONFIG_SUFFIXES = {".env", ".properties", ".yaml", ".yml", ".json", ".toml"}
_MAX_DISCOVERED_SECRET_VALUES = 4096
_MAX_DISCOVERED_SECRET_CHARS = 1024 * 1024
_MAX_STRUCTURED_NODES = 100_000
_SUPPRESSED_OUTPUT = (
    "[Testausgabe unterdrückt: Die Secret-Erkennung konnte nicht vollständig "
    "und sicher durchgeführt werden. Der Test wurde ausgeführt, aber seine "
    "Ausgabe wird nicht an das Modell zurückgegeben.]"
)


class SecretDiscoveryLimitError(ValueError):
    """Raised when bounded secret discovery cannot safely retain more values."""


def _candidate_config_file(path: Path) -> bool:
    name = path.name.casefold()
    if name == ".env" or name.startswith(".env."):
        return True
    return path.suffix.casefold() in _TEXT_CONFIG_SUFFIXES


def _is_sensitive_key(value: object) -> bool:
    return isinstance(value, str) and _SENSITIVE_KEY.search(value) is not None


def _contains_sensitive_key_hint(text: str) -> bool:
    # This is deliberately conservative and is only used when a format-aware
    # parser cannot safely parse a candidate config file. False positives only
    # suppress returned logs; false negatives could expose a secret.
    return _SENSITIVE_KEY.search(text) is not None


def _iter_scalar_values(value: object) -> Iterator[str]:
    stack: list[object] = [value]
    seen: set[int] = set()
    visited = 0

    while stack:
        current = stack.pop()
        visited += 1
        if visited > _MAX_STRUCTURED_NODES:
            raise SecretDiscoveryLimitError(
                "Konfigurationsstruktur ist zu groß für sichere Secret-Erkennung."
            )

        if current is None:
            continue

        if isinstance(current, Mapping):
            identity = id(current)
            if identity in seen:
                continue
            seen.add(identity)
            stack.extend(current.values())
            continue

        if isinstance(current, (list, tuple, set)):
            identity = id(current)
            if identity in seen:
                continue
            seen.add(identity)
            stack.extend(current)
            continue

        if isinstance(current, bytes):
            try:
                yield current.decode("utf-8")
            except UnicodeDecodeError:
                yield current.hex()
            continue

        yield str(current)


def _iter_mapping_secret_values(value: object) -> Iterator[str]:
    stack: list[object] = [value]
    seen: set[int] = set()
    visited = 0

    while stack:
        current = stack.pop()
        visited += 1
        if visited > _MAX_STRUCTURED_NODES:
            raise SecretDiscoveryLimitError(
                "Konfigurationsstruktur ist zu groß für sichere Secret-Erkennung."
            )

        if isinstance(current, Mapping):
            identity = id(current)
            if identity in seen:
                continue
            seen.add(identity)
            for key, item in current.items():
                if _is_sensitive_key(key):
                    yield from _iter_scalar_values(item)
                if isinstance(item, (Mapping, list, tuple, set)):
                    stack.append(item)
        elif isinstance(current, (list, tuple, set)):
            identity = id(current)
            if identity in seen:
                continue
            seen.add(identity)
            stack.extend(current)


def _iter_yaml_secret_values(text: str) -> Iterator[str]:
    for document in yaml.safe_load_all(text):
        if document is not None:
            yield from _iter_mapping_secret_values(document)


def _parse_structured_secret_values(path: Path, text: str) -> tuple[str, ...]:
    suffix = path.suffix.casefold()
    name = path.name.casefold()

    try:
        if suffix == ".json":
            parsed: Any = json.loads(text)
            return tuple(_iter_mapping_secret_values(parsed))
        if suffix == ".toml":
            parsed = tomllib.loads(text)
            return tuple(_iter_mapping_secret_values(parsed))
        if suffix in {".yaml", ".yml"}:
            return tuple(_iter_yaml_secret_values(text))
        if suffix == ".properties":
            parsed = javaproperties.loads(text)
            return tuple(_iter_mapping_secret_values(parsed))
        if name == ".env" or name.startswith(".env."):
            parsed = dotenv_values(stream=io.StringIO(text), interpolate=False)
            return tuple(_iter_mapping_secret_values(parsed))
    except SecretDiscoveryLimitError:
        raise
    except Exception as exc:
        if _contains_sensitive_key_hint(text):
            raise SecretDiscoveryLimitError(
                f"{path.name} konnte trotz möglicher sensitiver Schlüssel "
                "nicht sicher geparst werden."
            ) from exc
        return ()

    return ()


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

            for candidate in _parse_structured_secret_values(path, text):
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


def _pem_private_key_label(line: str) -> str | None:
    marker = line.strip()
    if not marker.startswith(_PRIVATE_KEY_BEGIN) or not marker.endswith("-----"):
        return None
    label = marker[len(_PRIVATE_KEY_BEGIN) : -5].strip()
    if not label.endswith("PRIVATE KEY"):
        return None
    return label


def _redact_private_keys(value: str) -> str:
    """Redact PEM private-key blocks with a linear line-oriented scan."""
    result: list[str] = []
    pending: list[str] = []
    active_label: str | None = None

    for line in value.splitlines(keepends=True):
        label = _pem_private_key_label(line)
        if active_label is None:
            if label is None:
                result.append(line)
            else:
                active_label = label
                pending = [line]
            continue

        if line.strip() == f"{_PRIVATE_KEY_END_PREFIX}{active_label}-----":
            newline = "\n" if line.endswith(("\n", "\r")) else ""
            result.append("<redacted-private-key>" + newline)
            pending = []
            active_label = None
            continue

        if label is not None:
            result.extend(pending)
            active_label = label
            pending = [line]
            continue

        pending.append(line)

    if pending:
        result.extend(pending)
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
