# Estado funcional e critérios de conclusão

Atualizado em 02/11/2026. Não existe certificação de “100%” de uma rede pública neste repositório.

## Entregue nesta etapa

1. Modelo Qwen2.5-Coder-0.5B-Instruct, revisão fixa ea3f2471cf1b1f0db85067f1ef93848e38e88c25, com 24 camadas divididas entre dois workers. GPT-2 continua como regressão leve.
2. RoPE, GQA e cache incremental Qwen por partição. Prompt de chat usa o template do tokenizer. Contexto operacional limitado a 512 tokens e resposta a 128.
3. Alternância de execução por conta, até oito sessões e uma tarefa por conta. Prefill em fatias de até 32 tokens reduz exclusividade de entradas grandes. Saldo não compra prioridade. É justiça local ao solicitante/coordenador, não um escalonador global da rede.
4. Descoberta por gossip com contatos assinados Ed25519, validade curta, cache e múltiplos contatos iniciais. Endereços e identidades precisam estar previamente autorizados. Não é DHT pública nem consenso.
5. No modo P2P autorizado, registro e comandos internos têm assinaturas individuais vinculadas ao corpo, rota e timestamp. Respostas de execução têm recibos assinados vinculados à requisição e ao resultado, arquivados com a contabilidade. Identidade comprova autoria, não correção do cálculo.
6. Arquivos privados por conta, edição com revisão otimista e diff. Travessia de diretórios e links recusados; limites de arquivos/tamanho. Verificação sintática Python e testes unittest em Docker opt-in, com imagem local aprovada por SHA-256.
7. Container de testes sem rede, projeto somente leitura, usuário sem privilégios, capacidades removidas e limites de CPU/RAM/processos/tempo/saída. Não há shell arbitrário no host.
8. Interface com arquivos, editor, diff/console de testes, participantes e saldo. JavaScript validado sintaticamente; avaliação visual nova ainda pendente por recusa anterior da autorização do navegador.

## Evidência executada

- A rodada com Docker passou em 71 testes em 183,03 segundos; a última rodada passou em 74 testes e pulou 2 testes Docker em 248,15 segundos, incluindo limites reais do Docker, concorrência, assinaturas, descoberta e regressão de cache Qwen com pesos sintéticos. A prova de checkpoint real é separada, descrita a seguir.
- Checkpoint Qwen real: oito passos distribuídos numericamente equivalentes ao modelo completo, erro máximo 0,0 na execução registrada.
- Modelo real gerou `def add(a, b): return a + b`, validado para (2,3), (-4,1) e (0,0). É uma tarefa pequena; não é um benchmark amplo de programação nem equivalência ao Codex.
- Descoberta manteve troca de anúncios novos entre workers quando o contato inicial/coordenador foi desligado. A inferência aguardou a volta de um solicitante; a contabilidade continua local.
- A demonstração com assinaturas verificou 62 recibos individuais, erro numérico 0,0, código salvo e sintaxe válida; executor Docker explicitamente pulado. O perfil persistente posterior passou no smoke real com 75 recibos, contribuição nas duas direções e arquivos privados; reinício preservou saldos e arquivos. Detalhes em TEST_RESULTS.md.

## O que impede declarar a visão completa concluída

- O usuário confirmou que não há um segundo computador disponível. Testes físicos entre hosts, GPU, condições reais de rede e escala permanecem bloqueados por essa ausência.
- Créditos continuam em SQLite sob um coordenador. Ainda não há consenso de transações entre solicitantes independentes, prevenção global de gasto duplicado ou recuperação financeira por quorum.
- Participação pública exige identidade resistente a Sybil/conluio, prova/auditoria de execução e proteção de dados contra workers hostis. Assinaturas e modelos detectores não eliminam esses problemas.
- DHT pública, NAT traversal/relays, alocação automática e recuperação de KV em outro worker ainda não estão implementados.
- Remuneração de disponibilidade ociosa ainda exige prova de recursos úteis e política contra emissão indevida.
- O editor e o executor de testes não constituem um agente completo que planeja projetos, usa ferramentas iterativamente e corrige todos os erros sozinho. Histórico de conversas durável e ferramentas adicionais seguem no roadmap.
- Preparar checkpoints ainda carrega o modelo completo offline. Para modelos que não cabem em nenhuma máquina preparadora, será necessário particionamento/obtenção de pesos em streaming.
- Eficiência entre computadores e qualidade abrangente de programação precisam de benchmarks maiores. Não garantir velocidade, privacidade absoluta ou disponibilidade contínua.

## Como executar o perfil de código

No Windows, após instalar requirements-dev.txt, executar `run-coder.ps1`. O script prepara o checkpoint se necessário e inicia o ambiente em localhost:8400. Para ativar testes isolados, instalar Docker e preparar uma imagem oficial com `docker pull python:3.11-slim`; o script usa o ID SHA-256 encontrado localmente. Não baixa imagem automaticamente por solicitação de usuário da interface.

Segredos ficam em runtime/simulation/<execução>/config.json. Nunca publicá-los. O modo gerado é uma demonstração com duas contas e identidades locais; não é configuração pública de produção. Leia também SECURITY.md e DEPLOY_LAN.md.

## Ocorrência no ambiente de testes

Após a suíte de 71 testes ter passado, a demonstração combinada atingiu timeout no executor Docker. Em seguida o serviço Docker local respondeu HTTP 500; ele não foi reiniciado por ser compartilhado com outros projetos. O lançador permite continuar sem executor e registra a etapa como skipped. Esse é um impedimento concreto à revalidação end-to-end do container nesta sessão, sem invalidar os testes isolados anteriores, nem permitir alegar que a demonstração combinada passou.

O lançador run-coder.ps1 reutiliza os arquivos locais de cada partição para evitar copiar GB a cada início; processos, caches e diretórios de trabalho continuam separados. A simulação padrão sem --reuse-weights preserva a opção de pastas de pesos copiadas. O prazo de inicialização do perfil de código é maior para acomodar carregamento frio; não é uma garantia de tempo de resposta.

## Resultado final da aplicação persistente

O perfil normal está separado dos diagnósticos. runtime/network/config.json conserva identidades, contas e tokens; o banco e os arquivos ficam nos diretórios persistentes desse perfil. Não há um modelo de referência completo carregado no caminho normal da aplicação.

O smoke real passou com código Python gerado e três casos, arquivos privados, sintaxe, créditos e verificação criptográfica de 75 recibos. A integridade da carteira passou. Saldos e dois arquivos foram comparados antes/depois de um reinício e permaneceram iguais.

Uma falha RemoteProtocolError observada durante o primeiro smoke motivou resultado idempotente no worker e uma repetição limitada no RPC. Testes injetam perda da resposta depois de execução real e confirmam um único cálculo e débito. Há somente cache do último passo por sessão ativa, não histórico ilimitado de respostas.

Docker permanece indisponível neste ambiente (erro 500); executor está desativado e a etapa é registrada skipped. As verificações reais do isolamento haviam passado na rodada anterior. Não anunciar o fluxo combinado de container como aprovado.

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
