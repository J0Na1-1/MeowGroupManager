from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken


class EncryptedConfig:
    """Encrypts admin-stored connection material; never logs plaintext."""

    def __init__(self, key: bytes):
        self._fernet = Fernet(key)

    def encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode()).decode()

    def decrypt(self, value: str) -> str:
        try:
            return self._fernet.decrypt(value.encode()).decode()
        except InvalidToken as exc:
            raise ValueError("invalid encrypted configuration") from exc
