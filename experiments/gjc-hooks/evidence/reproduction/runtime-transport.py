import concurrent.futures
import importlib.util
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import threading
import time

spec=importlib.util.spec_from_file_location('driver','/tmp/gjc-keychron-live-experiments/driver.py')
driver=importlib.util.module_from_spec(spec);spec.loader.exec_module(driver)
ROOT=driver.ROOT

def wait_for(predicate, timeout=20):
    start=time.monotonic()
    while not predicate():
        if time.monotonic()-start>timeout:raise TimeoutError('controlled runtime condition timed out')
        time.sleep(.025)

class Collector:
    def __init__(self, port=0, lose_type=None):
        self.rows=[];self.lost=[];self.connections=0;self.lose_type=lose_type;self.stop=threading.Event();self.ready=threading.Event();self.active=[]
        self.sock=socket.socket();self.sock.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);self.sock.bind(('127.0.0.1',port));self.port=self.sock.getsockname()[1];self.sock.listen();self.sock.settimeout(.1)
        self.thread=threading.Thread(target=self.run,daemon=True);self.thread.start()
    def run(self):
        while not self.stop.is_set():
            try:conn,_=self.sock.accept()
            except socket.timeout:continue
            except OSError:return
            self.active.append(conn);self.connections+=1;conn.settimeout(.1);buf=b''
            try:
                while not self.stop.is_set():
                    try:data=conn.recv(65536)
                    except socket.timeout:continue
                    if not data:break
                    buf+=data
                    while b'\n' in buf:
                        line,buf=buf.split(b'\n',1);row=json.loads(line)
                        if self.lose_type and row['type']==self.lose_type:
                            self.lost.append(row);self.lose_type=None;self.ready.set()
                            # Simulate collector failure after OS accepted write but before persistence.
                            conn.close();buf=b'';raise ConnectionAbortedError()
                        self.rows.append(row)
            except (OSError,ConnectionAbortedError):pass
            finally:
                conn.close()
    def close(self):
        self.stop.set();self.sock.close()
        for conn in self.active:
            try:conn.close()
            except OSError:pass
        self.thread.join(1)

def start(name,scenario,port,cwd_override=None):
    case,cwd,env,cmd=driver.prepare(name,64329,scenario,runtime=True,sdk=False)
    env['GJC_KEYCHRON_PORT']=str(port)
    cmd += ['--print','--mode','json',f'[GJC_CASE:{scenario}]']
    (case/'command.json').write_text(json.dumps(cmd))
    # Existing driver records only sanitized environment; update its transport port.
    (case/'environment.json').write_text(json.dumps(env,indent=2))
    stdout=open(case/'stdout.log','wb');stderr=open(case/'stderr.log','wb')
    proc=subprocess.Popen(cmd,env=env,cwd=cwd_override or cwd,stdout=stdout,stderr=stderr)
    return case,proc,stdout,stderr,cwd

