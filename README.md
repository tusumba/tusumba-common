# tusumba-common

Общая Python-библиотека бэкенд-сервисов Tusumba. Одинаково для всех пяти сервисов:

- проверка пользователя по JWT (RS256, публичный ключ Identity);
- защита и вызовы `/internal` по сервисному токену;
- единый формат ошибок `{"error": {"code": "...", "message": "..."}}`.

## Установка

В `requirements.txt` / `pyproject.toml` сервиса, по тегу версии:

```
tusumba-common @ git+https://github.com/tusumba/tusumba-common.git@v0.1.0
```

## Переменные окружения

| Переменная | Для чего |
|---|---|
| `JWT_PUBLIC_KEY` | Публичный ключ Identity в PEM (допустим вид с `\n` одной строкой) |
| `SERVICE_TOKEN` | Общий сервисный токен для заголовка `X-Service-Token` |

## Подключение

```python
from fastapi import Depends, FastAPI
from tusumba_common import (ApiError, CurrentUser, InternalClient, get_current_user,
                            install_error_handlers, optional_user, require_moderator,
                            require_service)

app = FastAPI()
install_error_handlers(app)   # все ошибки, включая валидацию, в едином формате

@app.get("/v1/me")
async def me(user: CurrentUser = Depends(get_current_user)):
    return {"id": user.id, "roles": user.roles}

@app.get("/v1/events")                       # доступно без входа
async def events(user: CurrentUser | None = Depends(optional_user)):
    ...

@app.post("/v1/moderation/x")                # только модератор
async def mod(user: CurrentUser = Depends(require_moderator)):
    ...

@app.get("/internal/users/{id}", dependencies=[Depends(require_service)])
async def internal_user(id: str):            # без верного X-Service-Token — 403
    ...

@app.get("/v1/orders")
async def orders():
    async with InternalClient(base_url="http://identity:8000") as c:   # токен добавится сам
        r = await c.get("/internal/users/1")
    raise ApiError(404, "order_not_found", "Заказ не найден")
```

## Ошибки

| Ситуация | HTTP | `code` |
|---|---|---|
| Нет заголовка Authorization | 401 | `not_authenticated` |
| Подпись неверна / токен повреждён | 401 | `invalid_token` |
| Срок действия истёк | 401 | `token_expired` |
| Нет нужной роли | 403 | `forbidden` |
| `/internal` без верного токена | 403 | `forbidden` |
| Ошибка валидации | 422 | `validation_error` |
| Необработанная ошибка | 500 | `internal_error` |

Своя ошибка: `raise ApiError(409, "already_exists", "Уже существует")`.

Формат токена: `sub` — id пользователя, `roles` — список строк, модератор — роль `moderator`. Принимается только RS256.

## Разработка

Тестовая пара ключей:

```
python -m tusumba_common.testing dev-keys
export JWT_PUBLIC_KEY="$(cat dev-keys/public.pem)"
```

В тестах сервиса: `from tusumba_common.testing import generate_keypair, make_token`.

```
pip install -e ".[dev]"
pytest
```

Релиз: тег `vX.Y.Z` на main, версию поднять в `pyproject.toml`.
