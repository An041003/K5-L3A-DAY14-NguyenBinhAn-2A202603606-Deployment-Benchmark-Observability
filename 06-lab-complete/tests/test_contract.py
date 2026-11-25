"""HTTP contract test using mocked Redis/LLM (NOT integration / official grade)."""
import os, sys, unittest, types
from pathlib import Path
from unittest.mock import patch

os.environ.update(AGENT_API_KEY='unit-test-only', RATE_LIMIT_PER_MINUTE='10', DAILY_BUDGET_USD='10', MONTHLY_BUDGET_USD='10')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
# Fixtures only: make isolated tests runnable without Redis package or upstream mock.
# Inject before imports. These modules exist only in this test process.
class RedisError(Exception): pass
class FixtureRedis:
    def __init__(self): self.available=True; self.calls=0; self.spent={}
    def ping(self):
        if not self.available: raise RedisError('unavailable')
        return True
    def close(self): pass
    def eval(self, script, count, *args):
        self.ping()
        if 'ZREMRANGEBYSCORE' in script:
            if self.calls >= int(args[1]): return 20
            self.calls += 1; return 0
        keys=args[:count]; values=args[count:]
        if 'EXPIREAT' in script:
            amount,daily,monthly,*_ = map(int,values)
            if any(self.spent.get(k,0)+amount > cap for k,cap in zip(keys,[daily,monthly])): return 0
            for k in keys: self.spent[k]=self.spent.get(k,0)+amount
        else:
            for k in keys: self.spent[k]=self.spent.get(k,0)+int(values[0])
        return 1
r=FixtureRedis()
redis=types.ModuleType('redis'); exceptions=types.ModuleType('redis.exceptions'); exceptions.RedisError=RedisError
redis.exceptions=exceptions; redis.from_url=lambda *a,**kw:r
sys.modules.update({'redis':redis,'redis.exceptions':exceptions})
utils=types.ModuleType('utils'); mock=types.ModuleType('utils.mock_llm'); mock.MOCK_RESPONSES={'default':['mock answer longer','short']}; mock.ask=lambda q:'short'; utils.mock_llm=mock
sys.modules.update({'utils':utils,'utils.mock_llm':mock})
from fastapi.testclient import TestClient
from app.main import app
from app.cost_guard import cost_nano, estimate_tokens, period_keys
from datetime import datetime, timezone

class Contract(unittest.TestCase):
    def setUp(self):
        r.available=True; r.calls=0; r.spent.clear(); self.client=TestClient(app); self.h={'X-API-Key':'unit-test-only'}
    def ask(self,headers=None): return self.client.post('/ask',json={'question':'Hello'},headers=headers)
    def test_health_ready(self):
        self.assertEqual(self.client.get('/health').status_code,200)
        self.assertEqual(self.client.get('/ready').status_code,200)
        r.available=False
        self.assertEqual(self.client.get('/health').status_code,200)
        self.assertEqual(self.client.get('/ready').status_code,503)
        self.assertEqual(self.ask(self.h).status_code,503)
    def test_auth(self):
        self.assertEqual(self.ask().status_code,401)
        self.assertEqual(self.ask({'X-API-Key':'wrong'}).status_code,401)
        self.assertEqual(self.ask(self.h).status_code,200)
    def test_rate(self):
        for _ in range(10): self.assertEqual(self.ask(self.h).status_code,200)
        response=self.ask(self.h)
        self.assertEqual(response.status_code,429); self.assertEqual(response.headers['retry-after'],'20')
    def test_cost(self):
        response=self.ask(self.h); self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['usage']['cost_usd'],cost_nano(2,2)/1e9)
        self.assertTrue(all(x==cost_nano(2,2) for x in r.spent.values()))
        for key in r.spent: r.spent[key]=10_000_000_000
        self.assertEqual(self.ask(self.h).status_code,402)
    def test_validation(self):
        self.assertEqual(self.client.post('/ask',json={'question':''},headers=self.h).status_code,422)
    def test_period(self):
        keys,exp=period_keys(datetime(2026,12,31,23,59,tzinfo=timezone.utc))
        self.assertTrue(keys[0].endswith('2026-12-31')); self.assertTrue(keys[1].endswith('2026-12')); self.assertEqual(exp[0],exp[1])
    def test_rollback(self):
        with patch('app.main.llm_ask',side_effect=RuntimeError('mock failure')):
            self.assertEqual(self.ask(self.h).status_code,502)
        self.assertTrue(all(x==0 for x in r.spent.values()))
    def test_request_id(self):
        self.assertTrue(self.ask(self.h).headers.get('x-request-id'))
if __name__=='__main__': unittest.main(verbosity=2)
