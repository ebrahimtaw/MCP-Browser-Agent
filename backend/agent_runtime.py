"""Runtime that owns the single shared browsing agent.

The container runs exactly one headless Chromium, so agent runs are serialized
behind a lock. Conversation history is kept per session id instead of on the
shared LLM, which otherwise leaks one caller's browsing context into the next
caller's answer and grows until it overflows the context window.
"""

import asyncio
import logging
import os
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

INSTRUCTION = dedent(
    """
    You are an autonomous web-browsing agent driving a real headless Chromium
    browser through the Playwright MCP server. You always have working browser
    tools; never claim you cannot access the web.

    Work in this order:
      1. browser_navigate to the target URL. If the user named a site rather
         than a URL, navigate to a sensible URL for it.
      2. browser_snapshot to read the rendered accessibility tree.
      3. Click, type, or navigate further as needed, taking a fresh snapshot
         after each action that changes the page.

    If a tool call fails, retry with a different approach rather than giving up.
    Base every factual claim on what you actually saw in a snapshot, and say so
    plainly when a page did not contain the answer. Report findings in concise
    Markdown.
    """
).strip()


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
            await self._mcp_context.__aenter__()

            self._agent = Agent(
                name="browser",
                instruction=INSTRUCTION,
                server_names=["playwright"],
            )
            await self._agent.initialize()
            self._llm = await self._agent.attach_llm(OpenAIAugmentedLLM)

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

    async def warmup(self) -> None:
        """Pay the browser-launch cost at boot instead of on the first prompt."""
        async with self._lock:
            try:
                await self._ensure_initialized()
            except Exception:
                # Warmup is best effort; /run_agent retries and reports properly.
                pass

    async def run(self, message: str, session_id: str = "default") -> str:
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
            try:
                result = await asyncio.wait_for(
                    self._llm.generate_str(
                        message=message,
                        request_params=RequestParams(
                            use_history=True,
                            maxTokens=MAX_TOKENS,
                            max_iterations=MAX_ITERATIONS,
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
                self._llm.history.clear()

        if not result or not result.strip():
            raise AgentUnavailableError(
                "The model returned an empty reply. This usually means the OpenAI "
                "call failed (invalid key, rate limit, or no access to the model)."
            )
        return result

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
