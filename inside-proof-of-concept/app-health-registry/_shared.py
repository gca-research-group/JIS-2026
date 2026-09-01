"""Bridge to the existing repository-local helpers (not a standalone package)."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from common.metrics import append_metric, default_metrics_file  # noqa: E402
from common.security import (  # noqa: E402
    decrypt_dataset,
    encrypt_dataset,
    verify_certificate,
)

__all__ = [
    "append_metric",
    "default_metrics_file",
    "decrypt_dataset",
    "encrypt_dataset",
    "verify_certificate",
]
