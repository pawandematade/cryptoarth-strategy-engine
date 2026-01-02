"""
Security utilities - Encryption/Decryption
Shared infrastructure for API credentials management
"""
from cryptography.fernet import Fernet, InvalidToken
from decouple import config


def encrypt_api_credentials(api_key: str, api_secret: str) -> tuple:
    """Encrypt API credentials"""
    FERNET_KEY = config('FERNET_KEY', default=None)
    if not FERNET_KEY:
        raise ValueError("FERNET_KEY not configured")
    f = Fernet(FERNET_KEY)
    encrypted_key = f.encrypt(api_key.encode()).decode()
    encrypted_secret = f.encrypt(api_secret.encode()).decode()
    return encrypted_key, encrypted_secret


def decrypt_api_credentials(encrypted_key: str, encrypted_secret: str) -> tuple:
    """Decrypt API credentials"""
    FERNET_KEY = config('FERNET_KEY', default=None)
    if not FERNET_KEY:
        return None, None
    f = Fernet(FERNET_KEY)
    try:
        key = f.decrypt(encrypted_key.encode()).decode() if encrypted_key else None
        secret = f.decrypt(encrypted_secret.encode()).decode() if encrypted_secret else None
        return key, secret
    except (InvalidToken, AttributeError):
        return None, None


def set_broker_credentials(broker, api_key: str, api_secret: str, db):
    """Encrypt and store API credentials on broker model"""
    encrypted_key, encrypted_secret = encrypt_api_credentials(api_key, api_secret)
    broker.api_key = encrypted_key
    broker.api_secret = encrypted_secret
    db.commit()


def get_broker_credentials(broker) -> tuple:
    """Decrypt and return API credentials from broker model"""
    return decrypt_api_credentials(broker.api_key, broker.api_secret)
