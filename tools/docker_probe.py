"""Enable optional tests only after bounded actual container execution."""
import os
import re
import subprocess
import uuid

def probe():
    flags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
    name='ia-probe-'+uuid.uuid4().hex
    started=False
    try:
        result=subprocess.run(['docker','image','inspect','python:3.11-slim','--format','{{.Id}}'],capture_output=True,text=True,timeout=5,creationflags=flags)
        image=result.stdout.strip()
        if result.returncode or not re.fullmatch(r'sha256:[0-9a-f]{64}',image):return
        started=True
        result=subprocess.run(['docker','run','--rm','--pull=never','--name',name,'--network=none','--read-only','--cap-drop=ALL','--security-opt=no-new-privileges','--user=65534:65534','--cpus=1','--memory=256m','--pids-limit=32',image,'python','-B','-c','print("IA_PROBE_OK")'],capture_output=True,text=True,timeout=5,creationflags=flags)
        if result.returncode==0 and result.stdout.strip()=='IA_PROBE_OK':print(image)
    except (OSError,subprocess.TimeoutExpired):pass
    finally:
        if started:
            try:subprocess.run(['docker','rm','-f',name],capture_output=True,timeout=3,creationflags=flags)
            except (OSError,subprocess.TimeoutExpired):pass

if __name__=='__main__':probe()
