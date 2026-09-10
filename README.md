# ClaimFlow — Expense Claims Assessment

A free, self-contained expense-claims application built for the VSP Techverse assessment.

## Live application

Open ClaimFlow here: **[https://vsp-assesement.onrender.com](https://vsp-assesement.onrender.com)**

The free Render service can take about a minute to start after inactivity.

## What is included

- Separate manager and employee login.
- New-employee access requests, reviewed only by the manager.
- Profile page with password changes for every user.
- Bill-image upload and manager bill preview before approval.
- Receipt-text parser that extracts vendor, date, amount and category before submission.
- Duplicate-receipt protection using normalized text + similarity + vendor/amount/date signals.
- Manager approval workflow with server-side protection against self-approval and cross-team approval.
- One-way claim state machine: submitted → approved/rejected; approved → paid. Paid claims cannot move backwards.
- Finance dashboard with monthly total, category spend, employee spend and monthly limits.
- Sample claims for Mounika, Rakshitha, Rakhith, and Preetham.
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


## Suggested demo flow

1. Sign in as an employee and submit a claim with a bill image.
2. Sign in as Preetham (Manager), open Approvals, view the bill, and approve or reject the claim.
3. Use the Submitted, Approved, and Paid filters on the Claims page.
4. Submit a new employee-access request and approve it from the New Employees tab.
5. Open Profile to update a password.

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

1. A claim belongs to the employee who submits it. Only the manager can select another employee when creating a claim.
2. A manager can approve/reject only claims belonging to their direct reports.
3. A manager cannot approve/reject their own claim.
4. Finance can mark approved claims as paid.
5. State transitions are enforced in the API, not only in the UI.
6. Paid claims are terminal and cannot be edited back to an earlier state.
7. Duplicate detection is a warning/blocking rule using receipt-text similarity plus vendor, amount and date. A production version would use a stronger fingerprint, receipt image/OCR and configurable tolerance rules.
8. Monthly spend in the demo is calculated from all claims for the month. A production policy could count only approved/paid claims; this should be agreed with the business.
9. The receipt parser is deterministic to keep runtime free. It intentionally shows extracted fields to the user for correction before submission.
10. The assessment login uses locally stored credentials and a browser session. Production would use password hashing, SSO/OAuth, and server-side sessions/JWTs.

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
