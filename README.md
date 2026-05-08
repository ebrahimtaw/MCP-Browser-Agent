# Browser MCP Agent

An intelligent MCP agent that navigates, extracts, and summarizes web content.

## Setup

### Backend
```bash
export OPENAI_API_KEY="your-api-key"
pip install -r requirements.txt
uvicorn backend.app:app --reload --port 8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

Visit http://localhost:3000
