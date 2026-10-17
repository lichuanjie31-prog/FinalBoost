import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import httpx
from test_auth import register, bearer, HEADERS, PASSWORD
from test_business import post, exam_body, upload

def test_real_process_restart_and_connection_failure_probe(tmp_path):
    root=Path(__file__).resolve().parents[2]
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0)); port=sock.getsockname()[1]
    base=f'http://127.0.0.1:{port}'
    # Allow the persisted job to survive both independently bounded (30 s)
    # server startups. Expiry itself has separate business tests.
    env={**os.environ,'DATA_DIR':str(tmp_path),'GRADING_MODE':'mock','JOB_SECONDS':'2','JOB_TIMEOUT':'90'}
    def start():
        process=subprocess.Popen([sys.executable,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port',str(port),'--log-level','warning'],cwd=root/'backend',env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        limit=time.monotonic()+30
        while time.monotonic()<limit:
            assert process.poll() is None,'HTTP server exited during startup'
            try:
                if httpx.get(base+'/api/v1/health',timeout=.5,trust_env=False).status_code==200: return process
            except httpx.TransportError: pass
            time.sleep(.05)
        process.kill(); process.wait(); raise AssertionError('HTTP server startup timed out')
    process=start()
    try:
        with httpx.Client(base_url=base,trust_env=False,timeout=5) as c:
            auth=bearer(register(c))
            eid=post(c,'/exams',exam_body(),auth).json()['data']['examId']
            file=upload(c,auth).json()['data']
            gid=post(c,'/grading',{'examId':eid,'fileIds':[file['fileId']]},auth).json()['data']['gradingId']
            process.kill(); process.wait(timeout=5)
            red=subprocess.run([sys.executable,str(root/'scripts/health_probe.py'),base],capture_output=True,text=True,timeout=10)
            assert red.returncode==1
            print('\nINTENTIONAL DISCONNECT: '+red.stdout.strip()+'; exit=1')
            process=start()
            green=subprocess.run([sys.executable,str(root/'scripts/health_probe.py'),base],capture_output=True,text=True,timeout=10)
            assert green.returncode==0
            print('RESTORED CONNECTION: '+green.stdout.strip()+'; exit=0')
            login=c.post('/api/v1/auth/login',json={'username':'student_one','password':PASSWORD},headers=HEADERS)
            assert login.status_code==200
            auth=bearer(login.json()['data'])
            assert c.get('/api/v1/exams/'+eid,headers=auth).status_code==200
            assert c.get(file['url'],headers=auth).status_code==200
            deadline=time.monotonic()+6
            while time.monotonic()<deadline:
                job=c.get('/api/v1/grading/'+gid,headers=auth).json()['data']
                if job['status'] in ('failed','succeeded'): break
                time.sleep(.1)
            assert job['status']=='succeeded' and job['result']['totalScore']==63
            assert post(c,f'/exams/{eid}/diagnosis',{'gradingId':gid},auth).status_code==200
            print('RESTART RECOVERY PASS: account, exam, file, pending grading and diagnosis')
    finally:
        if process.poll() is None: process.terminate(); process.wait(timeout=10)
