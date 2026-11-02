# Testes executados — 02/11/2026

## Primeira execução

Comando: `.venv/Scripts/python -m pytest -q --basetemp=runtime/pytest` com HF_HOME=data/hf.

Resultado real: **16 passed in 48.87s**.

- Dois workers e coordenador em processos separados, usando sockets loopback.
- Oito passos de inferência, prefill e KV incremental: erro máximo dos logits **0,0**, tolerâncias atol=1e-6/rtol=1e-5; argmax idêntico ao modelo completo.
- Chat pela API: 12 tokens em 2,445 s, aproximadamente 4,91 tokens/s.
- Créditos: 24 lançamentos, os dois workers, débito e crédito balanceados, cadeia íntegra.
- RSS inicial: 245.047.296 e 245.084.160 bytes. KV ativo: 64 bytes por worker na sequência de quatro tokens. Após release: zero bytes de KV e zero sessões; variação de RSS inferior a 64 MiB.
- Worker encerrado durante disponibilidade da rede: falha explícita; cache acessível liberado; reinício e nova geração bem-sucedidos.
- Autenticação, validação de tensores, limite de payload, vocabulário/tipos, posição KV, idempotência e adulteração do livro contábil verificados conforme testes.

## Navegador

Chrome, http://127.0.0.1:8000, dois workers online. Pergunta enviada pela interface: "What is artificial intelligence?". Resposta real de 32 tokens repetindo "stairs", 4,60 tokens/s, zero falhas. Captura: runtime/chat-validado.png. Modelo de validação sem qualidade conversacional.

## Versão final — suíte completa

Comando: `.venv/Scripts/python -m pytest -q --basetemp=runtime/pytest-final` com HF_HOME=data/hf.

Resultado real: **26 passed in 100.00s (0:01:40)**, sem avisos.

Integração repetida em HTTP loopback e HTTPS com certificados de teste explicitamente confiados. Certificado não confiável recusado. Logits com erro máximo 0.0, oito passos em cada transporte. Chat HTTPS: 12 tokens em 3.241 s (3.70 tokens/s). Dois workers efetivos e créditos dos dois estágios.

Também passaram: planejador de memória, rejeição por orçamento de KV, recusa de HTTP remoto, recusa de partição atribuída incorretamente, token fora do vocabulário, concorrência (429) e cancelamento do cliente com liberação dos dois caches e da trava do coordenador.

O teste novo de cancelamento inicialmente falhou em HTTP e HTTPS: 2 failed, 24 passed em 118,19 s. Foi corrigido substituindo o middleware HTTP por middleware ASGI que preserva a desconexão e protegendo a limpeza do KV contra cancelamento. Regressão isolada: 2 passed em 48,00 s. A suíte final acima confirma a correção.

Evidência detalhada: runtime/test-evidence.json. O verificador tools/verify_remote.py foi executado com sucesso contra os dois workers **locais**, com oito passos equivalentes, chat e créditos: runtime/local-verifier-evidence.json. Essa execução do verificador precedeu a última correção de cancelamento; a suíte final testa a correção.

A interface final foi reaberta no Chrome após reiniciar todos os serviços. Gerou 32 tokens a 3,26 tokens/s, sem falhas. Captura atualizada: runtime/chat-validado.png. Desempenho varia com a carga da máquina; esses números não são benchmark de aceleração.

## Não executado

Duas máquinas físicas, execução de camadas no celular/navegador, CUDA/VRAM, perda física de rede, carga prolongada, modelo maior/instruído e produção com participantes hostis. O limite de RSS é uma verificação curta de regressão, não um limite de memória pico. Não houve promessa de aceleração por distribuir este modelo minúsculo; o transporte domina o custo.

## Dois hosts lógicos no mesmo computador — 02/11/2026

Executado `tools/simulate_hosts.py --serve`. Coordenador HTTP apenas em loopback 127.0.0.1:8200; workers reais pc-a em HTTPS 127.0.0.2:8201 e pc-b em HTTPS 127.0.0.3:8202. Processos de serviço inicialmente observados: {'coordinator': 17964, 'pc-a': 17144, 'pc-b': 27452}. Pastas separadas; cada worker recebeu somente sua partição. Há um único sistema operacional/hardware; diretórios separados não constituem isolamento de permissões.

Certificado não confiável foi rejeitado. O worker pc-b foi encerrado; a geração falhou explicitamente. Após reinício, oito passos tiveram erro máximo de logits 0.0 comparados ao modelo local. Chat gerou 12 tokens em 2.500 s. Livro íntegro com 25 lançamentos, incluindo um estágio concluído antes da falha induzida. A falha vista no painel é a do teste intencional.

