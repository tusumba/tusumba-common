from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from tusumba_common import ApiError, install_error_handlers


class Thing(BaseModel):
    name: str


def make_client() -> TestClient:
    app = FastAPI()
    install_error_handlers(app)

    @app.post("/things")
    async def create_thing(thing: Thing):
        return thing

    @app.get("/rule")
    async def rule():
        details = [{"field": "date", "message": "Дата в прошлом."}]
        raise ApiError(422, "validation_error", "Дата в прошлом.", details=details)

    return TestClient(app)


def test_api_error_format(client):
    r = client.get("/boom")
    assert r.status_code == 409
    assert r.json() == {"error": {"code": "already_exists", "message": "Уже существует"}}


def test_validation_error_format(client):
    r = client.get("/items/abc")
    assert r.status_code == 422
    error = r.json()["error"]
    assert error["code"] == "validation_error"
    assert error["message"] == "Проверьте введённые данные."
    assert error["details"] == [{"field": "n", "message": "Некорректное значение."}]


def test_not_found_format(client):
    r = client.get("/nope")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"
    assert set(r.json()["error"]) == {"code", "message"}


def test_validation_details_for_body():
    client = make_client()
    r = client.post("/things", json={})
    expected = [{"field": "name", "message": "Заполните обязательное поле."}]
    assert r.json()["error"]["details"] == expected
    r = client.post("/things", content="oops", headers={"Content-Type": "application/json"})
    assert r.json()["error"]["details"] == [{"field": "body", "message": "Некорректный JSON."}]


def test_api_error_with_details():
    r = make_client().get("/rule")
    assert r.status_code == 422
    error = r.json()["error"]
    assert error["message"] == "Дата в прошлом."
    assert error["details"] == [{"field": "date", "message": "Дата в прошлом."}]
