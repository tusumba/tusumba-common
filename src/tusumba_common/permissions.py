"""Клиент прав Events & Clubs с кешем ответа в Redis.

Ticketing и Moderation проверяют роль пользователя в мероприятии и права на секцию через
GET /internal/events/{id}/permissions и GET /internal/clubs/{id}/permissions (OpenAPI Events, #18891).
Ответ кешируется на 30-60 секунд. Если Redis недоступен, клиент работает без кеша.
"""
import json
import logging
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

import httpx

from .errors import ApiError
from .internal import InternalClient

logger = logging.getLogger("tusumba_common.permissions")

TTL_MIN = 30
TTL_MAX = 60
DEFAULT_TTL = 45

EVENT_NOT_FOUND = ("event_not_found", "Мероприятие недоступно.")
CLUB_NOT_FOUND = ("club_not_found", "Секция недоступна.")
UNAVAILABLE = ("service_unavailable", "Сервис временно недоступен. Попробуйте позже.")


class AsyncRedis(Protocol):
    """Нужные клиенту методы redis.asyncio.Redis (подходит и fakeredis для тестов)."""

    async def get(self, name: str) -> Any: ...

    async def set(self, name: str, value: str, ex: int | None = None) -> Any: ...

    async def delete(self, *names: str) -> Any: ...


@dataclass(frozen=True)
class EventPermissions:
    event_id: str
    user_id: str
    is_member: bool
    role: str | None  # owner, admin, editor, scanner; None, если пользователь не в команде

    def has_role(self, *roles: str) -> bool:
        return self.is_member and self.role in roles


@dataclass(frozen=True)
class ClubPermissions:
    club_id: str
    user_id: str
    is_admin: bool


def _uuid(value: UUID | str) -> str:
    """Приводит id к каноническому виду: в ключ кеша и в URL попадает только настоящий UUID."""
    return str(UUID(str(value)))


class PermissionsClient:
    """client = PermissionsClient("http://events:8000", redis=redis_client)

    perms = await client.event_permissions(event_id, user_id)
    if not perms.has_role("owner", "admin"):
        raise ApiError(403, "forbidden", "Недостаточно прав.")
    """

    def __init__(
        self,
        base_url: str,
        redis: AsyncRedis | None = None,
        *,
        ttl_seconds: int = DEFAULT_TTL,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not TTL_MIN <= ttl_seconds <= TTL_MAX:
            raise ValueError(f"ttl_seconds должен быть от {TTL_MIN} до {TTL_MAX} секунд")
        self._redis = redis
        self._ttl = ttl_seconds
        self._http = client or InternalClient(base_url=base_url)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def event_permissions(
        self, event_id: UUID | str, user_id: UUID | str
    ) -> EventPermissions:
        event, user = _uuid(event_id), _uuid(user_id)
        data = await self._cached_get(
            f"permissions:event:{event}:{user}",
            f"/internal/events/{event}/permissions",
            user,
            EVENT_NOT_FOUND,
            "is_member",
        )
        return EventPermissions(
            event_id=event,
            user_id=user,
            is_member=bool(data["is_member"]),
            role=data.get("role"),
        )

    async def club_permissions(self, club_id: UUID | str, user_id: UUID | str) -> ClubPermissions:
        club, user = _uuid(club_id), _uuid(user_id)
        data = await self._cached_get(
            f"permissions:club:{club}:{user}",
            f"/internal/clubs/{club}/permissions",
            user,
            CLUB_NOT_FOUND,
            "is_admin",
        )
        return ClubPermissions(club_id=club, user_id=user, is_admin=bool(data["is_admin"]))

    async def invalidate_event(self, event_id: UUID | str, user_id: UUID | str) -> None:
        """Сбросить кеш, например сразу после изменения роли пользователя."""
        await self._forget(f"permissions:event:{_uuid(event_id)}:{_uuid(user_id)}")

    async def invalidate_club(self, club_id: UUID | str, user_id: UUID | str) -> None:
        await self._forget(f"permissions:club:{_uuid(club_id)}:{_uuid(user_id)}")

    async def _cached_get(
        self, key: str, path: str, user_id: str, not_found: tuple[str, str], field: str
    ) -> dict[str, Any]:
        cached = await self._read(key)
        if cached is not None and field in cached:
            return cached
        data = await self._fetch(path, user_id, not_found, field)
        await self._write(key, data)
        return data

    async def _fetch(
        self, path: str, user_id: str, not_found: tuple[str, str], field: str
    ) -> dict[str, Any]:
        try:
            response = await self._http.get(path, params={"user_id": user_id})
        except httpx.HTTPError:
            logger.warning("Events не ответил на %s", path, exc_info=True)
            raise ApiError(503, *UNAVAILABLE) from None
        if response.status_code == 404:
            # 404 не кешируем: мероприятие или секция могут появиться
            raise ApiError(404, *_error_of(response, not_found))
        if response.status_code != 200:
            # 403 здесь значит неверный SERVICE_TOKEN: ошибка настройки, а не пользователя
            logger.error("Events ответил %s на %s", response.status_code, path)
            raise ApiError(503, *UNAVAILABLE)
        try:
            data = response.json()
            if not isinstance(data, dict):
                raise TypeError("ожидался JSON-объект")
            if field not in data:
                raise KeyError(field)
        except (ValueError, TypeError, KeyError):
            logger.error("Events вернул неожиданный ответ на %s", path)
            raise ApiError(503, *UNAVAILABLE) from None
        return data

    async def _read(self, key: str) -> dict[str, Any] | None:
        if self._redis is None:
            return None
        try:
            raw = await self._redis.get(key)
            if raw is None:
                return None
            value = json.loads(raw)
            return value if isinstance(value, dict) else None
        except Exception:
            logger.warning("Redis недоступен при чтении %s", key, exc_info=True)
            return None

    async def _write(self, key: str, data: dict[str, Any]) -> None:
        if self._redis is None:
            return
        try:
            await self._redis.set(key, json.dumps(data), ex=self._ttl)
        except Exception:
            logger.warning("Redis недоступен при записи %s", key, exc_info=True)

    async def _forget(self, key: str) -> None:
        if self._redis is None:
            return
        try:
            await self._redis.delete(key)
        except Exception:
            logger.warning("Redis недоступен при удалении %s", key, exc_info=True)


def _error_of(response: httpx.Response, default: tuple[str, str]) -> tuple[str, str]:
    """Код и текст ошибки из ответа Events в едином формате, иначе значения по умолчанию."""
    try:
        error = response.json()["error"]
        return str(error["code"]), str(error["message"])
    except (ValueError, KeyError, TypeError):
        return default
