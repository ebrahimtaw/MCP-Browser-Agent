"""Runtime that owns the single shared browsing agent.

The container runs exactly one headless Chromium, so agent runs are serialized
behind a lock. Conversation history is kept per session id instead of on the
shared LLM, which otherwise leaks one caller's browsing context into the next
caller's answer and grows until it overflows the context window.
"""

import asyncio
import logging
import os
import re
from textwrap import dedent

from mcp_agent.app import MCPApp
from mcp_agent.agents.agent import Agent
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM
from mcp_agent.workflows.llm.augmented_llm import RequestParams

log = logging.getLogger(__name__)

# A browsing turn is navigate -> snapshot -> maybe click -> extract, so the
# default of 10 iterations / 2048 tokens truncates real tasks mid-way.
MAX_ITERATIONS = int(os.getenv("AGENT_MAX_ITERATIONS", "25"))
MAX_TOKENS = int(os.getenv("AGENT_MAX_TOKENS", "8000"))
RUN_TIMEOUT_SECONDS = float(os.getenv("AGENT_RUN_TIMEOUT", "240"))
# Turns are (user, assistant, plus tool traffic); keep the tail so long
# sessions cannot grow the prompt without bound.
MAX_HISTORY_MESSAGES = int(os.getenv("AGENT_MAX_HISTORY_MESSAGES", "40"))
# A full accessibility snapshot of a large page runs to ~1.1M characters
# (~280k tokens) -- past any context window. Cap each tool result so one big
# page degrades into a truncated read instead of a hard context-overflow error.
MAX_TOOL_RESULT_CHARS = int(os.getenv("AGENT_MAX_TOOL_RESULT_CHARS", "80000"))
MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
# The MCP SDK spawns stdio servers with a scrubbed environment -- only
# HOME/LOGNAME/PATH/SHELL/TERM/USER survive (see mcp.client.stdio
# .get_default_environment). Anything the browser needs must be forwarded
# explicitly, or Playwright falls back to $HOME/.cache/ms-playwright and
# reports the browser as "not installed".
FORWARDED_SERVER_ENV = ("PLAYWRIGHT_BROWSERS_PATH",)

# Screenshots are captured automatically after any action that changes the page,
# so the user can watch what the agent saw. Bounded because each one is base64
# in the JSON response.
MAX_SCREENSHOTS = int(os.getenv("AGENT_MAX_SCREENSHOTS", "6"))
SCREENSHOT_TIMEOUT = float(os.getenv("AGENT_SCREENSHOT_TIMEOUT", "30"))
PAGE_CHANGING_TOOLS = frozenset({
    "browser_navigate",
    "browser_navigate_back",
    "browser_click",
    "browser_type",
    "browser_select_option",
    "browser_press_key",
    "browser_fill_form",
})

_PAGE_URL_RE = re.compile(r"^- Page URL:\s*(.+)$", re.M)
_PAGE_TITLE_RE = re.compile(r"^- Page Title:\s*(.+)$", re.M)


def _page_meta(result) -> tuple[str, str]:
    """Pull the URL and title the server reports alongside a tool result."""
    text = "".join(
        getattr(part, "text", "") or "" for part in getattr(result, "content", None) or []
    )
    url = _PAGE_URL_RE.search(text)
    title = _PAGE_TITLE_RE.search(text)
    return (url.group(1).strip() if url else "", title.group(1).strip() if title else "")

INSTRUCTION = dedent(
    """
    You are an autonomous web-browsing agent driving a real headless Chromium
    browser. You always have working browser tools; never claim you cannot
    access the web.

    Your tools are named with a `playwright_` prefix, e.g.
    `playwright_browser_navigate`.

    How to read a page efficiently:
      1. `playwright_browser_navigate` to the target URL.
      2. To READ or SUMMARIZE content, call `playwright_browser_evaluate` with
         the function `() => document.body.innerText`. This returns clean text
         and is many times smaller than a full snapshot.
      3. To FIND something specific on a long page, use
         `playwright_browser_find` rather than dumping the whole page.
      4. Only call `playwright_browser_snapshot` when you need element refs in
         order to click, type, or fill a form -- its output is very large.

    Do not call `playwright_browser_take_screenshot` yourself: a screenshot is
    captured automatically after every action that changes the page, and shown
    to the user alongside your answer.

    After any action that changes the page, re-read it before relying on it.
    If a tool call fails, retry with a different approach rather than giving up.
    If a tool result says it was truncated, do not re-request the same thing --
    narrow it with `playwright_browser_find` instead.

    Base every factual claim on what you actually saw, and say so plainly when
    a page did not contain the answer. Report findings in concise Markdown.
    """
).strip()


