# tusumba-common

Общая библиотека для всех сервисов бэкенда Tusumba.

**Ответственный:** Артем Власов (задача #18886).

## Что внутри

- проверка JWT (RS256) по публичному ключу Identity: каждый сервис проверяет токен сам;
- сервисный токен для вызовов `/internal`: исходящие вызовы добавляют его в заголовок, входящие проверяют;
- единый формат ошибок API.

## Как используется

Подключается как зависимость в `identity-service`, `events-service`, `ticketing-service`, `moderation-service`, `notifications-service` и в `service-template`. Изменения здесь затрагивают все сервисы, поэтому PR в этот репозиторий проверяет ответственный.

## Стек

Python 3.12, FastAPI, Pydantic v2.

## Документация

Wiki проекта: https://ai.nsu.ru/projects/tusumba/wiki/Архитектура. Задачи ведутся в Redmine: https://ai.nsu.ru/projects/tusumba. Issues и Wiki GitHub выключены.

## Правила работы

Ветки, коммиты, pull request и code review описаны в [CONTRIBUTING.md](https://github.com/tusumba/.github/blob/main/CONTRIBUTING.md). Коротко:

- ветка называется `feature/<номер задачи Redmine>-<пара слов>`, например `feature/18901-login`;
- номер задачи указывается в каждом коммите и в названии PR;
- в `main` изменения попадают только через PR с одним одобрением и зелёным CI, прямой push и force push запрещены.
