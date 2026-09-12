# Base image version is kept in step with the @playwright/mcp pin below so the
# preinstalled system libraries match the Chromium build we actually launch.
FROM mcr.microsoft.com/playwright:v1.63.0-noble

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DEBIAN_FRONTEND=noninteractive \
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:$PATH \
    PLAYWRIGHT_BROWSERS_PATH=/root/.cache/ms-playwright

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-pip python3-venv ca-certificates curl \
    && rm -rf /var/lib/apt/lists/* \
    && python3 -m venv $VIRTUAL_ENV \
    && pip install --upgrade pip

# Pinned: @playwright/mcp ships an alpha playwright-core, so "latest" can change
# the required browser revision without warning.
#
# Browsers go to the DEFAULT cache location ($HOME/.cache/ms-playwright) on
# purpose. The MCP server is spawned with a scrubbed environment that keeps only
# HOME/LOGNAME/PATH/SHELL/TERM/USER, so a PLAYWRIGHT_BROWSERS_PATH pointing
# anywhere else gets dropped and the server looks here regardless.
#
# `install-browser chrome-for-testing` is the package's own command and installs
# exactly the build the server resolves to -- `install chromium` put it in a
# different layout and the server reported it as not installed.
#
# The final `test` fails the build instead of letting this surface at runtime.
RUN npm install -g @playwright/mcp@0.0.80 \
    && playwright-mcp install-browser --with-deps chrome-for-testing \
    && playwright-mcp --version \
    && ls -1 "$PLAYWRIGHT_BROWSERS_PATH" \
    && test -n "$(find "$PLAYWRIGHT_BROWSERS_PATH" -maxdepth 3 -name chrome -type f -print -quit)" \
    && echo "chrome binary present in $PLAYWRIGHT_BROWSERS_PATH"

WORKDIR /app

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY backend/ ./backend/
COPY mcp_agent.config.yaml playwright-mcp.config.json ./

ENV PORT=8000
EXPOSE 8000

# Single worker on purpose: the process owns one Chromium and serializes runs.
CMD ["sh", "-c", "uvicorn backend.app:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --timeout-keep-alive 300"]
