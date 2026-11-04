import time

import jwt

from tusumba_common.testing import generate_keypair, make_token


def bearer(t):
    return {"Authorization": f"Bearer {t}"}


def test_valid_token(client, token):
    r = client.get("/me", headers=bearer(token(user_id="42", roles=["user"])))
    assert r.status_code == 200
    assert r.json() == {"id": "42", "roles": ["user"]}


def test_expired_token(client, token):
    r = client.get("/me", headers=bearer(token(expires_in=-10)))
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "token_expired"


def test_forged_signature(client):
    other_private, _ = generate_keypair()
    r = client.get("/me", headers=bearer(make_token(other_private)))
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "invalid_token"


def test_hs256_and_none_rejected(client, keys):
    forged = jwt.encode({"sub": "1", "exp": int(time.time()) + 60}, "x" * 32, algorithm="HS256")
    assert client.get("/me", headers=bearer(forged)).status_code == 401
    none = jwt.encode({"sub": "1", "exp": int(time.time()) + 60}, None, algorithm="none")
    assert client.get("/me", headers=bearer(none)).status_code == 401


def test_no_token(client):
    r = client.get("/me")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "not_authenticated"


def test_optional_user(client, token):
    assert client.get("/public").json() == {"user": None}
    assert client.get("/public", headers=bearer(token(user_id="7"))).json() == {"user": "7"}
    assert client.get("/public", headers=bearer("garbage")).status_code == 401


def test_moderator(client, token):
    assert client.get("/mod", headers=bearer(token(roles=["user"]))).status_code == 403
    assert client.get("/mod", headers=bearer(token(roles=["moderator"]))).status_code == 200
