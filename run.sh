#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
python3 -m venv backend/.venv
source backend/.venv/bin/activate
pip install -r backend/requirements.txt
python backend/seed.py
( cd backend && source .venv/bin/activate && uvicorn app:app --reload --port 8000 ) &
( cd frontend && npm install && npm run dev )
