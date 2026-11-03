# Como continuar

## Retomar a demonstração atual

Execute python -m mesh slow-run --job runtime/slow-480b-proof --max-tiles 1 usando o ambiente existente para avançar mais um bloco real do 480B. Para repetir os dois blocos com dois processos, preserve a referência no ponto de duas confirmações e use tools/verify_real_tiles.py. Novas instalações devem seguir docs/MODO-LENTO.md. Para validação numérica MoE, gere a referência sintética isolada com tools/make_moe_reference.py; o ambiente principal mantém Transformers 4.44.2.

Próximas provas: portar o protocolo de blocos para firmware/app, medir RAM total em aparelho físico, validar TLS e retomada após perda de energia, e testar a execução integral com computadores que caibam no plano de 72B/480B. Ainda faltam integração de trabalhos lentos ao chat/créditos e medições de recuperação/latência em escala.

1. Leia AGENTS.md, ARCHITECTURE.md, PROGRESS.md e TEST_RESULTS.md.
2. Abra D:/Projetos/RedeInferencia. Se os serviços não estiverem ativos, execute run-local.ps1.
3. Abra http://127.0.0.1:8000; token está em runtime/config.json (não publicar esse arquivo).
4. Execute testes com HF_HOME apontando para data/hf e `.venv/Scripts/python -m pytest -q --basetemp=runtime/pytest`.
5. Para concluir a etapa física, obter endereço/acesso autorizado de uma segunda máquina e seguir DEPLOY_LAN.md. Não declarar essa etapa concluída antes do teste real.
6. Executar o verificador remoto `tools/verify_remote.py` no coordenador para comparar oito passos com o checkpoint local e obter métricas do chat. Salvar resultado e atualizar TEST_RESULTS.md.
7. Para melhorar respostas, adicionar adaptador de modelo pequeno instruído. tiny-gpt2 valida distribuição, não utilidade de conversação.

Estado de serviços desta sessão: lançador local iniciado com dois workers CPU em 8100/8101 e coordenador em 8000. Pode encerrar ao fim da sessão de execução; run-local.ps1 reabre tudo. Antes de reiniciar, verifique se a página ainda responde para evitar conflito de portas.

Não modificar outros projetos de D:/Projetos. Não reutilizar segredos do ambiente de testes em implantação externa. Não remover verificação TLS para fazer a LAN funcionar.

## Prioridade atual: computadores

O usuário corrigiu a referência ao celular: era de outro chat. Não desenvolver worker móvel agora. O ambiente com dois hosts lógicos está validado e pode ser repetido com `.venv/Scripts/python tools/simulate_hosts.py --serve`. Consultar SIMULATION.md. Para teste físico, obter um segundo computador e seguir DEPLOY_LAN.md.

## Estrutura base do repositório

Preparada publicação em ArthurCarlosF/IA_COLABORATIVA, com empacotamento Python, rotina de CI, premissas e limites de segurança. Dados de runtime, pesos, ambiente virtual e credenciais ficam ignorados. A execução de CI no GitHub só pode ser confirmada após a publicação e consulta ao resultado.

## Próxima sessão: carteira e política diária

Leia docs/CREDIT_PLAN.md. Funcionalidade implementada e validada com 43 testes; o painel novo tem somente checagem sintática, porque o navegador recusou acesso à demonstração. Não tentar contornar essa recusa. O usuário pode abrir localhost:8300 e conferir manualmente.

Iniciar demonstração: `.venv/Scripts/python tools/simulate_hosts.py --credits-demo --port 8300 --serve`. Caminho de configuração e relatório em runtime/simulation/latest.json. user_token autentica local-user; accounts.peer-user autentica peer-user. Não publicar esses tokens nem copiar config para o Git. A versão antiga em localhost:8000/8200, se ainda ativa, pode não conter o painel atualizado.

Continuar com avaliação visual autorizada, fila justa, identidade pública/consenso e modelo pequeno instruído. Não ativar remuneração por memória anunciada nem cadastro público sem verificação contra fraude. Não vender créditos: decisão explícita do usuário.

Ao continuar, leia também LEIA-ME-PRIMEIRO.txt e mantenha-o atualizado na mesma alteração de qualquer mudança relevante, conforme AGENTS.md.

## Continuidade do perfil de programação e P2P autorizado

1. Ler LEIA-ME-PRIMEIRO.txt e docs/FUNCTIONAL_STATUS.md. Preservar a distinção entre descoberta P2P e consenso contábil, e entre assinatura de recibo e prova de execução neural.
2. Fonte Qwen preparada em data/qwen-coder; revisão ea3f2471cf1b1f0db85067f1ef93848e38e88c25. Iniciar com run-coder.ps1, porta 8400. O lançador cria uma pasta de simulação; runtime/simulation/latest.json indica a pasta e o config.json com tokens locais (não publicar).
3. A suíte final de backend passou em 71 testes. Para repetir os testes Docker, primeiro verificar que o Docker do operador está saudável; ele passou a responder 500 após a execução registrada. Não reiniciar o serviço compartilhado sem avaliar o impacto e obter autorização se necessário. Docker indisponível desativa somente o executor de testes, com motivo explícito.
4. Conferir report.json da última demonstração: numerical, coding_task, workspace_syntax, workspace_tests (pode estar skipped), credits.verified_individual_receipts, discovery e individual_auth. Uma demonstração sem report.json ou com workspace_tests.skipped não prova execução end-to-end do container.
5. A nova interface teve validação sintática, sem conferência visual autorizada. Não abrir outra origem/navegador para contornar a recusa anterior. O usuário pode avaliar manualmente.
6. Validar dois PCs físicos quando houver um segundo host autorizado. O usuário informou que não há um disponível agora; manter esse item pendente, sem simular conclusão.
7. Próxima decisão técnica: protocolo de consenso de créditos e identidade/anti-Sybil para rede pública. Não implementar um registro de assinaturas e chamá-lo de blockchain segura. Definir ameaça, quorum, finalização, recuperação e testes de partição antes de abrir acesso anônimo.
8. Depois: obtenção seletiva de pesos sem carregar modelo completo offline, distribuição automática conforme recursos, NAT/relay, recuperação de KV, benchmarks maiores, ferramentas iterativas e histórico durável.
9. Manter TXT principal atualizado em qualquer alteração relevante e registrar testes exatamente como executados.

