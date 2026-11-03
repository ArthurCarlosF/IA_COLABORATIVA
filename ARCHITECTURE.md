# Arquitetura

## Grafo interno e checkpoint de cálculo — 02/11/2026

O formato graph-f32-v1 descreve embeddings, atenção com KV local, roteadores, especialistas, linhas das projeções e cabeça de saída. O coordenador reúne ativações e escolhe especialistas pelo top-k. Os participantes armazenam somente suas atribuições. O orçamento padrão dos perfis grandes em grafo é 1B de parâmetros por worker; a instalação valida formas e intervalos dos tensores reais. Atenção ainda é uma unidade do grafo residente; o modo em trânsito divide suas projeções lineares em linhas e colunas.

O modo slow-run usa somente metadados e pequenos blocos de pesos. A posição da soma parcial e seu conteúdo são confirmados na mesma transação SQLite. KV e resultado de atenção são confirmados por operação/posição, permitindo repetir com segurança uma geração interrompida. O protocolo tile/matmul é separado do RPC de camadas: participantes de blocos não carregam modelo. A lista de executores é configurada pelo operador, e só há tentativa alternativa antes do commit da soma. Não há expiração por tempo no trabalho local. Veja docs/MODO-LENTO.md para limites e provas executadas.

O grafo em rede usa unidades operação-token efetivamente reportadas para repartir créditos, conservando a cobrança total e sem multiplicar novamente as unidades por tokens. Não é uma estimativa de FLOPs ou energia. O modo lento e os executores de microblocos ainda não liquidam créditos. A descoberta autorizada aceita até 8.192 identidades e mantém lotes de até 64 anúncios por troca; essa capacidade de configuração não é uma medição de escala física.

## Caminho real de um token

Navegador → POST /api/chat → tokenizer no coordenador → worker inicial (embedding de tokens + posições, camadas iniciais) → ativações float32 → worker final (camadas restantes, LayerNorm, LM head) → logits → argmax no coordenador → SSE no navegador.

A saída do worker inicial é entrada do seguinte. Não existem agentes, votação de respostas ou modelos independentes. A preparação offline carrega temporariamente o checkpoint completo para criar arquivos menores. Durante a inferência cada worker instancia **somente** seus próprios blocos e os componentes de fronteira necessários. O coordenador contém tokenizer, manifesto e hashes, sem camadas neurais.

## Partições e recursos

`mesh/model.py` prepara partes contíguas; `mesh/planner.py` aceita orçamento de pesos por computador. Primeiro worker recebe embeddings; último recebe normalização e cabeça. GPT-2 amarra embedding e cabeça no checkpoint original; a mesma matriz é copiada para as duas fronteiras quando estão em máquinas diferentes. Isso é replicação de um parâmetro necessário, não replicação do modelo completo.

`/internal/register` valida identidade permitida, URL fixa, hash dos pesos e intervalo exato de camadas. Heartbeat a cada 2 s; offline após 8 s. Configurações inválidas ou partições duplicadas são recusadas. Recursos de CPU/RAM/RSS e, quando disponível, VRAM aparecem na API e parcialmente na interface. Plano é fixado antes da execução; capacidade não é rebalanceada automaticamente.

## KV cache e geração

Cada sessão usa UUID; cada worker guarda K/V por bloco, posição e última atividade. Prefill processa o prompt inteiro; passos seguintes recebem somente o token novo. As posições são idênticas nas partições. Cache é liberado ao concluir, cancelar ou falhar; se a rede impedir a liberação, o TTL de 120 s remove a sessão. O orçamento configurável bloqueia expansão de cache antes da execução. Um orçamento de KV não é limite de RSS nem garante ausência de OOM no runtime.

Decodificação gulosa determinística; contexto 512 e batch 1. Um escalonador por conta alterna os passos de até oito sessões. Uma tarefa por conta é admitida; excesso recebe 429. O prefill usa fatias de até 32 tokens. Erros de rede encerram a geração explicitamente, preservam cobranças de trabalho concluído e tentam liberar todos os caches. Não há retry de passos nem continuação de KV perdido.

## Protocolo e segurança

FastAPI/Uvicorn + HTTPX; JSON/base64 little-endian nativo de float32/int64 nas máquinas suportadas (x86). Payload limitado a 4 MiB, 1 milhão de elementos e contexto de 512. Tipos, batch, vocabulário, comprimento, finitude e posição são validados. HMAC autentica o corpo com timestamp; HTTPS protege confidencialidade e respostas em LAN. Sem pickle na rede. Chave única de cluster implica confiança mútua entre workers. Autenticação do usuário é um token local único nesta versão.