class BoundedOpenAIAugmentedLLM(OpenAIAugmentedLLM):
    """Caps tool output, and captures a screenshot after each page change.

    The browser runs headless on the server, so the screenshots are the only way
    a user can see what the agent actually looked at.
    """

    @property
    def screenshots(self) -> list[dict]:
        # Lazy rather than set in __init__, so this does not depend on the
        # constructor signature attach_llm happens to use.
        if not hasattr(self, "_screenshots"):
            self._screenshots: list[dict] = []
        return self._screenshots

    def reset_screenshots(self) -> None:
        self.screenshots.clear()

    async def post_tool_call(self, tool_call_id, request, result):
        result = await super().post_tool_call(
            tool_call_id=tool_call_id, request=request, result=result
        )
        tool_name = request.params.name
        # Tools reach the model namespaced by server, e.g. playwright_browser_*.
        bare_name = tool_name.split("playwright_", 1)[-1]

        if bare_name in PAGE_CHANGING_TOOLS and len(self.screenshots) < MAX_SCREENSHOTS:
            await self._capture_screenshot(result)

        self._truncate(tool_name, result)
        self._strip_images(result)
        return result

    async def _capture_screenshot(self, trigger_result) -> None:
        """Best effort: a failed screenshot must never fail the user's request."""
        try:
            shot = await asyncio.wait_for(
                self.agent.call_tool("browser_take_screenshot", {"type": "jpeg"}),
                timeout=SCREENSHOT_TIMEOUT,
            )
        except Exception:
            log.warning("Screenshot capture failed.", exc_info=True)
            return

        data = next(
            (
                part.data
                for part in getattr(shot, "content", None) or []
                if getattr(part, "data", None)
            ),
            None,
        )
        if not data:
            return

        url, title = _page_meta(trigger_result)
        self.screenshots.append(
            {
                "url": url,
                "title": title,
                "image": f"data:image/jpeg;base64,{data}",
            }
        )

    @staticmethod
    def _truncate(tool_name: str, result) -> None:
        for part in getattr(result, "content", None) or []:
            text = getattr(part, "text", None)
            if text is not None and len(text) > MAX_TOOL_RESULT_CHARS:
                dropped = len(text) - MAX_TOOL_RESULT_CHARS
                part.text = (
                    text[:MAX_TOOL_RESULT_CHARS]
                    + f"\n\n[Truncated: {dropped} more characters were dropped. "
                    "Do not re-request this; use playwright_browser_find to "
                    "search the page for the specific text you need.]"
                )
                log.warning(
                    "Truncated %s result: %d -> %d chars.",
                    tool_name,
                    len(text),
                    MAX_TOOL_RESULT_CHARS,
                )

    @staticmethod
    def _strip_images(result) -> None:
        """Keep base64 images out of the prompt.

        They are for the user, not the model: sending them back would bill every
        screenshot as a vision input and crowd out the page text the model needs.
        """
        content = getattr(result, "content", None)
        if not content:
            return
        kept = [part for part in content if getattr(part, "type", None) != "image"]
        if len(kept) != len(content):
            result.content = kept


class AgentUnavailableError(RuntimeError):
    """Raised when the agent cannot service requests at all."""


