from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

password_context = PasswordHasher()


def get_password_hash(password: str) -> str:
    return password_context.hash(password)


def check_password(password: str, hashed_password: str) -> bool:
    try:
        password_context.verify(hashed_password, password)
    except VerifyMismatchError:
        return False
    return True
