param([switch]$NoBrowser)
$ErrorActionPreference='Stop'
Set-Location $PSScriptRoot
$env:HF_HOME=Join-Path $PSScriptRoot "data/hf"
$python=Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
if (!(Test-Path $python)) { throw 'Execute a instalação descrita no README.md' }
if (!(Test-Path 'runtime/config.json')) { & $python -m mesh init }
if (!(Test-Path 'data/model/manifest.json')) { & $python -m mesh prepare; if ($LASTEXITCODE -ne 0) { throw 'Falha ao preparar modelo' } }
New-Item -ItemType Directory -Force runtime | Out-Null
$children=@()
try {
  $children+=Start-Process -FilePath $python -ArgumentList '-m','mesh','coordinator' -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput 'runtime/coordinator.out.log' -RedirectStandardError 'runtime/coordinator.err.log'
  foreach ($i in 0,1) {
    $children+=Start-Process -FilePath $python -ArgumentList '-m','mesh','worker','--id',"worker-$i",'--part',"$i" -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput "runtime/worker-$i.out.log" -RedirectStandardError "runtime/worker-$i.err.log"
  }
  @($children | ForEach-Object { $_.Id }) | ConvertTo-Json | Set-Content -Encoding UTF8 'runtime/processes.json'
  Write-Host 'Chat: http://127.0.0.1:8000. Token: runtime/config.json. Ctrl+C encerra os três serviços.'
  if (!$NoBrowser) { Start-Process 'http://127.0.0.1:8000' }
  while ($true) {
    Start-Sleep -Seconds 2
    foreach ($child in $children) { if ($child.HasExited) { throw "Serviço encerrou; veja runtime/*.err.log" } }
  }
} finally {
  foreach ($child in $children) { if (!$child.HasExited) { Stop-Process -Id $child.Id } }
}
