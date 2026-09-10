from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from pathlib import Path
from datetime import date, datetime
from difflib import SequenceMatcher
import sqlite3, re, json

BASE = Path(__file__).resolve().parent
DB = BASE / 'expense_claims.db'
app = FastAPI(title='ClaimFlow Expense Claims API', version='1.0.0')
app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_methods=['*'], allow_headers=['*'])

STATUSES = ['submitted','approved','rejected','paid']

class ReceiptInput(BaseModel):
    text: str

class ClaimInput(BaseModel):
    employee_id: int
    receipt_text: str
    vendor: str
    expense_date: str
    amount: float
    category: str
    notes: str = ''

class StatusInput(BaseModel):
    status: str
    actor_id: int

class SeedReset(BaseModel):
    confirm: bool

def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    con = db()
    con.executescript('''
    CREATE TABLE IF NOT EXISTS employees (
      id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL, role TEXT NOT NULL,
      manager_id INTEGER, monthly_limit REAL NOT NULL DEFAULT 30000
    );
    CREATE TABLE IF NOT EXISTS claims (
      id INTEGER PRIMARY KEY AUTOINCREMENT, employee_id INTEGER NOT NULL, vendor TEXT NOT NULL,
      expense_date TEXT NOT NULL, amount REAL NOT NULL, category TEXT NOT NULL, notes TEXT,
      receipt_text TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'submitted',
      created_at TEXT NOT NULL, approved_by INTEGER, paid_at TEXT,
      FOREIGN KEY(employee_id) REFERENCES employees(id)
    );
    CREATE TABLE IF NOT EXISTS audit_log (
      id INTEGER PRIMARY KEY AUTOINCREMENT, claim_id INTEGER, actor_id INTEGER, action TEXT,
      details TEXT, created_at TEXT NOT NULL
    );
    ''')
    con.commit(); con.close()

def normalize(s: str) -> str:
    return re.sub(r'[^a-z0-9]+', ' ', (s or '').lower()).strip()

def parse_receipt(text: str):
    t = text.strip()
    low = t.lower()
    # amount: supports ₹ 1,234.50 / rs 1234 / total 250
    amounts = re.findall(r'(?:₹|rs\.?|inr)?\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.\d{1,2})?|[0-9]+(?:\.\d{1,2})?)', low)
    vals=[]
    for x in amounts:
        try: vals.append(float(x.replace(',','')))
        except: pass
    amount = max(vals) if vals else None
    date_match = re.search(r'\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{1,2}[/-]\d{1,2})\b', t)
    parsed_date = None
    if date_match:
        raw=date_match.group(1).replace('/','-')
        for fmt in ('%d-%m-%Y','%d-%m-%y','%Y-%m-%d','%d-%m-%Y'):
            try: parsed_date=datetime.strptime(raw,fmt).date().isoformat(); break
            except: pass
    vendor=None
    m=re.search(r'(?:vendor|merchant|store|restaurant|cab|uber|ola)\s*[:=-]\s*([^\n,]+)', t, re.I)
    if m: vendor=m.group(1).strip()
    if not vendor:
        first=re.split(r'[\n,]', t)[0].strip()
        vendor=first[:60] if first else 'Unknown merchant'
    category='Other'
    rules=[('Travel',['uber','ola','cab','taxi','flight','train','metro','fuel','petrol']),('Meals',['restaurant','cafe','coffee','lunch','dinner','meal','food','swiggy','zomato']),('Supplies',['stationery','paper','office','notebook','supplies']),('Accommodation',['hotel','inn','resort','stay']),('Client Entertainment',['client','entertainment','dinner meeting'])]
    for cat, words in rules:
        if any(w in low for w in words): category=cat; break
    return {'vendor':vendor,'amount':amount,'expense_date':parsed_date,'category':category}

def duplicate_candidates(con, employee_id, vendor, expense_date, amount, receipt_text, exclude_id=None):
    rows=con.execute('SELECT * FROM claims WHERE employee_id=? AND id != COALESCE(?, -1)',(employee_id,exclude_id)).fetchall()
    n=normalize(receipt_text)
    out=[]
    for r in rows:
        sim=SequenceMatcher(None,n,normalize(r['receipt_text'])).ratio()
        same_amount=abs(r['amount']-amount) < 0.01
        same_day=r['expense_date']==expense_date
        vendor_sim=SequenceMatcher(None,normalize(vendor),normalize(r['vendor'])).ratio()
        score=max(sim, 0.75*vendor_sim + 0.15*(same_amount) + 0.10*(same_day))
        if (sim>=0.84) or (same_amount and vendor_sim>=0.82 and abs((date.fromisoformat(expense_date)-date.fromisoformat(r['expense_date'])).days)<=21):
            out.append({'id':r['id'],'vendor':r['vendor'],'amount':r['amount'],'expense_date':r['expense_date'],'status':r['status'],'similarity':round(score,2)})
    return out

