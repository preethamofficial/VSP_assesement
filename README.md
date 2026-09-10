# ClaimFlow — Expense Claims Assessment

A free, self-contained expense-claims application built for the VSP Techverse assessment.

## What is included

- Staff, manager and finance demo roles.
- Receipt-text parser that extracts vendor, date, amount and category before submission.
- Duplicate-receipt protection using normalized text + similarity + vendor/amount/date signals.
- Manager approval workflow with server-side protection against self-approval and cross-team approval.
- One-way claim state machine: submitted → approved/rejected; approved → paid. Paid claims cannot move backwards.
- Finance dashboard with monthly total, category spend, employee spend and monthly limits.
- Realistic seed data, including a deliberately similar duplicate receipt and an employee near their monthly limit.
- Automated backend tests.
- Optional Docker deployment.

## Free-of-cost design

The demo uses SQLite and a deterministic receipt parser, so it does **not** require a paid API key, cloud database, payment gateway, OCR subscription or AI API. It runs locally for free.

AI assistance used during development: ChatGPT was used to help design, implement, debug and document the application. No external AI service is required at runtime.

## Requirements

- Python 3.10+
- Node.js 20.19+ (or a current supported Node release)
- npm

## Run on Windows

After downloading and unzipping the project:

1. Install Python 3.10+ and Node.js.
2. Open the extracted `expense_claims_assessment` folder.
3. Double-click `run_windows.bat`.

The launcher creates a Python virtual environment, installs backend requirements,
initializes the demo data, starts FastAPI, installs frontend npm packages when
needed, starts Vite, and opens the app.

The application is available at http://localhost:5173. The backend runs at
http://127.0.0.1:8000 and API docs are at http://127.0.0.1:8000/docs.

## Run manually

### Backend

```bash
cd backend
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python seed.py
uvicorn app:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173.

## Demo roles

Use the role/person dropdown in the top-right to switch between demo users:

- Aarav Sharma — Staff
- Meera Nair — Manager
- Rohan Iyer — Staff
- Ananya Rao — Finance
- Vikram Singh — Manager

The dropdown is a demo convenience; a production system would use real authentication and authorization.

## Suggested demo flow

1. Start as Aarav (Staff).
2. Open New claim.
3. Paste the sample receipt text below and click Extract fields.
4. Review the extracted values and submit.
5. Switch to Meera (Manager).
6. Open Approvals and approve a team claim.
7. Switch to Ananya (Finance).
8. Open Finance and mark an approved claim as paid.
9. Demonstrate duplicate protection by pasting a receipt matching an existing Metro Cabs claim.
10. Explain the monthly limit view and the immutable paid state.

### Sample receipt text

```text
METRO CABS
02/09/2026
AUTO RIDE TO CLIENT OFFICE
TOTAL Rs 210
Thank you
```

A deliberately similar receipt already exists in the seed data, so the duplicate check can be demonstrated.

## Assessment decisions / assumptions

1. A claim belongs to the employee who submits it. Managers are also employees and can submit claims.
2. A manager can approve/reject only claims belonging to their direct reports.
3. A manager cannot approve/reject their own claim.
4. Finance can mark approved claims as paid.
5. State transitions are enforced in the API, not only in the UI.
6. Paid claims are terminal and cannot be edited back to an earlier state.
7. Duplicate detection is a warning/blocking rule using receipt-text similarity plus vendor, amount and date. A production version would use a stronger fingerprint, receipt image/OCR and configurable tolerance rules.
8. Monthly spend in the demo is calculated from all claims for the month. A production policy could count only approved/paid claims; this should be agreed with the business.
9. The receipt parser is deterministic to keep runtime free. It intentionally shows extracted fields to the user for correction before submission.
10. Authentication is simulated by a role/person selector for the assessment demo. Production would use SSO/OAuth and server-side sessions/JWTs.

## Tests

From the project root:

```bash
cd backend
pip install -r requirements.txt
cd ..
pip install pytest httpx
pytest -q
```

## Docker

Build and run:

```bash
docker build -t claimflow .
docker run --rm -p 8000:8000 claimflow
```

Then open http://localhost:8000.

## If I had another week

- Add real authentication and role-based access control.
- Add receipt image upload and OCR.
- Add stronger duplicate detection using embeddings and merchant/receipt identifiers.
- Add edit/audit history and notification emails.
- Add CSV/PDF export for finance.
- Add configurable policies per category and employee.
- Add production PostgreSQL, migrations and CI/CD.
- Add accessibility and end-to-end browser tests.
