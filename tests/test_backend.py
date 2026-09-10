import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from fastapi.testclient import TestClient
import app

app.init_db(); app.seed(); client = TestClient(app.app)

def test_health():
    r=client.get('/api/health'); assert r.status_code==200 and r.json()['ok'] is True

def test_parse_receipt():
    r=client.post('/api/parse-receipt',json={'text':'METRO CABS\n02/09/2026\nTOTAL Rs 210'})
    assert r.status_code==200
    d=r.json(); assert d['amount']==210 and d['expense_date']=='2026-09-02'

def test_paid_is_terminal():
    # seeded claim 1 is already paid
    r=client.post('/api/claims/1/status',json={'status':'approved','actor_id':2})
    assert r.status_code==409

def test_manager_cannot_self_approve():
    # claim 6 belongs to Vikram, a manager; Vikram is actor 5
    r=client.post('/api/claims/6/status',json={'status':'approved','actor_id':5})
    assert r.status_code==403
