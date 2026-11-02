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

## Troca real e atribuição parcial — 02/11/2026

Implementados mesh/partition_store.py e mesh/model_control.py. Catálogo com revisões fixas, análise dos cabeçalhos safetensors por HTTP Range, divisão por orçamento e assignment por worker. O coordenador guarda somente configuração/tokenizer/índice de tensores; cada worker busca seus próprios intervalos em blocos de até 8 MiB, converte para FP32 em disco e valida hashes locais. Resposta que ignore Range e ofereça download completo é recusada sem ler o corpo. A construção Qwen usa dispositivo meta, atribuição de parâmetros mapeados e buffers RoPE locais; não instancia o modelo completo.

Troca em fases: bloquear novas sessões, exigir ausência de chat/agente ativo, consultar memória, planejar, preparar pesos locais, ativar partições e persistir seleção. Inferência inclui fingerprint da partição. Falhas de ativação restauram o modelo anterior; journal pendente bloqueia geração até recuperação explícita. Reinício usa a seleção e caches locais. Operação restrita ao operador local; um checkpoint ativo por rede. Créditos e arquivos não são recriados na troca. GPU compartilhada e RAM do mesmo host têm orçamento agrupado; GPU real ainda não validada.

CLI plan-model gera só metadados e assignment-N.json; worker --assignment baixa somente a atribuição. O lançador usa esse caminho em instalação nova e mantém compatibilidade com o perfil legado já existente. Configuração de worker não exige user_token: não distribuir tokens de usuários nem a chave privada do coordenador para participantes.

Validação real: Qwen2.5-Coder-0.5B-Instruct foi trocado por Qwen2.5-0.5B-Instruct sem reiniciar os processos; worker A ficou com camadas 0–11 e B com 12–23. Cada um buscou cerca de 601 MiB da origem, sem pesos das camadas do outro; cache contém 145/146 tensores respectivamente. O modelo novo respondeu “2+2 equals 4.” em sete tokens/6,65 s; carteira auditável e reservas liberadas. Evidências em runtime/network/model-switch-evidence.json e new-checkpoint-chat.json.

Planejamento real do Coder32B: 32 partições, 122,05 GiB FP32 previstos, mínimo 3,63 e máximo 6,53 GiB por partição antes de runtime/KV. Pasta runtime/plans/coder-32b ocupou 11,31 MiB e nenhum arquivo de pesos. Solicitar 32B nos dois workers atuais retornou falta de memória antes da preparação de pesos; partições locais e consumo permaneceram iguais, modelo anterior preservado. Evidência em runtime/network/large-model-preflight-evidence.json. Planejamento não é inferência grande executada. Perfil72B cadastrado; não foi executado nem validado em escala.

Ainda faltam computadores físicos, rede pública/consenso, avaliação de qualidade de modelos maiores, quantização, contexto ampliado e eficiência. O novo fluxo elimina a exigência de baixar/carregar todos os pesos numa máquina; não elimina a necessidade de capacidade agregada nem demonstra equivalência ao Codex. A preparação prepare antiga carrega o modelo completo e permanece somente para diagnósticos pequenos.
