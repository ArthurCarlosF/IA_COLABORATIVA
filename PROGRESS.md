# Progresso — 02/11/2026

Projeto criado em D:/Projetos/RedeInferencia. Ambiente Python 3.11 em .venv com PyTorch 2.8.0 e Transformers 4.44.2. Dependências instaladas e checkpoint baixado com acesso de rede autorizado.

Implementados coordenador, dois workers reais de camadas, KV cache, chat web com SSE, telemetria e créditos SQLite. Preparado tiny-gpt2 na revisão fixa 5f91d94bd9cd7190a9f3216ff93cd1dd95f2c7be2. Workers carregam somente sua partição.

Primeira execução: 16 testes passaram em 48,87 s. Comparação de 8 passos: erro máximo dos logits 0,0; tokens idênticos à execução local. Chat API: 12 tokens em 2,445 s. Falha/reinício e liberação de cache passaram.

Validação manual automatizada no Chrome: dois workers online, pergunta "What is artificial intelligence?", 32 tokens gerados, 4,60 tokens/s e zero falhas. Texto repetitivo "stairs" reflete a baixa qualidade esperada do checkpoint de validação. Captura em runtime/chat-validado.png. Nenhuma resposta foi simulada.

Depois dessa validação foram adicionados planejamento offline de memória e orçamento de KV; resultados da reexecução estão em TEST_RESULTS.md.

Validação entre computadores físicos permanece pendente de um segundo host autorizado. O foco atual é a rede de computadores; compatibilidade móvel está adiada. Procedimento em DEPLOY_LAN.md.

Versão final: 26 testes passaram em 100,00 s, sem avisos. HTTP e HTTPS, logits equivalentes, créditos, cache, falha/reinício, cancelamento e concorrência verificados. Corrigida falha encontrada pelo teste de cancelamento. Interface final: 32 tokens, 3,26 tokens/s, zero falhas. Serviços locais reiniciados com código final.

## Dois hosts lógicos no mesmo computador — 02/11/2026

Executado `tools/simulate_hosts.py --serve`. Coordenador HTTP apenas em loopback 127.0.0.1:8200; workers reais pc-a em HTTPS 127.0.0.2:8201 e pc-b em HTTPS 127.0.0.3:8202. Processos de serviço inicialmente observados: {'coordinator': 17964, 'pc-a': 17144, 'pc-b': 27452}. Pastas separadas; cada worker recebeu somente sua partição. Há um único sistema operacional/hardware; diretórios separados não constituem isolamento de permissões.

Certificado não confiável foi rejeitado. O worker pc-b foi encerrado; a geração falhou explicitamente. Após reinício, oito passos tiveram erro máximo de logits 0.0 comparados ao modelo local. Chat gerou 12 tokens em 2.500 s. Livro íntegro com 25 lançamentos, incluindo um estágio concluído antes da falha induzida. A falha vista no painel é a do teste intencional.

Evidência desta execução: D:/Projetos/RedeInferencia/runtime/simulation/20261102-150404-3782b3/report.json. O script executou de fato inicialização, comunicação TLS, desligamento/reinício e verificador numérico. A suíte anterior de 26 testes não foi repetida nesta alteração, que adiciona somente um lançador de validação; o motor neural não foi modificado.

Prioridade atual: rede de computadores. Compatibilidade móvel adiada.

## Estrutura base do repositório

Preparada publicação em ArthurCarlosF/IA_COLABORATIVA, com empacotamento Python, rotina de CI, premissas e limites de segurança. Dados de runtime, pesos, ambiente virtual e credenciais ficam ignorados. A execução de CI no GitHub só pode ser confirmada após a publicação e consulta ao resultado.

## Validação da estrutura base para o GitHub — 02/11/2026

Instalação editável do pacote ia-colaborativa 0.1.0 concluída com sucesso (`pip install -e . --no-deps`); comando `ia-colaborativa --help` executado. Suíte local repetida: **26 passed in 106.03s (0:01:46)**, com HTTP/HTTPS e inferência real. Rotina de GitHub Actions adicionada; o resultado remoto não foi verificado nesta validação local. Revisão de publicação: 31 arquivos; pesos, runtime, chaves e credenciais locais excluídos.

## Franquia diária e créditos por contribuição — 02/11/2026

Implementados: carteiras por conta, franquia inicial configurável de 20.000 tokens/dia à meia-noite de America/Sao_Paulo, extras sem expiração, divisão por camadas, bloqueio de autorremuneração, reservas, liquidação idempotente, recuperação e extrato privado. O painel mostra tokens, renovação, contribuição e extras. Ver docs/CREDIT_PLAN.md.

