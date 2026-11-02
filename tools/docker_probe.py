"""Consulta somente leitura com prazo para não bloquear o lançador."""
import os
import subprocess
try:
    result=subprocess.run(['docker','image','inspect','python:3.11-slim','--format','{{.Id}}'],capture_output=True,text=True,timeout=5,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    if result.returncode==0:print(result.stdout.strip())
except (OSError,subprocess.TimeoutExpired):
    pass