def seed():
    con=db(); con.execute('DELETE FROM audit_log'); con.execute('DELETE FROM claims'); con.execute('DELETE FROM employees')
    employees=[
      (1,'Mounika','mounika@local','staff',4,30000),
      (2,'Rakshitha','rakshitha@local','team_lead',4,40000),
      (3,'Rakhith','rakhith@local','staff',4,30000),
      (4,'Preetham','preetham@local','manager',None,50000),
    ]
    con.executemany('INSERT INTO employees VALUES (?,?,?,?,?,?)',employees)
    claims=[
      (1,'Bean & Brew','2026-09-10',480,'Meals','Client lunch meeting','submitted',None),
      (2,'OfficeMart','2026-09-10',1250,'Supplies','Team stationery purchase','submitted',None),
      (3,'City Cab','2026-09-10',360,'Travel','Sales client visit','submitted',None),
      (4,'Grand Hotel','2026-09-10',2200,'Accommodation','Manager business stay','submitted',None),
    ]
    """
      (1,'Metro Cabs','2026-09-02',210,'Travel','Auto ride to client office, receipt says Metro Cabs 02/09/2026 total ₹210','paid',4),
      (3,'QuickRide','2026-09-05',320,'Travel','QuickRide taxi 05/09/2026 ₹320','submitted',None),
      (5,'Grand Central Hotel','2026-09-06',8200,'Accommodation','Grand Central Hotel room 06/09/2026 total ₹8200','submitted',None),
    """
    now=datetime.now().isoformat(timespec='seconds')
    for emp,vendor,dt,amt,cat,txt,status,approver in claims:
        con.execute('INSERT INTO claims(employee_id,vendor,expense_date,amount,category,notes,receipt_text,status,created_at,approved_by) VALUES (?,?,?,?,?,?,?,?,?,?)',(emp,vendor,dt,amt,cat,'',txt,status,now,approver))
    con.commit(); con.close()

@app.on_event('startup')
def startup():
    init_db()
    con=db(); count=con.execute('SELECT COUNT(*) c FROM employees').fetchone()['c']; con.close()
    if count==0: seed()

@app.get('/api/health')
def health(): return {'ok':True,'service':'ClaimFlow API'}

@app.get('/api/employees')
def employees():
    con=db(); rows=[dict(r) for r in con.execute('SELECT * FROM employees ORDER BY role DESC,name')]; con.close(); return rows

@app.post('/api/parse-receipt')
def parse(inp: ReceiptInput):
    if not inp.text.strip(): raise HTTPException(400,'Receipt text is required')
    return parse_receipt(inp.text)

@app.get('/api/claims')
def claims(employee_id: int|None=None, status: str|None=None):
    con=db(); q='''SELECT c.*, e.name employee_name, e.manager_id FROM claims c JOIN employees e ON e.id=c.employee_id WHERE 1=1'''; p=[]
    if employee_id: q+=' AND c.employee_id=?'; p.append(employee_id)
    if status: q+=' AND c.status=?'; p.append(status)
    q+=' ORDER BY c.id DESC'; rows=[dict(r) for r in con.execute(q,p)]; con.close(); return rows

@app.get('/api/claims/{claim_id}')
def get_claim(claim_id:int):
    con=db(); r=con.execute('''SELECT c.*,e.name employee_name,e.manager_id,e.monthly_limit FROM claims c JOIN employees e ON e.id=c.employee_id WHERE c.id=?''',(claim_id,)).fetchone(); con.close()
    if not r: raise HTTPException(404,'Claim not found')
    return dict(r)

@app.post('/api/claims')
def create_claim(inp: ClaimInput):
    if inp.amount<=0: raise HTTPException(400,'Amount must be positive')
    try: date.fromisoformat(inp.expense_date)
    except: raise HTTPException(400,'expense_date must be YYYY-MM-DD')
    con=db(); emp=con.execute('SELECT * FROM employees WHERE id=?',(inp.employee_id,)).fetchone()
    if not emp: con.close(); raise HTTPException(404,'Employee not found')
    dups=duplicate_candidates(con,inp.employee_id,inp.vendor,inp.expense_date,inp.amount,inp.receipt_text)
    if dups:
        con.close(); raise HTTPException(409,detail={'message':'Possible duplicate receipt detected','duplicates':dups})
    cur=con.execute('INSERT INTO claims(employee_id,vendor,expense_date,amount,category,notes,receipt_text,status,created_at) VALUES (?,?,?,?,?,?,?,?,?)',(inp.employee_id,inp.vendor.strip(),inp.expense_date,inp.amount,inp.category,inp.notes,inp.receipt_text,'submitted',datetime.now().isoformat(timespec='seconds')))
    claim_id=cur.lastrowid
    con.execute('INSERT INTO audit_log(claim_id,actor_id,action,details,created_at) VALUES (?,?,?,?,?)',(claim_id,inp.employee_id,'submitted','Claim created',datetime.now().isoformat(timespec='seconds')))
    con.commit(); con.close(); return get_claim(claim_id)