def finish(case,proc,stdout,stderr,collector,extra=None):
    try:code=proc.wait(30)
    except subprocess.TimeoutExpired:proc.kill();code=proc.wait();extra={**(extra or {}),'harnessTimeout':True}
    stdout.close();stderr.close();time.sleep(.15)
    rows=driver.events_at(case/'events.jsonl');stream=collector.rows[:]
    (case/'stream.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in stream))
    (case/'collector-lost.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in collector.lost))
    result={'case':case.name,'actualGjc':True,'syntheticLocalModel':True,'sdkDisabled':True,'returncode':code,'pid':proc.pid,'hookTypes':[r['type'] for r in rows],'streamTypes':[r['type'] for r in stream],'sessionIds':sorted({r.get('sessionId') for r in rows}),'producerIds':sorted({r['producerId'] for r in rows}),'connections':collector.connections,'hookCount':len(rows),'streamCount':len(stream),**(extra or {})}
    (case/'result.json').write_text(json.dumps(result,indent=2));collector.close();return result

def late():
    reserved=socket.socket();reserved.bind(('127.0.0.1',0));port=reserved.getsockname()[1]
    case,proc,out,err,cwd=start('transport_late_receiver','slow',port)
    try:
        wait_for(lambda:any(r['type']=='agent_start' for r in driver.events_at(case/'events.jsonl')))
        before=driver.events_at(case/'events.jsonl');time.sleep(.3);reserved.close();collector=Collector(port)
        wait_for(lambda:len(collector.rows)>=len(before))
        result=finish(case,proc,out,err,collector,{'eventsBeforeReceiver':len(before),'queuedEventIdsDelivered':all(any(s['eventId']==r['eventId'] for s in collector.rows) for r in before),'snapshotOnConnect':False})
        assert result['queuedEventIdsDelivered'];assert 'agent_end' in result['streamTypes'];return result
    finally:
        reserved.close()
        if proc.poll() is None:proc.kill()

def reconnect_gap():
    collector=Collector(lose_type='agent_start');case,proc,out,err,cwd=start('transport_receiver_loss','slow',collector.port)
    try:
        wait_for(lambda:bool(collector.lost))
        result=finish(case,proc,out,err,collector)
        lost=collector.lost[0];rows=driver.events_at(case/'events.jsonl');stream=driver.events_at(case/'stream.jsonl')
        result.update({'simulatedCollectorLossEvent':lost['type'],'lostEventPresentInLocalTrace':any(r['eventId']==lost['eventId'] for r in rows),'lostEventReplayedAfterReconnect':any(r['eventId']==lost['eventId'] for r in stream),'snapshotAfterReconnect':False,'laterCompletionArrived':'agent_end' in result['streamTypes'],'interpretation':'Receiver crash after socket acceptance can lose state. Later events resume; no snapshot or ACK reconstructs the missing start.'})
        (case/'result.json').write_text(json.dumps(result,indent=2));assert result['connections']>=2;assert not result['lostEventReplayedAfterReconnect'];assert result['laterCompletionArrived'];return result
    finally:
        if proc.poll() is None:proc.kill()

def death_restart():
    collector=Collector();case,proc,out,err,cwd=start('transport_sigkill','hang',collector.port)
    try:
        wait_for(lambda:any(r['type']=='turn_start' for r in driver.events_at(case/'events.jsonl')))
        time.sleep(1);assert proc.poll() is None;proc.kill()
        result=finish(case,proc,out,err,collector,{'termination':'SIGKILL only this experiment child PID','terminalEventObserved':False})
        assert result['returncode']==-signal.SIGKILL;assert 'agent_end' not in result['hookTypes'];assert 'session_shutdown' not in result['hookTypes']
        restarted=Collector();case2,proc2,out2,err2,_=start('transport_after_sigkill','success',restarted.port,cwd)
        result2=finish(case2,proc2,out2,err2,restarted,{'reusedWorkspace':str(cwd),'newProducer':True,'newSession':True})
        assert set(result['producerIds']).isdisjoint(result2['producerIds']);assert set(result['sessionIds']).isdisjoint(result2['sessionIds']);return [result,result2]
    finally:
        if proc.poll() is None:proc.kill()

def concurrent_same_cwd():
    a=Collector();ca,pa,oa,ea,cwd=start('transport_same_cwd_a','slow',a.port)
    b=Collector();cb,pb,ob,eb,_=start('transport_same_cwd_b','success',b.port,cwd)
    try:
        rb=finish(cb,pb,ob,eb,b,{'reusedWorkspace':str(cwd)})
        ra=finish(ca,pa,oa,ea,a)
        assert set(ra['sessionIds']).isdisjoint(rb['sessionIds']);assert set(ra['producerIds']).isdisjoint(rb['producerIds'])
        identity_a=driver.events_at(ca/'events.jsonl')[0];identity_b=driver.events_at(cb/'events.jsonl')[0]
        comparison={'sameCwdDifferentSessions':True,'sameInheritedOrcaTerminalHandle':identity_a.get('orcaTerminalHandle')==identity_b.get('orcaTerminalHandle'),'meaning':'Inherited Orca handle is a location hint, not unique session identity.'}
        ra.update(comparison);rb.update(comparison)
        (ca/'result.json').write_text(json.dumps(ra,indent=2));(cb/'result.json').write_text(json.dumps(rb,indent=2));return [ra,rb]
    finally:
        for p in [pa,pb]:
            if p.poll() is None:p.kill()

if __name__=='__main__':
    results=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for future in concurrent.futures.as_completed([pool.submit(fn) for fn in [late,reconnect_gap,death_restart,concurrent_same_cwd]]):
            try:
                r=future.result();results.extend(r if isinstance(r,list) else [r])
            except Exception as exc:results.append({'experimentError':str(exc),'errorType':type(exc).__name__})
    (ROOT/'transport-results.json').write_text(json.dumps(results,indent=2))
    print(json.dumps(results,indent=2))
