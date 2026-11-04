"""Единый формат ошибок: {"error": {"code": "...", "message": "..."}}."""
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class ApiError(Exception):
    def __init__(self, status_code: int, code: str, message: str,
                 headers: dict[str, str] | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.headers = headers


def error_response(status: int, code: str, message: str,
                   headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message}},
        headers=headers,
    )


_HTTP_CODES = {
    400: "bad_request", 401: "unauthorized", 403: "forbidden",
    404: "not_found", 405: "method_not_allowed", 409: "conflict",
    429: "too_many_requests",
}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError):
        return error_response(exc.status_code, exc.code, exc.message, exc.headers)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException):
        code = _HTTP_CODES.get(exc.status_code, "http_error")
        message = exc.detail if isinstance(exc.detail, str) else "Ошибка запроса"
        return error_response(exc.status_code, code, message, getattr(exc, "headers", None))

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError):
        parts = []
        for e in exc.errors():
            loc = ".".join(str(x) for x in e.get("loc", ()) if x != "body")
            parts.append(f"{loc}: {e.get('msg')}" if loc else str(e.get("msg")))
        return error_response(422, "validation_error",
                              "Некорректные данные: " + "; ".join(parts))

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception):
        return error_response(500, "internal_error", "Внутренняя ошибка сервера")
