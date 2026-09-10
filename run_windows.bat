@echo off
setlocal
cd /d %~dp0
if not exist backend\.venv python -m venv backend\.venv
call backend\.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r backend\requirements.txt
python backend\seed.py
start "ClaimFlow API" cmd /k "cd /d %~dp0backend && call .venv\Scripts\activate && uvicorn app:app --reload --port 8000"
cd frontend
if not exist node_modules npm install
start "ClaimFlow Frontend" cmd /k "npm run dev"
timeout /t 4 >nul
start http://localhost:5173
endlocal
