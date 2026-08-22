import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import numpy as np
from scipy.stats import shapiro, mannwhitneyu

from metric_schema import CORE_FLOW, TRUSTED_INTERNAL, TRUSTED_FORBIDDEN_METRICS


class TeeLogger:
    def __init__(self, *streams):
        self.streams = streams

    def write(self, data: str) -> None:
        for stream in self.streams:
            stream.write(data)
            stream.flush()

    def flush(self) -> None:
        for stream in self.streams:
            stream.flush()


def load_csv(path: str) -> pd.DataFrame:
    return pd.read_csv(path)


def complete_successful_run_ids(df: pd.DataFrame) -> set[str]:
    """Return run IDs that contain one complete, uncontaminated workflow."""
    valid: set[str] = set()
    grouped = df[df["run_id"].notna() & (df["run_id"].astype(str) != "")].groupby("run_id")
    for run_id, rows in grouped:
        trusted = bool((rows["component"] == "launcher").any())
        required = list(CORE_FLOW) + (list(TRUSTED_INTERNAL) if trusted else [])
        ok = True
        for component, operation, metric, service_id in required:
            selected = rows[
                (rows["component"] == component)
                & (rows["operation"] == operation)
                & (rows["metric"] == metric)
            ]
            if service_id:
                selected = selected[selected["service_id"] == service_id]
            else:
                selected = selected[selected["service_id"].fillna("") == ""]
            if len(selected) != 1:
                ok = False
                break
        if ok:
            metrics = set(rows["metric"].astype(str))
            if "execute_failed_ms" in metrics:
                ok = False
            if trusted and metrics.intersection(TRUSTED_FORBIDDEN_METRICS):
                ok = False
        if ok:
            valid.add(str(run_id))
    return valid


def filter_complete_runs(df: pd.DataFrame, label: str) -> pd.DataFrame:
    valid = complete_successful_run_ids(df)
    all_ids = set(df["run_id"].dropna().astype(str)) - {""}
    excluded = all_ids - valid
    print(f"{label}: {len(valid)} complete successful runs; {len(excluded)} incomplete/failed run IDs excluded")
    return df[df["run_id"].astype(str).isin(valid)].copy()


def extract_metric(
    df: pd.DataFrame,
    metric: str,
    component: str = "integration_process",
    operation: str | None = None,
    service_id: str | None = None,
) -> np.ndarray:
    rows = df[(df["component"] == component) & (df["metric"] == metric)]
    if operation is not None:
        rows = rows[rows["operation"] == operation]
    if service_id is not None:
        rows = rows[rows["service_id"] == service_id]
    return rows["value_ms"].astype(float).to_numpy()


def mean_std(x: np.ndarray) -> tuple[float, float]:
    if len(x) == 0:
        return float("nan"), float("nan")
    if len(x) == 1:
        return float(np.mean(x)), 0.0
    return float(np.mean(x)), float(np.std(x, ddof=1))


def cliff_delta(x: np.ndarray, y: np.ndarray) -> float:
    n = len(x) * len(y)
    if n == 0:
        return float("nan")
    greater = sum(i > j for i in x for j in y)
    less = sum(i < j for i in x for j in y)
    return (greater - less) / n


def holm_correction(p_values: list[float]) -> list[float]:
    m = len(p_values)
    indexed = sorted(enumerate(p_values), key=lambda t: t[1])
    adjusted = [0.0] * m
    prev = 0.0
    for rank, (idx, p) in enumerate(indexed, start=1):
        value = (m - rank + 1) * p
        value = max(value, prev)
        adjusted[idx] = min(value, 1.0)
        prev = adjusted[idx]
    return adjusted


def iqr_filter(x: np.ndarray) -> np.ndarray:
    if len(x) == 0:
        return x
    q1 = np.percentile(x, 25)
    q3 = np.percentile(x, 75)
    iqr = q3 - q1
    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr
    return x[(x >= lower) & (x <= upper)]


def relative_time(operation_mean: float, total_mean: float) -> float:
    if total_mean == 0 or np.isnan(total_mean):
        return float("nan")
    return 100.0 * operation_mean / total_mean


