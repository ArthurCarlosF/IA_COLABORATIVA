# IA Colaborativa — base de inferência distribuída

Um único checkpoint GPT-2 é dividido por camadas. Dois workers executam partes reais da rede; ativações atravessam HTTP autenticado. O coordenador não carrega o modelo completo na inferência.

## Estrutura base

- `mesh/`: coordenador, workers, motor, protocolo, créditos e interface inicial.
- `tests/`: testes unitários e integração com processos reais, HTTP e HTTPS.
- `tools/`: validação numérica e dois hosts lógicos no mesmo computador.
- `docs/PREMISES.md`: objetivo da rede e propostas ainda em discussão.
- `.github/workflows/tests.yml`: rotina de testes para GitHub Actions.
- `ARCHITECTURE.md`, `ROADMAP.md`, `PROGRESS.md`, `TEST_RESULTS.md`, `NEXT_STEPS.md`: estado e continuidade.

A base atual usa um coordenador e um modelo minúsculo. Descentralização P2P, consenso, remuneração por disponibilidade, fila justa multiusuário e interface completa semelhante ao Codex são próximos estágios; consulte [as premissas](docs/PREMISES.md) e [as limitações de segurança](SECURITY.md).

## Executar no Windows

```powershell
git clone https://github.com/ArthurCarlosF/IA_COLABORATIVA.git
cd IA_COLABORATIVA
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
$env:HF_HOME="$PWD/data/hf"
$env:HF_HUB_DISABLE_XET='1'
.\.venv\Scripts\python -m mesh prepare
.\.venv\Scripts\python -m mesh init
.\run-local.ps1
```

Depois da primeira instalação, basta executar `run-local.ps1`. Se a política local impedir scripts, execute `powershell -NoProfile -ExecutionPolicy Bypass -File .\run-local.ps1` (vale somente para esse processo).

Abra http://127.0.0.1:8000 e copie `user_token` de `runtime/config.json` para o campo Token de acesso. Clique Conectar. O token não é salvo no navegador. Ctrl+C no lançador encerra os três processos. Logs ficam em `runtime/`.

Para iniciar individualmente, em três terminais:

```powershell
.\.venv\Scripts\python -m mesh coordinator
.\.venv\Scripts\python -m mesh worker --id worker-0 --part 0
.\.venv\Scripts\python -m mesh worker --id worker-1 --part 1
```

Não execute o lançador se esses serviços já estiverem usando as portas 8000, 8100 e 8101.

## Modelo e escopo

Modelo: [sshleifer/tiny-gpt2](https://huggingface.co/sshleifer/tiny-gpt2), revisão fixa `5f91d94bd9cd7190a9f3216ff93cd1dd95f2c7be2`. Duas camadas, dimensão oculta 2. É um checkpoint real, diminuto, inadequado a respostas úteis: repetição de palavras é esperada. A validação é da execução neural distribuída, não da qualidade do assistente.

Também é possível preparar outro checkpoint **da arquitetura GPT-2**, informando `--model`, `--revision` e `--parts`. Outras arquiteturas exigem novos adaptadores. Para distribuir camadas conforme orçamento disponível para pesos:

```powershell
.\.venv\Scripts\python -m mesh prepare --root data/outro-modelo --model openai-community/gpt2 --revision REVISAO_EXATA --parts 2 --memory-mb 400,400
```

O exemplo não foi executado. Orçamentos são em MiB, um por worker, depois de reservar memória para Python/PyTorch, buffers e KV cache. O planejador minimiza o maior percentual de ocupação de pesos em partições contíguas. A distribuição é preparada offline e validada pelo coordenador no registro; não há migração automática durante uma geração.

O worker detecta CPU, RAM e uso do processo. `--device cuda:0` ativa a GPU e telemetria de VRAM, se o PyTorch instalado oferecer CUDA. CUDA não foi validado nesta sessão. Limites iniciais: uma geração por coordenador, batch 1, contexto total 512 tokens, até 128 tokens novos. `MESH_THREADS` controla threads CPU; `MESH_CACHE_MB` limita KV cache por worker (128 MiB por padrão). KV reside no dispositivo do worker; não existe memória global única nem offload automático RAM/VRAM.

## Testar

Instale dependências de testes TLS com `.venv/Scripts/python -m pip install -r requirements-dev.txt`.

```powershell
$env:HF_HOME="$PWD/data/hf"
.\.venv\Scripts\python -m pytest -q --basetemp=runtime/pytest
```

A suíte usa portas locais livres e encerra seus próprios processos. Exige o checkpoint preparado. Escreve evidência numérica, memória e desempenho em `runtime/test-evidence.json`. Veja TEST_RESULTS.md para resultados executados e NEXT_STEPS.md para a etapa física.

## Segurança e créditos

Serviços escutam apenas loopback por padrão. Mensagens internas têm HMAC-SHA256 com janela de 30 s; cada passo verifica a posição KV para rejeitar repetições. Workers e URLs precisam constar da lista permitida; o hash dos pesos e a especificação devem coincidir com o manifesto do coordenador. Tensores usam JSON/base64 com dimensões e tipos restritos: nenhum pickle de rede. Os arquivos de pesos locais são carregados com `weights_only=True`.

O chat e a telemetria exigem Bearer token; prompts não são gravados em logs. Para rede remota, o programa recusa HTTP e exige HTTPS com verificação de certificado. Não abrir portas de roteador. Consulte DEPLOY_LAN.md. A proteção padrão é para uma rede de workers **confiáveis**, não para participantes anônimos potencialmente maliciosos. O segredo de cluster é compartilhado: não fornece identidade criptográfica independente por máquina.

O livro SQLite contém lançamentos de débito e crédito, identificadores idempotentes e uma cadeia SHA-256 verificável. Unidade: tokens de entrada efetivamente processados × camadas executadas. Inclui prefill e passos concluídos antes de uma falha. Não equivale a FLOPs, dinheiro ou prova contra fraude. O tempo é reportado pelo worker. Um administrador com controle do banco pode reescrever a cadeia; exporte e ancore os hashes externamente para auditoria contra esse cenário. Não há pagamentos nem saldo mínimo obrigatório nesta versão.

## Validar como dois hosts no mesmo computador

Execute `.venv/Scripts/python tools/simulate_hosts.py --serve`. O ambiente usa outros endereços/portas e não altera o ambiente padrão. Leia SIMULATION.md para detalhes, token de acesso, testes executados e limites dessa validação.
