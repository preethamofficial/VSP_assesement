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
SAMPLE_BILL = '/sample-bill.png'
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
    receipt_image: str | None = None

class StatusInput(BaseModel):
    status: str
    actor_id: int

class SeedReset(BaseModel):
    confirm: bool

class LoginInput(BaseModel):
    name: str
    password: str
    access_type: str

class EmployeeRequestInput(BaseModel):
    name: str
    email: str
    password: str

class EmployeeRequestDecision(BaseModel):
    actor_id: int
    approve: bool

class PasswordChangeInput(BaseModel):
    actor_id: int
    current_password: str
    new_password: str

def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    con = db()
    con.executescript('''
    CREATE TABLE IF NOT EXISTS employees (
      id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL, role TEXT NOT NULL,
      manager_id INTEGER, monthly_limit REAL NOT NULL DEFAULT 30000,
      password TEXT NOT NULL DEFAULT 'employee123'
    );
    CREATE TABLE IF NOT EXISTS claims (
      id INTEGER PRIMARY KEY AUTOINCREMENT, employee_id INTEGER NOT NULL, vendor TEXT NOT NULL,
      expense_date TEXT NOT NULL, amount REAL NOT NULL, category TEXT NOT NULL, notes TEXT,
      receipt_text TEXT NOT NULL, receipt_image TEXT, status TEXT NOT NULL DEFAULT 'submitted',
      created_at TEXT NOT NULL, approved_by INTEGER, paid_at TEXT,
      FOREIGN KEY(employee_id) REFERENCES employees(id)
    );
    CREATE TABLE IF NOT EXISTS audit_log (
      id INTEGER PRIMARY KEY AUTOINCREMENT, claim_id INTEGER, actor_id INTEGER, action TEXT,
      details TEXT, created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS employee_requests (
      id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, email TEXT NOT NULL UNIQUE,
      password TEXT NOT NULL DEFAULT 'employee123', status TEXT NOT NULL DEFAULT 'pending', created_at TEXT NOT NULL, reviewed_at TEXT,
      reviewed_by INTEGER
    );
    ''')
    columns={row['name'] for row in con.execute('PRAGMA table_info(claims)')}
    if 'receipt_image' not in columns:
        con.execute('ALTER TABLE claims ADD COLUMN receipt_image TEXT')
    employee_columns={row['name'] for row in con.execute('PRAGMA table_info(employees)')}
    if 'password' not in employee_columns:
        con.execute("ALTER TABLE employees ADD COLUMN password TEXT NOT NULL DEFAULT 'employee123'")
    request_columns={row['name'] for row in con.execute('PRAGMA table_info(employee_requests)')}
    if 'password' not in request_columns:
        con.execute("ALTER TABLE employee_requests ADD COLUMN password TEXT NOT NULL DEFAULT 'employee123'")
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
    con=db(); con.execute('DELETE FROM audit_log'); con.execute('DELETE FROM claims'); con.execute('DELETE FROM employee_requests'); con.execute('DELETE FROM employees')
    employees=[
      (1,'Mounika','mounika@local','staff',4,30000),
      (2,'Rakshitha (Team Lead)','rakshitha@local','staff',4,40000),
      (3,'Rakhith','rakhith@local','staff',4,30000),
      (4,'Preetham','preetham@local','manager',None,50000),
    ]
    con.executemany('INSERT INTO employees(id,name,email,role,manager_id,monthly_limit) VALUES (?,?,?,?,?,?)',employees)
    con.execute("UPDATE employees SET password='manager123' WHERE role='manager'")
    claims=[
      (1,'Bean & Brew','2026-09-10',480,'Meals','Client lunch meeting','submitted',None),
      (1,'Metro Cabs','2026-09-09',310,'Travel','Travel to client office','submitted',None),
      (1,'OfficeMart','2026-09-08',950,'Supplies','Work stationery purchase','submitted',None),
      (1,'Sky Airlines','2026-09-06',4800,'Travel','Client-site travel','submitted',None),
      (1,'Green Leaf Cafe','2026-09-04',290,'Meals','Working lunch','submitted',None),
      (1,'Rapid Rail','2026-09-03',180,'Travel','Local client commute','submitted',None),
      (1,'Paper Point','2026-09-02',640,'Supplies','Project stationery','submitted',None),
      (1,'Business Inn','2026-09-01',1950,'Accommodation','Customer workshop stay','submitted',None),
      (2,'OfficeMart','2026-09-10',1250,'Supplies','Team stationery purchase','submitted',None),
      (2,'Cloud Cafe','2026-09-09',420,'Meals','Team planning session','submitted',None),
      (2,'Team Taxi','2026-09-07',650,'Travel','Team meeting travel','submitted',None),
      (2,'Client Lounge','2026-09-05',1500,'Client Entertainment','Client review meeting','submitted',None),
      (2,'Morning Roasters','2026-09-04',360,'Meals','Leadership breakfast','submitted',None),
      (2,'Express Metro','2026-09-03',220,'Travel','Office commute','submitted',None),
      (2,'Tech Stationers','2026-09-02',880,'Supplies','Team workshop materials','submitted',None),
      (2,'City Suites','2026-09-01',2600,'Accommodation','Regional planning event','submitted',None),
      (3,'City Cab','2026-09-10',360,'Travel','Sales client visit','submitted',None),
      (3,'Sales Lunch','2026-09-09',780,'Meals','Prospect meeting lunch','submitted',None),
      (3,'Printer Pro','2026-09-07',2100,'Supplies','Sales material printing','submitted',None),
      (3,'Travel Stay','2026-09-04',3200,'Accommodation','Outstation sales visit','submitted',None),
      (3,'Coffee Corner','2026-09-03',250,'Meals','Customer follow-up','submitted',None),
      (3,'Airport Shuttle','2026-09-02',540,'Travel','Airport client pickup','submitted',None),
      (3,'Brand Print Hub','2026-09-01',1350,'Supplies','Brochure printing','submitted',None),
      (3,'Market Plaza Hotel','2026-09-01',2800,'Accommodation','Sales conference stay','submitted',None),
      (4,'Grand Hotel','2026-09-10',2200,'Accommodation','Manager business stay','submitted',None),
      (4,'Executive Cab','2026-09-09',850,'Travel','Leadership meeting travel','submitted',None),
      (4,'Strategy Dinner','2026-09-07',1800,'Client Entertainment','Business strategy dinner','submitted',None),
      (4,'HQ Supplies','2026-09-05',760,'Supplies','Office supplies','submitted',None),
      (4,'Boardroom Bistro','2026-09-04',980,'Meals','Executive team lunch','submitted',None),
      (4,'Premier Cars','2026-09-03',1100,'Travel','Partner meeting travel','submitted',None),
      (4,'Office Source','2026-09-02',1430,'Supplies','Management workshop supplies','submitted',None),
      (4,'Central Residency','2026-09-01',3400,'Accommodation','Business review stay','submitted',None),
    ]
    """
      (1,'Metro Cabs','2026-09-02',210,'Travel','Auto ride to client office, receipt says Metro Cabs 02/09/2026 total ₹210','paid',4),
      (3,'QuickRide','2026-09-05',320,'Travel','QuickRide taxi 05/09/2026 ₹320','submitted',None),
      (5,'Grand Central Hotel','2026-09-06',8200,'Accommodation','Grand Central Hotel room 06/09/2026 total ₹8200','submitted',None),
    """
    now=datetime.now().isoformat(timespec='seconds')
    for emp,vendor,dt,amt,cat,txt,status,approver in claims:
        con.execute('INSERT INTO claims(employee_id,vendor,expense_date,amount,category,notes,receipt_text,receipt_image,status,created_at,approved_by) VALUES (?,?,?,?,?,?,?,?,?,?,?)',(emp,vendor,dt,amt,cat,'',txt,SAMPLE_BILL,status,now,approver))
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
    con=db(); rows=[dict(r) for r in con.execute('SELECT id,name,email,role,manager_id,monthly_limit FROM employees ORDER BY role DESC,name')]; con.close(); return rows

