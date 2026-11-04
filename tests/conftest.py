import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from tusumba_common import (
    ApiError,
    CurrentUser,
    get_current_user,
    install_error_handlers,
    optional_user,
    require_moderator,
    require_service,
)
from tusumba_common.testing import generate_keypair, make_token


@pytest.fixture(scope="session")
def keys():
    return generate_keypair()


@pytest.fixture(autouse=True)
def env(monkeypatch, keys):
    monkeypatch.setenv("JWT_PUBLIC_KEY", keys[1])
    monkeypatch.setenv("SERVICE_TOKEN", "secret-service-token")


@pytest.fixture
def app():
    app = FastAPI()
    install_error_handlers(app)

    @app.get("/me")
    async def me(user: CurrentUser = Depends(get_current_user)):
        return {"id": user.id, "roles": user.roles}

    @app.get("/public")
    async def public(user: CurrentUser | None = Depends(optional_user)):
        return {"user": user.id if user else None}

    @app.get("/mod")
    async def mod(user: CurrentUser = Depends(require_moderator)):
        return {"id": user.id}

    @app.get("/internal/ping", dependencies=[Depends(require_service)])
    async def ping():
        return {"ok": True}

    @app.get("/boom")
    async def boom():
        raise ApiError(409, "already_exists", "Уже существует")

    @app.get("/items/{n}")
    async def item(n: int):
        return {"n": n}

    return app


@pytest.fixture
def client(app):
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def token(keys):
    return lambda **kw: make_token(keys[0], **kw)
