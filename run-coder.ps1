param([int]$Port=8400,[switch]$AllowHostCommands)
$ErrorActionPreference='Stop'
$env:PYTHONUTF8='1'
Set-Location $PSScriptRoot
$env:HF_HOME=Join-Path $PSScriptRoot 'data/hf'
$env:HF_HUB_DISABLE_XET='1'
$python=Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
if (!(Test-Path $python)) { throw 'Instale as dependências conforme README.md' }
if (!(Test-Path 'data/qwen-coder/manifest.json')) {
  & $python -m mesh prepare --root data/qwen-coder --model Qwen/Qwen2.5-Coder-0.5B-Instruct --revision ea3f2471cf1b1f0db85067f1ef93848e38e88c25
  if ($LASTEXITCODE -ne 0) { throw 'Falha ao preparar o modelo' }
}
$arguments=@('tools/run_network.py','--root','data/qwen-coder','--port',"$Port")
if ($AllowHostCommands) { $arguments+='--allow-host-commands' }
$imageId=& $python tools/docker_probe.py
if ($imageId -match '^sha256:[0-9a-f]{64}$') { $arguments+=@('--sandbox-image',"$imageId") }
else { Write-Host 'Docker indisponível ou sem imagem local; testes em container ficam desativados.' }
& $python @arguments