Há descoberta gossip entre identidades previamente autorizadas. Não há descoberta pública/DHT, NAT traversal, consenso blockchain ou prova de correção contra workers hostis. As contas atuais são provisionadas pelo operador. Serviços vinculados a loopback por padrão; modo LAN exige certificados confiáveis. A cadeia contábil detecta edições internas, mas precisa de ancoragem externa para detectar reescrita integral/truncamento.

## Recibos de diagnóstico em token-layer

Por passo de cada worker: receipt = sessão:iteração:worker. Dupla entrada balanceada, user local com débito e worker com crédito, unidades token-layer, duração de execução e timestamp. SQLite serializa lançamentos e encadeia hashes. Na versão com carteira, somente um passo completo entre todas as partições gera recibos e liquidação. Um crash entre execução remota e persistência pode perder um lançamento: confirmação transacional distribuída fica no roadmap.

## Arquivos

- `mesh/model.py`: preparação e execução de camadas GPT-2.
- `mesh/worker.py`: cache, monitoramento, endpoints e heartbeat.
- `mesh/coordinator.py`: registro, validação, ordenação, tokenização e streaming.
- `mesh/protocol.py`: tensores e autenticação.
- `mesh/ledger.py`: livro auditável.
- `mesh/web.html`: interface sem dependências externas.
- `mesh/__main__.py`: CLI e restrições de implantação.
- `tests/`: testes unitários e integração com processos separados.

O coordenador atribui as partes na ordem dos workers da configuração e recusa registros de uma parte diferente da atribuída. Dois navegadores de chat compartilham esse mesmo pipeline: abrir abas não cria novos workers. O worker da versão inicial é um processo Python, não JavaScript no navegador.

## Ambiente de dois hosts lógicos

`tools/simulate_hosts.py` inicia três processos, usa endereços loopback diferentes para os workers, diretórios próprios com somente a partição designada, identidades distintas e TLS validado para RPC aos workers. O coordenador/chat continua HTTP estritamente em 127.0.0.1. Nenhuma configuração de firewall/interface nem confiança global de certificados é alterada. Isso valida fronteiras de processo e o protocolo de rede, mas não simula sistemas operacionais separados, limites de hardware, NICs, latência ou falhas de rede física.

## Carteiras, contas e franquia diária

`mesh/credits.py` compartilha a conexão SQLite com o livro de diagnóstico, usando transações BEGIN IMMEDIATE e lock reentrante. Tabelas credit_accounts, credit_days, credit_reservations e credit_events implementam a projeção dos saldos. Inteiros em milionésimos de token evitam perda de precisão no saldo por ponto flutuante; não há moeda nem dinheiro.

Cada conta autorizada recebe uma concessão única por data no fuso configurado. Não há acúmulo de dias offline. Datas já vistas não reabrem ao recuar o relógio. A concessão diária fica registrada; mudar o valor configurado não aumenta retroativamente o dia já concedido.

O coordenador é dono do mapeamento worker → proprietário; mensagens de registro não podem escolher o beneficiário. Tokens Bearer distintos são comparados por hash. /api/usage retorna somente a própria carteira. /api/credits expõe o extrato próprio e a contribuição do próprio dono em tarefas externas; segredos/prompts não são retornados.

Antes de gerar, uma reserva desconta disponibilidade, sem marcar consumo. O painel separa saldo restante e disponibilidade para novas tarefas. A revisão do extrato impede atualizações atrasadas de sobrescrever saldos mais novos. Após um passo completo e logits válidos, liquida entrada+primeira saída, ou uma saída em passos subsequentes. Distribui o valor entre as camadas; a parte da própria conta não é creditada. Não repassar crédito por um estágio isolado que não completou o pipeline.

Liquidações são idempotentes por sessão/iteração. Cada liquidação de carteira, seus repasses e evento são atômicos. Recibos antigos token-layer são apenas diagnóstico e podem ser gravados em transações posteriores; não representam saldo. Reservas sobram devolvidas ao terminar/cancelar/falhar. Um coordenador exclusivo recupera reservas abertas ao reiniciar; não compartilhar o mesmo banco entre coordenadores ativos.

