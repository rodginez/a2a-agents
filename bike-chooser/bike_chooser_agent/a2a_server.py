"""
A2A (Agent-to-Agent) server for the Bike Chooser Agent.

Implements the Google A2A protocol:
  - GET  /.well-known/agent.json  →  Agent Card
  - POST /                        →  JSON-RPC 2.0 task endpoint

Supported methods:
  message/send    — send a user message and get a reply (non-streaming)
  message/stream  — send a user message and stream the reply via SSE
  tasks/send      — alias for message/send (backward compat)
  tasks/get       — retrieve an existing task by ID
  tasks/cancel    — cancel a pending/working task

Session state is kept in-memory; each sessionId maintains its own
conversation history for multi-turn interactions.

Usage:
    uvicorn bike_chooser_agent.a2a_server:app --host 0.0.0.0 --port 8080
"""

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncIterator

import anthropic
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.security import APIKeyHeader

from bike_chooser_agent.agent import SYSTEM_PROMPT

load_dotenv()

# ---------------------------------------------------------------------------
# App & client setup
# ---------------------------------------------------------------------------

app = FastAPI(title="Bike Chooser A2A Agent")

_client = anthropic.AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

_A2A_API_KEY = os.getenv("A2A_API_KEY")
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

# ---------------------------------------------------------------------------
# In-memory stores
# ---------------------------------------------------------------------------

_sessions: dict[str, list[dict]] = {}
_tasks: dict[str, dict] = {}

# ---------------------------------------------------------------------------
# Agent Card
# ---------------------------------------------------------------------------

AGENT_URL = os.getenv("AGENT_URL", "http://localhost:8080")

AGENT_CARD = {
    "name": "Bike Chooser Agent",
    "description": (
        "A conversational AI agent that helps you choose the perfect bicycle "
        "based on your needs, budget, terrain, and riding style."
    ),
    "url": AGENT_URL,
    "version": "1.0.0",
    "documentationUrl": f"{AGENT_URL}/docs",
    "capabilities": {
        "streaming": True,
        "pushNotifications": False,
        "stateTransitionHistory": False,
    },
    "defaultInputModes": ["text"],
    "defaultOutputModes": ["text"],
    "securitySchemes": {
        "ApiKeyAuth": {
            "type": "apiKey",
            "in": "header",
            "name": "X-API-Key",
        }
    },
    "security": [{"ApiKeyAuth": []}],
    "skills": [
        {
            "id": "bike-recommendation",
            "name": "Bike Recommendation",
            "description": (
                "Guides users through a friendly conversation to understand "
                "their cycling needs and recommends the best bike for them."
            ),
            "tags": ["bikes", "cycling", "recommendations", "shopping"],
            "examples": [
                "I need a bike for my daily commute of 10 km",
                "What's the best mountain bike under $1,000?",
                "I want to start road cycling — where do I begin?",
                "Help me choose between a gravel bike and a hybrid",
            ],
        }
    ],
}


@app.get("/.well-known/agent.json")
async def agent_card() -> dict:
    return AGENT_CARD


@app.get("/")
async def health() -> dict:
    return {"status": "ok", "agent": AGENT_CARD["name"], "version": AGENT_CARD["version"]}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _extract_text(parts: list[dict]) -> str:
    texts = []
    for p in parts:
        text = p.get("text", "")
        part_type = p.get("type", "text")  # default to "text" if omitted
        if text and part_type == "text":
            texts.append(text)
    return " ".join(texts).strip()


def _make_task(task_id: str, context_id: str, state: str) -> dict:
    messages: list[dict] = []
    for msg in _sessions.get(context_id, []):
        a2a_role = "user" if msg["role"] == "user" else "agent"
        messages.append({
            "messageId": str(uuid.uuid4()),
            "role": a2a_role,
            "parts": [{"type": "text", "text": msg["content"]}],
        })
    return {
        "id": task_id,
        "contextId": context_id,
        "status": {"state": state, "timestamp": _now()},
        "messages": messages,
        "artifacts": [],
    }


def _sse(data: Any) -> str:
    return f"data: {json.dumps(data)}\n\n"


def _rpc_result(rpc_id: Any, result: Any) -> dict:
    return {"jsonrpc": "2.0", "id": rpc_id, "result": result}


