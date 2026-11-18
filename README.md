# DocGuard

**DocGuard** is an AI-powered documentation drift detection platform built to help engineering teams keep project documentation synchronized with code changes.

---

## Milestone 1: Project Foundation

This repository currently implements **Milestone 1 (Project Foundation)**:

- **Backend (`backend/`)**: Python + FastAPI + Uvicorn providing a health check endpoint (`GET /api/health`), root welcome endpoint (`GET /`), Pydantic response schemas, CORS configuration for local development, and automated tests with `pytest`.
- **Frontend (`frontend/`)**: React (JavaScript) + Vite + Tailwind CSS responsive developer dashboard with live backend connectivity checking (`/api/health`), repository configuration inputs, analysis status display, and an honest placeholder notice for future analysis milestones.
- **Documentation (`docs/`)**: Project documentation directory.

> **Note:** GitHub integration, code analysis, documentation analysis, AI integration, and database persistence are intentionally excluded from Milestone 1 and will be introduced in later milestones.

---

## Project Structure

```text
DocGuard/
├── backend/
│   ├── .venv/                  # Local Python virtual environment (git-ignored)
│   ├── app/
│   │   ├── __init__.py
│   │   └── main.py             # FastAPI application & endpoints
│   ├── tests/
│   │   ├── __init__.py
│   │   └── test_main.py        # Pytest test suite for Milestone 1
│   ├── .env.example            # Example environment variables (no secrets)
│   └── requirements.txt        # Python dependencies
├── frontend/
│   ├── src/
│   │   ├── api/
│   │   │   └── health.js       # Frontend API service for GET /api/health
│   │   ├── App.jsx             # DocGuard Dashboard UI component
│   │   ├── index.css           # Tailwind CSS entry point
│   │   └── main.jsx            # React DOM root entry
│   ├── index.html
│   ├── package.json
│   └── vite.config.js          # Vite config with /api proxy to FastAPI
├── docs/
│   └── README.md
├── .gitignore
└── README.md
```

---

## Prerequisites

Ensure the following tools are installed on your Windows machine:

- **Python** 3.10+ (`python --version`)
- **pip** (`pip --version`)
- **Node.js** 18+ and **npm** (`node --version`, `npm --version`)
- **Git** (`git --version`)

---

## Windows PowerShell Setup & Execution Guide

### 1. Backend Setup (FastAPI + Uvicorn)

Open **Windows PowerShell** in the root `DocGuard` workspace folder:

```powershell
# Navigate to the backend directory
cd backend

# Create the Python virtual environment inside backend/.venv (if not already created)
python -m venv .venv

# Activate the virtual environment in PowerShell
.\.venv\Scripts\Activate.ps1

# Install required Python packages
pip install -r requirements.txt
```

*(Optional)* If PowerShell blocks script execution when running `Activate.ps1`, you can either run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` first, or invoke binaries directly via `.\.venv\Scripts\python.exe`.

#### Start the Backend Server

From inside `backend/` with the virtual environment activated:

```powershell
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

- **Health Check URL**: `http://127.0.0.1:8000/api/health`
- **Interactive Swagger UI**: `http://127.0.0.1:8000/docs`

Expected `GET /api/health` JSON response:

```json
{
  "status": "ok",
  "application": "DocGuard",
  "version": "0.1.0"
}
```

#### Run Backend Automated Tests

From inside `backend/`:

```powershell
.\.venv\Scripts\python.exe -m pytest -v
```

---

### 2. Frontend Setup (React + Vite + Tailwind CSS)

Open a **second Windows PowerShell** terminal in the root `DocGuard` workspace folder:

```powershell
# Navigate to the frontend directory
cd frontend

# Install Node.js dependencies
npm install

# Start the Vite development server
npm run dev
```

- Open the application in your browser at: `http://localhost:5173`
- Vite automatically proxies requests starting with `/api` to `http://127.0.0.1:8000`.
- When the FastAPI backend is running, the dashboard displays **"Backend connected"** along with the application name and version. If the backend is stopped, it displays **"Backend disconnected"** with error details.

#### Build Frontend for Production

```powershell
cd frontend
npm run build
```
