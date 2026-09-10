# 3–5 minute assessment video script

## 0:00–0:30 — Problem
“Hi, I’m Preetham. For this assessment I built ClaimFlow, an expense-claims workflow for staff, managers and finance. The main problems I focused on were slow receipt entry, duplicate receipts, approval controls and monthly spend visibility.”

## 0:30–1:15 — Staff flow
“Here I’m logged in as Aarav, a staff member. I can see my monthly spend, pending claims and policy headroom. I’ll create a new claim by pasting raw receipt text instead of filling every field manually. The parser extracts vendor, date, amount and category, and I can review and correct the values before submitting.”

## 1:15–2:00 — Duplicate protection
“An important requirement was preventing the same receipt from being paid twice. The seeded demo contains two very similar Metro Cabs receipts. The backend normalizes the text and compares similarity, while also checking vendor, amount and date. When I try to submit the duplicate, the API blocks it and tells me that a possible duplicate was detected.”

## 2:00–2:45 — Manager workflow
“Now I switch to Meera, the manager. The approval screen only exposes her team’s claims. The approval rules are enforced by the backend, not just hidden in the UI. A manager cannot approve their own claim, and a manager cannot approve a claim belonging to another manager’s team.”

## 2:45–3:30 — Finance workflow
“Finally I switch to Finance. Finance can see total monthly spend, category totals, employee limits and the payment queue. An approved claim can be marked paid. The state machine is one-way: submitted can become approved or rejected, approved can become paid, and paid is terminal.”

## 3:30–4:00 — Engineering decisions
“I kept the runtime completely free by using SQLite and a deterministic receipt parser rather than requiring a paid AI API. The project includes realistic seed data, backend validation, API documentation and tests. If I had another week, I would add real authentication, OCR for receipt images, stronger duplicate matching, notifications, exports and PostgreSQL.”

## 4:00–4:15 — Close
“That’s ClaimFlow. The main goal was to keep the workflow simple for staff while making the important financial controls enforceable on the backend.”
