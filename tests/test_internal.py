import httpx

from tusumba_common import InternalClient


def test_internal_without_token(client):
    r = client.get("/internal/ping")
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "forbidden"


def test_internal_wrong_token(client):
    assert client.get("/internal/ping", headers={"X-Service-Token": "nope"}).status_code == 403


def test_internal_ok(client):
    r = client.get("/internal/ping", headers={"X-Service-Token": "secret-service-token"})
    assert r.status_code == 200


async def test_internal_client_adds_token():
    seen = {}

    def handler(request: httpx.Request):
        seen["token"] = request.headers.get("X-Service-Token")
        return httpx.Response(200, json={"ok": True})

    async with InternalClient(base_url="http://identity:8000",
                              transport=httpx.MockTransport(handler)) as c:
        r = await c.get("/internal/users/1")
    assert r.status_code == 200
    assert seen["token"] == "secret-service-token"
