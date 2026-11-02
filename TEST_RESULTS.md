# Testes executados — 02/11/2026

## Primeira execução

Comando: `.venv/Scripts/python -m pytest -q --basetemp=runtime/pytest` com HF_HOME=data/hf.

Resultado real: **16 passed in 48.87s**.

- Dois workers e coordenador em processos separados, usando sockets loopback.
- Oito passos de inferência, prefill e KV incremental: erro máximo dos logits **0,0**, tolerâncias atol=1e-6/rtol=1e-5; argmax idêntico ao modelo completo.
- Chat pela API: 12 tokens em 2,445 s, aproximadamente 4,91 tokens/s.
- Créditos: 24 lançamentos, os dois workers, débito e crédito balanceados, cadeia íntegra.
- RSS inicial: 245.047.296 e 245.084.160 bytes. KV ativo: 64 bytes por worker na sequência de quatro tokens. Após release: zero bytes de KV e zero sessões; variação de RSS inferior a 64 MiB.
- Worker encerrado durante disponibilidade da rede: falha explícita; cache acessível liberado; reinício e nova geração bem-sucedidos.
- Autenticação, validação de tensores, limite de payload, vocabulário/tipos, posição KV, idempotência e adulteração do livro contábil verificados conforme testes.

## Navegador

Chrome, http://127.0.0.1:8000, dois workers online. Pergunta enviada pela interface: "What is artificial intelligence?". Resposta real de 32 tokens repetindo "stairs", 4,60 tokens/s, zero falhas. Captura: runtime/chat-validado.png. Modelo de validação sem qualidade conversacional.

## Versão final — suíte completa

Comando: `.venv/Scripts/python -m pytest -q --basetemp=runtime/pytest-final` com HF_HOME=data/hf.

Resultado real: **26 passed in 100.00s (0:01:40)**, sem avisos.

Integração repetida em HTTP loopback e HTTPS com certificados de teste explicitamente confiados. Certificado não confiável recusado. Logits com erro máximo 0.0, oito passos em cada transporte. Chat HTTPS: 12 tokens em 3.241 s (3.70 tokens/s). Dois workers efetivos e créditos dos dois estágios.

Também passaram: planejador de memória, rejeição por orçamento de KV, recusa de HTTP remoto, recusa de partição atribuída incorretamente, token fora do vocabulário, concorrência (429) e cancelamento do cliente com liberação dos dois caches e da trava do coordenador.

O teste novo de cancelamento inicialmente falhou em HTTP e HTTPS: 2 failed, 24 passed em 118,19 s. Foi corrigido substituindo o middleware HTTP por middleware ASGI que preserva a desconexão e protegendo a limpeza do KV contra cancelamento. Regressão isolada: 2 passed em 48,00 s. A suíte final acima confirma a correção.

Evidência detalhada: runtime/test-evidence.json. O verificador tools/verify_remote.py foi executado com sucesso contra os dois workers **locais**, com oito passos equivalentes, chat e créditos: runtime/local-verifier-evidence.json. Essa execução do verificador precedeu a última correção de cancelamento; a suíte final testa a correção.

A interface final foi reaberta no Chrome após reiniciar todos os serviços. Gerou 32 tokens a 3,26 tokens/s, sem falhas. Captura atualizada: runtime/chat-validado.png. Desempenho varia com a carga da máquina; esses números não são benchmark de aceleração.

## Não executado

Duas máquinas físicas, execução de camadas no celular/navegador, CUDA/VRAM, perda física de rede, carga prolongada, modelo maior/instruído e produção com participantes hostis. O limite de RSS é uma verificação curta de regressão, não um limite de memória pico. Não houve promessa de aceleração por distribuir este modelo minúsculo; o transporte domina o custo.

## Dois hosts lógicos no mesmo computador — 02/11/2026

Executado `tools/simulate_hosts.py --serve`. Coordenador HTTP apenas em loopback 127.0.0.1:8200; workers reais pc-a em HTTPS 127.0.0.2:8201 e pc-b em HTTPS 127.0.0.3:8202. Processos de serviço inicialmente observados: {'coordinator': 17964, 'pc-a': 17144, 'pc-b': 27452}. Pastas separadas; cada worker recebeu somente sua partição. Há um único sistema operacional/hardware; diretórios separados não constituem isolamento de permissões.

