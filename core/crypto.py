from cryptography.fernet import Fernet

from core.config import settings


def _f() -> Fernet:
    if not settings.secret_key:
        raise RuntimeError("SECRET_KEY не задан")
    return Fernet(settings.secret_key.encode())


def encrypt(value: str) -> str:
    return _f().encrypt(value.encode()).decode()


def decrypt(token: str) -> str:
    return _f().decrypt(token.encode()).decode()
