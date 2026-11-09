"""Проверка пользователя по JWT (RS256), выданному Identity."""
import os
from dataclasses import dataclass, field

import jwt
from fastapi import Depends, Request

from .errors import ApiError

MODERATOR_ROLE = "moderator"
ACCESS_TOKEN_TYPE = "access"


@dataclass(frozen=True)
class CurrentUser:
    id: str
    roles: list[str] = field(default_factory=list)

    def has_role(self, role: str) -> bool:
        return role in self.roles


def _public_key() -> str:
    key = os.environ.get("JWT_PUBLIC_KEY")
    if not key:
        raise RuntimeError("Не задана переменная окружения JWT_PUBLIC_KEY")
    # допускаем PEM с \n одной строкой (удобно для .env)
    return key.replace("\\n", "\n")


def _unauthorized(code: str, message: str) -> ApiError:
    return ApiError(401, code, message, headers={"WWW-Authenticate": "Bearer"})


def _decode(token: str) -> CurrentUser:
    try:
        payload = jwt.decode(
            token,
            _public_key(),
            algorithms=["RS256"],  # только RS256: защита от alg=none/HS256
            options={"require": ["sub", "exp", "typ"]},
        )
    except jwt.ExpiredSignatureError:
        raise _unauthorized("token_expired", "Срок действия токена истёк")
    except jwt.PyJWTError:
        raise _unauthorized("invalid_token", "Недействительный токен")
    # refresh-токен (typ = refresh) принимает только Identity в /v1/auth/refresh
    if payload["typ"] != ACCESS_TOKEN_TYPE:
        raise _unauthorized("invalid_token", "Недействительный токен")
    roles = payload.get("roles") or []
    if not isinstance(roles, list):
        raise _unauthorized("invalid_token", "Недействительный токен")
    return CurrentUser(id=str(payload["sub"]), roles=[str(r) for r in roles])


def _bearer(request: Request) -> str | None:
    header = request.headers.get("Authorization")
    if not header:
        return None
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise _unauthorized("invalid_token", "Ожидается заголовок Authorization: Bearer <токен>")
    return token.strip()


async def get_current_user(request: Request) -> CurrentUser:
    token = _bearer(request)
    if token is None:
        raise _unauthorized("not_authenticated", "Требуется авторизация")
    return _decode(token)


async def optional_user(request: Request) -> CurrentUser | None:
    """Для страниц без обязательного входа. Невалидный токен — всё равно ошибка."""
    token = _bearer(request)
    return _decode(token) if token else None


def require_role(role: str):
    async def dep(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if not user.has_role(role):
            raise ApiError(403, "forbidden", "Недостаточно прав")
        return user
    return dep


require_moderator = require_role(MODERATOR_ROLE)