def format_p(p: float) -> str:
    if np.isnan(p):
        return "n/a"
    return "<0.001" if p < 0.001 else f"{p:.6f}"


def analyse_main_comparison(inside_csv: str, outside_csv: str) -> None:
    inside = filter_complete_runs(load_csv(inside_csv), "Trusted")
    outside = filter_complete_runs(load_csv(outside_csv), "Conventional")

    metrics = [
        ("read_act_total_ms", "Read_act", "health-registry-service"),
        ("write_act_total_ms", "Write_act Hospital Service", "hospital-service"),
        ("write_act_total_ms", "Write_act Messaging Service", "messaging-service"),
        ("execute_total_ms", "Execution", None),
    ]
    raw_p: list[float] = []
    comparison_rows: list[tuple[str, str | None, np.ndarray, np.ndarray, float, float]] = []

    print("=== Main comparison: trusted vs conventional ===")
    for metric, label, service_id in metrics:
        x = extract_metric(inside, metric, service_id=service_id)
        y = extract_metric(outside, metric, service_id=service_id)

        if len(x) == 0 or len(y) == 0:
            print(f"\nMetric: {label} ({metric})")
            print(f"Trusted samples: {len(x)}")
            print(f"Conventional samples: {len(y)}")
            print("Result: missing data; metric not analysed")
            continue

        mean_x, std_x = mean_std(x)
        mean_y, std_y = mean_std(y)

        p_shapiro_x = shapiro(x).pvalue if len(x) >= 3 else float("nan")
        p_shapiro_y = shapiro(y).pvalue if len(y) >= 3 else float("nan")

        _, p_mw = mannwhitneyu(x, y, alternative="two-sided")
        raw_p.append(p_mw)
        delta = cliff_delta(x, y)
        comparison_rows.append((label, service_id, x, y, p_mw, delta))

        print(f"\nMetric: {label} ({metric})")
        print(f"Trusted samples: {len(x)}")
        print(f"Conventional samples: {len(y)}")
        print(f"Trusted mean ± std: {mean_x:.2f} ± {std_x:.2f}")
        print(f"Conventional mean ± std: {mean_y:.2f} ± {std_y:.2f}")
        print(f"Overhead: {((mean_x - mean_y) / mean_y) * 100.0:.1f}%")
        print(f"Shapiro trusted: {format_p(p_shapiro_x)}")
        print(f"Shapiro conventional: {format_p(p_shapiro_y)}")
        print(f"Mann–Whitney raw p-value: {format_p(p_mw)}")
        print(f"Cliff's Delta: {delta:.3f}")

    adjusted = holm_correction(raw_p)
    for (label, _service_id, _x, _y, _p_mw, _delta), p_adj in zip(comparison_rows, adjusted):
        print(f"Holm-adjusted p-value for {label}: {format_p(p_adj)}")

    print("\n=== Robustness analysis after IQR filtering ===")
    for label, service_id, x, y, _p_mw, _delta in comparison_rows:
        xf = iqr_filter(x)
        yf = iqr_filter(y)
        mean_xf, std_xf = mean_std(xf)
        mean_yf, std_yf = mean_std(yf)

        print(f"\nMetric: {label}")
        print(f"Trusted mean ± std without outliers: {mean_xf:.2f} ± {std_xf:.2f}")
        print(f"Conventional mean ± std without outliers: {mean_yf:.2f} ± {std_yf:.2f}")
        print(f"Trusted outliers removed: {len(x) - len(xf)}")
        print(f"Conventional outliers removed: {len(y) - len(yf)}")


