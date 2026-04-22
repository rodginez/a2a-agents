# A2A Agents

A production-ready template for building and deploying AI agents that expose the [Agent-to-Agent (A2A) protocol](https://google.github.io/A2A/), allowing them to be discovered and called by any A2A-compatible client.

Built with [FastAPI](https://fastapi.tiangolo.com/) and the [Anthropic Python SDK](https://github.com/anthropics/anthropic-sdk-python).

---

## What is A2A?

A2A (Agent-to-Agent) is an open protocol by Google that defines how AI agents communicate with each other and with client applications. It provides:

- **Discovery** — a standard `/.well-known/agent.json` endpoint (Agent Card) that describes the agent's capabilities, skills, and authentication requirements
- **Invocation** — a JSON-RPC 2.0 `POST /` endpoint for sending messages and receiving replies
- **Streaming** — SSE-based streaming for real-time token-by-token responses
- **Multi-turn conversations** — session state via `contextId` to maintain conversation history across calls

Any A2A-compatible client can discover and interact with your agent without custom integration code.

---

## Project Structure

```
bike_agent/
  agent.py        # System prompt — the only file you change per agent
  a2a_server.py   # A2A-compliant FastAPI server (reusable across agents)
A2A_SPEC.md       # Validated A2A protocol reference (field rules, gotchas)
Procfile          # Railway deployment entry point
requirements.txt
```

---

## How It Works

### 1. Agent Card

Every A2A agent advertises itself at `GET /.well-known/agent.json`. This tells clients the agent's name, skills, supported methods, and how to authenticate.

### 2. Message Flow

Clients call `POST /` with a JSON-RPC 2.0 payload. The server:

1. Authenticates the request via `X-API-Key` header
2. Retrieves or creates the conversation history for the given `contextId`
3. Appends the user message and calls Claude with the full history
4. Appends the agent reply and returns a Task object with the complete conversation

### 3. Multi-turn Conversations

State is maintained per `contextId`. Sending subsequent messages with the same `contextId` gives Claude the full conversation history, enabling natural multi-turn interactions.

### 4. Streaming

`message/stream` returns a `text/event-stream` response. The client receives:
- A `working` status event immediately
- One event per token chunk as Claude generates the reply
- A final `completed` event with the full Task object

---

## Supported Methods

| Method | Description |
|---|---|
| `message/send` | Send a message, receive the full reply at once |
| `message/stream` | Send a message, stream the reply token-by-token via SSE |
| `tasks/get` | Retrieve a past task by ID |
| `tasks/cancel` | Cancel a non-terminal task |

---

## Building a New Agent

Only two things need to change per agent:

**1. Edit `agent.py`** — replace the system prompt with your agent's persona and instructions:

```python
SYSTEM_PROMPT = """You are an expert in X.
Your job is to help users with Y.
..."""
```

**2. Update the Agent Card in `a2a_server.py`** — set the name, description, and skills:

```python
AGENT_CARD = {
    "name": "Your Agent Name",
    "description": "What your agent does.",
    "skills": [
        {
            "id": "your-skill-id",
            "name": "Skill Name",
            "description": "What this skill does.",
            "tags": ["tag1", "tag2"],
            "examples": ["Example prompt"],
        }
    ],
    ...
}
```

Everything else — the A2A protocol handling, streaming, authentication, session management — stays the same.

> See [A2A_SPEC.md](A2A_SPEC.md) for the full validated protocol reference including field rules, response shapes, and implementation gotchas.

---

## Deployment (Railway)

```bash
# 1. Install Railway CLI
brew install railway

# 2. Login and deploy
railway login
railway init
railway up

# 3. Set environment variables
railway variables set ANTHROPIC_API_KEY=sk-ant-...
railway variables set A2A_API_KEY=your-secret-key
railway variables set AGENT_URL=https://your-app.up.railway.app

# 4. Generate a public domain
railway domain
```

The `Procfile` handles the rest:
```
web: uvicorn bike_agent.a2a_server:app --host 0.0.0.0 --port $PORT
```

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | Yes | Your Anthropic API key |
| `AGENT_URL` | Yes | Public URL of the deployed agent (used in Agent Card) |
| `A2A_API_KEY` | No | If set, all `POST /` requests must include `X-API-Key: <value>`. Leave unset for open access. |

---

## Local Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

ANTHROPIC_API_KEY=sk-ant-... uvicorn bike_agent.a2a_server:app --reload --port 8080
```

Test the agent card:
```bash
curl http://localhost:8080/.well-known/agent.json
```

Send a message:
```bash
curl -X POST http://localhost:8080/ \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "1",
    "method": "message/send",
    "params": {
      "id": "task-1",
      "contextId": "session-abc",
      "message": {
        "messageId": "msg-1",
        "role": "user",
        "parts": [{ "type": "text", "text": "Hello" }]
      }
    }
  }'
```