A auditoria verifica hash encadeado e reconstrói contas, dias e reservas para comparar com as projeções do banco. Não impede reescrita integral pelo administrador. Migração cria tabelas novas sem converter recibos antigos em créditos. Uma queda entre cálculo e persistência não remunera aquele cálculo. Duas contas em conluio ainda podem transformar franquias em extras: não há cadastro público nesta fase.

## Perfil Qwen e agendamento

O adaptador Qwen2 usa camadas Decoder, RMSNorm, RoPE e GQA originais da versão fixada do Transformers. Os índices de cache são locais à partição; posições da sequência permanecem globais. Pesos são float32, sem quantização ou treinamento. O último estágio entrega logits; chat template e EOS são os do tokenizer. O checkpoint Qwen2.5-Coder-0.5B-Instruct está fixado por revisão, com 24 camadas em dois intervalos contíguos. Preparação offline ainda carrega o modelo completo.

`mesh/scheduler.py` admite uma sessão por conta, máximo oito, e alterna turnos sem olhar o saldo. Entradas são divididas em fatias de até 32 tokens; saídas avançam um passo por turno. Cache é separado por sessão no worker. A conta só é cobrada quando o passo lógico completo termina. Tickets evitam que uma limpeza antiga remova uma sessão nova da mesma conta; limpeza de StreamingResponse também cobre desconexão antes do primeiro token.

## Gossip e assinaturas

`mesh/discovery.py` guarda contatos assinados Ed25519 e os troca com múltiplos pares. A lista autorizada fixa chave e URLs; anúncios expiram em 30 segundos e versões antigas/conflitantes são recusadas. O cache é persistido e cada anúncio aprendido é verificado antes de ser aceito ou usado como destino. O protocolo limita mensagens e participantes; não oferece participação anônima.

`mesh/identity.py` vincula assinaturas de comandos à rota, timestamp e corpo, e recibos ao digest da requisição/resultado. O coordenador verifica a chave individual fixada para o endpoint antes de liquidar trabalho; trabalhadores só aceitam comandos do solicitante autorizado. Recibos são guardados na carteira e no histórico de diagnóstico. Isso não é prova matemática de inferência nem consenso de créditos.

## Projeto e testes

`mesh/workspace.py` mapeia cada conta a um diretório próprio, valida caminhos, recusa links, limita tamanho/quantidade e exige revisão para sobrescrever. A interface mostra diff. Ast.parse verifica sintaxe sem executar. Unittest é opt-in em Docker com imagem local aprovada por ID SHA-256, rede none, montagem somente leitura, usuário 65534, capabilities removidas, no-new-privileges e limites de CPU/RAM/PIDs/tempo/saída. Por padrão não há execução de comandos no host. O agente inicial e a opção de aprovação por comando estão descritos na atualização abaixo; ainda não há um ambiente completo de programação equivalente ao Codex.

## Estado persistente e repetição segura

A aplicação de uso normal é iniciada por tools/run_network.py em runtime/network; preserva configuração, identidades, carteira e arquivos. tools/simulate_hosts.py permanece diagnóstico descartável e tools/verify_remote.py pode carregar uma referência completa fora do caminho normal. tools/smoke_network.py valida aplicação real sem referência extra, persistindo checkpoints de evidência.

Cada sessão worker guarda somente a última posição de entrada, hash da requisição e resposta completa, incluindo recibo, além do KV. Repetição idêntica do último passo devolve a resposta sem novo cálculo; conflito retorna 409. Depois que a sessão avança, pedidos mais antigos não são aceitos. O coordenador repete uma vez erros transitórios de protocolo/leitura/conexão/timeout, com assinatura temporal nova e o mesmo corpo. Liquidação continua uma vez por iteração. Cache expira com a sessão; falhas permanentes continuam explícitas.

## Agente de projeto e seletor honesto — 02/11/2026

mesh/agent.py adiciona ciclo de até dez ações, histórico SQLite privado por conta, arquivos/busca/diff, verificadores Python/JSON/estrutura HTML, unittest opcional e cancelamento. A inferência de cada ação usa o mesmo pipeline distribuído, carteira, fila e recibos do chat. Instruções do protocolo usam papel system, separado da tarefa. Tokens de autenticação ficam só em memória, não no histórico do agente. Históricos recentes são limitados; contexto excedido é recusado, sem descartar silenciosamente a tarefa.