Suíte final executada: **43 passed in 101.06s (0:01:41)**, comando `.venv/Scripts/python -m pytest -q --basetemp=runtime/pytest-credits-final`. Inclui 13 testes de carteira, 14 anteriores e 16 integrações com inferência real, HTTP/HTTPS e contas distintas. Comparação incremental: 8 passos, erro máximo 0.0. Reciprocidade: {'local_cost': 4, 'peer_reward': 2.0, 'reverse_reward': 2.0, 'private_audit': True}. Esgotamento: {'zero_balance_http': 402, 'output_clipped': True, 'extra_spent': 2}.

Verificados: fronteira 23:59:59/00:00 no fuso, não acúmulo, persistência, recuo de relógio sem reabrir dias, mudança de política sem nova emissão no mesmo dia, reservas atravessando meia-noite, gasto diário antes de extras, sobreconsumo concorrente, arredondamento, múltiplos workers do mesmo dono, idempotência/replay conflitante, adulteração de saldo/eventos, histórico privado, falha/cancelamento sem reservas presas e saldo esgotado 402. O limite de saída é reduzido ao saldo disponível.

JavaScript da interface passou em `node --check`. A autorização para abrir http://127.0.0.1:8300 no navegador foi recusada; **a conferência visual da nova interface não foi executada** e não existe captura nova validada. Não reutilizar capturas antigas como evidência deste painel.

A demonstração anterior com duas contas executou contribuição real em ambas as direções: local-user consumiu 17 e ganhou 4,5; peer-user consumiu 9 e ganhou 8,5. Carteiras e cadeia íntegras, sem dinheiro ou créditos inventados. A demonstração foi reiniciada com a revisão final em localhost:8300; consultar runtime/simulation/latest.json para a pasta e report.json desta execução.

Limites: continua sendo um coordenador/banco local, identidades autorizadas e tiny-gpt2. Rede pública, consenso, remuneração por ociosidade, privacidade contra workers hostis, fila justa distribuída e qualidade de um assistente de programação não foram implementados. O valor diário não garante horas de uso. Não foram realizados testes físicos entre máquinas nem uma espera real até a meia-noite: fronteira de horário testada com relógio injetado no motor contábil, explicitamente sem simular a inferência.

## Apresentação para quem baixar — 02/11/2026

Criado LEIA-ME-PRIMEIRO.txt na raiz com visão, princípios, impacto pretendido, funcionamento, créditos, estado real, validação e próximos desafios. README destaca o arquivo. AGENTS.md exige sua revisão e atualização em toda alteração relevante. Verificação documental executada; não foi necessário repetir testes de código nesta alteração de documentação.

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

## Agente de projeto e seletor honesto — 02/11/2026

mesh/agent.py adiciona ciclo de até dez ações, histórico SQLite privado por conta, arquivos/busca/diff, verificadores Python/JSON/estrutura HTML, unittest opcional e cancelamento. A inferência de cada ação usa o mesmo pipeline distribuído, carteira, fila e recibos do chat. Instruções do protocolo usam papel system, separado da tarefa. Tokens de autenticação ficam só em memória, não no histórico do agente. Históricos recentes são limitados; contexto excedido é recusado, sem descartar silenciosamente a tarefa.

Comandos no host são desativados por padrão. O operador pode iniciar run-coder.ps1 -AllowHostCommands: cada comando exige decisão local individual, com argumentos/pasta e impressão das revisões do projeto; mudanças após a proposta invalidam a aprovação. Aprovação é de uso único e expira no reinício. O comando executa no computador do solicitante com seus direitos, sem isolamento; workers remotos só executam suas camadas. Há limites de duração/saída e cancelamento da árvore de processos. Não equivale a isolamento contra comandos hostis nem a controle geral do desktop.

A interface ganhou seletor de modelo abaixo da mensagem, modo Chat/Agente, histórico de tarefas e propostas de aprovação. API /api/models expõe somente o checkpoint carregado; pedidos com outro modelo são recusados. Existe um checkpoint por cluster, sem troca dinâmica/download pelo seletor. Qwen tem contexto limitado a 4096 tokens, saída até 512; GPT-2 mantém 512/128. Não foram instalados nem validados modelos gigantes. DEPENDENCIAS.md e MODELOS.md documentam instalação, limites e etapas necessárias. Não há equivalência de qualidade demonstrada com o Codex.

Salvar pelo agente também executa automaticamente o verificador disponível e devolve o resultado ao modelo. Isso verifica sintaxe/estrutura, não a correção funcional. Histórico de ações usa rótulos textuais para reduzir a cópia indevida do envelope pelo modelo pequeno.

