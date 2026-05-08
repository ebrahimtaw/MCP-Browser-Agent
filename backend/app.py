import os
import sys
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Body
from fastapi.middleware.cors import CORSMiddleware

try:
    from .agent_runtime import runtime
except ImportError as e:
    print(f"Warning: Could not import agent_runtime: {e}")
    print("Agent will initialize on first request")
    runtime = None

app = FastAPI(title="MCP Browser Agent API")

# CORS configuration for production
allowed_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:3001").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/run_agent")
async def run_agent(data: dict = Body(...)):
    """Receives a command and returns agent response."""
    if runtime is None:
        return {"response": "Error: Agent runtime not available. Check deployment logs."}
    message = data.get("message", "")
    result = await runtime.run(message)
    return {"response": result}

@app.get("/")
async def root():
    return {"status": "ok", "message": "MCP Browser Agent running!"}