def _rpc_error(rpc_id: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": rpc_id, "error": {"code": code, "message": message}}


def _check_auth(request: Request) -> bool:
    if not _A2A_API_KEY:
        return True
    return request.headers.get("X-API-Key") == _A2A_API_KEY


# ---------------------------------------------------------------------------
# JSON-RPC 2.0 dispatcher
# ---------------------------------------------------------------------------

@app.post("/")
async def jsonrpc_handler(request: Request):
    if not _check_auth(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    try:
        body = await request.json()
    except Exception:
        return JSONResponse(_rpc_error(None, -32700, "Parse error"), status_code=400)

    rpc_id = body.get("id")
    method = body.get("method", "")
    params = body.get("params", {})

    if body.get("jsonrpc") != "2.0":
        return JSONResponse(_rpc_error(rpc_id, -32600, "Invalid JSON-RPC version"))

    if method in ("message/send", "tasks/send"):
        return JSONResponse(await _handle_message_send(rpc_id, params))
    if method == "message/stream":
        return StreamingResponse(
            _handle_message_stream(rpc_id, params),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    if method == "tasks/get":
        return JSONResponse(_handle_tasks_get(rpc_id, params))
    if method == "tasks/cancel":
        return JSONResponse(_handle_tasks_cancel(rpc_id, params))

    return JSONResponse(_rpc_error(rpc_id, -32601, f"Method not found: {method}"))


# ---------------------------------------------------------------------------
# Method handlers
# ---------------------------------------------------------------------------

async def _handle_message_send(rpc_id: Any, params: dict) -> dict:
    task_id = params.get("id") or str(uuid.uuid4())
    context_id = params.get("contextId") or params.get("sessionId") or str(uuid.uuid4())
    user_text = _extract_text(params.get("message", {}).get("parts", []))

    if not user_text:
        return _rpc_error(rpc_id, -32602, "Message must contain at least one text part")

    if context_id not in _sessions:
        _sessions[context_id] = []
    _sessions[context_id].append({"role": "user", "content": user_text})

    try:
        response = await _client.messages.create(
            model="claude-opus-4-7",
            max_tokens=1024,
            thinking={"type": "adaptive"},
            system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
            messages=_sessions[context_id],
        )
        agent_reply = next((b.text for b in response.content if b.type == "text"), "")
    except Exception as exc:
        _tasks[task_id] = _make_task(task_id, context_id, "failed")
        return _rpc_error(rpc_id, -32000, f"Agent error: {exc}")

    _sessions[context_id].append({"role": "assistant", "content": agent_reply})
    task = _make_task(task_id, context_id, "completed")
    _tasks[task_id] = task
    return _rpc_result(rpc_id, task)


async def _handle_message_stream(rpc_id: Any, params: dict) -> AsyncIterator[str]:
    task_id = params.get("id") or str(uuid.uuid4())
    context_id = params.get("contextId") or params.get("sessionId") or str(uuid.uuid4())
    user_text = _extract_text(params.get("message", {}).get("parts", []))

    if not user_text:
        yield _sse(_rpc_error(rpc_id, -32602, "Message must contain at least one text part"))
        return

    if context_id not in _sessions:
        _sessions[context_id] = []
    _sessions[context_id].append({"role": "user", "content": user_text})

    yield _sse(_rpc_result(rpc_id, {
        "id": task_id,
        "contextId": context_id,
        "status": {"state": "working", "timestamp": _now()},
    }))

    collected = []
    try:
        async with _client.messages.stream(
            model="claude-opus-4-7",
            max_tokens=1024,
            system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
            messages=_sessions[context_id],
        ) as stream:
            async for text in stream.text_stream:
                collected.append(text)
                yield _sse(_rpc_result(rpc_id, {
                    "id": task_id,
                    "contextId": context_id,
                    "status": {"state": "working", "timestamp": _now()},
                    "delta": {"type": "text", "text": text},
                }))
    except Exception as exc:
        yield _sse(_rpc_error(rpc_id, -32000, f"Agent error: {exc}"))
        return

    agent_reply = "".join(collected)
    _sessions[context_id].append({"role": "assistant", "content": agent_reply})
    task = _make_task(task_id, context_id, "completed")
    _tasks[task_id] = task
    yield _sse(_rpc_result(rpc_id, task))


def _handle_tasks_get(rpc_id: Any, params: dict) -> dict:
    task_id = params.get("id")
    if not task_id:
        return _rpc_error(rpc_id, -32602, "Missing required param: id")
    task = _tasks.get(task_id)
    if task is None:
        return _rpc_error(rpc_id, -32001, f"Task not found: {task_id}")
    return _rpc_result(rpc_id, task)


def _handle_tasks_cancel(rpc_id: Any, params: dict) -> dict:
    task_id = params.get("id")
    if not task_id:
        return _rpc_error(rpc_id, -32602, "Missing required param: id")
    task = _tasks.get(task_id)
    if task is None:
        return _rpc_error(rpc_id, -32001, f"Task not found: {task_id}")
    if task["status"]["state"] in ("completed", "failed", "canceled"):
        return _rpc_error(rpc_id, -32002, f"Task already in terminal state: {task['status']['state']}")
    task["status"] = {"state": "canceled", "timestamp": _now()}
    return _rpc_result(rpc_id, task)
