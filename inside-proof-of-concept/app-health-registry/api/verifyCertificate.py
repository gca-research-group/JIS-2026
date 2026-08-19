from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from common.security import verify_certificate, encrypt_dataset, decrypt_dataset


def verifyCertificate(cert: str):
    ok = verify_certificate(cert)
    return ok, ("Simulated certificate accepted" if ok else "Missing simulated certificate")


def encrypt(public_key: str, data: str) -> str:
    return encrypt_dataset(public_key, data)


def decrypt(private_key: str, data_enc: str) -> str:
    return decrypt_dataset(private_key, data_enc)
