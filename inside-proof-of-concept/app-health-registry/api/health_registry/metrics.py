"""Per-request timing with the existing experiment's CSV contract."""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Callable, Generator

from ._shared import append_metric
from .config import SERVICE_ID


def now_ms() -> float:
    return time.perf_counter() * 1000.0


def emit_metric(
    metrics_file: str, name: str, value_ms: float, run_id: str = "", program_id: str = ""
) -> None:
    append_metric(
        __file__,
        "digital_service",
        "request",
        name,
        value_ms,
        run_id=run_id,
        program_id=program_id,
        service_id=SERVICE_ID,
        metrics_file=metrics_file,
    )


class MetricsCollector:
    """Collect stage durations and emit them before the total metric."""

    def __init__(
        self, emit: Callable[[str, float, str, str], None], run_id: str = "", program_id: str = ""
    ) -> None:
        self.emit = emit
        self.run_id = run_id
        self.program_id = program_id
        self.timings: dict[str, float] = {}
        self.total_t0 = now_ms()

    @contextmanager
    def time_block(self, name: str) -> Generator[None, None, None]:
        t0 = now_ms()
        try:
            yield
        finally:
            self.timings[name] = now_ms() - t0

    def flush(self, total_metric_name: str) -> None:
        total_ms = now_ms() - self.total_t0
        for name, value in self.timings.items():
            self.emit(name, value, self.run_id, self.program_id)
        self.emit(total_metric_name, total_ms, self.run_id, self.program_id)
