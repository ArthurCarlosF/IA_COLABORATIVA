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
- Adaptador Llama/Qwen pequeno instruído; validação numérica por arquitetura.
- Alocação automática segundo memória real e benchmark, distribuição segura dos pesos.
- Protocolos binários compactos, geração concorrente, batching e cancelamento testado sob carga.
- Rebalanceamento entre requisições e recuperação com recomputação de KV.
- Offload RAM/VRAM e validação de orçamento de memória pico.

## Etapa 4 — rede com participantes independentes
- Identidades individuais e mTLS, isolamento e limites por participante.
- Verificação de execução e política para workers não confiáveis.
- Contabilidade transacional com recibos independentes, ancoragem externa e usuários múltiplos.
- Só depois avaliar pagamentos reais e modelo econômico.
