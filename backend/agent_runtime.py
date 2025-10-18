import os
import asyncio
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
        """Initialize the MCP agent (uses YAML config automatically if present)."""
        if self.initialized:
            return

        # ✅ Start context (loads mcp_agent.config.yaml automatically)
        self.mcp_context = self.mcp_app.run()
        self.mcp_agent_app = await self.mcp_context.__aenter__()

        # ✅ Create the browser agent configured to talk to the Playwright MCP
        self.browser_agent = Agent(
            name="browser",
            instruction=dedent("""
                You are a direct, autonomous web-browsing agent.
                - Follow the user’s commands directly without asking for confirmation.
                - Use the Playwright MCP server to open pages, scroll, click, and extract content.
                - Provide concise, human-readable markdown summaries of what you find.
            """),
            server_names=["playwright"],
        )

        await self.browser_agent.initialize()

        # ✅ Attach OpenAI model (same as prototype)
        self.llm = await self.browser_agent.attach_llm(OpenAIAugmentedLLM)

        self.initialized = True
        print("✅ MCP Agent initialized with Node-based Playwright MCP server.")

    async def run(self, message: str) -> str:
        """Execute the browsing agent exactly like in the prototype."""
        if not self.initialized:
            await self.initialize()

        if not os.getenv("OPENAI_API_KEY"):
            return "Error: OPENAI_API_KEY not configured."

        try:
            result = await self.llm.generate_str(
                message=message,
                request_params=RequestParams(use_history=True, maxTokens=10000),
            )
            return result
        except Exception as e:
            return f"Error running MCP Agent: {str(e)}"


# Create one shared runtime instance
runtime = MCPAgentRuntime()