def print_internal_metric(
    df: pd.DataFrame,
    metric: str,
    label: str,
    total_mean: float | None = None,
    component: str = "launcher",
    operation: str | None = None,
    service_id: str | None = None,
) -> None:
    values = extract_metric(df, metric, component=component, operation=operation, service_id=service_id)
    # Backward compatibility with older CSV files that used operation=read_write
    # or did not store service_id for some Launcher metrics. New collections
    # should use the more specific read/write operation labels.
    if len(values) == 0 and operation in {"read", "write"}:
        values = extract_metric(df, metric, component=component, operation="read_write", service_id=service_id)
    if len(values) == 0 and component == "launcher" and service_id is not None:
        values = extract_metric(df, metric, component=component, operation=operation, service_id=None)
    if len(values) == 0 and operation in {"read", "write"} and component == "launcher":
        values = extract_metric(df, metric, component=component, operation="read_write", service_id=None)
    if len(values) == 0:
        print(f"{label}: no data")
        return
    m = float(np.mean(values))
    if total_mean is None:
        print(f"{label}: mean={m:.6f} ms")
    else:
        c = relative_time(m, total_mean)
        print(f"{label}: mean={m:.6f} ms, relative_time={c:.3f}%")


def analyse_trusted_internal_cost(inside_csv: str) -> None:
    inside = filter_complete_runs(load_csv(inside_csv), "Trusted internal-cost analysis")

    read_total = extract_metric(inside, "read_act_total_ms", service_id="health-registry-service")
    read_total_mean = float(np.mean(read_total)) if len(read_total) else float("nan")

    print("\n=== Internal cost of Read_act in the trusted environment ===")
    print_internal_metric(inside, "lookupService_ms", "Service lookup", read_total_mean, component="launcher", operation="read", service_id="health-registry-service")
    print_internal_metric(inside, "getCertificate_ms", "Certificate retrieval", read_total_mean, component="launcher", operation="read", service_id="health-registry-service")
    print_internal_metric(inside, "getProgramPublicKey_ms", "Public-key retrieval", read_total_mean, component="launcher", operation="read", service_id="health-registry-service")
    print_internal_metric(inside, "request_ms", "Launcher request/response interval", read_total_mean, component="launcher", operation="read", service_id="health-registry-service")
    print_internal_metric(inside, "launcher_read_total_ms", "Launcher read mediation", read_total_mean, component="launcher", operation="read", service_id="health-registry-service")
    print_internal_metric(inside, "request_total_ms", "DigitalService.request()", read_total_mean, component="digital_service", operation="request", service_id="health-registry-service")
    print_internal_metric(inside, "verifyCertificate_ms", "Service certificate verification", read_total_mean, component="digital_service", operation="request", service_id="health-registry-service")
    print_internal_metric(inside, "retrieveLocalData_ms", "Service data retrieval", read_total_mean, component="digital_service", operation="request", service_id="health-registry-service")
    print_internal_metric(inside, "encrypt_ms", "Service-side encryption", read_total_mean, component="digital_service", operation="request", service_id="health-registry-service")
    print_internal_metric(inside, "decrypt_ms", "Local decryption", read_total_mean, component="integration_process", operation="read", service_id="health-registry-service")
    print(f"Read_act total mean: {read_total_mean:.6f} ms")

    print("\n=== Internal cost of Write_act in the trusted environment ===")
    for service_id, service_label in [("hospital-service", "Hospital Service"), ("messaging-service", "Messaging Service")]:
        write_total = extract_metric(inside, "write_act_total_ms", service_id=service_id)
        write_total_mean = float(np.mean(write_total)) if len(write_total) else float("nan")
        print(f"\nWrite_act to {service_label}:")
        print_internal_metric(inside, "getServicePublicKey_ms", "Service public-key retrieval", write_total_mean, component="integration_process", operation="write", service_id=service_id)
        print_internal_metric(inside, "encrypt_ms", "Local encryption", write_total_mean, component="integration_process", operation="write", service_id=service_id)
        print_internal_metric(inside, "lookupService_ms", "Service lookup", write_total_mean, component="launcher", operation="write", service_id=service_id)
        print_internal_metric(inside, "getCertificate_ms", "Certificate retrieval", write_total_mean, component="launcher", operation="write", service_id=service_id)
        print_internal_metric(inside, "post_ms", "Launcher post/response interval", write_total_mean, component="launcher", operation="write", service_id=service_id)
        print_internal_metric(inside, "launcher_write_total_ms", "Launcher write mediation", write_total_mean, component="launcher", operation="write", service_id=service_id)
        print_internal_metric(inside, "verifyCertificate_ms", "Service certificate verification", write_total_mean, component="digital_service", operation="post", service_id=service_id)
        print_internal_metric(inside, "decrypt_ms", "Service-side decryption", write_total_mean, component="digital_service", operation="post", service_id=service_id)
        print_internal_metric(inside, "storeLocalData_ms", "Service data persistence", write_total_mean, component="digital_service", operation="post", service_id=service_id)
        print_internal_metric(inside, "post_total_ms", "Service post handling", write_total_mean, component="digital_service", operation="post", service_id=service_id)
        print(f"Write_act total mean: {write_total_mean:.6f} ms")

    start_ops = [
        ("retrieveProgram_ms", "Source-code retrieval"),
        ("createCompartment_ms", "Compartment creation"),
        ("deploy_ms", "Deployment"),
        ("getIntegratedServices_ms", "Integrated-services retrieval"),
        ("exchangeKeys_ms", "Key exchange"),
        ("generateAttestableDoc_ms", "Attestable-document generation"),
        ("generateCertificate_ms", "Certificate generation"),
        ("sign_ms", "Certificate signing"),
        ("run_ms", "Program execution"),
        ("start_total_ms", "Launcher.start()"),
    ]

    print("\n=== Internal cost of Launcher.start() in the trusted environment ===")
    compile_values = extract_metric(inside, "compile_ms", component="launcher", operation="start")
    if len(compile_values) == 0:
        print("Compilation: not part of the repeated campaign; the executable was precompiled")
    else:
        print_internal_metric(inside, "compile_ms", "Compilation", component="launcher", operation="start")
    for metric, label in start_ops:
        print_internal_metric(inside, metric, label, component="launcher", operation="start")

    print("\n=== Experimental control outside Launcher.start() ===")
    print_internal_metric(inside, "validateServices_ms", "Service-environment validation", component="launcher", operation="experimental_control")

    start_total = extract_metric(inside, "start_total_ms", component="launcher", operation="start")
    selected_metrics = [m for m, _ in start_ops if m != "start_total_ms"]
    selected_sum = 0.0
    all_present = True
    for metric in selected_metrics:
        vals = extract_metric(inside, metric, component="launcher", operation="start")
        if len(vals) == 0:
            all_present = False
            break
        selected_sum += float(np.mean(vals))
    if len(start_total) and all_present:
        total_mean = float(np.mean(start_total))
        print(f"Selected measured start intervals: mean sum={selected_sum:.6f} ms")
        print(f"Uninstrumented Launcher.start() residual: mean={total_mean - selected_sum:.6f} ms")

    run_values = extract_metric(inside, "run_ms", component="launcher", operation="start")
    exec_values = extract_metric(inside, "execute_total_ms", component="integration_process", operation="execute")
    if len(run_values) and len(exec_values) and len(run_values) == len(exec_values):
        print(f"Launcher run envelope minus IntegrationProcess Execution: mean={float(np.mean(run_values) - np.mean(exec_values)):.6f} ms")


if __name__ == "__main__":
    base_dir = Path(__file__).resolve().parent
    project_dir = base_dir.parent
    INSIDE_CSV = str(project_dir / "inside-proof-of-concept" / "metrics" / "all_metrics.csv")
    OUTSIDE_CSV = str(project_dir / "outside-proof-of-concept" / "metrics" / "all_metrics.csv")
    LOG_FILE = str(base_dir / "analysis_results.log")

    original_stdout = sys.stdout
    with open(LOG_FILE, "w", encoding="utf-8") as log_file:
        sys.stdout = TeeLogger(original_stdout, log_file)
        try:
            print(f"Analysis started at: {datetime.now().isoformat(timespec='seconds')}")
            print(f"Inside CSV: {INSIDE_CSV}")
            print(f"Outside CSV: {OUTSIDE_CSV}")
            print(f"Log file: {LOG_FILE}\n")

            analyse_main_comparison(INSIDE_CSV, OUTSIDE_CSV)
            analyse_trusted_internal_cost(INSIDE_CSV)

            print(f"\nAnalysis finished at: {datetime.now().isoformat(timespec='seconds')}")
        finally:
            sys.stdout = original_stdout

    print(f"Results were also saved to: {LOG_FILE}")
