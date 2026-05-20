from fastapi import Depends
from src.core.jwt import JWTManager


def get_jwt_manager():
    return JWTManager()
