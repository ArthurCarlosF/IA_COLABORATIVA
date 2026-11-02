# IA Colaborativa — base de inferência distribuída

**Comece por [LEIA-ME-PRIMEIRO.txt](LEIA-ME-PRIMEIRO.txt)**: visão, dimensão, princípios, funcionamento e estado real do projeto. Esse arquivo deve acompanhar as alterações relevantes.

Um único checkpoint GPT-2 ou Qwen2 é dividido por camadas. Dois workers executam partes reais da rede; ativações atravessam HTTP autenticado. O coordenador não carrega o modelo completo na inferência.

Dependências e instalação detalhadas: [DEPENDENCIAS.md](DEPENDENCIAS.md). Codex e Claude são opcionais e não são dependências de execução.

## Estrutura base

- `mesh/`: coordenador, workers, motor, protocolo, créditos e interface inicial.
- `tests/`: testes unitários e integração com processos reais, HTTP e HTTPS.
- `tools/`: validação numérica e dois hosts lógicos no mesmo computador.
- `docs/PREMISES.md`: objetivo da rede e propostas ainda em discussão.
- `.github/workflows/tests.yml`: rotina de testes para GitHub Actions.
- `ARCHITECTURE.md`, `ROADMAP.md`, `PROGRESS.md`, `TEST_RESULTS.md`, `NEXT_STEPS.md`: estado e continuidade.

A base atual usa um coordenador para inferência e créditos; há um perfil leve GPT-2 de regressão e um perfil Qwen2.5-Coder de programação. Há descoberta P2P autorizada e alternância local por conta. Consenso público, remuneração por disponibilidade, escalonamento global e um agente completo de programação seguem como próximos estágios; consulte [as premissas](docs/PREMISES.md) e [as limitações de segurança](SECURITY.md).

## Perfil de programação e estado atual

Consulte [o estado funcional](docs/FUNCTIONAL_STATUS.md) antes de usar ou ampliar a rede. Para executar o modelo de código no Windows:

```powershell
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
.\run-coder.ps1
```

O perfil baixa Qwen/Qwen2.5-Coder-0.5B-Instruct na revisão fixa `ea3f2471cf1b1f0db85067f1ef93848e38e88c25`, prepara duas partições e inicia http://127.0.0.1:8400. Mantém contas, créditos e arquivos em `runtime/network/`, com descoberta assinada. A aplicação não carrega o modelo de referência nem repete benchmarks a cada início. Download e preparação consomem alguns GB de disco/RAM; a validação também carrega o modelo de referência localmente. A primeira execução pode demorar.

Para o executor de testes, Docker deve estar disponível e a imagem oficial `python:3.11-slim` preparada localmente. A opção é ativada pelo lançador somente se houver um ID de imagem disponível. A interface permite salvar arquivos, conferir diferenças e executar unittest restrito, sem execução de comandos no host por padrão. A opção de aprovação individual está descrita abaixo.

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

Também é possível preparar outro checkpoint **GPT-2 ou Qwen2 sem sliding window**, informando `--model`, `--revision` e `--parts`. Outras arquiteturas exigem novos adaptadores. O perfil Qwen usa template de chat e cache RoPE/GQA próprios. Para distribuir camadas conforme orçamento disponível para pesos:

```powershell
.\.venv\Scripts\python -m mesh prepare --root data/outro-modelo --model openai-community/gpt2 --revision REVISAO_EXATA --parts 2 --memory-mb 400,400
```

O exemplo não foi executado. Orçamentos são em MiB, um por worker, depois de reservar memória para Python/PyTorch, buffers e KV cache. O planejador minimiza o maior percentual de ocupação de pesos em partições contíguas. A distribuição é preparada offline e validada pelo coordenador no registro; não há migração automática durante uma geração.

O worker detecta CPU, RAM e uso do processo. `--device cuda:0` ativa a GPU e telemetria de VRAM, se o PyTorch instalado oferecer CUDA. CUDA não foi validado nesta sessão. Limites atuais: até oito sessões, uma tarefa por conta, batch 1, contexto total 512 tokens e até 128 tokens novos. O escalonador alterna passos entre contas e fatias de até 32 tokens de entrada. `MESH_THREADS` controla threads CPU; `MESH_CACHE_MB` limita KV cache por worker (128 MiB por padrão). KV reside no dispositivo do worker; não existe memória global única nem offload automático RAM/VRAM.

## Testar

Instale dependências de testes TLS com `.venv/Scripts/python -m pip install -r requirements-dev.txt`.

```powershell
$env:HF_HOME="$PWD/data/hf"
.\.venv\Scripts\python -m pytest -q --basetemp=runtime/pytest
```

A suíte usa portas locais livres e encerra seus próprios processos. Exige o checkpoint preparado. Escreve evidência numérica, memória e desempenho em `runtime/test-evidence.json`. Veja TEST_RESULTS.md para resultados executados e NEXT_STEPS.md para a etapa física.

## Segurança e créditos

Serviços escutam apenas loopback por padrão. Mensagens internas têm HMAC-SHA256 com janela de 30 s; cada passo verifica a posição KV para rejeitar repetições. Workers e URLs precisam constar da lista permitida; o hash dos pesos e a especificação devem coincidir com o manifesto do coordenador. Tensores usam JSON/base64 com dimensões e tipos restritos: nenhum pickle de rede. Os arquivos de pesos locais são carregados com `weights_only=True`.

O chat, a telemetria e o saldo exigem Bearer token por conta; prompts não são gravados em logs. Para rede remota, o programa recusa HTTP e exige HTTPS com verificação de certificado. Não abrir portas de roteador. Consulte DEPLOY_LAN.md. A proteção padrão é para workers **autorizados**. O modo P2P acrescenta identidades Ed25519 individuais para anúncios, comandos e recibos; a compatibilidade antiga sem configuração P2P usa somente segredo compartilhado. Nenhum modo implementa prova de execução contra workers hostis ou consenso de créditos.

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

