import json
import time
import uuid

import fakeredis
import httpx
import pytest

from tusumba_common import ApiError, PermissionsClient

EVENT = str(uuid.uuid4())
CLUB = str(uuid.uuid4())
USER = str(uuid.uuid4())
BASE = "http://events:8000"


class FakeEvents:
    """Подменяет Events & Clubs: считает запросы и отдаёт заданные ответы."""

    def __init__(self):
        self.calls: list[httpx.Request] = []
        self.role: str | None = "admin"
        self.is_admin = True
        self.status = 200

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        path = request.url.path
        if self.status == 404:
            code = "event_not_found" if "/events/" in path else "club_not_found"
            return httpx.Response(404, json={"error": {"code": code, "message": "Недоступно."}})
        if self.status != 200:
            return httpx.Response(self.status, json={"error": {"code": "x", "message": "x"}})
        if "/events/" in path:
            member = self.role is not None
            return httpx.Response(
                200,
                json={
                    "event_id": EVENT,
                    "user_id": request.url.params["user_id"],
                    "is_member": member,
                    **({"role": self.role} if member else {}),
                },
            )
        return httpx.Response(
            200,
            json={
                "club_id": CLUB,
                "user_id": request.url.params["user_id"],
                "is_admin": self.is_admin,
            },
        )


@pytest.fixture
def events():
    return FakeEvents()


@pytest.fixture
def redis():
    return fakeredis.FakeAsyncRedis(decode_responses=True)


@pytest.fixture
async def client(events, redis):
    http = httpx.AsyncClient(base_url=BASE, transport=httpx.MockTransport(events))
    yield PermissionsClient(BASE, redis, client=http)
    await http.aclose()


async def test_event_role_is_returned(client, events):
    perms = await client.event_permissions(EVENT, USER)
    assert perms.is_member is True
    assert perms.role == "admin"
    assert perms.has_role("owner", "admin")
    assert not perms.has_role("scanner")
    request = events.calls[0]
    assert request.url.path == f"/internal/events/{EVENT}/permissions"
    assert request.url.params["user_id"] == USER


async def test_not_a_member(client, events):
    events.role = None
    perms = await client.event_permissions(EVENT, USER)
    assert perms.is_member is False
    assert perms.role is None
    assert not perms.has_role("owner", "admin", "editor", "scanner")


async def test_club_admin(client, events):
    assert (await client.club_permissions(CLUB, USER)).is_admin is True
    events.is_admin = False
    await client.invalidate_club(CLUB, USER)
    assert (await client.club_permissions(CLUB, USER)).is_admin is False
    assert events.calls[0].url.path == f"/internal/clubs/{CLUB}/permissions"


async def test_service_token_is_sent(events, redis):
    # InternalClient сам добавляет X-Service-Token из SERVICE_TOKEN
    seen = {}

    def handler(request):
        seen["token"] = request.headers.get("X-Service-Token")
        return events(request)

    client = PermissionsClient(BASE, redis)
    client._http._transport = httpx.MockTransport(handler)
    await client.event_permissions(EVENT, USER)
    await client.aclose()
    assert seen["token"] == "secret-service-token"


async def test_second_call_is_served_from_cache(client, events, redis):
    first = await client.event_permissions(EVENT, USER)
    second = await client.event_permissions(EVENT, USER)
    assert first == second
    assert len(events.calls) == 1
    assert json.loads(await redis.get(f"permissions:event:{EVENT}:{USER}"))["role"] == "admin"


async def test_cache_is_per_user_and_per_object(client, events):
    other_user = str(uuid.uuid4())
    await client.event_permissions(EVENT, USER)
    await client.event_permissions(EVENT, other_user)
    await client.club_permissions(CLUB, USER)
    assert len(events.calls) == 3


async def test_cache_lives_30_to_60_seconds(client, redis):
    await client.event_permissions(EVENT, USER)
    ttl = await redis.ttl(f"permissions:event:{EVENT}:{USER}")
    assert 30 <= ttl <= 60


