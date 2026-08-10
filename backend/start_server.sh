#!/bin/bash
cd /Users/hoquanghuy/Documents/GitHub/project-luvcraft/backend
.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