**Limites:** o valor diário inicial não garante horas de uso nem qualidade de programação. O perfil leve continua tiny-gpt2; o perfil de código usa Qwen2.5-Coder-0.5B-Instruct. Identidades autorizadas e um coordenador/banco local são obrigatórios nesta fase; contas em conluio e participantes hostis não estão resolvidos. Contas distintas alternam turnos; uma segunda tarefa da mesma conta ou capacidade excedida recebem 429. A política ainda é local ao coordenador. Veja o [plano detalhado](docs/CREDIT_PLAN.md).

## Validar como dois hosts no mesmo computador

Execute `.venv/Scripts/python tools/simulate_hosts.py --serve`. O ambiente usa outros endereços/portas e não altera o ambiente padrão. Leia SIMULATION.md para detalhes, token de acesso, testes executados e limites dessa validação.

O lançador run-coder.ps1 reutiliza os arquivos locais de cada partição para evitar copiar GB a cada início; processos, caches e diretórios de trabalho continuam separados. A simulação padrão sem --reuse-weights preserva a opção de pastas de pesos copiadas. O prazo de inicialização do perfil de código é maior para acomodar carregamento frio; não é uma garantia de tempo de resposta.

## Aplicação persistente e diagnósticos separados

`run-coder.ps1` inicia `tools/run_network.py` com dados em `runtime/network/`. O token principal está em `runtime/network/config.json`; a segunda conta está em `accounts.peer-user`. Os arquivos e saldos sobrevivem ao reinício. O executor Docker é opcional e sua consulta inicial é limitada a cinco segundos; indisponibilidade não impede inferência/arquivos/sintaxe.

Para verificar a aplicação sem carregar um modelo de referência adicional, em outro terminal:

```powershell
.\.venv\Scripts\python.exe tools/smoke_network.py
```

Isso executa uma tarefa real e consome a franquia das contas de teste. Salva evidência por etapa em `runtime/network/smoke-evidence.json`. Para a comparação numérica completa, executar separadamente `tools/verify_remote.py --config runtime/network/active-config.json --root data/qwen-coder --ca runtime/network/worker-cert.pem --coding-task --output runtime/network/reference-evidence.json`, com HF_HOME=data/hf e RAM suficiente para a referência.

A simulação `tools/simulate_hosts.py` continua criando ambientes descartáveis, copiando pesos por padrão e provocando falhas para diagnóstico. Não usar seus diretórios novos a cada execução como carteira persistente de produção.

Falhas transitórias de transporte têm uma repetição limitada. O worker devolve o resultado armazenado se receber exatamente o último passo da sessão novamente; uma repetição conflitante é recusada. Assim uma resposta perdida não reexecuta o mesmo passo nem gera novo débito.

## Agente de projeto e escolha de modelo

A caixa de mensagem tem os modos Chat e Agente de projeto. O seletor oferece perfis para preparar e trocar na rede; somente o checkpoint ativo é usado na inferência, e identificadores ausentes são recusados. Há um checkpoint por cluster; modelos grandes disponíveis para planejamento não são anunciados como já executados. O agente encadeia inferência distribuída e ferramentas de arquivos/busca/diff/verificação, com histórico privado persistente e cancelamento. Limita-se a dez etapas; ao reiniciar, tarefas em andamento ficam interrompidas, sem repetir comandos automaticamente.

Comandos no computador do solicitante são opcionais: `run-coder.ps1 -AllowHostCommands`. Cada proposta precisa de aprovação local individual, vinculada aos argumentos e revisões do projeto. Comandos executam com os direitos do usuário; não são isolados. Sem essa opção, o agente trabalha com arquivos e verificadores ou unittest isolado quando Docker está disponível. A interface não oferece controle geral de navegador/computador, nem demonstra qualidade equivalente ao Codex. Histórico do agente não é memória ilimitada: contexto excedido é recusado explicitamente.

Avaliação real do agente nesta etapa: arquivo criado e sintaxe válida, porém tarefa não concluída dentro de 420 segundos por respostas de ferramentas inconsistentes do modelo. O modo é experimental. Leia TEST_RESULTS.md: testes do executor aprovados não significam autonomia ou qualidade comparável ao Codex. Docker local falhou por timeout e deve permanecer desabilitado quando o probe não executar.

## Troca real e pesos somente por participante

O seletor inicia preparação/troca coordenada entre workers, com checagem de recursos, download HTTP parcial por tensor e recuperação diante de falha. Cada worker recebe somente seu assignment; o coordenador guarda metadados e tokenizer. Nenhuma máquina precisa carregar o checkpoint inteiro no novo fluxo. Consulte [MODELOS.md](MODELOS.md) para modelos, limites, configuração física e comandos.

Perfis: Qwen2.5-Coder 0,5B/1,5B/32B e Qwen2.5 geral 0,5B/72B, com revisão fixa. 32B e 72B exigem recursos agregados suficientes; ainda não foram executados. Troca real para outro checkpoint de 0,5B e geração distribuída foram verificadas. O plano real de 32B gerou 32 assignments, cerca de 122 GiB de pesos FP32 previstos, sem baixar arquivos de pesos. O pedido de ativação de 32B nos dois workers atuais foi recusado antes de qualquer nova partição.

Em instalação nova, run-coder.ps1 usa plan-model e os workers baixam suas próprias partes. prepare continua disponível como diagnóstico legado que carrega o modelo completo; não usar esse comando para checkpoints gigantes.