async def test_cache_expires(client, events, redis, monkeypatch):
    await client.event_permissions(EVENT, USER)
    await client.event_permissions(EVENT, USER)
    assert len(events.calls) == 1

    events.role = "scanner"
    real_time = time.time
    monkeypatch.setattr(time, "time", lambda: real_time() + 61)
    perms = await client.event_permissions(EVENT, USER)

    assert len(events.calls) == 2  # кеш истёк, снова спросили Events
    assert perms.role == "scanner"  # и получили свежую роль


async def test_invalidate_forces_new_request(client, events):
    await client.event_permissions(EVENT, USER)
    events.role = "owner"
    await client.invalidate_event(EVENT, USER)
    assert (await client.event_permissions(EVENT, USER)).role == "owner"
    assert len(events.calls) == 2


async def test_not_found_is_raised_and_not_cached(client, events):
    events.status = 404
    with pytest.raises(ApiError) as error:
        await client.event_permissions(EVENT, USER)
    assert error.value.status_code == 404
    assert error.value.code == "event_not_found"

    events.status = 200
    assert (await client.event_permissions(EVENT, USER)).is_member is True  # не закешировано
    assert len(events.calls) == 2


async def test_club_not_found(client, events):
    events.status = 404
    with pytest.raises(ApiError) as error:
        await client.club_permissions(CLUB, USER)
    assert error.value.code == "club_not_found"


@pytest.mark.parametrize("status", [403, 500, 503])
async def test_events_failure_becomes_503_and_is_not_cached(client, events, redis, status):
    events.status = status
    with pytest.raises(ApiError) as error:
        await client.event_permissions(EVENT, USER)
    assert error.value.status_code == 503
    assert error.value.code == "service_unavailable"
    assert await redis.get(f"permissions:event:{EVENT}:{USER}") is None


async def test_network_error_becomes_503(redis):
    def boom(request):
        raise httpx.ConnectError("down")

    http = httpx.AsyncClient(base_url=BASE, transport=httpx.MockTransport(boom))
    client = PermissionsClient(BASE, redis, client=http)
    with pytest.raises(ApiError) as error:
        await client.club_permissions(CLUB, USER)
    assert error.value.status_code == 503
    await http.aclose()


async def test_works_without_redis(events):
    http = httpx.AsyncClient(base_url=BASE, transport=httpx.MockTransport(events))
    client = PermissionsClient(BASE, None, client=http)
    await client.event_permissions(EVENT, USER)
    await client.event_permissions(EVENT, USER)
    assert len(events.calls) == 2
    await http.aclose()


async def test_redis_failure_does_not_break_requests(events):
    class BrokenRedis:
        async def get(self, name):
            raise ConnectionError("redis down")

        async def set(self, name, value, ex=None):
            raise ConnectionError("redis down")

        async def delete(self, *names):
            raise ConnectionError("redis down")

    http = httpx.AsyncClient(base_url=BASE, transport=httpx.MockTransport(events))
    client = PermissionsClient(BASE, BrokenRedis(), client=http)
    assert (await client.event_permissions(EVENT, USER)).role == "admin"
    await client.invalidate_event(EVENT, USER)
    await http.aclose()


async def test_corrupt_cache_entry_is_ignored(client, events, redis):
    await redis.set(f"permissions:event:{EVENT}:{USER}", "not json")
    assert (await client.event_permissions(EVENT, USER)).role == "admin"
    assert len(events.calls) == 1


async def test_invalid_ids_are_rejected_before_any_request(client, events):
    with pytest.raises(ValueError):
        await client.event_permissions("../../etc", USER)
    assert events.calls == []


@pytest.mark.parametrize("ttl", [0, 29, 61])
def test_ttl_must_be_30_to_60_seconds(ttl):
    with pytest.raises(ValueError):
        PermissionsClient(BASE, None, ttl_seconds=ttl)
