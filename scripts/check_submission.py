"""Preflight only: checks artifacts and consistency, not official score or screenshot content."""
import csv, json, re, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
REPORTS=ROOT/'reports'
CHECKS=[]
def check(label, ok, detail=''):
    CHECKS.append(bool(ok)); print(f'{"OK" if ok else "PENDING"}: {label}'+(f' — {detail}' if detail else ''))
def read(path):
    return path.read_text(encoding='utf-8',errors='replace') if path.is_file() else ''
def js(name):
    try: return json.loads((REPORTS/name).read_text(encoding='utf-8'))
    except (OSError,ValueError): return None

def main():
    for file in ('MISSION_ANSWERS.md','DEPLOYMENT.md','BENCHMARK_REPORT.md'):
        t=read(ROOT/file)
        check(file,bool(t)); check(file+' pending markers',bool(t) and not re.search(r'\bPENDING\b|YOUR-REAL-DOMAIN|\[tự điền\]',t.replace('PENDING = chưa đo','chưa đo'),re.I),'review any remaining placeholder manually')
    m=read(ROOT/'MISSION_ANSWERS.md')
    check('AI log section',bool(re.search(r'^## AI log',m,re.M|re.I)),'self-verification must be written by student')
    grade=read(REPORTS/'production_ready.txt'); check('Full grader evidence',bool(re.search(r'PASS\s+12\s*/\s*12',grade)) and bool(re.search(r'PASS\s+12\s*/\s*12',m)),'verify full Docker run and pasted checklist manually')
    d=read(ROOT/'DEPLOYMENT.md'); check('Public deployment URL recorded',bool(re.search(r'^https://(?!YOUR|localhost|127\.0\.0\.1)[^\s]+',d,re.M|re.I)),'verify public HTTP statuses 200/200/401/200 yourself')
    for c in (1,10,50,100):
        name=f'load_v2_c{c}.json'; r=js(name)
        check(name,bool(r and r.get('concurrency')==c and r.get('total_requests')==300 and all(k in r.get('latency_ms',{}) for k in ('p50','p95','p99')) and 'slo' in r),'300 requests, correct concurrency; SLO FAIL is valid')
    for rate in ('0','0.03','0.1'):
        name=f'load_v2_slow_{rate}.json'; r=js(name)
        check(name,bool(r and r.get('concurrency')==20 and r.get('total_requests')==300 and all(k in r.get('latency_ms',{}) for k in ('avg','p95','p99'))),'verify actual slow rate from run/config')
    for name,version in [('eval_v1.json','v1'),('eval_v2.json','v2'),('eval_v2_fixed.json','v2')]:
        r=js(name); check(name,bool(r and r.get('agent_version')==version and r.get('total')==23 and len(r.get('results',[]))==23))
    b=js('eval_v2.json'); f=js('eval_v2_fixed.json'); gate=(f or {}).get('quality_gate',{})
    bp={x['id'] for x in (b or {}).get('results',[]) if x.get('passed')}; fp={x['id'] for x in (f or {}).get('results',[]) if x.get('passed')}
    check('Fixed eval gate 23/23 + no regression',bool(b and f and f.get('passed')==23 and f.get('accuracy')==1 and len(fp)==23 and bp<=fp and gate.get('passed') is True and gate.get('regressions')==[]))
    for n in (1,3):
        p=ROOT/'benchmark-results'/f'scale_{n}_stats.csv'; ok=False
        if p.is_file():
            with p.open(encoding='utf-8-sig') as h:
                r=next((x for x in csv.DictReader(h) if x.get('Name')=='Aggregated'),{})
            ok=all(r.get(k) not in (None,'') for k in ('Requests/s','50%','95%','99%','Failure Count'))
        check(p.name,ok,'verify 100 users, 2m, 1/3 instances')
    for name in ('dashboard','running','test','grafana-dashboard','jaeger-slow-trace','jaeger-error-trace','prometheus-alert-firing'):
        p=ROOT/'screenshots'/f'{name}.png'; check(str(p.relative_to(ROOT)),p.is_file() and p.stat().st_size>8 and p.open('rb').read(8)==b'\x89PNG\r\n\x1a\n','presence/signature only, content must be verified')
    try:
        files=subprocess.check_output(['git','ls-files'],cwd=ROOT,text=True).splitlines()
        bad=[x for x in files if Path(x).name.startswith('.env') and Path(x).name!='.env.example']
        history=subprocess.check_output(['git','log','--all','--oneline','--','*.env','.env','*.env.local','.env.local'],cwd=ROOT,text=True)
        check('Tracked env files and selected Git history',not bad and not history,'not a complete secret scan; inspect history and screenshots manually')
    except (OSError,subprocess.CalledProcessError): check('Git history',False,'run inside the fork')
    print(f'\nPreflight checks: {sum(CHECKS)}/{len(CHECKS)}. Not official grade. Verify repo name/Public, real screenshots, ≥2 simultaneous firing alerts, trace/log match, report numbers, and AI log yourself.')
    return 0 if all(CHECKS) else 1
if __name__=='__main__': sys.exit(main())
