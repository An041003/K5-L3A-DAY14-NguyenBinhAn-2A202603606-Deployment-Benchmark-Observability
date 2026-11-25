"""CP7: run upstream tools, never overwrite existing JSON evidence silently."""
import argparse, json, os, shutil, socket, subprocess, sys, tempfile, time
from pathlib import Path
from contextlib import contextmanager
from urllib.request import urlopen
from fix_kb import apply, BASE, MARKER
ROOT = Path(__file__).resolve().parents[1]
DEV = BASE / 'develop'
REPORTS = DEV / 'reports'
ROOT_REPORTS = ROOT / 'reports'
LEGACY = {'tail_0.json':'load_v2_slow_0.json', 'tail_003.json':'load_v2_slow_0.03.json', 'tail_010.json':'load_v2_slow_0.1.json'}
REQUIRED = [*(f'load_v2_c{c}.json' for c in (1,10,50,100)), *LEGACY.values(), 'eval_v1.json','eval_v2.json','eval_v2_fixed.json']

def sync_one(src, dst):
    if not src.exists(): return
    if dst.exists():
        if src.read_bytes() != dst.read_bytes():
            raise RuntimeError(f'Conflicting evidence: {src} vs {dst}; reconcile manually.')
    else:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

def sync_reports():
    for name in [*REQUIRED, 'eval_v1_regression.json']:
        sync_one(ROOT_REPORTS/name, REPORTS/name)
        sync_one(REPORTS/name, ROOT_REPORTS/name)
    for old,new in LEGACY.items():
        for folder in (ROOT_REPORTS, REPORTS):
            sync_one(folder/old, REPORTS/new)
        sync_one(REPORTS/new, ROOT_REPORTS/new)

def command(script, args, output):
    path = REPORTS/output
    if path.exists():
        data=json.loads(path.read_text(encoding='utf-8'))
        print(f'Reusing existing evidence: {path}')
        gate=data.get('quality_gate',data.get('slo',{}))
        return 0 if gate.get('passed') else 1
    # Write to temporary path; only publish valid JSON, even on legitimate gate/SLO failure.
    with tempfile.TemporaryDirectory(dir=REPORTS) as tmp:
        temp=Path(tmp)/output
        cp=subprocess.run([sys.executable, str(DEV/script), *args, '--out',str(temp)],cwd=DEV)
        if cp.returncode not in (0,1) or not temp.exists():
            raise RuntimeError(f'{script}: no usable JSON report (exit {cp.returncode})')
        json.loads(temp.read_text(encoding='utf-8'))
        shutil.copy2(temp,path)
    sync_one(path,ROOT_REPORTS/output)
    return cp.returncode

@contextmanager
def server(version, slow='0.03', errors='0.01', port=None):
    if port is None:
        with socket.socket() as s:
            s.bind(('127.0.0.1',0)); port=s.getsockname()[1]
    url=f'http://127.0.0.1:{port}'
    env={**os.environ,'AGENT_VERSION':version,'PORT':str(port),'MOCK_SLOW_RATE':slow,
         'MOCK_ERROR_RATE':errors,'LLM_MODEL':'mock-llm-small','PYTHONIOENCODING':'utf-8'}
    # Do not reuse credentials from a different exercise.
    env.pop('AGENT_API_KEY',None)
    log=REPORTS/f'agent_{version}_slow{slow}_err{errors}.log'
    with log.open('a',encoding='utf-8') as f:
        proc=subprocess.Popen([sys.executable,'app.py'],cwd=DEV,env=env,stdout=f,stderr=subprocess.STDOUT)
        try:
            for _ in range(100):
                if proc.poll() is not None: raise RuntimeError(f'Agent exited: {log}')
                try:
                    with urlopen(url+'/health',timeout=1) as res:
                        if json.load(res).get('agent_version')==version: break
                except OSError: pass
                time.sleep(.2)
            else: raise RuntimeError(f'Agent not healthy: {log}')
            yield url
        finally:
            proc.terminate()
            try: proc.wait(timeout=10)
            except subprocess.TimeoutExpired: proc.kill(); proc.wait()

def evaluation(url,name,baseline=None,strict=False):
    args=['--url',url,'--min-accuracy','1.0' if strict else '0.8','--retries','3']
    if baseline: args+=['--baseline',str(REPORTS/baseline)]
    return command('eval/run_eval.py',args,name)

def load(url,count,concurrency,name):
    return command('load_test.py',['--url',url,'--requests',str(count),'--concurrency',str(concurrency),
                                   '--slo-p95-ms','500','--slo-error-rate','0.02'],name)

def main():
    p=argparse.ArgumentParser(); p.add_argument('--requests',type=int,default=300); p.add_argument('--fixed-only',action='store_true'); a=p.parse_args()
    if a.requests < 100: p.error('Use >=100 requests for meaningful tail measurements; official CP7 uses 300.')
    if not (DEV/'app.py').is_file(): p.error('Apply overlay to the current upstream fork first.')
    REPORTS.mkdir(exist_ok=True); ROOT_REPORTS.mkdir(exist_ok=True); sync_reports()
    kb=DEV/'utils/mock_llm.py'
    baseline_names=[n for n in REQUIRED if n!='eval_v2_fixed.json']
    missing=[n for n in baseline_names if not (REPORTS/n).exists()]
    if not a.fixed_only and missing:
        if MARKER in kb.read_text(encoding='utf-8'):
            raise SystemExit('KB already patched, baseline incomplete: archive existing evidence and restore original mock from upstream to measure missing baseline, or use --fixed-only (does not complete missing reports).')
        # Eval isolates KB quality from stochastic errors. Load retains baseline 1% mock error rate.
        with server('v1',errors='0') as u: evaluation(u,'eval_v1.json')
        with server('v2',errors='0') as u: evaluation(u,'eval_v2.json','eval_v1.json')
        with server('v1',errors='0') as u: evaluation(u,'eval_v1_regression.json','eval_v2.json',True)
        with server('v2') as u:
            for c in (1,10,50,100): load(u,a.requests,c,f'load_v2_c{c}.json')
            load(u,a.requests,20,'load_v2_slow_0.03.json')
        for slow in ('0','0.1'):
            with server('v2',slow=slow) as u: load(u,a.requests,20,f'load_v2_slow_{slow}.json')
    if not (REPORTS/'eval_v2.json').exists(): raise SystemExit('Missing original v2 baseline')
    for kind in ('develop','production'): apply(BASE/kind/'utils/mock_llm.py')
    with server('v2',errors='0') as u: result=evaluation(u,'eval_v2_fixed.json','eval_v2.json',True)
    sync_reports()
    subprocess.run([sys.executable,str(ROOT/'scripts/update_report.py')],check=True)
    raise SystemExit(result)
if __name__=='__main__': main()
