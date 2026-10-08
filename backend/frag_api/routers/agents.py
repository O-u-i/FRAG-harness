"""Opt-in loopback carrier, review control and built review-page delivery."""
import asyncio
import json
from pathlib import Path
from typing import Annotated
from urllib.parse import urlsplit
from fastapi import APIRouter, Body, Depends, Request, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import FileResponse
from pydantic import ValidationError
from frag_api.errors import RuntimeConflictError, RuntimeNotFoundError, RequestContractError
from frag_api.http import reject_body, reject_query
from frag_api.schemas.agents import AgentPrepare, AgentExecute, AgentCheck
from frag_api.services.agent_host import AgentConnection, ProtocolError

router = APIRouter()
LOOPBACK = {"127.0.0.1", "::1", "localhost"}


def allowed(request):
    host = request.headers.get("host", "")
    try:
        hostname = urlsplit("http://" + host).hostname
    except ValueError:
        return False
    return request.client and request.client.host in LOOPBACK and hostname in LOOPBACK


def enabled(request: Request):
    if not request.app.state.agent_host_enabled or not allowed(request):
        raise HTTPException(404)
    origin = request.headers.get("origin")
    if origin and origin != request.app.state.agent_host.review_origin:
        raise HTTPException(403)


guards = [Depends(enabled), Depends(reject_query)]


@router.get("/api/agents/sessions", dependencies=[*guards, Depends(reject_body)])
def sessions(request: Request):
    return request.app.state.agent_host.runtime.repository.agent_sessions()


@router.get("/api/agents/sessions/{session_id}", dependencies=[*guards, Depends(reject_body)])
def view(request: Request, session_id: str):
    host = request.app.state.agent_host
    with host.lock, host.model_route(session_id):
        carrier = host.current(session_id)
        turn = carrier.turns[-1] if carrier.turns else None
        report = host.runtime.repository.get(turn.run_id) if turn and turn.run_id else None
        pending = host.pending.get(session_id)
        preview = pending[4] if pending and carrier.version == pending[0] and report and report.run.version == pending[2] else None
        return host.review_view(carrier, report, preview)


@router.post("/api/agents/sessions/{session_id}/prepare", dependencies=guards)
def prepare(request: Request, session_id: str, body: Annotated[AgentPrepare, Body()]):
    try:
        return request.app.state.agent_host.prepare(session_id, body)
    except ValidationError as error:
        raise RequestContractError([{"path": "sourceRequest", "message": "Select valid evidence for this task."}]) from error


@router.post("/api/agents/sessions/{session_id}/recover", dependencies=guards)
def recover(request: Request, session_id: str, body: Annotated[AgentCheck, Body()]):
    return request.app.state.agent_host.recover(session_id, body.version, body.turn_id)


@router.post("/api/agents/sessions/{session_id}/execute", dependencies=guards)
def execute(request: Request, session_id: str, body: Annotated[AgentExecute, Body()]):
    return request.app.state.agent_host.execute(session_id, body)


@router.post("/api/agents/sessions/{session_id}/cancel", dependencies=guards)
def cancel(request: Request, session_id: str, body: Annotated[AgentCheck, Body()]):
    host = request.app.state.agent_host
    with host.lock:
        host.check(session_id, body.version, body.turn_id)
        host.cancel(session_id, body.turn_id)
        return view(request, session_id)


@router.get("/review")
def review_page(request: Request):
    if not request.app.state.agent_host_enabled or not allowed(request):
        raise HTTPException(404)
    path = request.app.state.review_assets / "index.html"
    if not path.is_file():
        raise HTTPException(503)
    return FileResponse(path, headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; font-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"})


@router.get("/review/help", dependencies=[Depends(enabled)])
def help_page(request: Request):
    return FileResponse(request.app.state.review_help, media_type="text/plain")


@router.websocket("/api/agents/ahp")
async def carrier(socket: WebSocket):
    # Native Electron connects with a vscode-file origin; arbitrary websites cannot drive the host.
    if (not socket.app.state.agent_host_enabled or not allowed(socket)
            or socket.headers.get("origin") not in (None, "vscode-file://vscode-app")):
        await socket.close(code=1008)
        return
    await socket.accept()
    host = socket.app.state.agent_host
    connection = AgentConnection(host)
    host.clients.add(connection)

    async def writer():
        while True:
            if connection.failed:
                await socket.close(code=1013)
                return
            await socket.send_json(await connection.queue.get())

    tasks = [asyncio.create_task(writer())]
    try:
        while True:
            raw = await socket.receive_text()
            if len(raw.encode()) > 256 * 1024:
                await socket.close(code=1009)
                break
            message = None
            try:
                message = json.loads(raw)
                if (not isinstance(message, dict) or message.get("jsonrpc") != "2.0"
                        or not isinstance(message.get("method"), str) or not isinstance(message.get("params", {}), dict)):
                    raise ProtocolError(-32600, "Invalid JSON-RPC request.")
                result = await connection.request(message["method"], message.get("params", {}))
                if "id" in message:
                    connection.queue.put_nowait({"jsonrpc": "2.0", "id": message["id"], "result": result})
            except (ProtocolError, RuntimeNotFoundError, RuntimeConflictError, ValidationError, ValueError, TypeError, KeyError, AttributeError) as error:
                payload = error.payload if isinstance(error, ProtocolError) else {"code": -32602, "message": "Invalid or stale FRAG carrier request."}
                if isinstance(message, dict) and "id" in message:
                    connection.queue.put_nowait({"jsonrpc": "2.0", "id": message["id"], "error": payload})
                elif isinstance(message, dict) and message.get("method") == "dispatchAction":
                    params = message.get("params", {})
                    action = params.get("action", {}) if isinstance(params, dict) else {}
                    if isinstance(action, dict) and action.get("type") == "chat/turnStarted" and isinstance(action.get("turnId"), str):
                        await host.emit(params.get("channel", ""), {"type": "chat/error", "turnId": action["turnId"][:128],
                            "duration": 0, "part": {"kind": "error", "id": "frag-invalid-task",
                                "error": {"message": payload["message"]}, "resumable": False}})
    except WebSocketDisconnect:
        pass
    except asyncio.QueueFull:
        await socket.close(code=1013)
    finally:
        host.clients.discard(connection)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