Evidência desta execução: D:/Projetos/RedeInferencia/runtime/simulation/20261102-150404-3782b3/report.json. O script executou de fato inicialização, comunicação TLS, desligamento/reinício e verificador numérico. A suíte anterior de 26 testes não foi repetida nesta alteração, que adiciona somente um lançador de validação; o motor neural não foi modificado.

## Validação da estrutura base para o GitHub — 02/11/2026

Instalação editável do pacote ia-colaborativa 0.1.0 concluída com sucesso (`pip install -e . --no-deps`); comando `ia-colaborativa --help` executado. Suíte local repetida: **26 passed in 106.03s (0:01:46)**, com HTTP/HTTPS e inferência real. Rotina de GitHub Actions adicionada; o resultado remoto não foi verificado nesta validação local. Revisão de publicação: 31 arquivos; pesos, runtime, chaves e credenciais locais excluídos.

## Franquia diária e créditos por contribuição — 02/11/2026

Implementados: carteiras por conta, franquia inicial configurável de 20.000 tokens/dia à meia-noite de America/Sao_Paulo, extras sem expiração, divisão por camadas, bloqueio de autorremuneração, reservas, liquidação idempotente, recuperação e extrato privado. O painel mostra tokens, renovação, contribuição e extras. Ver docs/CREDIT_PLAN.md.

Suíte final executada: **43 passed in 101.06s (0:01:41)**, comando `.venv/Scripts/python -m pytest -q --basetemp=runtime/pytest-credits-final`. Inclui 13 testes de carteira, 14 anteriores e 16 integrações com inferência real, HTTP/HTTPS e contas distintas. Comparação incremental: 8 passos, erro máximo 0.0. Reciprocidade: {'local_cost': 4, 'peer_reward': 2.0, 'reverse_reward': 2.0, 'private_audit': True}. Esgotamento: {'zero_balance_http': 402, 'output_clipped': True, 'extra_spent': 2}.

Verificados: fronteira 23:59:59/00:00 no fuso, não acúmulo, persistência, recuo de relógio sem reabrir dias, mudança de política sem nova emissão no mesmo dia, reservas atravessando meia-noite, gasto diário antes de extras, sobreconsumo concorrente, arredondamento, múltiplos workers do mesmo dono, idempotência/replay conflitante, adulteração de saldo/eventos, histórico privado, falha/cancelamento sem reservas presas e saldo esgotado 402. O limite de saída é reduzido ao saldo disponível.

JavaScript da interface passou em `node --check`. A autorização para abrir http://127.0.0.1:8300 no navegador foi recusada; **a conferência visual da nova interface não foi executada** e não existe captura nova validada. Não reutilizar capturas antigas como evidência deste painel.

A demonstração anterior com duas contas executou contribuição real em ambas as direções: local-user consumiu 17 e ganhou 4,5; peer-user consumiu 9 e ganhou 8,5. Carteiras e cadeia íntegras, sem dinheiro ou créditos inventados. A demonstração foi reiniciada com a revisão final em localhost:8300; consultar runtime/simulation/latest.json para a pasta e report.json desta execução.

Limites: continua sendo um coordenador/banco local, identidades autorizadas e tiny-gpt2. Rede pública, consenso, remuneração por ociosidade, privacidade contra workers hostis, fila justa distribuída e qualidade de um assistente de programação não foram implementados. O valor diário não garante horas de uso. Não foram realizados testes físicos entre máquinas nem uma espera real até a meia-noite: fronteira de horário testada com relógio injetado no motor contábil, explicitamente sem simular a inferência.

## Evolução para perfil de programação e rede autorizada — 02/11/2026

Implementados: adaptador Qwen2 (RoPE/GQA/KV), Qwen2.5-Coder-0.5B-Instruct na revisão ea3f2471cf1b1f0db85067f1ef93848e38e88c25, template de chat, alternância por conta com prefill de até 32 tokens, oito sessões/uma por conta e limpeza idempotente inclusive antes do primeiro token. GPT-2 permanece para regressões leves.

Descoberta gossip com Ed25519, cache, expiração, lista autorizada e múltiplos contatos. Comandos e recibos individuais vinculados a corpo/rota/timestamp e requisição/resultado no modo P2P autorizado. Assinaturas não provam correção neural nem validam créditos por consenso. A descoberta continuou trocando anúncios novos entre workers com o contato inicial desligado, conforme demonstração registrada em runtime/simulation/20261102-170003-0159f1/report.json.

