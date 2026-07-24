"""
Encrypts/decrypts each workspace's stored AI provider API key at rest.

FERNET_ENCRYPTION_KEY is required infrastructure, not an optional feature —
unlike e.g. a missing ScraperAPI-style key in the old prototype (which just
degrades one feature), a missing/invalid encryption key here would mean
every stored provider credential is unreadable or, worse, silently stored
unencrypted. So this fails fast at import time rather than at first use.
"""
from cryptography.fernet import Fernet, InvalidToken

from app.config import settings

if not settings.FERNET_ENCRYPTION_KEY:
    raise RuntimeError(
        "FERNET_ENCRYPTION_KEY is not set. Generate one with: "
        "python -c \"from cryptography.fernet import Fernet; "
        "print(Fernet.generate_key().decode())\" "
        "and set it in your .env — see backend/.env.example."
    )

_fernet = Fernet(settings.FERNET_ENCRYPTION_KEY.encode())


def encrypt_key(raw_api_key: str) -> str:
    return _fernet.encrypt(raw_api_key.encode()).decode()


def decrypt_key(encrypted_api_key: str) -> str:
    try:
        return _fernet.decrypt(encrypted_api_key.encode()).decode()
    except InvalidToken:
        raise ValueError(
            "Stored API key could not be decrypted — FERNET_ENCRYPTION_KEY "
            "may have changed since it was encrypted."
        )
