from __future__ import annotations

import csv
import importlib


metrics_module = importlib.import_module("launcher.metrics")


def test_collector_records_durations_context_and_total_last(monkeypatch):
    ticks = iter([0.0, 1.0, 3.0, 4.0, 9.0, 10.0])
    monkeypatch.setattr(metrics_module, "now_ms", lambda: next(ticks))
    emitted = []
    collector = metrics_module.MetricsCollector(
        lambda *args: emitted.append(args), run_id="run-1", program_id="9"
    )

    with collector.time_block("first_ms"):
        pass
    with collector.time_block("second_ms"):
        pass
    collector.flush("total_ms")

    assert emitted == [
        ("first_ms", 2.0, "run-1", "9"),
        ("second_ms", 5.0, "run-1", "9"),
        ("total_ms", 10.0, "run-1", "9"),
    ]


def test_emit_metric_preserves_launcher_csv_identity(tmp_path):
    destination = tmp_path / "metrics.csv"

    metrics_module.emit_metric(
        str(destination),
        "read",
        "health-registry-service",
        "request_ms",
        12.5,
        "run-2",
        "4",
    )

    with destination.open(newline="", encoding="utf-8") as source:
        rows = list(csv.DictReader(source))
    assert rows[0]["component"] == "launcher"
    assert rows[0]["operation"] == "read"
    assert rows[0]["metric"] == "request_ms"
    assert rows[0]["run_id"] == "run-2"
    assert rows[0]["program_id"] == "4"
    assert rows[0]["service_id"] == "health-registry-service"


def test_default_metrics_destination_is_resolved_at_call_time(monkeypatch, tmp_path):
    first = str(tmp_path / "first.csv")
    second = str(tmp_path / "second.csv")
    monkeypatch.setenv("METRICS_FILE", first)
    assert metrics_module.default_launcher_metrics_file() == first
    monkeypatch.setenv("METRICS_FILE", second)
    assert metrics_module.default_launcher_metrics_file() == second
