from __future__ import annotations

# Simulated security layer for CheriBSD/Python environments where the
# cryptography package is not available. The proof-of-concept keeps the same
# API-level control flow and metrics, but certificate verification and
# encryption/decryption are represented with plain text.

SIMULATED_CERT_PREFIX = "SIMULATED_ATTESTATION_CERTIFICATE"
SIMULATED_PUBLIC_KEY_PREFIX = "SIMULATED_PUBLIC_KEY"


def verify_certificate(signed_cert: str) -> bool:
    """Return True for non-empty simulated or pre-existing certificate text."""
    if not isinstance(signed_cert, str):
        return False
    return bool(signed_cert.strip())


def encrypt_dataset(public_key: str, data: str) -> str:
    """Plain-text simulation of encryption."""
    return "" if data is None else str(data)


def decrypt_dataset(private_key: str, data_enc: str) -> str:
    """Plain-text simulation of decryption."""
    return "" if data_enc is None else str(data_enc)
