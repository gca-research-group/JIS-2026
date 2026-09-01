"""Timing and CSV emission for Hospital requests."""

from __future__ import annotations

import time

from _shared import append_metric
from config import SERVICE_ID


def now_ms() -> float:
    return time.perf_counter() * 1000.0


def emit_metric(
    metrics_file: str,
    name: str,
    value_ms: float,
    run_id: str = "",
    program_id: str = "",
) -> None:
    append_metric(
        __file__,
        "digital_service",
        "post",
        name,
        value_ms,
        run_id=run_id,
        program_id=program_id,
        service_id=SERVICE_ID,
        metrics_file=metrics_file,
    )
