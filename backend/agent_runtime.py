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
        """Initialize the MCP agent using YAML config (Node-based Playwright MCP)."""
        if self.initialized:
            return

        # Start context — automatically loads mcp_agent.config.yaml
        self.mcp_context = self.mcp_app.run()
        self.mcp_agent_app = await self.mcp_context.__aenter__()

        # Create the autonomous browser agent
        self.browser_agent = Agent(
            name="browser",
            instruction=dedent("""
                You are a powerful autonomous web-browsing agent.
                - Follow the user's instructions directly without confirmation.
                - Use the Playwright MCP server to browse, scroll, click, and extract information.
                - Summarize pages in clean Markdown with short, natural responses.
            """),
            server_names=["playwright"],
        )

        await self.browser_agent.initialize()
        self.llm = await self.browser_agent.attach_llm(OpenAIAugmentedLLM)
        self.initialized = True
        print("MCP Agent initialized with Node-based Playwright MCP server.")

    async def run(self, message: str) -> str:
        """Execute browsing or reasoning."""
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


# Single runtime instance (used by FastAPI)
runtime = MCPAgentRuntime()