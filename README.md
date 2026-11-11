# tusumba-common

Общая Python-библиотека бэкенд-сервисов Tusumba. Одинаково для всех пяти сервисов:

- проверка пользователя по JWT (RS256, публичный ключ Identity);
- защита и вызовы `/internal` по сервисному токену;
- проверка прав на мероприятие и секцию через Events & Clubs с кешем в Redis;
- единый формат ошибок `{"error": {"code": "...", "message": "..."}}`, у ошибок по полям ещё `details`.

## Установка

В `requirements.txt` / `pyproject.toml` сервиса, по тегу версии:

```
tusumba-common @ git+https://github.com/tusumba/tusumba-common.git@v0.4.0
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
| Подпись неверна / токен повреждён / не access-токен | 401 | `invalid_token` |
| Срок действия истёк | 401 | `token_expired` |
| Нет нужной роли | 403 | `forbidden` |
| `/internal` без верного токена | 403 | `forbidden` |
| Ошибка валидации | 422 | `validation_error` |
| Необработанная ошибка | 500 | `internal_error` |

Своя ошибка: `raise ApiError(409, "already_exists", "Уже существует")`.

Ошибка валидации приходит с общим текстом «Проверьте введённые данные.» и списком `details`: в каждом элементе `field` — путь к полю без `body`, `query` и `path` (например `event.date`, `size`), `message` — текст на русском. Нужен текст из требования — бросьте свою ошибку с `details`: `raise ApiError(422, "validation_error", "Дата в прошлом.", details=[{"field": "date", "message": "Дата в прошлом."}])`.

Формат токена: `sub` — id пользователя, `roles` — список строк, модератор — роль `moderator`, `typ` — `access`, `exp` — срок действия. Принимается только RS256.

Сервисы принимают только access-токен. Токен без `typ` или с другим значением, например refresh-токен (`typ` = `refresh`), получает 401 `invalid_token`: refresh-токен принимает только Identity в `POST /v1/auth/refresh`.

## Права на мероприятие и секцию

`PermissionsClient` спрашивает Events & Clubs (`GET /internal/events/{id}/permissions?user_id=` и
`GET /internal/clubs/{id}/permissions?user_id=`, OpenAPI Events) и кеширует ответ в Redis на 30-60 секунд
(по умолчанию 45). Сервисный токен клиент добавляет сам. Нужен пакет `redis`:
`tusumba-common[redis] @ git+https://github.com/tusumba/tusumba-common.git@v0.4.0`.

```python
from redis.asyncio import Redis
from tusumba_common import ApiError, PermissionsClient

redis = Redis.from_url("redis://redis:6379/0", decode_responses=True)
permissions = PermissionsClient("http://events:8000", redis)   # redis=None - без кеша

# Ticketing, Moderation: роль в команде мероприятия
perms = await permissions.event_permissions(event_id, user.id)
if not perms.has_role("owner", "admin"):
    raise ApiError(403, "forbidden", "Недостаточно прав.")

# Moderation: заявка от имени секции
if not (await permissions.club_permissions(club_id, user.id)).is_admin:
    raise ApiError(403, "club_forbidden", "У вас нет прав на выбранную секцию.")
```

- `EventPermissions`: `is_member`, `role` (`owner`, `admin`, `editor`, `scanner` или `None`), `has_role(*roles)`;
  `ClubPermissions`: `is_admin`;
- нет мероприятия или секции - `ApiError` 404 с кодом `event_not_found` или `club_not_found` (не кешируется);
- Events не ответил, вернул 5xx или отклонил сервисный токен - `ApiError` 503 `service_unavailable`, в кеш не попадает;
- Redis недоступен - клиент пишет предупреждение в лог и ходит в Events напрямую;
- после смены роли можно сбросить кеш: `await permissions.invalidate_event(event_id, user_id)` (так же `invalidate_club`);
  иначе новая роль подхватится не позже чем через минуту;
- в конце работы: `await permissions.aclose()`.

## Разработка

Тестовая пара ключей:

```
python -m tusumba_common.testing dev-keys
export JWT_PUBLIC_KEY="$(cat dev-keys/public.pem)"
```

В тестах сервиса: `from tusumba_common.testing import generate_keypair, make_token`. `make_token` выпускает access-токен (`typ` = `access`), другой тип можно передать в `typ`.

```
pip install -e ".[dev]"   # с redis и fakeredis для тестов
pytest
```

Релиз: тег `vX.Y.Z` на main, версию поднять в `pyproject.toml`.
