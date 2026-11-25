"""Refresh only marked measured tables; preserve all hand-written notes."""
import json,csv,platform
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; REPORTS=ROOT/'reports'
def get(n):
    p=REPORTS/n
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else None

def fmt(x): return str(x) if x is not None else 'PENDING'

def table(headers,rows):
    return '\n'.join(['| '+' | '.join(headers)+' |','| '+' | '.join(['---']*len(headers))+' |',*['| '+' | '.join(map(fmt,r))+' |' for r in rows]])

def locust(n):
    p=ROOT/'benchmark-results'/f'scale_{n}_stats.csv'
    if not p.exists(): return [n]+['PENDING']*5
    with p.open(encoding='utf-8-sig') as f: rows=list(csv.DictReader(f))
    r=next((r for r in rows if r.get('Name')=='Aggregated'),None)
    if r is None: return [n]+['PENDING']*5
    return [n,r.get('Requests/s'),r.get('50%'),r.get('95%'),r.get('99%'),r.get('Failure Count')]

def replace_block(text, name, content):
    start=f'<!-- BEGIN AUTO:{name} -->'; end=f'<!-- END AUTO:{name} -->'
    if text.count(start)!=1 or text.count(end)!=1 or text.index(start)>text.index(end):
        raise ValueError(f'Missing or ambiguous block {name}; back up old report and migrate manually to v2 template.')
    a=text.index(start)+len(start); b=text.index(end)
    return text[:a]+'\n'+content+'\n'+text[b:]

def main():
    path=ROOT/'BENCHMARK_REPORT.md'
    text=path.read_text(encoding='utf-8')
    rows=[]
    for c in (1,10,50,100):
        r=get(f'load_v2_c{c}.json'); rows.append([c]+([r['rps'],*[r['latency_ms'][k] for k in ('p50','p95','p99')],f"{r['error_rate']:.2%}",'PASS' if r['slo']['passed'] else 'FAIL'] if r else ['PENDING']*6))
    text=replace_block(text,'LOAD',table(['Concurrency','RPS','p50 ms','p95 ms','p99 ms','Error rate','SLO'],rows))
    rows=[]
    for rate in ('0','0.03','0.1'):
        r=get(f'load_v2_slow_{rate}.json'); rows.append([rate]+([r['latency_ms'][k] for k in ('avg','p95','p99')] if r else ['PENDING']*3))
    text=replace_block(text,'TAIL',table(['Slow rate','avg ms','p95 ms','p99 ms'],rows))
    rows=[]
    for name in ('eval_v1','eval_v2','eval_v2_fixed'):
        r=get(name+'.json'); rows.append([name]+([f"{r['accuracy']:.2%} ({r['passed']}/{r['total']})",r['avg_tokens'],r['total_cost_usd'],r['cost_per_correct_usd'],'PASS' if r['quality_gate']['passed'] else 'FAIL',len(r['quality_gate']['regressions'])] if r else ['PENDING']*6))
    text=replace_block(text,'QUALITY',table(['Version','Accuracy','Avg tokens','Cost USD','Cost/correct','Gate','Regression'],rows))
    b=get('eval_v2.json'); f=get('eval_v2_fixed.json'); fixed={x['id']:x for x in f['results']} if f else {}
    failures=[[x['id'],', '.join(x.get('missing_keywords',[])) or x.get('error',''),('PASS' if fixed[x['id']]['passed'] else 'FAIL') if x['id'] in fixed else 'PENDING'] for x in b['results'] if not x['passed']] if b else [['PENDING','PENDING','PENDING']]
    text=replace_block(text,'FAILURES',table(['ID fail ban đầu','Thiếu keyword','Sau sửa'],failures))
    text=replace_block(text,'SCALING',table(['Instances','RPS','p50 ms','p95 ms','p99 ms','Failures'],[locust(1),locust(3)]))
    path.write_text(text,encoding='utf-8')
if __name__=='__main__': main()