@app.post('/api/login')
def login(inp: LoginInput):
    if inp.access_type not in ('manager','employee'): raise HTTPException(400,'Select manager or employee access')
    con=db(); row=con.execute('SELECT id,name,email,role,manager_id,monthly_limit,password FROM employees WHERE lower(name)=lower(?)',(inp.name.strip(),)).fetchone(); con.close()
    if not row or row['password']!=inp.password: raise HTTPException(401,'Incorrect name or password')
    if inp.access_type=='manager' and row['role']!='manager': raise HTTPException(403,'This account does not have manager access')
    if inp.access_type=='employee' and row['role']=='manager': raise HTTPException(403,'Please use manager access')
    result=dict(row); result.pop('password'); return result

@app.post('/api/employee-requests')
def request_employee_access(inp: EmployeeRequestInput):
    name=inp.name.strip(); email=inp.email.strip().lower()
    if not name or not email or '@' not in email: raise HTTPException(400,'Enter a valid name and email')
    if len(inp.password)<6: raise HTTPException(400,'Password must contain at least 6 characters')
    con=db()
    if con.execute('SELECT 1 FROM employees WHERE email=?',(email,)).fetchone() or con.execute('SELECT 1 FROM employee_requests WHERE email=? AND status="pending"',(email,)).fetchone():
        con.close(); raise HTTPException(409,'An account or pending request already exists for this email')
    con.execute('INSERT INTO employee_requests(name,email,password,created_at) VALUES (?,?,?,?)',(name,email,inp.password,datetime.now().isoformat(timespec='seconds')))
    con.commit(); con.close(); return {'ok':True,'message':'Request sent to the manager for approval'}

