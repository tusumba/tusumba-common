def test_api_error_format(client):
    r = client.get("/boom")
    assert r.status_code == 409
    assert r.json() == {"error": {"code": "already_exists", "message": "Уже существует"}}


def test_validation_error_format(client):
    r = client.get("/items/abc")
    assert r.status_code == 422
    body = r.json()
    assert set(body) == {"error"}
    assert body["error"]["code"] == "validation_error"
    assert isinstance(body["error"]["message"], str)


def test_not_found_format(client):
    r = client.get("/nope")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"
    assert set(r.json()["error"]) == {"code", "message"}
