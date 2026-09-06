import sys,json,threading,subprocess,shutil,time,concurrent.futures
from pathlib import Path
sys.path.insert(0,'/tmp/gjc-keychron-provider-experiments')
import mock_provider as m
import driver
old=m.plan

def plan(body,scenario):
    step=len(m.turn_tool_calls(body))
    if scenario in ('matrix_pause','matrix_isolation'):
        if step==0:return [('task',{'agent':'executor','isolated':scenario=='matrix_isolation','tasks':[{'id':'lab_child_0','description':'fixture child','assignment':'[GJC_CASE:child_slow] Finish the isolated fixture.','inheritContext':'none'}]})]
        if scenario=='matrix_pause':
            if step==1:return [('subagent',{'action':'pause','ids':['0-lab_child_0']})]
            if step==2:return [('bash',{'command':'sleep 14','timeout':18})]
            if step==3:return [('subagent',{'action':'inspect','ids':['0-lab_child_0']})]
            if step==4:return [('subagent',{'action':'resume','id':'0-lab_child_0','message':'[GJC_CASE:child_success] Finish now.'})]
            if step==5:return [('subagent',{'action':'await','ids':['0-lab_child_0'],'timeout_ms':10000})]
        elif step==1:return [('subagent',{'action':'await','ids':['0-lab_child_0'],'timeout_ms':15000})]
        return []
    return old(body,scenario)
m.plan=plan
server=m.ThreadingHTTPServer(('127.0.0.1',0),m.Handler);server.daemon_threads=True
server.log_path=Path('/tmp/gjc-keychron-live-experiments/matrix-provider.jsonl')
threading.Thread(target=server.serve_forever,daemon=True).start()
port=server.server_address[1]
def run(name,scenario,committed=False):
    case,cwd,env,cmd=driver.prepare(name,port,'success',tools='read,bash,ask,task,subagent',sdk=False)
    cwd=cwd.resolve()
    cfg=json.loads((case/'agent/config.yml').read_text());cfg['task']={'isolation':{'mode':'rcopy'},'enableLsp':False,'maxRecursionDepth':3};(case/'agent/config.yml').write_text(json.dumps(cfg))
    agents=cwd/'.gjc/agents';agents.mkdir(exist_ok=True)
    (agents/'executor.md').write_text('---\nname: executor\ndescription: Local fixture\ntools: [read, bash, yield]\nmodel: keychron-lab/lab-success\n---\nPerform only local fixture and finish using yield.\n')
    if scenario=='matrix_isolation':
        for args in [['init'],['config','user.name','Local Fixture'],['config','user.email','fixture@example.invalid'],['add','fixture.txt','AGENTS.md','.gjc/agents'],['commit','-m','fixture base']]:subprocess.run(['git',*args],cwd=cwd,capture_output=True,check=True)
        if committed:
            subprocess.run(['git','add','.gjc/hooks'],cwd=cwd,check=True,capture_output=True);subprocess.run(['git','commit','-m','fixture observer'],cwd=cwd,check=True,capture_output=True)
    cmd+=['--print','--mode','json',f'[GJC_CASE:{scenario}]']
    (case/'command.json').write_text(json.dumps(cmd));start=time.monotonic()
    try:p=subprocess.run(cmd,cwd=cwd,env=env,capture_output=True,timeout=42);code=p.returncode;out=p.stdout;err=p.stderr;timeout=False
    except subprocess.TimeoutExpired as e:code=None;out=e.stdout or b'';err=e.stderr or b'';timeout=True
    (case/'stdout.log').write_bytes(out);(case/'stderr.log').write_bytes(err)
    events=driver.events_at(case/'events.jsonl')
    result={'case':name,'scenario':scenario,'returncode':code,'timeout':timeout,'seconds':round(time.monotonic()-start,2),'sessionIds':sorted({e.get('sessionId','') for e in events}),'terminals':[e for e in events if e.get('type')=='agent_end'],'toolResults':[e for e in events if e.get('type') in ('tool_result','tool_execution_end')],'stderrTail':err.decode(errors='replace')[-1000:]}
    (case/'result.json').write_text(json.dumps(result,indent=2));return result
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
    results=list(pool.map(lambda a:run(*a),[('matrix_isolation_rcopy_uncommitted','matrix_isolation',False),('matrix_isolation_rcopy_committed','matrix_isolation',True)]))
rp=Path('/tmp/gjc-keychron-live-experiments/matrix-runtime-results.json');rp.write_text(json.dumps(json.loads(rp.read_text())+results,indent=2))
server.shutdown()
print(json.dumps([{k:r[k] for k in ('case','returncode','timeout','seconds','sessionIds')} for r in results]))
