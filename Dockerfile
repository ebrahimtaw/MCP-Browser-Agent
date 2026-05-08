FROM mcr.microsoft.com/playwright:v1.49.1-jammy

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DEBIAN_FRONTEND=noninteractive \
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:$PATH

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-pip python3-venv ca-certificates curl \
    && rm -rf /var/lib/apt/lists/* \
    && python3 -m venv $VIRTUAL_ENV \
    && pip install --upgrade pip

RUN npm install -g @playwright/mcp@latest \
    && cd /usr/lib/node_modules/@playwright/mcp \
    && node node_modules/playwright-core/cli.js install --no-shell chromium \
    && node node_modules/playwright-core/cli.js install chromium-headless-shell

WORKDIR /app

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY backend/ ./backend/
COPY mcp_agent.config.yaml ./

ENV PORT=8000
EXPOSE 8000

CMD ["sh", "-c", "uvicorn backend.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
