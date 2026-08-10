#!/bin/bash
# Start FastAPI development server
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
