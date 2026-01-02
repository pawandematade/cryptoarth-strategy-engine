"""
API Credentials Encryption/Decryption
Extracted from legacy Django models
"""
from cryptography.fernet import Fernet, InvalidToken
from decouple import config


def set_api_credentials(broker, api_key: str, api_secret: str, db):
    """Encrypt and store API credentials"""
    FERNET_KEY = config('FERNET_KEY', default=None)
    f = Fernet(FERNET_KEY)
    
    broker.api_key = f.encrypt(api_key.encode()).decode()
    broker.api_secret = f.encrypt(api_secret.encode()).decode()
    db.commit()


def get_api_credentials(broker):
    """Decrypt and return API credentials"""
    FERNET_KEY = config('FERNET_KEY', default=None)
    f = Fernet(FERNET_KEY)
    try:
        key = f.decrypt(broker.api_key.encode()).decode() if broker.api_key else None
        secret = f.decrypt(broker.api_secret.encode()).decode() if broker.api_secret else None
        return key, secret
    except (InvalidToken, AttributeError):
        return None, None
