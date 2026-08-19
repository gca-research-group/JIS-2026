from __future__ import annotations
import csv
import time
import threading
from pathlib import Path

try:
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX host
    fcntl = None

_lock = threading.Lock()

DEFAULT_COLUMNS = ["ts", "run_id", "component", "operation", "metric", "value_ms", "program_id", "service_id"]


def project_root(start: str | Path) -> Path:
    """Return the proof-of-concept root directory for metrics collection."""
    p = Path(start).resolve()
    if p.is_file():
        p = p.parent

    for candidate in [p, *p.parents]:
        if candidate.name in {"inside-proof-of-concept", "outside-proof-of-concept"}:
            return candidate
        if (candidate / "app-health-registry").is_dir() and (candidate / "app-hospital").is_dir():
            return candidate
        if (candidate / "launcher").is_dir() and (candidate / "programs-data-base").exists():
            return candidate

    return p


def default_metrics_file(start: str | Path) -> Path:
    return project_root(start) / "metrics" / "all_metrics.csv"


def append_metric(base: str | Path, component: str, operation: str, metric: str, value_ms: float,
                  run_id: str = "", program_id: str = "", service_id: str = "", metrics_file: str | Path | None = None) -> None:
    path = Path(metrics_file) if metrics_file else default_metrics_file(base)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        with path.open("a+", newline="", encoding="utf-8") as f:
            if fcntl is not None:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                f.seek(0, 2)
                new_file = f.tell() == 0
                writer = csv.writer(f)
                if new_file:
                    writer.writerow(DEFAULT_COLUMNS)
                writer.writerow([int(time.time() * 1000), run_id, component, operation, metric, f"{value_ms:.6f}", program_id, service_id])
                f.flush()
            finally:
                if fcntl is not None:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
