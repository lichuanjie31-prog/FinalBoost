# FinalBoost

FinalBoost is an AI study assistant for high school students. It helps learners review exam papers, understand mistakes, identify weak topics, and build a focused revision plan.

## Features

- Exam workspace for uploading papers and organizing grading results and diagnoses
- AI study assistant with study context, tool use, conversation history, and optional retrieval augmented generation
- Vision based paper marking through Qwen VL, with a Tencent Cloud provider also available
- Question bank for private and public papers
- Guided practice with staged exercises, mastery checks, and PDF export
- Mock exams, answer review, and a mistake collection
- Account authentication and per user data isolation
- MCP bridge for exposing study tools to compatible clients

## Tech Stack

- Frontend: React 19, TypeScript, Vite, and React Router
- Backend: Python, FastAPI, Pydantic, and SQLite
- AI: LangChain, LangGraph, compatible chat models, Qwen VL, and optional Qdrant based retrieval
- Testing: pytest and Playwright

## Repository Layout

```text
backend/       FastAPI application and Python tests
frontend/      React application and Playwright tests
contracts/     OpenAPI contract
scripts/       Local startup and verification scripts
docs/          Architecture, API, and provider documentation
```

## Requirements

- Node.js 20 or later
- Python 3.11 or later

## Run Locally

### Backend

```powershell
cd backend
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.lock
$env:GRADING_MODE = "mock"
.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### Frontend

In a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173> in your browser. The frontend development server proxies API requests to the local backend.

The local mock grading mode returns sample results and does not analyze uploaded images. To use live paper marking, configure the backend environment as described below.

## Configure AI Providers

Live Qwen marking requires a DashScope API key. Set these variables in the backend environment before starting the server:

```powershell
$env:MARKING_MODE = "live"
$env:MARKING_PROVIDER = "qwen"
$env:DASHSCOPE_API_KEY = "your-dashscope-api-key"
```

The default marking model is `qwen3-vl-plus`; set `QWEN_MARKING_MODEL` to change it. Tencent Cloud marking is also supported through `MARKING_PROVIDER=tencent`, with `TENCENTCLOUD_SECRET_ID` and `TENCENTCLOUD_SECRET_KEY` configured on the backend.

The study assistant's chat model can be configured with `LLM_API_KEY`, `LLM_MODEL`, and `LLM_BASE_URL`. Retrieval augmented generation can use Qdrant and an embedding provider. See the configuration and integration guides in [`docs/`](docs/) and [`backend/SETUP_LANGCHAIN.md`](backend/SETUP_LANGCHAIN.md) for details.

Keep API keys in backend environment variables. Do not commit credentials or place them in frontend code.

## Tests and Checks

```powershell
cd backend
.venv\Scripts\python -m pytest -q
```

```powershell
cd frontend
npm run build
npm run test:e2e
```

Additional Playwright configurations cover provider marking and failure scenarios. See the scripts in `frontend/package.json`.

## Project Status

FinalBoost is under active development. Local mock mode is intended for development and demonstrations. Production startup is currently disabled until a production ready grading adapter and deployment configuration are in place. Some practice and mock exam content uses built in sample questions.