Arquivos privados por conta, limite de tamanho/quantidade, recusa de travessia/links, revisão/diff e verificação sintática Python. Executor unittest opt-in com Docker local aprovado por SHA-256, sem rede, projeto somente leitura, usuário 65534, capacidades removidas e limites de CPU/RAM/PIDs/tempo/saída. Editor/console/participantes adicionados à interface; avaliação visual ainda pendente por recusa anterior do navegador, sem nova tentativa de contornar a recusa.

Suítes executadas nesta etapa: 45 testes em 112,50 s; 65 em 138,81 s; suíte final **71 passed in 183.03s (0:03:03)**. Comando final: `.venv/Scripts/python -m pytest -q --basetemp=runtime/pytest-functional-final`, com HF_HOME=data/hf e MESH_TEST_IMAGE=sha256:db20d8506e2f15b6db39b40b6015ca46bae855dec6dd326d462cfe79ae972893. Inclui testes Docker reais de usuário sem privilégios, montagem somente leitura, falta de socket Docker/rede, tempo limite e limite de saída. Regressão Qwen unitária usa pesos sintéticos e não é apresentada como prova de qualidade. A prova do checkpoint real é separada.

Checkpoint Qwen real já validado entre dois workers: oito passos com erro máximo dos logits 0,0. Gerou `def add(a, b): return a + b`, com três casos aritméticos aprovados. Isso é uma tarefa pequena, sem promessa de equivalência ao Codex ou qualidade ampla.

A demonstração combinada seguinte chegou aos testes do projeto, mas falhou por timeout do Docker (saída: tempo limite, 21,187 s incluindo limpeza). O verificador foi ajustado para liberar o modelo de referência antes da geração/testes. Na tentativa posterior, o Docker passou a retornar HTTP 500 em /version e /images/.../json. Não foi reiniciado porque serve outros projetos. O lançador agora limita a consulta opcional ao Docker a cinco segundos e continua com testes em container explicitamente desativados quando indisponível. Validação numérica, código, arquivos e sintaxe continuam possíveis; pular o executor não é declarar sua execução aprovada.

O usuário confirmou que não há segundo computador disponível. Validação física/GPU/escala continua bloqueada por hardware ausente. Consenso público, anti-Sybil/conluio, prova neural, privacidade contra peers hostis, DHT/NAT, alocação automática/recuperação remota e um agente completo de programação ainda não foram implementados. Leia docs/FUNCTIONAL_STATUS.md para o escopo exato e run-coder.ps1 para iniciar o perfil.

## Fechamento: perfil persistente e recuperação de transporte — 02/11/2026

A comparação de checkpoint real com assinaturas terminou em runtime/simulation/20261102-173249-48d00b/report.json: oito passos, erro máximo 0,0, geração de add(a,b) com três casos, arquivos/sintaxe, 62 recibos criptográficos verificados, recusa de um worker se passando pelo solicitante e troca de anúncios novos com contato inicial desligado. Container foi explicitamente skipped porque Docker não estava habilitado/saudável. Não tratar esse skipped como execução aprovada.

O perfil normal foi separado da simulação: tools/run_network.py + run-coder.ps1, estado fixo em runtime/network, sem cópias de GB e sem carregar referência completa a cada início. Foi verificado um reinício real preservando daily_remaining, extra_remaining, earned_total, spent_total e dois arquivos; evidência em runtime/network/persistence-evidence.json.

Um primeiro smoke do perfil persistente gerou/salvou código, mas encontrou RemoteProtocolError durante a segunda conta. Foi implementado cache da resposta do último passo por sessão, hash de requisição, recusa de repetição conflitante e uma repetição de transporte no coordenador. Uma resposta perdida depois da inferência real não executa nem cobra o passo novamente. Cache é limitado a uma resposta por sessão (máximo oito), com liberação/TTL da sessão. Não é garantia de entrega diante de falha permanente.

Suíte final atualizada: **74 passed, 2 skipped in 248.15s (0:04:08)**, comando `.venv/Scripts/python -m pytest -q --basetemp=runtime/pytest-retry-final`, HF_HOME=data/hf e MESH_TEST_IMAGE ausente devido ao Docker indisponível. Os dois skipped são os testes Docker; os mesmos testes haviam sido executados com sucesso na rodada anterior de 71. Inclui perda de resposta injetada após cálculo neural real em HTTP/HTTPS, sem débito duplicado, conflito de passo, prefill Qwen em fatias e caminhos de arquivos. Checagens direcionadas anteriores: 13 testes de workspace e regressão Qwen de prefill fragmentado aprovadas.

Smoke posterior da aplicação persistente: **application_smoke_passed**, runtime/network/smoke-evidence.json. Modelo Qwen gerou `def add(a, b): return a + b`, validado em três casos; arquivos privados e sintaxe passaram; contribuição inversa criou extras; 75 recibos assinados verificados; auditoria íntegra e reservas zeradas. O saldo registrado nessa execução foi 19.864 tokens diários + 31,5 extras para local-user, após as tarefas reais de validação. Não são créditos fictícios nem valores fixos do produto. Docker explicitamente skipped. Verificação visual da interface continua pendente pela recusa anterior do navegador.

