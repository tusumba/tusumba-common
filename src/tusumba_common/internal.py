"""Внутренние вызовы между сервисами (/internal) по X-Service-Token."""
import hmac
import os

import httpx
from fastapi import Request

from .errors import ApiError

HEADER = "X-Service-Token"


def _token() -> str:
    token = os.environ.get("SERVICE_TOKEN")
    if not token:
        raise RuntimeError("Не задана переменная окружения SERVICE_TOKEN")
    return token


async def require_service(request: Request) -> None:
    """Зависимость для эндпоинтов /internal: без верного токена — 403."""
    given = request.headers.get(HEADER, "")
    try:
        expected = _token()
    except RuntimeError:
        raise ApiError(403, "forbidden", "Доступ запрещён")
    if not hmac.compare_digest(given.encode(), expected.encode()):
        raise ApiError(403, "forbidden", "Доступ запрещён")


class InternalClient(httpx.AsyncClient):
    """httpx-клиент, сам добавляющий X-Service-Token.

    client = InternalClient(base_url="http://identity:8000")
    """

    def __init__(self, *args, timeout: float = 5.0, **kwargs):
        headers = dict(kwargs.pop("headers", None) or {})
        headers[HEADER] = _token()
        super().__init__(*args, headers=headers, timeout=timeout, **kwargs)