Certificado não confiável foi rejeitado. O worker pc-b foi encerrado; a geração falhou explicitamente. Após reinício, oito passos tiveram erro máximo de logits 0.0 comparados ao modelo local. Chat gerou 12 tokens em 2.500 s. Livro íntegro com 25 lançamentos, incluindo um estágio concluído antes da falha induzida. A falha vista no painel é a do teste intencional.

Evidência desta execução: D:/Projetos/RedeInferencia/runtime/simulation/20261102-150404-3782b3/report.json. O script executou de fato inicialização, comunicação TLS, desligamento/reinício e verificador numérico. A suíte anterior de 26 testes não foi repetida nesta alteração, que adiciona somente um lançador de validação; o motor neural não foi modificado.

## Validação da estrutura base para o GitHub — 02/11/2026

Instalação editável do pacote ia-colaborativa 0.1.0 concluída com sucesso (`pip install -e . --no-deps`); comando `ia-colaborativa --help` executado. Suíte local repetida: **26 passed in 106.03s (0:01:46)**, com HTTP/HTTPS e inferência real. Rotina de GitHub Actions adicionada; o resultado remoto não foi verificado nesta validação local. Revisão de publicação: 31 arquivos; pesos, runtime, chaves e credenciais locais excluídos.

## Franquia diária e créditos por contribuição — 02/11/2026

Implementados: carteiras por conta, franquia inicial configurável de 20.000 tokens/dia à meia-noite de America/Sao_Paulo, extras sem expiração, divisão por camadas, bloqueio de autorremuneração, reservas, liquidação idempotente, recuperação e extrato privado. O painel mostra tokens, renovação, contribuição e extras. Ver docs/CREDIT_PLAN.md.

Suíte final executada: **43 passed in 101.06s (0:01:41)**, comando `.venv/Scripts/python -m pytest -q --basetemp=runtime/pytest-credits-final`. Inclui 13 testes de carteira, 14 anteriores e 16 integrações com inferência real, HTTP/HTTPS e contas distintas. Comparação incremental: 8 passos, erro máximo 0.0. Reciprocidade: {'local_cost': 4, 'peer_reward': 2.0, 'reverse_reward': 2.0, 'private_audit': True}. Esgotamento: {'zero_balance_http': 402, 'output_clipped': True, 'extra_spent': 2}.

Verificados: fronteira 23:59:59/00:00 no fuso, não acúmulo, persistência, recuo de relógio sem reabrir dias, mudança de política sem nova emissão no mesmo dia, reservas atravessando meia-noite, gasto diário antes de extras, sobreconsumo concorrente, arredondamento, múltiplos workers do mesmo dono, idempotência/replay conflitante, adulteração de saldo/eventos, histórico privado, falha/cancelamento sem reservas presas e saldo esgotado 402. O limite de saída é reduzido ao saldo disponível.

JavaScript da interface passou em `node --check`. A autorização para abrir http://127.0.0.1:8300 no navegador foi recusada; **a conferência visual da nova interface não foi executada** e não existe captura nova validada. Não reutilizar capturas antigas como evidência deste painel.

A demonstração anterior com duas contas executou contribuição real em ambas as direções: local-user consumiu 17 e ganhou 4,5; peer-user consumiu 9 e ganhou 8,5. Carteiras e cadeia íntegras, sem dinheiro ou créditos inventados. A demonstração foi reiniciada com a revisão final em localhost:8300; consultar runtime/simulation/latest.json para a pasta e report.json desta execução.

Limites: continua sendo um coordenador/banco local, identidades autorizadas e tiny-gpt2. Rede pública, consenso, remuneração por ociosidade, privacidade contra workers hostis, fila justa distribuída e qualidade de um assistente de programação não foram implementados. O valor diário não garante horas de uso. Não foram realizados testes físicos entre máquinas nem uma espera real até a meia-noite: fronteira de horário testada com relógio injetado no motor contábil, explicitamente sem simular a inferência.
