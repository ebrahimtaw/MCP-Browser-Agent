#!/usr/bin/env bash
# Verifies the image can actually browse. Run inside the container:
#   docker build -t browser-mcp-agent . && docker run --rm browser-mcp-agent scripts/smoke_test.sh
set -uo pipefail

fail=0
check() { if [ "$1" -eq 0 ]; then echo "  PASS"; else echo "  FAIL"; fail=1; fi; }

echo "=== node / playwright-mcp on PATH ==="
node --version
playwright-mcp --version
check $?

echo ""
echo "=== Python deps import (the mcp 2.x break shows up here) ==="
python3 -c "
import mcp, mcp_agent, fastapi, openai
from mcp_agent.app import MCPApp
print('mcp', mcp.__version__ if hasattr(mcp,'__version__') else '?', '| fastapi', fastapi.__version__)
print('mcp_agent.app imported OK')
"
check $?

echo ""
echo "=== Chromium present where the server will look ==="
echo "PLAYWRIGHT_BROWSERS_PATH=${PLAYWRIGHT_BROWSERS_PATH:-<unset>}"
find "${PLAYWRIGHT_BROWSERS_PATH:-/ms-playwright}" -maxdepth 2 -name 'headless_shell' -o -maxdepth 2 -name 'chrome' 2>/dev/null | head -3
check $?

echo ""
echo "=== MCP server starts and exposes browser tools ==="
python3 - <<'PY'
import asyncio, sys
from mcp_agent.app import MCPApp
from mcp_agent.agents.agent import Agent

async def main():
    ctx = MCPApp(name="smoke").run()
    await ctx.__aenter__()
    agent = Agent(name="browser", instruction="smoke test", server_names=["playwright"])
    await asyncio.wait_for(agent.initialize(), timeout=90)
    tools = await asyncio.wait_for(agent.list_tools(), timeout=60)
    names = [t.name for t in tools.tools]
    print(f"TOOL_COUNT: {len(names)}")
    await ctx.__aexit__(None, None, None)
    sys.exit(0 if any("navigate" in n for n in names) else 1)

asyncio.run(main())
PY
check $?

echo ""
if [ "$fail" -eq 0 ]; then echo "SMOKE TEST: ALL PASS"; else echo "SMOKE TEST: FAILURES ABOVE"; fi
exit $fail
