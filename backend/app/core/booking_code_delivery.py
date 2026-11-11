import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


def _fernet() -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(settings.secret_key.encode()).digest())
    return Fernet(key)


def encrypt_booking_code(code: str) -> str:
    return _fernet().encrypt(code.encode()).decode()


def decrypt_booking_code(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except (InvalidToken, ValueError) as error:
        raise RuntimeError("The booking check-in code could not be decrypted") from error
