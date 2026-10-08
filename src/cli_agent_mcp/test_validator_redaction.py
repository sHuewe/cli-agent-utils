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
from dotenv.parser import parse_stream

_SENSITIVE_KEY = re.compile(
    r"(?i)(?:password|passwd|secret|token|api[_.-]?key|access[_.-]?key|"
    r"private[_.-]?key|credential)"
)
_GENERIC_PATTERNS = (
    re.compile(r"(?i)(Authorization\s*:\s*Bearer\s+)[^\s]+"),
    re.compile(
        r"(?i)((?:password|passwd|secret|token|api[_.-]?key|access[_.-]?key|"
        r"credential)\s*[:=]\s*)[^\s,;]+"
    ),
)
_PRIVATE_KEY_BEGIN = "-----BEGIN "
_PRIVATE_KEY_END_PREFIX = "-----END "
_REDACTION_MARKER = "⟦x⟧"
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
    return _SENSITIVE_KEY.search(text) is not None


def _contains_sensitive_key_hint_bytes(content: bytes) -> bool:
    for encoding in ("utf-8-sig", "utf-16", "latin-1"):
        try:
            if _contains_sensitive_key_hint(content.decode(encoding)):
                return True
        except UnicodeError:
            continue
    return False


def _consume_node_budget(budget: list[int], amount: int = 1) -> None:
    budget[0] -= amount
    if budget[0] < 0:
        raise SecretDiscoveryLimitError(
            "Konfigurationsstruktur ist zu groß für sichere Secret-Erkennung."
        )


def _iter_scalar_values(
    value: object,
    *,
    budget: list[int],
) -> Iterator[str]:
    stack: list[object] = [value]
    seen: set[int] = set()

    while stack:
        current = stack.pop()
        _consume_node_budget(budget)

        if current is None:
            continue

        if isinstance(current, Mapping):
            identity = id(current)
            if identity in seen:
                continue
            seen.add(identity)
            _consume_node_budget(budget, len(current))
            stack.extend(current.values())
            continue

        if isinstance(current, (list, tuple, set)):
            identity = id(current)
            if identity in seen:
                continue
            seen.add(identity)
            _consume_node_budget(budget, len(current))
            stack.extend(current)
            continue

        if isinstance(current, bytes):
            try:
                yield current.decode("utf-8")
            except UnicodeDecodeError:
                yield current.hex()
            continue

        yield str(current)


def _iter_mapping_secret_values(
    value: object,
    *,
    budget: list[int] | None = None,
) -> Iterator[str]:
    shared_budget = budget if budget is not None else [_MAX_STRUCTURED_NODES]
    stack: list[object] = [value]
    seen: set[int] = set()

    while stack:
        current = stack.pop()
        _consume_node_budget(shared_budget)

        if isinstance(current, Mapping):
            identity = id(current)
            if identity in seen:
                continue
            seen.add(identity)
            _consume_node_budget(shared_budget, len(current))
            for key, item in current.items():
                if _is_sensitive_key(key):
                    yield from _iter_scalar_values(
                        item,
                        budget=shared_budget,
                    )
                if isinstance(item, (Mapping, list, tuple, set)):
                    stack.append(item)
        elif isinstance(current, (list, tuple, set)):
            identity = id(current)
            if identity in seen:
                continue
            seen.add(identity)
            _consume_node_budget(shared_budget, len(current))
            stack.extend(current)


def _iter_yaml_secret_values(content: bytes) -> Iterator[str]:
    budget = [_MAX_STRUCTURED_NODES]
    for document in yaml.safe_load_all(content):
        if document is not None:
            yield from _iter_mapping_secret_values(
                document,
                budget=budget,
            )


def _parse_dotenv_secret_values(text: str) -> tuple[str, ...]:
    values: list[str] = []
    for binding in parse_stream(io.StringIO(text)):
        if binding.error:
            if _contains_sensitive_key_hint(binding.original.string):
                raise SecretDiscoveryLimitError(
                    "Eine sensitive .env-Zeile konnte nicht sicher geparst werden."
                )
            continue
        if (
            binding.key is not None
            and _is_sensitive_key(binding.key)
            and binding.value is not None
        ):
            if "${" in binding.value:
                raise SecretDiscoveryLimitError(
                    "Eine sensitive .env-Zeile verwendet Variableninterpolation; "
                    "sichere Secret-Erkennung ist nicht vollständig möglich."
                )
            values.extend(
                _iter_scalar_values(
                    binding.value,
                    budget=[_MAX_STRUCTURED_NODES],
                )
            )
    return tuple(values)


