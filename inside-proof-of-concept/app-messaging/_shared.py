"""Bridge to repository-local helpers used by the inside services."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from common.metrics import append_metric, default_metrics_file  # noqa: E402
from common.security import decrypt_dataset, encrypt_dataset  # noqa: E402
from common.security import verify_certificate as shared_verify_certificate  # noqa: E402

__all__ = [
    "append_metric",
    "default_metrics_file",
    "decrypt_dataset",
    "encrypt_dataset",
    "shared_verify_certificate",
]
