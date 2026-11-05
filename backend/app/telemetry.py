"""PHI-safe structured logging and process metrics."""

from __future__ import annotations

import json
import logging
import threading
import time
from collections import defaultdict
from collections.abc import Mapping
from typing import Any


SAFE_CONTEXT_FIELDS = ("request_id", "user_id", "organization_id")
SAFE_LABEL_KEYS = {"method", "route", "status", "operation", "stage", "provider", "result"}


class RedactionFilter(logging.Filter):
    """Prevent log records from carrying free-form messages or unsafe fields."""

    def filter(self, record: logging.LogRecord) -> bool:
        for field in SAFE_CONTEXT_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                setattr(record, field, str(value)[:128])
        record.telemetry_event = str(getattr(record, "telemetry_event", record.name))[:128]
        return True


class JsonLogFormatter(logging.Formatter):
    """Emit only allowlisted structured fields; record messages are never serialized."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "event": getattr(record, "telemetry_event", record.name),
        }
        for field in SAFE_CONTEXT_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = str(value)[:128]
        return json.dumps(payload, separators=(",", ":"), sort_keys=True)


class MetricsStore:
    """Small dependency-free Prometheus text registry with fixed label names."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: defaultdict[tuple[str, tuple[tuple[str, str], ...]], float] = defaultdict(float)
        self._gauges: dict[tuple[str, tuple[tuple[str, str], ...]], float] = {}
        self._histograms: defaultdict[tuple[str, tuple[tuple[str, str], ...]], list[float]] = defaultdict(list)

    def reset(self) -> None:
        with self._lock:
            self._counters.clear()
            self._gauges.clear()
            self._histograms.clear()

    @staticmethod
    def _labels(labels: Mapping[str, Any] | None) -> tuple[tuple[str, str], ...]:
        if not labels:
            return ()
        safe: list[tuple[str, str]] = []
        for key, value in labels.items():
            if key not in SAFE_LABEL_KEYS:
                continue
            text = str(value)[:128]
            lowered = text.casefold()
            if (
                any(character.isspace() for character in text)
                or "." in text
                or any(marker in lowered for marker in ("mrn", "note", "filename"))
            ):
                text = "redacted"
            safe.append((str(key), text))
        return tuple(sorted(safe))

    def increment(self, name: str, amount: float = 1, labels: Mapping[str, Any] | None = None) -> None:
        with self._lock:
            self._counters[(name, self._labels(labels))] += amount

    def set_gauge(self, name: str, value: float, labels: Mapping[str, Any] | None = None) -> None:
        with self._lock:
            self._gauges[(name, self._labels(labels))] = value

    def observe(self, name: str, value: float, labels: Mapping[str, Any] | None = None) -> None:
        with self._lock:
            self._histograms[(name, self._labels(labels))].append(value)

    def observe_request(self, method: str, route: str, status_code: int, duration_seconds: float) -> None:
        labels = {"method": method.upper(), "route": route[:128], "status": str(status_code)}
        self.increment("http_requests_total", labels=labels)
        self.observe("http_request_duration_seconds", duration_seconds, labels={"method": method.upper(), "route": route[:128]})
        if status_code >= 500:
            self.increment("http_request_errors_total", labels={"route": route[:128]})

    def render(self) -> str:
        lines: list[str] = []
        with self._lock:
            for (name, labels), value in sorted(self._counters.items()):
                lines.append(f"{name}{_render_labels(labels)} {value:g}")
            for (name, labels), value in sorted(self._gauges.items()):
                lines.append(f"{name}{_render_labels(labels)} {value:g}")
            for (name, labels), values in sorted(self._histograms.items()):
                if values:
                    lines.append(f"{name}_count{_render_labels(labels)} {len(values)}")
                    lines.append(f"{name}_sum{_render_labels(labels)} {sum(values):g}")
        return "\n".join(lines) + ("\n" if lines else "")


def _render_labels(labels: tuple[tuple[str, str], ...]) -> str:
    if not labels:
        return ""
    escaped = ",".join(f'{key}="{value.replace(chr(92), chr(92) * 2).replace(chr(34), chr(92) + chr(34))}"' for key, value in labels)
    return "{" + escaped + "}"


metrics = MetricsStore()


def render_metrics() -> str:
    return metrics.render()


def install_structured_logging() -> None:
    root = logging.getLogger()
    if not root.handlers:
        root.addHandler(logging.StreamHandler())
    for handler in root.handlers:
        if not any(isinstance(existing, RedactionFilter) for existing in handler.filters):
            handler.addFilter(RedactionFilter())
        handler.setFormatter(JsonLogFormatter())
