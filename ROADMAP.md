# Roadmap

## Etapa 1 — implementada e validada localmente
- Checkpoint real pequeno GPT-2, duas partições, dois processos worker.
- Comparação numérica com modelo local e KV cache incremental.
- Coordenador, heartbeat, recursos, chat SSE e livro de créditos.
- HMAC, limites de payload, allowlist e loopback padrão.
- Falha de worker, reinício e liberação de cache.
- Planejamento offline conforme orçamento de pesos; orçamento de KV.

## Etapa 2 — pendente de segunda máquina
- Implantar com certificados confiáveis em LAN privada.
- Comparar logits remotos e locais; medir RTT, bytes, RSS e tokens/s.
- Verificar interrupção física da rede e TTL remoto.
- Validar CUDA e execução mista CPU/GPU quando hardware permitir.

## Etapa 3 — qualidade e escala
- Entregue: adaptador Qwen2, checkpoint Qwen2.5-Coder-0.5B-Instruct e validação inicial de código/números.
- Alocação automática segundo memória real e benchmark, distribuição segura dos pesos.
- Protocolos binários compactos, geração concorrente, batching e cancelamento testado sob carga.
- Rebalanceamento entre requisições e recuperação com recomputação de KV.
- Offload RAM/VRAM e validação de orçamento de memória pico.

## Etapa 4 — rede com participantes independentes
- Identidades individuais e mTLS, isolamento e limites por participante.
- Verificação de execução e política para workers não confiáveis.
- Contabilidade transacional com recibos independentes, ancoragem externa e usuários múltiplos.
- Manter créditos exclusivamente para uso cooperativo, sem compra/venda ou pagamentos reais, conforme decisão do usuário.

## Franquia e reciprocidade — implementadas no coordenador local
- Franquia diária por identidade autorizada, fuso, renovação e não acúmulo.
- Extra por contribuição externa, precisão fracionária e prevenção de autorremuneração.
- Reservas, saldo insuficiente, cancelamento, recuperação e extrato privado auditável.
- Painel de uso com tokens restantes, contribuição e créditos extras.
- Próximos estágios: fila justa, prova de disponibilidade, identidade pública, consenso e modelos úteis.

## Evolução funcional — 02/11/2026
- Entregue: Qwen de programação dividido em 24 camadas, RoPE/GQA e chat template.
- Entregue: turnos por conta, prefill limitado, limpeza em desconexão precoce.
- Entregue: descoberta gossip assinada com múltiplos contatos e identidades autorizadas, sem diretório central obrigatório.
- Entregue: assinaturas individuais de comandos e recibos no modo P2P autorizado.
- Entregue: arquivos privados, revisão/diff, verificação sintática e unittest em Docker restrito e opt-in.
- Bloqueado por hardware ausente: validação entre dois computadores físicos e GPUs.
- Pendente de projeto/validação: consenso público, anti-Sybil/conluio, prova de execução, privacidade contra workers hostis, DHT/NAT, escalonamento global, carga em escala e agente completo de programação.
- Leia docs/FUNCTIONAL_STATUS.md; não confundir descoberta descentralizada com contabilidade descentralizada.

## Agente de projeto e seletor honesto — 02/11/2026

mesh/agent.py adiciona ciclo de até dez ações, histórico SQLite privado por conta, arquivos/busca/diff, verificadores Python/JSON/estrutura HTML, unittest opcional e cancelamento. A inferência de cada ação usa o mesmo pipeline distribuído, carteira, fila e recibos do chat. Instruções do protocolo usam papel system, separado da tarefa. Tokens de autenticação ficam só em memória, não no histórico do agente. Históricos recentes são limitados; contexto excedido é recusado, sem descartar silenciosamente a tarefa.

Comandos no host são desativados por padrão. O operador pode iniciar run-coder.ps1 -AllowHostCommands: cada comando exige decisão local individual, com argumentos/pasta e impressão das revisões do projeto; mudanças após a proposta invalidam a aprovação. Aprovação é de uso único e expira no reinício. O comando executa no computador do solicitante com seus direitos, sem isolamento; workers remotos só executam suas camadas. Há limites de duração/saída e cancelamento da árvore de processos. Não equivale a isolamento contra comandos hostis nem a controle geral do desktop.

A interface ganhou seletor de modelo abaixo da mensagem, modo Chat/Agente, histórico de tarefas e propostas de aprovação. API /api/models expõe somente o checkpoint carregado; pedidos com outro modelo são recusados. Existe um checkpoint por cluster, sem troca dinâmica/download pelo seletor. Qwen tem contexto limitado a 4096 tokens, saída até 512; GPT-2 mantém 512/128. Não foram instalados nem validados modelos gigantes. DEPENDENCIAS.md e MODELOS.md documentam instalação, limites e etapas necessárias. Não há equivalência de qualidade demonstrada com o Codex.