Resultado final da avaliação do agente real — 02/11/2026: tools/smoke_agent.py excedeu o limite de 420 segundos e solicitou cancelamento. O checkpoint criou o arquivo correto e a verificação automática de sintaxe passou, mas voltou a copiar exemplos/gerar ações inválidas e não concluiu a tarefa autonomamente. Evidência: runtime/network/agent-smoke-evidence.json; status de avaliação timeout_cancelled. Isto é falha de avaliação, não um teste aprovado. O modo permanece experimental. Não foi demonstrada equivalência ao Codex, nem instalado um modelo maior. Limitações concretas: modelo pequeno sem confiabilidade de ferramentas, RAM disponível insuficiente para checkpoints gigantes FP32/preparação que carrega tudo e ausência de segundo computador físico. Docker local também excedeu tempo de execução. O objetivo completo solicitado não foi atingido nesta sessão; a base distribuída, interface e executor foram ampliados e a continuidade está documentada.

## Troca real e atribuição parcial — 02/11/2026

Implementados mesh/partition_store.py e mesh/model_control.py. Catálogo com revisões fixas, análise dos cabeçalhos safetensors por HTTP Range, divisão por orçamento e assignment por worker. O coordenador guarda somente configuração/tokenizer/índice de tensores; cada worker busca seus próprios intervalos em blocos de até 8 MiB, converte para FP32 em disco e valida hashes locais. Resposta que ignore Range e ofereça download completo é recusada sem ler o corpo. A construção Qwen usa dispositivo meta, atribuição de parâmetros mapeados e buffers RoPE locais; não instancia o modelo completo.

Troca em fases: bloquear novas sessões, exigir ausência de chat/agente ativo, consultar memória, planejar, preparar pesos locais, ativar partições e persistir seleção. Inferência inclui fingerprint da partição. Falhas de ativação restauram o modelo anterior; journal pendente bloqueia geração até recuperação explícita. Reinício usa a seleção e caches locais. Operação restrita ao operador local; um checkpoint ativo por rede. Créditos e arquivos não são recriados na troca. GPU compartilhada e RAM do mesmo host têm orçamento agrupado; GPU real ainda não validada.

CLI plan-model gera só metadados e assignment-N.json; worker --assignment baixa somente a atribuição. O lançador usa esse caminho em instalação nova e mantém compatibilidade com o perfil legado já existente. Configuração de worker não exige user_token: não distribuir tokens de usuários nem a chave privada do coordenador para participantes.

Validação real: Qwen2.5-Coder-0.5B-Instruct foi trocado por Qwen2.5-0.5B-Instruct sem reiniciar os processos; worker A ficou com camadas 0–11 e B com 12–23. Cada um buscou cerca de 601 MiB da origem, sem pesos das camadas do outro; cache contém 145/146 tensores respectivamente. O modelo novo respondeu “2+2 equals 4.” em sete tokens/6,65 s; carteira auditável e reservas liberadas. Evidências em runtime/network/model-switch-evidence.json e new-checkpoint-chat.json.

Planejamento real do Coder32B: 32 partições, 122,05 GiB FP32 previstos, mínimo 3,63 e máximo 6,53 GiB por partição antes de runtime/KV. Pasta runtime/plans/coder-32b ocupou 11,31 MiB e nenhum arquivo de pesos. Solicitar 32B nos dois workers atuais retornou falta de memória antes da preparação de pesos; partições locais e consumo permaneceram iguais, modelo anterior preservado. Evidência em runtime/network/large-model-preflight-evidence.json. Planejamento não é inferência grande executada. Perfil72B cadastrado; não foi executado nem validado em escala.

Ainda faltam computadores físicos, rede pública/consenso, avaliação de qualidade de modelos maiores, quantização, contexto ampliado e eficiência. O novo fluxo elimina a exigência de baixar/carregar todos os pesos numa máquina; não elimina a necessidade de capacidade agregada nem demonstra equivalência ao Codex. A preparação prepare antiga carrega o modelo completo e permanece somente para diagnósticos pequenos.

Reinício real após seleção: o Qwen geral escolhido foi preservado e os dois workers voltaram usando suas próprias partições mapeadas. Créditos/ganhos e reservas foram preservados; pedido com identificador do checkpoint antigo retornou 409. A pasta selecionada do coordenador continha zero arquivos de pesos. Evidência: runtime/network/model-persistence-evidence.json. Sem novo download integral nem carga de referência para reiniciar. JavaScript passou em node --check; inspeção visual segue não realizada.