@app.get('/api/employee-requests')
def employee_requests(actor_id:int):
    con=db(); actor=con.execute('SELECT role FROM employees WHERE id=?',(actor_id,)).fetchone()
    if not actor or actor['role']!='manager': con.close(); raise HTTPException(403,'Only the manager can view employee requests')
    rows=[dict(r) for r in con.execute('SELECT * FROM employee_requests WHERE status="pending" ORDER BY id DESC')]; con.close(); return rows

@app.post('/api/employee-requests/{request_id}/decision')
def decide_employee_request(request_id:int, inp:EmployeeRequestDecision):
    con=db(); actor=con.execute('SELECT * FROM employees WHERE id=?',(inp.actor_id,)).fetchone(); request=con.execute('SELECT * FROM employee_requests WHERE id=? AND status="pending"',(request_id,)).fetchone()
    if not actor or actor['role']!='manager': con.close(); raise HTTPException(403,'Only the manager can approve employee requests')
    if not request: con.close(); raise HTTPException(404,'Pending employee request not found')
    status='approved' if inp.approve else 'rejected'
    con.execute('UPDATE employee_requests SET status=?, reviewed_at=?, reviewed_by=? WHERE id=?',(status,datetime.now().isoformat(timespec='seconds'),actor['id'],request_id))
    if inp.approve:
        con.execute('INSERT INTO employees(name,email,role,manager_id,monthly_limit,password) VALUES (?,?,?,?,?,?)',(request['name'],request['email'],'staff',actor['id'],30000,request['password']))
    con.commit(); con.close(); return {'ok':True,'status':status}

@app.post('/api/profile/password')
def change_password(inp: PasswordChangeInput):
    if len(inp.new_password)<6: raise HTTPException(400,'New password must contain at least 6 characters')
    con=db(); actor=con.execute('SELECT * FROM employees WHERE id=?',(inp.actor_id,)).fetchone()
    if not actor or actor['password']!=inp.current_password: con.close(); raise HTTPException(401,'Current password is incorrect')
    con.execute('UPDATE employees SET password=? WHERE id=?',(inp.new_password,inp.actor_id))
    con.commit(); con.close(); return {'ok':True}

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
    if inp.receipt_image and (not inp.receipt_image.startswith('data:image/') or len(inp.receipt_image)>7_000_000):
        raise HTTPException(400,'Upload a valid image smaller than 5 MB')
    con=db(); emp=con.execute('SELECT * FROM employees WHERE id=?',(inp.employee_id,)).fetchone()
    if not emp: con.close(); raise HTTPException(404,'Employee not found')
    dups=duplicate_candidates(con,inp.employee_id,inp.vendor,inp.expense_date,inp.amount,inp.receipt_text)
    if dups:
        con.close(); raise HTTPException(409,detail={'message':'Possible duplicate receipt detected','duplicates':dups})
    cur=con.execute('INSERT INTO claims(employee_id,vendor,expense_date,amount,category,notes,receipt_text,receipt_image,status,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)',(inp.employee_id,inp.vendor.strip(),inp.expense_date,inp.amount,inp.category,inp.notes,inp.receipt_text,inp.receipt_image,'submitted',datetime.now().isoformat(timespec='seconds')))
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

@app.delete('/api/claims/{claim_id}')
def delete_claim(claim_id:int, actor_id:int):
    con=db(); claim=con.execute('SELECT c.id,e.manager_id FROM claims c JOIN employees e ON e.id=c.employee_id WHERE c.id=?',(claim_id,)).fetchone(); actor=con.execute('SELECT * FROM employees WHERE id=?',(actor_id,)).fetchone()
    if not claim or not actor: con.close(); raise HTTPException(404,'Claim or actor not found')
    if actor['role']!='manager' or claim['manager_id']!=actor['id']:
        con.close(); raise HTTPException(403,'Only the assigned manager can delete this claim')
    con.execute('DELETE FROM audit_log WHERE claim_id=?',(claim_id,))
    con.execute('DELETE FROM claims WHERE id=?',(claim_id,))
    con.commit(); con.close(); return {'ok':True}

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
    @app.get('/sample-bill.png')
    def sample_bill():
        return FileResponse(BASE / 'assets' / 'sample-bill.png')
    @app.get('/{full_path:path}')
    def spa(full_path: str):
        candidate = DIST / full_path
        if candidate.exists() and candidate.is_file(): return FileResponse(candidate)
        return FileResponse(DIST / 'index.html')
