# A2A Agents — Configuration Log

## Project Overview

Three A2A-compliant agents built with the Anthropic SDK and deployed to Railway. All agents follow the A2A 0.3.0 protocol and are hosted in the GitHub repository [rodginez/a2a-agents](https://github.com/rodginez/a2a-agents).

---

## Agents

| Agent | Railway Project | URL | API Key |
|---|---|---|---|
| Bike Chooser | motivated-optimism | https://motivated-optimism-production-bbb1.up.railway.app | `bike-agent-344c6410acc28384` |
| Bike Upgrade | luminous-encouragement | https://luminous-encouragement-production-17f4.up.railway.app | `bike-upgrade-26ac957adac71379` |
| Bike Spots | disciplined-imagination | https://disciplined-imagination-production-f4b2.up.railway.app | `bike-spots-cf68b86b0aca8331` |

---

## Repository Structure

```
a2a-agent/                          ← GitHub repo: rodginez/a2a-agents
  bike-chooser/
    bike_chooser_agent/
      __init__.py
      agent.py                      ← SYSTEM_PROMPT only
      a2a_server.py                 ← FastAPI A2A server
    Procfile
    requirements.txt
    .gitignore
  bike-upgrade/
    bike_upgrade_agent/
      __init__.py
      agent.py
      a2a_server.py
    Procfile
    requirements.txt
    .gitignore
  bike-spots/
    bike_spots_agent/
      __init__.py
      agent.py
      a2a_server.py
    Procfile
    requirements.txt
    .gitignore
```

---

## Step-by-Step Configuration History

### Step 1 — Initial Bike Chooser Agent

- Created `bike_agent/agent.py` with a `SYSTEM_PROMPT` for a bike advisor
- Created `bike_agent/a2a_server.py` implementing the A2A protocol using FastAPI
- Used `anthropic.AsyncAnthropic` with `claude-opus-4-7` and `thinking: {type: "adaptive"}`
- Applied prompt caching (`cache_control: ephemeral`) on the system prompt

### Step 2 — Railway Deployment (Bike Chooser)

- Authenticated with Railway via browser login (`railway login`)
- Linked the project and set environment variables:
  - `ANTHROPIC_API_KEY` — Anthropic API key
  - `A2A_API_KEY` — `bike-agent-344c6410acc28384`
  - `AGENT_URL` — `https://motivated-optimism-production-bbb1.up.railway.app`
- Deployed via `railway up` from the agent directory
- Procfile: `web: uvicorn bike_chooser_agent.a2a_server:app --host 0.0.0.0 --port $PORT`

### Step 3 — A2A Protocol Compliance Fixes (iterative)

Fixed the following issues discovered through live testing with the A2A inspector:

| Issue | Fix |
|---|---|
| Authentication shown as "No auth" | Replaced non-standard `authentication.schemes` with OpenAPI `securitySchemes`/`security` fields |
| `message/send` method not found | Added routing for `message/send` alongside `tasks/send` |
| "Message must contain at least one text part" | Updated `_extract_text()` to default `type` to `"text"` when the field is absent |
| Pydantic validation errors | Fixed missing `contextId`, `messageId`, and wrong role name (`assistant` → `agent`) |
| `message/stream` not implemented | Added SSE streaming with `AsyncAnthropic` and `StreamingResponse` |
| GET / returning 404 | Added `GET /` health check handler to FastAPI app |

### Step 4 — Bike Upgrade Agent Created

- Created `/bike-upgrade/` as a standalone project mirroring the bike-chooser structure
- Changed agent name to `"Bike Part Upgrade Agent"`, skill id to `"bike-part-upgrade"`
- Wrote a new `SYSTEM_PROMPT` focused on component compatibility, part numbers, and price ranges
- Deployed to Railway project `luminous-encouragement`
- Set environment variables: `ANTHROPIC_API_KEY`, `A2A_API_KEY`, `AGENT_URL`

### Step 5 — Bike Spots Agent Created

- Created `/bike-spots/` as a standalone project
- Agent name: `"Bike Spots Agent"`, skill id: `"bike-spots"`
- `SYSTEM_PROMPT` focused on suggesting public parks, trails, and cycling paths by city
- Deployed to Railway project `disciplined-imagination`
- Set environment variables: `ANTHROPIC_API_KEY`, `A2A_API_KEY`, `AGENT_URL`

### Step 6 — Repository Reorganisation

- Originally all code lived in `supervisor-arch/` alongside an unrelated MTG multiagent framework
- Separated into two independent projects:
  - `rodginez/a2a-agents` — all A2A agents (this repo)
  - `rodginez/ai-multiagent-framework` — the MTG supervisor framework
- Moved `bike-chooser`, `bike-upgrade`, and `bike-spots` into subfolders under a single `a2a-agent/` directory
- Removed nested `.git` directories from subfolders so all agents live in a single repo

### Step 7 — A2A 0.3.0 Upgrade (all agents)

Updated all three agents to comply with the A2A 0.3.0 specification:

| Field / Behaviour | Before | After |
|---|---|---|
| Agent card endpoint | `/.well-known/agent.json` | `/.well-known/agent-card.json` (legacy alias kept) |
| Health check | `GET /` only | `GET /ping` added |
| `protocolVersion` | missing | `"0.3.0"` |
| Input/output modes | `["text"]` | `["text/plain"]` |
| Auth in agent card | `securitySchemes` + `security` | `authentication` object |
| Task `id` field | `id` | `id` (kept — required by inspector's Pydantic model) |
| Task state field | `status.state` nested | `status: {state, timestamp}` object |
| Part type discriminator | `type` | `kind` (with fallback to `type` for older clients) |
| `message/send` result | task object directly | `{"task": {...}}` wrapper |
| Streaming initial event | `{id, contextId, status}` | `{taskId, contextId, status, final: false}` |
| Streaming delta events | `{id, status, delta}` | `{taskId, contextId, artifact: {artifactId, parts, append, lastChunk}}` |
| Streaming final event | full task object | `{taskId, contextId, status, final: true}` |
| `tasks/get` param | `id` | `taskId` (with fallback to `id`) |
| `tasks/cancel` param | `id` | `taskId` (with fallback to `id`) |

### Step 8 — Authentication Field Update (all agents)

Updated the `authentication` field in all three agent cards to:

```json
"authentication": {
  "schemes": ["apiKey"],
  "credentials": "Provide your API key in the X-API-Key request header."
}
```

---

## Environment Variables (per agent)

| Variable | Description |
|---|---|
| `ANTHROPIC_API_KEY` | Anthropic API key for Claude |
| `A2A_API_KEY` | API key clients must send in the `X-API-Key` header |
| `AGENT_URL` | Public URL of the agent (used in the Agent Card `url` field) |

---

## How to Add a New Agent

1. Copy any existing agent subfolder (e.g. `bike-chooser/`) as a template
2. Rename the Python package folder (e.g. `bike_chooser_agent/` → `my_agent/`)
3. Update `agent.py` with the new `SYSTEM_PROMPT`
4. Update `a2a_server.py`: change `app` title, `AGENT_CARD` name/description/skills, and the import path
5. Update `Procfile` to point to the new package
6. Create a new Railway project and set the three environment variables
7. Run `railway link` from the new subfolder, then `railway up`
8. Commit and push to `rodginez/a2a-agents`
