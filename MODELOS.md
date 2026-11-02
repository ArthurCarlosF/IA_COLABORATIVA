# Modelos, capacidade e critérios de qualidade

## O que realmente executa hoje

O perfil run-coder usa Qwen2.5-Coder-0.5B-Instruct, revisão fixa ea3f2471cf1b1f0db85067f1ef93848e38e88c25: 24 camadas divididas em dois workers. É um modelo de validação, não equivalente a um assistente de programação de ponta. As ativações atravessam a rede e cada worker mantém seu KV cache. Há também tiny-gpt2 para regressões de transporte/números, sem finalidade de programação útil.

A interface mostra a identificação real obtida em /api/models. /api/chat e /api/agent/runs rejeitam modelo diferente do checkpoint ativo. Atualmente existe um checkpoint ativo por cluster; a seleção não faz troca automática nem download. Não listamos checkpoints ausentes como disponíveis. Contexto Qwen limitado nesta implementação a 4096 tokens incluindo saída, com até 512 tokens por resposta/ação. O contexto GPT-2 continua limitado a 512/128. Ultrapassar limites gera erro explícito.

## Por que adicionar computadores não garante qualidade

Dividir as camadas preserva a computação do checkpoint e permite distribuir pesos e KV entre participantes. Não acrescenta parâmetros, treinamento nem conhecimento ao modelo. Qualidade depende de pesos, instruções, contexto, ferramentas e verificações. Um modelo maior pode melhorar tarefas, mas não implica equivalência automática ao Codex. A única comparação numérica feita aqui é entre execução local e distribuída do mesmo checkpoint; não é comparação de inteligência com outro produto.

A execução de um token tem dependências sequenciais entre partições. Latência e banda entre máquinas podem reduzir bastante a velocidade. Mais workers podem aumentar capacidade de memória e atender pipelines, sem garantir menor latência de uma solicitação. Pesos de embeddings/saída e KV precisam ser incluídos no orçamento; RAM/VRAM não são um único espaço de acesso instantâneo.

## O que falta para um perfil grande real

1. Definir checkpoint aberto e revisão fixa, licença e arquitetura suportada. Atualmente só GPT-2 e Qwen2 sem sliding window têm adaptadores.
2. Implementar leitura/particionamento progressivo e formato quantizado, com regressões numéricas para cada formato. A preparação atual carrega todos os pesos FP32 numa única máquina: é um impedimento para checkpoints gigantes nesta máquina.
3. Medir memória disponível por worker, pesos de cada partição, cache para contexto/concorrrência e margem de execução; recusar alocação insuficiente antes de iniciar.
4. Transferir apenas partições necessárias com verificação de integridade e criar perfis persistentes por modelo; adicionar troca/coexistência real de clusters à seleção, com descarregamento coordenado.
5. Validar dois computadores físicos e depois maior escala: numérico, desconexão, retomada de KV, privacidade, throughput, latência e fila justa. O segundo computador ainda não está disponível.
6. Medir tarefas de programação representativas antes de anunciar capacidade: criar projeto, corrigir bug, alterar múltiplos arquivos, usar dependências, executar testes e manter contexto. Registrar falhas, tokens e tempo com recursos equivalentes. A avaliação de um concorrente exige acesso autorizado e condições reproduzíveis; ainda não foi feita.

Exemplo de orçamento, somente aritmética: 32 bilhões de parâmetros em FP32 são aproximadamente 119 GiB só de pesos, antes de buffers/KV/processos. Quantização reduz pesos, mas exige um motor compatível e validação; não está implementada. Não baixar um modelo desses nesta máquina como se estivesse pronto. Na inspeção desta etapa havia cerca de 5,5 GiB de RAM disponível dos 31,9 GiB totais; outros programas pertencem ao usuário e não devem ser encerrados para mascarar essa limitação.

## Agente e testes

O motor de ferramentas é separado da inteligência: ele valida ações JSON, lê/salva arquivos privados, mostra diferenças, verifica sintaxe/estrutura e permite unittest isolado quando Docker está disponível. Comando no host exige habilitação pelo operador e aprovação individual. Não existe controle geral de navegador/desktop, integração completa Git, imagens, extensões, nem ambiente equivalente a todos os recursos do Codex. Testes com respostas programadas comprovam o executor, não a capacidade do modelo; tools/smoke_agent.py faz uma avaliação separada com inferência real e salva evidência sem inventar respostas.

A meta é um assistente cooperativo de programação com capacidade demonstrável. Não há promessa de qualidade equivalente, perfeição ou segurança absoluta. O critério de anúncio deve ser uma matriz de tarefas executadas e resultados reproduzíveis, não o tamanho do nome exibido no seletor.
