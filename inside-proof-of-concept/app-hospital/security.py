"""Adapters for the existing simulated security helpers."""

from __future__ import annotations

from _shared import decrypt_dataset, encrypt_dataset, shared_verify_certificate


def verify_certificate(cert: str) -> tuple[bool, str]:
    ok = shared_verify_certificate(cert)
    return ok, ("Simulated certificate accepted" if ok else "Missing simulated certificate")


def encrypt(public_key: str, data: str) -> str:
    return encrypt_dataset(public_key, data)


def decrypt(private_key: str, data_enc: str) -> str:
    return decrypt_dataset(private_key, data_enc)
