import os

# ---------------------------------------------------------------------------
# Protobuf compatibility patch — a2a-sdk issue #1011
# field.label was removed in protobuf 5.x+; patch proto_utils BEFORE any
# other a2a modules are imported so all subsequent imports get fixed refs.
# ---------------------------------------------------------------------------
import a2a.utils.proto_utils as _proto_utils
from typing import Any as _Any
from google.protobuf.descriptor import FieldDescriptor as _FD
from google.protobuf.json_format import ParseDict as _ParseDict
from google.protobuf.message import Message as _PBMessage


def _parse_params_fixed(params: _Any, message: _PBMessage) -> None:
    descriptor = message.DESCRIPTOR
    fields = {f.camelcase_name: f for f in descriptor.fields}
    processed: dict[str, _Any] = {}
    for k in params.keys():
        if k not in fields:
            continue
        field = fields[k]
        v_list = params.getlist(k)
        if field.is_repeated:
            accumulated: list[_Any] = []
            for v in v_list:
                if not v:
                    continue
                accumulated.extend([x for x in v.split(",") if x] if isinstance(v, str) else [v])
            processed[k] = accumulated
        else:
            raw_val = v_list[-1]
            if raw_val is not None:
                processed[k] = (raw_val.lower() == "true") if field.type == _FD.TYPE_BOOL and isinstance(raw_val, str) else raw_val
    _ParseDict(processed, message, ignore_unknown_fields=True)


def _check_required_field_violation_fixed(msg: _PBMessage, field: _FD) -> _Any:
    val = getattr(msg, field.name)
    if field.is_repeated:
        if not val:
            return {"field": field.name, "message": "Field must contain at least one element."}
    elif field.has_presence:
        if not msg.HasField(field.name):
            return {"field": field.name, "message": "Field is required."}
    elif val == field.default_value:
        return {"field": field.name, "message": "Field is required."}
    return None


def _recurse_validation_fixed(msg: _PBMessage, field: _FD) -> list:
    errors: list = []
    if field.type != _FD.TYPE_MESSAGE:
        return errors
    val = getattr(msg, field.name)
    if not field.is_repeated:
        if msg.HasField(field.name):
            sub_errs = _proto_utils._validate_proto_required_fields_internal(val)
            _proto_utils._append_nested_errors(errors, field.name, sub_errs)
    elif field.message_type.GetOptions().map_entry:
        for k, v in val.items():
            if isinstance(v, _PBMessage):
                sub_errs = _proto_utils._validate_proto_required_fields_internal(v)
                _proto_utils._append_nested_errors(errors, f"{field.name}[{k}]", sub_errs)
    else:
        for i, item in enumerate(val):
            sub_errs = _proto_utils._validate_proto_required_fields_internal(item)
            _proto_utils._append_nested_errors(errors, f"{field.name}[{i}]", sub_errs)
    return errors


_proto_utils.parse_params = _parse_params_fixed
_proto_utils._check_required_field_violation = _check_required_field_violation_fixed
_proto_utils._recurse_validation = _recurse_validation_fixed
# ---------------------------------------------------------------------------

import uvicorn
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import (
    APIKeySecurityScheme,
    AgentCapabilities,
    AgentCard,
    AgentInterface,
    AgentSkill,
    SecurityRequirement,
    SecurityScheme,
    StringList,
)
from dotenv import load_dotenv
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from bike_spots_agent.agent_executor import BikeSpotAgentExecutor

load_dotenv()

AGENT_URL = os.getenv("AGENT_URL", "http://localhost:8080")
A2A_API_KEY = os.getenv("A2A_API_KEY")

_PUBLIC_PATHS = {"/.well-known/agent-card.json", "/ping"}


class APIKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not A2A_API_KEY or request.url.path in _PUBLIC_PATHS:
            return await call_next(request)
        if request.headers.get("X-API-Key") != A2A_API_KEY:
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        return await call_next(request)


skill = AgentSkill(
    id="bike-spots",
    name="Bike Spots",
    description=(
        "Helps cyclists find the best public places to ride in any city — "
        "parks, greenways, trails, and cycling paths with practical tips."
    ),
    tags=["bikes", "cycling", "spots", "trails", "parks"],
    examples=[
        "Where can I ride my bike in Barcelona?",
        "Best mountain bike trails near Denver",
        "Family-friendly cycling paths in Amsterdam",
        "I want a long gravel route around London",
    ],
)

agent_card = AgentCard(
    name="Bike Spots Agent",
    description=(
        "A conversational AI agent that recommends the best public cycling spots "
        "in any city, tailored to your riding style and experience level."
    ),
    version="1.0.0",
    default_input_modes=["text/plain"],
    default_output_modes=["text/plain"],
    capabilities=AgentCapabilities(streaming=True),
    skills=[skill],
    supported_interfaces=[
        AgentInterface(url=AGENT_URL, protocol_binding="JSONRPC"),
    ],
    security_schemes={
        "ApiKeyAuth": SecurityScheme(
            api_key_security_scheme=APIKeySecurityScheme(
                location="header",
                name="X-API-Key",
                description="Provide your API key in the X-API-Key request header.",
            )
        )
    },
    security_requirements=[SecurityRequirement(schemes={"ApiKeyAuth": StringList()})],
)

request_handler = DefaultRequestHandler(
    agent_executor=BikeSpotAgentExecutor(),
    task_store=InMemoryTaskStore(),
    agent_card=agent_card,
)

app = Starlette(
    routes=[
        *create_agent_card_routes(agent_card),
        *create_jsonrpc_routes(request_handler, rpc_url="/", enable_v0_3_compat=True),
    ]
)
app.add_middleware(APIKeyMiddleware)

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
