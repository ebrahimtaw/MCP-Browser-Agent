"""FastAPI surface for the browsing agent.

Note on health checks: `/` stays cheap and always-200 so the platform does not
recycle the container while a long browsing run holds the agent lock. `/health`
reports the real agent state and is the one to read when debugging.
"""

import asyncio
import glob
import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from fastapi import Body, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .agent_runtime import AgentUnavailableError, runtime

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("backend.app")

# Bounded so a wedged MCP server cannot stop the port from ever opening.
WARMUP_TIMEOUT = float(os.getenv("AGENT_WARMUP_TIMEOUT", "60"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Connect to the MCP server up front (it takes well under a second) so the
    # first real prompt does not pay for it. Done in the lifespan's own task
    # rather than a background one: mcp-agent ties its context to the task that
    # enters it, and tearing down from a different task raises on exit.
    try:
        await asyncio.wait_for(runtime.warmup(), timeout=WARMUP_TIMEOUT)
    except asyncio.TimeoutError:
        log.error("Agent warmup timed out; will retry on first request.")
    try:
        yield
    finally:
        await runtime.shutdown()


app = FastAPI(title="MCP Browser Agent API", lifespan=lifespan)

_raw_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:3001")
allowed_origins = [o.strip() for o in _raw_origins.split(",") if o.strip()]
# Without this the Vercel preview deployments (which get a new hostname per
# commit) are blocked by CORS even though production is allow-listed.
allow_origin_regex = os.getenv("ALLOWED_ORIGIN_REGEX", r"https://.*\.vercel\.app")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=allow_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {"status": "ok", "message": "MCP Browser Agent running!"}


def _browser_state() -> dict:
    """Where Playwright will look for a browser, and whether one is there.

    `agent_ready` only means the MCP server started; the browser is not launched
    until the first navigation. This reports the filesystem facts so a missing
    browser is visible here instead of arriving as an apology from the model.
    """
    # Matches Playwright's own resolution: the explicit override, else the
    # HOME-derived default (HOME is one of the few vars that survives the
    # scrubbed environment the MCP server is spawned with).
    configured = os.getenv("PLAYWRIGHT_BROWSERS_PATH")
    # Playwright's per-platform default cache. The container is Linux; the other
    # branches keep this report honest during local development.
    home = Path.home()
    if sys.platform == "darwin":
        default = str(home / "Library" / "Caches" / "ms-playwright")
    elif sys.platform == "win32":
        default = str(home / "AppData" / "Local" / "ms-playwright")
    else:
        default = str(home / ".cache" / "ms-playwright")
    search_root = configured or default

    executables = sorted(
        glob.glob(os.path.join(search_root, "*", "*", "chrome"))
        + glob.glob(os.path.join(search_root, "*", "*", "headless_shell"))
    )
    return {
        "browsers_path_env": configured,
        "browsers_path_default": default,
        "browsers_path_searched": search_root,
        "paths_agree": configured in (None, default),
        "browser_executables": executables[:5],
        "browser_installed": bool(executables),
    }


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "agent_ready": runtime.ready,
        "openai_key_configured": bool(os.getenv("OPENAI_API_KEY")),
        "init_error": runtime.init_error,
        "browser": _browser_state(),
    }


@app.post("/run_agent")
async def run_agent(data: dict = Body(...)):
    """Run one browsing turn and return the agent's Markdown answer."""
    message = (data.get("message") or "").strip()
    session_id = (data.get("session_id") or "default").strip() or "default"

    if not message:
        raise HTTPException(status_code=400, detail="`message` must not be empty.")

    try:
        result = await runtime.run(message, session_id=session_id)
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail=str(exc)) from exc
    except AgentUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        log.exception("Agent run failed.")
        raise HTTPException(
            status_code=500, detail=f"{type(exc).__name__}: {exc}"
        ) from exc

    return {"response": result}
