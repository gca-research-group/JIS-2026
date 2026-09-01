from __future__ import annotations

from functools import partial

from .metrics import MetricsCollector, default_launcher_metrics_file, emit_metric
from .read import get_certificate, lookup_service, post_json


def write(
    srv_id: str,
    program_id: int,
    data_enc: str,
    run_id: str = "",
    metrics_file: str | None = None,
) -> dict:
    """Forward encrypted data to a configured healthcare service."""
    destination = metrics_file or default_launcher_metrics_file()
    collector = MetricsCollector(
        partial(emit_metric, destination, "write", srv_id),
        run_id=run_id,
        program_id=str(program_id),
    )

    with collector.time_block("lookupService_ms"):
        service_url = lookup_service(srv_id)

    with collector.time_block("getCertificate_ms"):
        signed_cert = get_certificate(program_id)

    with collector.time_block("post_ms"):
        response = post_json(
            service_url,
            {
                "signedCert": signed_cert,
                "dataEnc": data_enc,
                "serviceId": srv_id,
                "programId": program_id,
                "runId": run_id,
                "environment": "inside",
            },
        )

    collector.flush("launcher_write_total_ms")
    return response