@app.post('/api/claims/{claim_id}/status')
def change_status(claim_id:int, inp: StatusInput):
    if inp.status not in STATUSES: raise HTTPException(400,'Invalid status')
    con=db(); claim=con.execute('SELECT c.*,e.manager_id,e.name employee_name FROM claims c JOIN employees e ON e.id=c.employee_id WHERE c.id=?',(claim_id,)).fetchone(); actor=con.execute('SELECT * FROM employees WHERE id=?',(inp.actor_id,)).fetchone()
    if not claim or not actor: con.close(); raise HTTPException(404,'Claim or actor not found')
    current=claim['status']
    transitions={'submitted':{'approved','rejected'},'approved':{'paid'},'rejected':set(),'paid':set()}
    if inp.status not in transitions[current]: con.close(); raise HTTPException(409,f'Cannot move claim from {current} to {inp.status}')
    if inp.status in ('approved','rejected'):
        if actor['role']!='manager': con.close(); raise HTTPException(403,'Only managers can approve/reject')
        if actor['id']==claim['employee_id']: con.close(); raise HTTPException(403,'A manager cannot approve or reject their own claim')
        if claim['manager_id'] != actor['id']: con.close(); raise HTTPException(403,'Manager can only review their own team')
    if inp.status=='paid' and actor['role']!='finance': con.close(); raise HTTPException(403,'Only finance can mark claims paid')
    paid_at=datetime.now().isoformat(timespec='seconds') if inp.status=='paid' else None
    con.execute('UPDATE claims SET status=?, approved_by=CASE WHEN ?="approved" THEN ? ELSE approved_by END, paid_at=CASE WHEN ?="paid" THEN ? ELSE paid_at END WHERE id=?',(inp.status,inp.status,actor['id'],inp.status,paid_at,claim_id))
    con.execute('INSERT INTO audit_log(claim_id,actor_id,action,details,created_at) VALUES (?,?,?,?,?)',(claim_id,actor['id'],inp.status,f'{current} -> {inp.status}',datetime.now().isoformat(timespec='seconds')))
    con.commit(); con.close(); return get_claim(claim_id)

@app.get('/api/report')
def report(month:str|None=None):
    month=month or datetime.now().strftime('%Y-%m')
    con=db()
    by_cat=[dict(r) for r in con.execute('''SELECT category, ROUND(SUM(amount),2) total, COUNT(*) claims FROM claims WHERE substr(expense_date,1,7)=? GROUP BY category ORDER BY total DESC''',(month,))]
    by_person=[dict(r) for r in con.execute('''SELECT e.id,e.name,e.monthly_limit,ROUND(COALESCE(SUM(c.amount),0),2) spent,ROUND(e.monthly_limit-COALESCE(SUM(c.amount),0),2) remaining FROM employees e LEFT JOIN claims c ON c.employee_id=e.id AND substr(c.expense_date,1,7)=? GROUP BY e.id ORDER BY spent DESC''',(month,))]
    total=con.execute('SELECT COALESCE(SUM(amount),0) t FROM claims WHERE substr(expense_date,1,7)=?',(month,)).fetchone()['t']
    con.close(); return {'month':month,'total':round(total,2),'by_category':by_cat,'by_person':by_person}

@app.post('/api/reset')
def reset(inp: SeedReset):
    if not inp.confirm: raise HTTPException(400,'Confirmation required')
    seed(); return {'ok':True}

# Optional single-container production serving: after frontend build, backend serves /frontend-dist.
DIST = BASE.parent / 'frontend' / 'dist'
if DIST.exists():
    app.mount('/assets', StaticFiles(directory=DIST / 'assets'), name='assets')
    @app.get('/{full_path:path}')
    def spa(full_path: str):
        candidate = DIST / full_path
        if candidate.exists() and candidate.is_file(): return FileResponse(candidate)
        return FileResponse(DIST / 'index.html')
