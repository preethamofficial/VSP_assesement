# Optional AI agent setup prompt

Paste this into Codex, Cursor, GitHub Copilot Chat or another coding agent if you want the agent to perform the local setup.

> You are setting up the ClaimFlow Expense Claims assessment project. Work only inside this repository. First inspect README.md. Check that Python 3.10+ and Node.js 20.19+ are installed. Create backend/.venv, install backend/requirements.txt, initialize the SQLite seed data, then run the backend on port 8000. In a second terminal install frontend npm dependencies and run Vite on port 5173. Verify GET /api/health and open the frontend. Do not add paid services or API keys. If a dependency installation fails, report the exact error and do not silently replace versions or services. Run pytest after setup and report the results.