def _parse_structured_secret_values(path: Path, content: bytes) -> tuple[str, ...]:
    suffix = path.suffix.casefold()
    name = path.name.casefold()

    try:
        if suffix == ".json":
            parsed: Any = json.loads(content)
            return tuple(_iter_mapping_secret_values(parsed))
        if suffix == ".toml":
            parsed = tomllib.load(io.BytesIO(content))
            return tuple(_iter_mapping_secret_values(parsed))
        if suffix in {".yaml", ".yml"}:
            return tuple(_iter_yaml_secret_values(content))
        if suffix == ".properties":
            parsed = javaproperties.loads(content)
            return tuple(_iter_mapping_secret_values(parsed))
        if name == ".env" or name.startswith(".env."):
            text = content.decode("utf-8-sig")
            return _parse_dotenv_secret_values(text)
    except SecretDiscoveryLimitError:
        raise
    except Exception as exc:
        if _contains_sensitive_key_hint_bytes(content):
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
        if candidate in values:
            return
        if not candidate:
            return
        if len(candidate) < 4:
            raise SecretDiscoveryLimitError(
                "Ein sensitiver Wert ist zu kurz für sichere exakte Redaction."
            )
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
            for candidate in _parse_structured_secret_values(path, content):
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
            chunks.append(_REDACTION_MARKER)
            cursor = end
        chunks.append(value[cursor:])
        return "".join(chunks)


def _find_pem_private_key_begin(line: str) -> tuple[str, int, int] | None:
    search_from = 0
    while True:
        start = line.find(_PRIVATE_KEY_BEGIN, search_from)
        if start < 0:
            return None
        label_end = line.find("-----", start + len(_PRIVATE_KEY_BEGIN))
        if label_end < 0:
            return None
        label = line[start + len(_PRIVATE_KEY_BEGIN) : label_end].strip()
        if label.endswith("PRIVATE KEY"):
            return label, start, label_end + 5
        search_from = start + 1


def _find_pem_private_key_end(
    line: str,
    label: str,
    *,
    start: int = 0,
) -> tuple[int, int] | None:
    marker = f"{_PRIVATE_KEY_END_PREFIX}{label}-----"
    marker_start = line.find(marker, start)
    if marker_start < 0:
        return None
    return marker_start, marker_start + len(marker)


def _line_ending(line: str) -> str:
    if line.endswith("\r\n"):
        return "\r\n"
    if line.endswith("\n"):
        return "\n"
    if line.endswith("\r"):
        return "\r"
    return ""


def _redact_private_keys(value: str) -> str:
    """Redact PEM private-key blocks even when log lines add prefixes."""
    result: list[str] = []
    active_label: str | None = None

    for line in value.splitlines(keepends=True):
        if active_label is None:
            begin = _find_pem_private_key_begin(line)
            if begin is None:
                result.append(line)
                continue

            label, marker_start, marker_end = begin
            result.append(line[:marker_start])
            result.append(_REDACTION_MARKER)

            end = _find_pem_private_key_end(line, label, start=marker_end)
            if end is not None:
                result.append(line[end[1] :])
                continue

            active_label = label
            ending = _line_ending(line)
            if ending:
                result.append(ending)
            continue

        end = _find_pem_private_key_end(line, active_label)
        if end is not None:
            result.append(line[end[1] :])
            active_label = None
            continue

        ending = _line_ending(line)
        if ending:
            result.append(ending)

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

        text = _redact_private_keys(value)
        text = self._matcher.redact(text)
        text = _GENERIC_PATTERNS[0].sub(
            lambda match: match.group(1),
            text,
        )
        return _GENERIC_PATTERNS[1].sub(
            lambda match: match.group(1),
            text,
        )