Comandos no host são desativados por padrão. O operador pode iniciar run-coder.ps1 -AllowHostCommands: cada comando exige decisão local individual, com argumentos/pasta e impressão das revisões do projeto; mudanças após a proposta invalidam a aprovação. Aprovação é de uso único e expira no reinício. O comando executa no computador do solicitante com seus direitos, sem isolamento; workers remotos só executam suas camadas. Há limites de duração/saída e cancelamento da árvore de processos. Não equivale a isolamento contra comandos hostis nem a controle geral do desktop.

A interface ganhou seletor de modelo abaixo da mensagem, modo Chat/Agente, histórico de tarefas e propostas de aprovação. API /api/models expõe somente o checkpoint carregado; pedidos com outro modelo são recusados. Existe um checkpoint por cluster, sem troca dinâmica/download pelo seletor. Qwen tem contexto limitado a 4096 tokens, saída até 512; GPT-2 mantém 512/128. Não foram instalados nem validados modelos gigantes. DEPENDENCIAS.md e MODELOS.md documentam instalação, limites e etapas necessárias. Não há equivalência de qualidade demonstrada com o Codex.

Salvar pelo agente também executa automaticamente o verificador disponível e devolve o resultado ao modelo. Isso verifica sintaxe/estrutura, não a correção funcional. Histórico de ações usa rótulos textuais para reduzir a cópia indevida do envelope pelo modelo pequeno.

## Troca real e atribuição parcial — 02/11/2026

Implementados mesh/partition_store.py e mesh/model_control.py. Catálogo com revisões fixas, análise dos cabeçalhos safetensors por HTTP Range, divisão por orçamento e assignment por worker. O coordenador guarda somente configuração/tokenizer/índice de tensores; cada worker busca seus próprios intervalos em blocos de até 8 MiB, converte para FP32 em disco e valida hashes locais. Resposta que ignore Range e ofereça download completo é recusada sem ler o corpo. A construção Qwen usa dispositivo meta, atribuição de parâmetros mapeados e buffers RoPE locais; não instancia o modelo completo.

Troca em fases: bloquear novas sessões, exigir ausência de chat/agente ativo, consultar memória, planejar, preparar pesos locais, ativar partições e persistir seleção. Inferência inclui fingerprint da partição. Falhas de ativação restauram o modelo anterior; journal pendente bloqueia geração até recuperação explícita. Reinício usa a seleção e caches locais. Operação restrita ao operador local; um checkpoint ativo por rede. Créditos e arquivos não são recriados na troca. GPU compartilhada e RAM do mesmo host têm orçamento agrupado; GPU real ainda não validada.

CLI plan-model gera só metadados e assignment-N.json; worker --assignment baixa somente a atribuição. O lançador usa esse caminho em instalação nova e mantém compatibilidade com o perfil legado já existente. Configuração de worker não exige user_token: não distribuir tokens de usuários nem a chave privada do coordenador para participantes.

Validação real: Qwen2.5-Coder-0.5B-Instruct foi trocado por Qwen2.5-0.5B-Instruct sem reiniciar os processos; worker A ficou com camadas 0–11 e B com 12–23. Cada um buscou cerca de 601 MiB da origem, sem pesos das camadas do outro; cache contém 145/146 tensores respectivamente. O modelo novo respondeu “2+2 equals 4.” em sete tokens/6,65 s; carteira auditável e reservas liberadas. Evidências em runtime/network/model-switch-evidence.json e new-checkpoint-chat.json.

Planejamento real do Coder32B: 32 partições, 122,05 GiB FP32 previstos, mínimo 3,63 e máximo 6,53 GiB por partição antes de runtime/KV. Pasta runtime/plans/coder-32b ocupou 11,31 MiB e nenhum arquivo de pesos. Solicitar 32B nos dois workers atuais retornou falta de memória antes da preparação de pesos; partições locais e consumo permaneceram iguais, modelo anterior preservado. Evidência em runtime/network/large-model-preflight-evidence.json. Planejamento não é inferência grande executada. Perfil72B cadastrado; não foi executado nem validado em escala.

Ainda faltam computadores físicos, rede pública/consenso, avaliação de qualidade de modelos maiores, quantização, contexto ampliado e eficiência. O novo fluxo elimina a exigência de baixar/carregar todos os pesos numa máquina; não elimina a necessidade de capacidade agregada nem demonstra equivalência ao Codex. A preparação prepare antiga carrega o modelo completo e permanece somente para diagnósticos pequenos.
