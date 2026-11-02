# Arquitetura

## Caminho real de um token

Navegador → POST /api/chat → tokenizer no coordenador → worker inicial (embedding de tokens + posições, camadas iniciais) → ativações float32 → worker final (camadas restantes, LayerNorm, LM head) → logits → argmax no coordenador → SSE no navegador.

A saída do worker inicial é entrada do seguinte. Não existem agentes, votação de respostas ou modelos independentes. A preparação offline carrega temporariamente o checkpoint completo para criar arquivos menores. Durante a inferência cada worker instancia **somente** seus próprios blocos e os componentes de fronteira necessários. O coordenador contém tokenizer, manifesto e hashes, sem camadas neurais.

## Partições e recursos

`mesh/model.py` prepara partes contíguas; `mesh/planner.py` aceita orçamento de pesos por computador. Primeiro worker recebe embeddings; último recebe normalização e cabeça. GPT-2 amarra embedding e cabeça no checkpoint original; a mesma matriz é copiada para as duas fronteiras quando estão em máquinas diferentes. Isso é replicação de um parâmetro necessário, não replicação do modelo completo.

`/internal/register` valida identidade permitida, URL fixa, hash dos pesos e intervalo exato de camadas. Heartbeat a cada 2 s; offline após 8 s. Configurações inválidas ou partições duplicadas são recusadas. Recursos de CPU/RAM/RSS e, quando disponível, VRAM aparecem na API e parcialmente na interface. Plano é fixado antes da execução; capacidade não é rebalanceada automaticamente.

## KV cache e geração

Cada sessão usa UUID; cada worker guarda K/V por bloco, posição e última atividade. Prefill processa o prompt inteiro; passos seguintes recebem somente o token novo. As posições são idênticas nas partições. Cache é liberado ao concluir, cancelar ou falhar; se a rede impedir a liberação, o TTL de 120 s remove a sessão. O orçamento configurável bloqueia expansão de cache antes da execução. Um orçamento de KV não é limite de RSS nem garante ausência de OOM no runtime.

Decodificação gulosa determinística; contexto 512 e batch 1. Uma trava por coordenador impede gerações concorrentes (429). Erros de rede encerram a geração explicitamente, preservam cobranças de trabalho concluído e tentam liberar todos os caches. Não há retry de passos nem continuação de KV perdido.

## Protocolo e segurança

FastAPI/Uvicorn + HTTPX; JSON/base64 little-endian nativo de float32/int64 nas máquinas suportadas (x86). Payload limitado a 4 MiB, 1 milhão de elementos e contexto de 512. Tipos, batch, vocabulário, comprimento, finitude e posição são validados. HMAC autentica o corpo com timestamp; HTTPS protege confidencialidade e respostas em LAN. Sem pickle na rede. Chave única de cluster implica confiança mútua entre workers. Autenticação do usuário é um token local único nesta versão.

Não há descoberta na internet, NAT traversal, blockchain, execução redundante para prova de correção, usuários múltiplos ou isolamento para workers hostis. Serviços vinculados a loopback por padrão; modo LAN exige certificados confiáveis. A cadeia contábil detecta edições internas, mas precisa de ancoragem externa para detectar reescrita integral/truncamento.

## Créditos

Por passo de cada worker: receipt = sessão:iteração:worker. Dupla entrada balanceada, user local com débito e worker com crédito, unidades token-layer, duração de execução e timestamp. SQLite serializa lançamentos e encadeia hashes. Trabalho concluído é lançado mesmo se outro estágio falhar. Um crash entre execução remota e persistência pode perder um lançamento: confirmação transacional distribuída fica no roadmap.

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