## Ponto atual para retomar

- A aplicação normal agora é persistente: run-coder.ps1 → tools/run_network.py → runtime/network/config.json. A simulação continua separada. Saldos e arquivos foram verificados em reinício real. Não orientar usuários a usar uma pasta nova de simulação como carteira durável.
- Smoke final aprovado: runtime/network/smoke-evidence.json, 75 recibos e código real; comparação numérica anterior assinada: runtime/simulation/20261102-173249-48d00b/report.json, erro 0,0.
- Backend final: 74 passed, 2 skipped; Docker isolado havia passado na rodada de 71 e está indisponível agora com erro 500. Não reiniciar Docker compartilhado sem tratar o impacto com o usuário.
- Corrigido RemoteProtocolError transitório com passo idempotente e uma repetição RPC. Não remover essa proteção; recibos/contas não podem duplicar por perda de resposta.
- Atualizar TXT principal e docs/FUNCTIONAL_STATUS.md a cada avanço. Próximas prioridades: validação visual autorizada, segundo PC físico quando disponível, consenso/identidade pública e benchmarks reais maiores. Não afirmar equivalência ao Codex a partir de uma função simples.

## Continuidade após agente inicial — 02/11/2026

1. Iniciar run-coder.ps1; dados persistem em runtime/network. Usar token local desse perfil. Modo Agente cria tarefas e registra eventos. tools/smoke_agent.py valida modelo real; não usar testes com respostas programadas como prova da inteligência.
2. Ampliar avaliação de tarefas, com correção de bugs/múltiplos arquivos/testes reais. Um sucesso simples não estabelece qualidade geral. Instalar checkpoints maiores só após orçamento real de memória e benchmark.
3. Implementar preparação progressiva/quantização e perfis/seleção de clusters reais. Hoje preparar carrega todo o modelo FP32; 32B FP32 requer cerca de 119 GiB só de pesos. O modelo atual não equivale ao Codex.
4. Histórico persistido não inclui retomada automática: após reinício fica interrompido. Acrescentar retomada explícita com revalidação de arquivos e nova aprovação, compactação recuperável e diffs transacionais.
5. Comandos: opt-in -AllowHostCommands, aprovação por comando, somente operador local. Ampliar isolamento antes de reduzir aprovações. Git, navegador/desktop, importação de projetos grandes e multimodalidade continuam pendentes.
6. Dois computadores físicos/GPU/escala exigem hardware não disponível nesta sessão. Não declarar testes físicos aprovados. Consenso público, anti-Sybil, prova neural, privacidade hostil e NAT/DHT continuam pendentes.
7. Validação visual da interface continua pendente após recusa anterior do navegador; sintaxe JavaScript pode ser verificada sem contornar essa recusa.

Impedimento de qualidade observado: Qwen0,5B repete exemplos e gera ações malformadas mesmo após instrução system e ajustes do histórico. O executor recusa essas ações; não relaxar aprovação/validação para mascarar o problema. Próxima evolução exige avaliar um checkpoint de código mais capaz em recursos suficientes, preservar a comparação numérica e medir tarefas reais. O seletor atual não troca checkpoints pelo navegador.

## Continuidade após troca parcial

- Usar seletor na aplicação iniciada por run-coder.ps1. Modelos ausentes são preparação, não inferência disponível. A troca exige terminar agentes/chats e é operação do administrador local.
- Para distribuir modelos maiores, usar plan-model --model-profile coder-32b --parts N --root PASTA; entregar só assignment-i.json ao participante i e configuração de worker sem credenciais de usuários/coordenador. Definir exatamente os N endpoints/certificados/identidades na rede privada. Seguir MODELOS.md.
- O impedimento “preparação exige modelo inteiro em RAM” foi removido no novo fluxo. O comando prepare legado não deve ser utilizado para grandes checkpoints. Continuam pendentes recursos físicos agregados para efetivamente executar 32B/72B e comparação numérica em hardware real.
- Ampliar validação de troca em múltiplos computadores, queda durante commit, recuperação de rede e persistência. Hashes locais/HTTPS não provam inferência nem fornecem privacidade contra peers hostis.
- Implementar quantização/precisão reduzida, teste GPU real e contexto/KV ajustável por orçamento; avaliar modelos maiores em tarefas representativas. Agente continua experimental e não há equivalência de qualidade ao Codex demonstrada.
