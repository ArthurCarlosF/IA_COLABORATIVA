# IA Colaborativa — base de inferência distribuída

**Comece por [LEIA-ME-PRIMEIRO.txt](LEIA-ME-PRIMEIRO.txt)**: visão, dimensão, princípios, funcionamento e estado real do projeto. Esse arquivo deve acompanhar as alterações relevantes.

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

O chat, a telemetria e o saldo exigem Bearer token por conta; prompts não são gravados em logs. Para rede remota, o programa recusa HTTP e exige HTTPS com verificação de certificado. Não abrir portas de roteador. Consulte DEPLOY_LAN.md. A proteção padrão é para uma rede de workers **confiáveis**, não para participantes anônimos potencialmente maliciosos. O segredo de cluster é compartilhado: não fornece identidade criptográfica independente por máquina.

O SQLite conserva os recibos antigos em token-layer como diagnóstico e mantém uma carteira nova, em tokens equivalentes, com reservas, liquidações e cadeia de eventos. O extrato verifica também se os saldos/reservas correspondem aos eventos. Não há pagamentos, venda ou transferência de créditos. O administrador local ainda pode reescrever banco e cadeia; não é consenso distribuído.

## Franquia diária e créditos por contribuição

- Padrão: **20.000 tokens/dia**, renovação às **00:00 de America/Sao_Paulo**, sem acumular a parte gratuita. A concessão ocorre na primeira consulta/requisição do novo dia, inclusive após ficar offline; não depende de um agendador.
- Entrada e saída calculadas consomem tokens; saída EOS também conta. Usa primeiro a franquia e depois os créditos extras, que não expiram.
- Antes de gerar, reserva um orçamento. Se houver pouco saldo, reduz o limite de saída; se não couber entrada + uma saída, responde 402. Valores reservados aparecem separados. O saldo restante cai conforme cada passo é concluído.
- Um token completo tem seu crédito dividido entre workers proporcionalmente às camadas, com precisão de seis casas decimais. Uma partição não ganha um token inteiro por repetir apenas uma fração do modelo.
- Trabalho para a própria conta não gera crédito extra. Contribuição remunerada só vem de tarefas de outras contas. Nenhum crédito é emitido por um passo incompleto ou por apenas anunciar memória.
- Ao terminar, cancelar ou falhar, devolve a reserva não utilizada. Reinício recupera reservas abandonadas. Durante a meia-noite, uma tarefa usa a reserva do dia em que iniciou; a franquia nova não é usada para cobrar retroativamente.
- O cartão **Uso e créditos** mostra franquia diária, renovação, extra disponível, contribuição acumulada, reservas e extrato privado.

Configure `daily_tokens`, `credit_timezone`, `accounts` e `worker_owners` em `runtime/config.json`. A conta `local-user` usa `user_token`; `accounts` mapeia identificadores adicionais a tokens secretos distintos de pelo menos 32 caracteres. `worker_owners` associa cada worker a uma conta existente. Sem associação explícita, os workers pertencem a `local-user`. Não compartilhar o segredo de cluster com usuários comuns.

Para demonstrar duas contas e contribuições reais:

```powershell
.\.venv\Scripts\python.exe tools/simulate_hosts.py --credits-demo --port 8300 --serve
```

Abra http://127.0.0.1:8300. O caminho do arquivo de configuração é exibido pelo lançador e também está em `runtime/simulation/latest.json`. Use `user_token` para a conta principal ou o token em `accounts.peer-user` para a outra conta. O lançador executa tarefas nas duas direções e compara os logits com a execução local. Dados, segredos e certificados ficam ignorados pelo Git.

**Limites:** o valor diário inicial não garante horas de uso nem qualidade de programação. O checkpoint continua tiny-gpt2. Identidades autorizadas e um coordenador/banco local são obrigatórios nesta fase; contas em conluio e participantes hostis não estão resolvidos. Concorrência ainda recebe 429 em vez de uma fila justa. Veja o [plano detalhado](docs/CREDIT_PLAN.md).

## Validar como dois hosts no mesmo computador

Execute `.venv/Scripts/python tools/simulate_hosts.py --serve`. O ambiente usa outros endereços/portas e não altera o ambiente padrão. Leia SIMULATION.md para detalhes, token de acesso, testes executados e limites dessa validação.
