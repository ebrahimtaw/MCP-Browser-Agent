import os
from textwrap import dedent

from mcp_agent.app import MCPApp
from mcp_agent.agents.agent import Agent
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM
from mcp_agent.workflows.llm.augmented_llm import RequestParams


class MCPAgentRuntime:
    def __init__(self):
        self.initialized = False
        self.mcp_app = MCPApp(name="api_mcp_agent")
        self.mcp_context = None
        self.mcp_agent_app = None
        self.browser_agent = None
        self.llm = None

    async def initialize(self):
        if self.initialized:
            return

        self.mcp_context = self.mcp_app.run()
        self.mcp_agent_app = await self.mcp_context.__aenter__()

        self.browser_agent = Agent(
            name="browser",
            instruction=dedent("""
                You are an autonomous web-browsing agent with full access to a real
                headless Chromium browser via the Playwright MCP server. You ALWAYS
                have working browser tools available. Never say you cannot access
                the web — you can. If a tool call fails, retry with a different
                approach (e.g. navigate first, then snapshot, then click). Always
                start a browsing task by calling the browser_navigate tool with the
                target URL. After navigating, call browser_snapshot to read the
                page, then click or extract as needed. Report findings in concise
                Markdown.
            """).strip(),
            server_names=["playwright"],
        )

        await self.browser_agent.initialize()
        self.llm = await self.browser_agent.attach_llm(OpenAIAugmentedLLM)
        self.initialized = True
        print("MCP Agent initialized with headless Playwright (Chromium).")

    async def run(self, message: str) -> str:
        if not os.getenv("OPENAI_API_KEY"):
            return "Error: OPENAI_API_KEY not configured."

        if not self.initialized:
            await self.initialize()

        try:
            result = await self.llm.generate_str(
                message=message,
                request_params=RequestParams(use_history=True, maxTokens=10000),
            )
            if not result or not result.strip():
                return (
                    "The agent finished without a textual reply. "
                    "Check the server logs — usually this means the OpenAI API "
                    "call failed (e.g. invalid key, rate limit, or model access)."
                )
            return result
        except Exception as e:
            return f"Error running MCP Agent: {str(e)}"


runtime = MCPAgentRuntime()