A aplicação está em http://127.0.0.1:8400; token em runtime/network/config.json. Não há um segundo computador físico disponível, conforme resposta do usuário. A visão pública ainda exige consenso, anti-Sybil/conluio, prova de execução, privacidade em workers hostis, NAT/DHT, escalonamento global e agente completo de ferramentas. O código desta etapa não deve ser apresentado como “100%” da rede pública.

## Agente inicial e interface de modelos — 02/11/2026

Suíte executada: `.venv/Scripts/python -m pytest -q --basetemp=runtime/pytest-agent-final`, HF_HOME=data/hf, MESH_TEST_IMAGE ausente: **79 passed, 2 skipped in 277.48s**. Os dois skipped são Docker e não são apresentados como testes executados nesta rodada. Inclui cinco novos testes do executor: correção após sintaxe inválida, histórico/isolamento de contas, aprovação local/uso único/mudança de projeto, processo real e timeout, interrupção/expiração após reinício. As respostas programadas desses testes verificam a orquestração, não inteligência de um checkpoint.

Depois foram adicionados dois testes de API: catálogo real, autenticação, modelo ausente, corpos JSON inválidos, histórico privado e comando no host desativado. Rodada direcionada `.venv/Scripts/python -m pytest tests/test_agent.py tests/test_agent_api.py -q`: **7 passed in 17.29s**. JavaScript da interface passou em `node --check`; conferência visual não foi executada após a recusa anterior do navegador. Não contornar a recusa com outro endereço.

Primeira avaliação do agente real: Qwen0.5B escolheu run_tests com argumento summary inexistente e alegação de teste passado sem resultado. A validação recusou a ação e nenhum sucesso foi registrado. A tarefa foi cancelada antes de consumir dez etapas. Ajuste posterior separou instrução system e tarefa, fornecendo exemplos de ações válidas. Evidência dessa tentativa em runtime/network/agent-evidence.json; não é resultado aprovado.

A segunda avaliação real (runtime/network/agent-smoke-protocol-failure.json) criou arquivo corretamente, mas repetiu envelopes/JSON inválidos. Foi cancelada explicitamente; não é tarefa autônoma concluída. O histórico foi reformulado para não apresentar o envelope action/result como exemplo de resposta, e write_file passou a devolver verificação automática real. Regressões direcionadas após essas alterações: **7 passed in 16.98s**.

A consulta de imagem Docker voltou a responder, mas a execução continuou falhando. Rodada explícita com MESH_TEST_IMAGE do perfil: `.venv/Scripts/python -m pytest tests/test_sandbox.py -q --basetemp=runtime/pytest-sandbox-agent`: **2 failed in 46.13s**, ambos por execução que excedeu o tempo; o teste de limite de saída não chegou a observar saída truncada porque também não executou a tempo. Não declarar isolamento do ambiente atual validado. O lançador foi corrigido: consultar a imagem não basta; tools/docker_probe.py agora tenta executar um container restrito de prova, com limite de cinco segundos e limpeza de seu próprio container. Quando falha, não imprime imagem e o executor fica desativado. O novo probe foi executado e não habilitou Docker. Não reiniciar Docker de outros projetos automaticamente.

Resultado final da avaliação do agente real — 02/11/2026: tools/smoke_agent.py excedeu o limite de 420 segundos e solicitou cancelamento. O checkpoint criou o arquivo correto e a verificação automática de sintaxe passou, mas voltou a copiar exemplos/gerar ações inválidas e não concluiu a tarefa autonomamente. Evidência: runtime/network/agent-smoke-evidence.json; status de avaliação timeout_cancelled. Isto é falha de avaliação, não um teste aprovado. O modo permanece experimental. Não foi demonstrada equivalência ao Codex, nem instalado um modelo maior. Limitações concretas: modelo pequeno sem confiabilidade de ferramentas, RAM disponível insuficiente para checkpoints gigantes FP32/preparação que carrega tudo e ausência de segundo computador físico. Docker local também excedeu tempo de execução. O objetivo completo solicitado não foi atingido nesta sessão; a base distribuída, interface e executor foram ampliados e a continuidade está documentada.

Checagem direcionada final do código após ajustes de histórico/verificação/catálogo: **7 passed in 42.24s**, tests/test_agent.py e tests/test_agent_api.py. py_compile dos módulos alterados e node --check passaram. Não houve inspeção visual autorizada da interface nova.