class MCPAgentRuntime:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._initialized = False
        self._init_error: str | None = None
        self._mcp_app = MCPApp(name="api_mcp_agent")
        self._mcp_context = None
        self._agent = None
        self._llm = None
        self._histories: dict[str, list] = {}

    @property
    def ready(self) -> bool:
        return self._initialized

    @property
    def init_error(self) -> str | None:
        return self._init_error

    async def _ensure_initialized(self) -> None:
        """Start the MCP session and launch the browser. Caller holds the lock."""
        if self._initialized:
            return

        log.info("Initializing MCP agent and launching headless Chromium...")
        try:
            self._mcp_context = self._mcp_app.run()
            agent_app = await self._mcp_context.__aenter__()
            self._forward_server_env(agent_app)

            self._agent = Agent(
                name="browser",
                instruction=INSTRUCTION,
                server_names=["playwright"],
            )
            await self._agent.initialize()
            self._llm = await self._agent.attach_llm(BoundedOpenAIAugmentedLLM)

            # Fail loudly here rather than on the first user prompt: if the
            # Playwright MCP server did not start, it has no tools to offer.
            tools = await self._agent.list_tools()
            tool_names = [t.name for t in tools.tools]
            if not tool_names:
                raise AgentUnavailableError(
                    "Playwright MCP server exposed no tools; the browser did not start."
                )

            self._initialized = True
            self._init_error = None
            log.info("MCP agent ready with %d browser tools.", len(tool_names))
        except Exception as exc:
            self._init_error = f"{type(exc).__name__}: {exc}"
            log.exception("MCP agent initialization failed.")
            await self._teardown()
            raise

    @staticmethod
    def _forward_server_env(agent_app) -> None:
        """Pass browser-related env vars through to the spawned MCP server."""
        try:
            server = agent_app.context.config.mcp.servers["playwright"]
        except (AttributeError, KeyError):
            log.warning("Could not reach playwright server settings to forward env.")
            return

        forwarded = {
            name: os.environ[name]
            for name in FORWARDED_SERVER_ENV
            if os.environ.get(name)
        }
        if forwarded:
            server.env = {**(server.env or {}), **forwarded}
            log.info("Forwarding to MCP server: %s", ", ".join(sorted(forwarded)))

    async def warmup(self) -> None:
        """Pay the browser-launch cost at boot instead of on the first prompt."""
        async with self._lock:
            try:
                await self._ensure_initialized()
            except Exception:
                # Warmup is best effort; /run_agent retries and reports properly.
                pass

    async def run(self, message: str, session_id: str = "default") -> dict:
        if not message or not message.strip():
            raise ValueError("message must not be empty")
        if not os.getenv("OPENAI_API_KEY"):
            raise AgentUnavailableError(
                "OPENAI_API_KEY is not set on the server."
            )

        # One browser, so one run at a time. Everything below is serialized.
        async with self._lock:
            await self._ensure_initialized()

            # Swap in this session's history so callers stay isolated.
            self._llm.history.set(list(self._histories.get(session_id, [])))
            self._llm.reset_screenshots()
            try:
                result = await asyncio.wait_for(
                    self._llm.generate_str(
                        message=message,
                        request_params=RequestParams(
                            use_history=True,
                            maxTokens=MAX_TOKENS,
                            max_iterations=MAX_ITERATIONS,
                            model=MODEL,
                        ),
                    ),
                    timeout=RUN_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError:
                # Leave _histories untouched so the partial turn is dropped; a
                # truncated tool exchange poisons the next request in a session.
                raise TimeoutError(
                    f"The agent did not finish within {RUN_TIMEOUT_SECONDS:.0f}s. "
                    "Try a narrower prompt or a more specific URL."
                )
            else:
                self._histories[session_id] = self._llm.history.get()[
                    -MAX_HISTORY_MESSAGES:
                ]
            finally:
                screenshots = list(self._llm.screenshots)
                self._llm.history.clear()

        if not result or not result.strip():
            raise AgentUnavailableError(
                "The model returned an empty reply. This usually means the OpenAI "
                "call failed (invalid key, rate limit, or no access to the model)."
            )
        return {"response": result, "screenshots": screenshots}

    async def _teardown(self) -> None:
        if self._mcp_context is not None:
            try:
                await self._mcp_context.__aexit__(None, None, None)
            except Exception:
                log.warning("Error while closing MCP context.", exc_info=True)
        self._mcp_context = None
        self._agent = None
        self._llm = None
        self._initialized = False

    async def shutdown(self) -> None:
        async with self._lock:
            await self._teardown()


runtime = MCPAgentRuntime()
