from argon2 import PasswordHasher

password_context = PasswordHasher()


def get_password_hash(password: str) -> str:
    return password_context.hash(password)


def check_password(password: str, hashed_password: str) -> bool:
    return password_context.verify(hashed_password, password)
