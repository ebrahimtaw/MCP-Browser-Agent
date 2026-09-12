# Browser MCP Agent

I've built this intelligent MCP agent that enables you to navigate, extract, and
summarize anything in your browser. The agent drives a real headless Chromium, so
it can scroll, click, and fill forms — not just read HTML.

- **Frontend** — Next.js 16, deployed on Vercel.
- **Backend** — FastAPI + [`mcp-agent`](https://github.com/lastmile-ai/mcp-agent)
  talking to the Playwright MCP server, deployed as a Docker container on Fly.io
  (`fly.toml`). `render.yaml` is kept for the equivalent Render setup.

The two halves are deployed separately on purpose: Playwright needs a real
Chromium process and a writable filesystem, which Vercel's serverless functions
do not provide.

## Architecture

```
Browser ──► Vercel (Next.js UI)
              │  POST /run_agent  { message, session_id }
              ▼
            Fly.io (FastAPI, Docker)
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
| `OPENAI_API_KEY` | Fly | Agent returns `503` without it. |
| `ALLOWED_ORIGINS` | Fly | Must contain your Vercel URL or the browser blocks every call with a CORS error. |
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

- `GET /` — cheap always-200 probe (this is what Fly's health check uses).
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

## Deploying the backend to Fly.io

```bash
brew install flyctl          # or: curl -L https://fly.io/install.sh | sh
fly auth signup              # or: fly auth login

# Creates the app from fly.toml without deploying yet.
fly apps create browser-mcp-agent

# Secrets never go in fly.toml.
fly secrets set OPENAI_API_KEY="sk-..."

# --ha=false matters: Fly otherwise creates two machines, which means two
# Chromium instances and twice the cost.
fly deploy --ha=false

fly status
curl https://browser-mcp-agent.fly.dev/health
```

Then point the frontend at it: set `NEXT_PUBLIC_API_URL` to the Fly URL in the
Vercel project settings and redeploy (the value is baked in at build time).

Useful afterwards:

```bash
fly logs                    # live logs
fly ssh console             # shell into the machine
fly scale memory 2048       # if Chromium gets OOM-killed on big pages
```

## Context budget

A full accessibility snapshot of a large page (e.g. the Wikipedia article on
Artificial Intelligence) is ~1.1M characters — far past any context window.
Two things keep that in check:

- The agent is instructed to read pages with `playwright_browser_evaluate`
  (`() => document.body.innerText`, ~5x smaller and actual prose) and to use
  `playwright_browser_find` for targeted lookups, reserving
  `playwright_browser_snapshot` for when it needs element refs to click.
- Every tool result is hard-capped at `AGENT_MAX_TOOL_RESULT_CHARS` (default
  80,000) before it reaches the model, so an oversized page degrades into a
  truncated read instead of a context-overflow error.
