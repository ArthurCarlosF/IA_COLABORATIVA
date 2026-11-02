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
