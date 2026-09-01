"""Per-read timing with the existing experiment's CSV contract."""

from __future__ import annotations

import os
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Generator

INSIDE_ROOT = Path(__file__).resolve().parents[2]
if str(INSIDE_ROOT) not in sys.path:
    sys.path.insert(0, str(INSIDE_ROOT))

from common.metrics import append_metric, default_metrics_file  # noqa: E402


def now_ms() -> float:
    return time.perf_counter() * 1000.0


def default_launcher_metrics_file() -> str:
    return os.environ.get("METRICS_FILE", str(default_metrics_file(__file__)))


def emit_metric(
    metrics_file: str,
    operation: str,
    service_id: str,
    name: str,
    value_ms: float,
    run_id: str = "",
    program_id: str = "",
) -> None:
    append_metric(
        __file__,
        "launcher",
        operation,
        name,
        value_ms,
        run_id=run_id,
        program_id=program_id,
        service_id=service_id,
        metrics_file=metrics_file,
    )


class MetricsCollector:
    """Collect stage durations and emit them before the total metric."""

    def __init__(
        self,
        emit: Callable[[str, float, str, str], None],
        run_id: str = "",
        program_id: str = "",
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
