"""Единый формат ошибок: {"error": {"code": "...", "message": "..."}}."""
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class ApiError(Exception):
    def __init__(self, status_code: int, code: str, message: str,
                 headers: dict[str, str] | None = None,
                 details: list[dict[str, str]] | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.headers = headers
        self.details = details


def error_response(status: int, code: str, message: str,
                   headers: dict[str, str] | None = None,
                   details: list[dict[str, str]] | None = None) -> JSONResponse:
    error: dict[str, object] = {"code": code, "message": message}
    if details is not None:
        error["details"] = details
    return JSONResponse(status_code=status, content={"error": error}, headers=headers)


_HTTP_CODES = {
    400: "bad_request", 401: "unauthorized", 403: "forbidden",
    404: "not_found", 405: "method_not_allowed", 409: "conflict",
    429: "too_many_requests",
}

VALIDATION_MESSAGE = "Проверьте введённые данные."
_LOCATIONS = {"body", "query", "path", "header", "cookie"}
_FIELD_MESSAGES = {"missing": "Заполните обязательное поле.", "json_invalid": "Некорректный JSON."}


def _field_error(error: dict[str, Any]) -> dict[str, str]:
    loc = [str(x) for x in error.get("loc", ())]
    if loc and loc[0] in _LOCATIONS:
        loc = loc[1:]
    if error.get("type") == "json_invalid":
        loc = []
    message = _FIELD_MESSAGES.get(str(error.get("type")), "Некорректное значение.")
    return {"field": ".".join(loc) or "body", "message": message}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError):
        return error_response(exc.status_code, exc.code, exc.message, exc.headers, exc.details)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException):
        code = _HTTP_CODES.get(exc.status_code, "http_error")
        message = exc.detail if isinstance(exc.detail, str) else "Ошибка запроса"
        return error_response(exc.status_code, code, message, getattr(exc, "headers", None))

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError):
        details = [_field_error(e) for e in exc.errors()]
        return error_response(422, "validation_error", VALIDATION_MESSAGE, details=details)

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception):
        return error_response(500, "internal_error", "Внутренняя ошибка сервера")
