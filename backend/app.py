from dotenv import load_dotenv
load_dotenv()
from fastapi import FastAPI, Body
from fastapi.middleware.cors import CORSMiddleware
from .agent_runtime import runtime

app = FastAPI(title="MCP Browser Agent API")

# --- Allow your frontend to talk to this backend ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Initialize the agent on startup ---
@app.on_event("startup")
async def startup_event():
    await runtime.initialize()
    print("✅ MCP Agent initialized with Playwright support.")


# --- Main endpoint for the frontend ---
@app.post("/run_agent")
async def run_agent(data: dict = Body(...)):
    """Accepts a user command and returns the agent's response."""
    message = data.get("message", "")
    result = await runtime.run(message)
    return {"response": result}


# --- (Optional) Simple health check route ---
@app.get("/")
async def root():
    return {"status": "ok", "message": "MCP Browser Agent running!"}