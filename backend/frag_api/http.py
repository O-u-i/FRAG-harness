from __future__ import annotations

import json
from collections.abc import Awaitable, Callable

from fastapi import Request
from fastapi.responses import JSONResponse

MAX_BODY_BYTES = 16 * 1024


def error_response(
    status: int,
    code: str,
    message: str,
    issues: list[dict[str, str]] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "issues": issues or []}},
        headers=headers,
    )


class BodyLimitMiddleware:
    def __init__(self, app, max_bytes: int = MAX_BODY_BYTES):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        max_bytes = self.max_bytes
        messages: list[dict] = []
        total = 0
        while True:
            message = await receive()
            messages.append(message)
            if message["type"] == "http.disconnect":
                return
            total += len(message.get("body", b""))
            if total > max_bytes:
                await error_response(
                    413, "REQUEST_TOO_LARGE", "Request body exceeds the allowed size."
                )(scope, receive, send)
                return
            if not message.get("more_body", False):
                break
        iterator = iter(messages)
        body = b"".join(message.get("body", b"") for message in messages)
        content_type = next(
            (
                value.decode("latin-1").lower()
                for name, value in scope.get("headers", [])
                if name.lower() == b"content-type"
            ),
            "",
        )
        if body and content_type.startswith("application/json"):
            try:
                parsed = json.loads(body)
                if not isinstance(parsed, (dict, list)):
                    raise json.JSONDecodeError("JSON body must be an object or array", "", 0)
            except (json.JSONDecodeError, UnicodeDecodeError):
                await error_response(
                    400, "MALFORMED_JSON", "Request body contains malformed JSON."
                )(scope, receive, send)
                return

        async def replay():
            try:
                return next(iterator)
            except StopIteration:
                return {"type": "http.request", "body": b"", "more_body": False}

        await self.app(scope, replay, send)


def issue_path(location: tuple[object, ...]) -> str:
    return ".".join(str(part) for part in location)


async def reject_query(request: Request) -> None:
    if request.query_params:
        from frag_api.errors import RequestContractError

        raise RequestContractError([{"path": "query", "message": "Unknown query parameters."}])


async def reject_body(request: Request) -> None:
    if await request.body():
        from frag_api.errors import RequestContractError

        raise RequestContractError([{"path": "body", "message": "Request body is not allowed."}])
