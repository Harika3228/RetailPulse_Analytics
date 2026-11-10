import base64
import hashlib
import json

from cryptography.fernet import Fernet, InvalidToken

from backend.auth_utils import SECRET_KEY
from fastapi import HTTPException


def _cipher() -> Fernet:
    key_material = f"retailpulse-integration-secrets:{SECRET_KEY}".encode("utf-8")
    key = base64.urlsafe_b64encode(hashlib.sha256(key_material).digest())
    return Fernet(key)


def encrypt_credentials(credentials: dict[str, str]) -> str | None:
    if not credentials:
        return None
    normalized = {
        key: value
        for key, value in credentials.items()
        if value
    }
    if not normalized:
        return None
    return _cipher().encrypt(
        json.dumps(normalized, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).decode("ascii")


def decrypt_credentials(encrypted_credentials: str | None) -> dict[str, str]:
    if not encrypted_credentials:
        return {}
    try:
        payload = _cipher().decrypt(encrypted_credentials.encode("ascii"))
        credentials = json.loads(payload)
    except (InvalidToken, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise HTTPException(
            status_code=500,
            detail="Stored integration credentials could not be decrypted",
        ) from error
    if not isinstance(credentials, dict) or any(
        not isinstance(key, str) or not isinstance(value, str)
        for key, value in credentials.items()
    ):
        raise HTTPException(
            status_code=500,
            detail="Stored integration credentials have an invalid format",
        )
    return credentials


def encrypt_source_data(source_data: bytes) -> str:
    return _cipher().encrypt(source_data).decode("ascii")


def decrypt_source_data(encrypted_source_data: str | None) -> bytes:
    if not encrypted_source_data:
        raise HTTPException(status_code=404, detail="No uploaded source file is available for this integration")
    try:
        return _cipher().decrypt(encrypted_source_data.encode("ascii"))
    except (InvalidToken, UnicodeDecodeError) as error:
        raise HTTPException(
            status_code=500,
            detail="Stored integration source data could not be decrypted",
        ) from error
