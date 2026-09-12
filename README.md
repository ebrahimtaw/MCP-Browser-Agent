# Browser MCP Agent

I've built this intelligent MCP agent that enables you to navigate, extract, and
summarize anything in your browser. The agent drives a real headless Chromium, so
it can scroll, click, and fill forms — not just read HTML.

- **Frontend** — Next.js 16, deployed on Vercel.
- **Backend** — FastAPI + [`mcp-agent`](https://github.com/lastmile-ai/mcp-agent)
  talking to the Playwright MCP server, deployed as a Docker container on Render.

The two halves are deployed separately on purpose: Playwright needs a real
Chromium process and a writable filesystem, which Vercel's serverless functions
do not provide.

## Architecture

```
Browser ──► Vercel (Next.js UI)
              │  POST /run_agent  { message, session_id }
              ▼
            Render (FastAPI, Docker)
              │  stdio (MCP)
              ▼
            playwright-mcp ──► headless Chromium
              │
              ▼
            OpenAI (gpt-4o-mini) tool-calling loop
```

One container owns one browser, so agent runs are serialized behind a lock and
conversation history is tracked per `session_id`.

## Configuration

Copy `.env.example` and fill it in. The two that break things when missing:

| Variable | Where | Why it matters |
| --- | --- | --- |
| `OPENAI_API_KEY` | Render | Agent returns `503` without it. |
| `ALLOWED_ORIGINS` | Render | Must contain your Vercel URL or the browser blocks every call with a CORS error. |
| `NEXT_PUBLIC_API_URL` | Vercel | Baked in **at build time** — changing it requires a redeploy, not a restart. |

## Local development

```bash
# Backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
npm install -g @playwright/mcp@0.0.80 && playwright install chromium
export OPENAI_API_KEY="sk-..."
uvicorn backend.app:app --reload --port 8000

# Frontend
cd frontend && npm install && npm run dev
```

Visit http://localhost:3000. `frontend/.env.local` already points at
`http://127.0.0.1:8000`.

## Health and debugging

- `GET /` — cheap always-200 probe (this is what Render's health check uses).
- `GET /health` — the useful one: reports `agent_ready`, `openai_key_configured`,
  and `init_error`.
- `scripts/smoke_test.sh` — run inside the container to verify Chromium launches
  and the MCP server exposes browser tools.

Errors surface as real HTTP status codes: `400` empty prompt, `503` agent or key
unavailable, `504` run exceeded `AGENT_RUN_TIMEOUT`, `500` everything else, with
the reason in the JSON `detail` field.

## Dependency pinning

`requirements.txt` pins `mcp<2` deliberately. `mcp-agent` declares `mcp>=1.20.0`,
and `mcp` 2.x renamed `FastMCP` to `MCPServer`, which breaks `import mcp_agent.app`
at import time. Likewise `@playwright/mcp` is pinned to an exact version in both
the Dockerfile and `mcp_agent.config.yaml`, because it ships alpha builds of
`playwright-core` that expect specific Chromium revisions.
