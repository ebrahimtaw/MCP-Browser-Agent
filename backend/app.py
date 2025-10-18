from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Body
from fastapi.middleware.cors import CORSMiddleware
from .agent_runtime import runtime

app = FastAPI(title="MCP Browser Agent API")

# Allow requests from your frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    await runtime.initialize()
    print("✅ MCP Agent initialized with Playwright support.")

@app.post("/run_agent")
async def run_agent(data: dict = Body(...)):
    """Receives a command and returns agent response."""
    message = data.get("message", "")
    result = await runtime.run(message)
    return {"response": result}

@app.get("/")
async def root():
    return {"status": "ok", "message": "MCP Browser Agent running!"}