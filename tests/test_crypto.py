from cryptography.fernet import Fernet
import pytest
from app.services.config_crypto import EncryptedConfig


def test_config_round_trip_and_rejects_wrong_key():
    crypto = EncryptedConfig(Fernet.generate_key())
    encrypted = crypto.encrypt("readonly-db-password")
    assert encrypted != "readonly-db-password"
    assert crypto.decrypt(encrypted) == "readonly-db-password"
    with pytest.raises(ValueError):
        EncryptedConfig(Fernet.generate_key()).decrypt(encrypted)
