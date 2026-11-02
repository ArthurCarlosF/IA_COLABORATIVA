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
