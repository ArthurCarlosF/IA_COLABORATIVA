# Objetivo e premissas

## Objetivo solicitado

Uma rede de computadores que execute partes de um único modelo de IA, mesmo quando ele não cabe em uma máquina. Os participantes fornecem CPU/GPU e memória, recebem créditos pela contribuição e utilizam a rede para suas tarefas. A rede deve evoluir para descoberta, organização e validação de créditos sem um servidor central indispensável.

A experiência desejada é semelhante à do Codex: projetos, conversas, arquivos, alterações, terminal, ferramentas, histórico e aprovações. Isso é uma meta de produto, não uma capacidade já entregue. Qualidade do modelo, eficiência de inferência e interface são objetivos separados e exigem avaliações próprias.

Foco atual: computadores. Compatibilidade móvel fica adiada.

## Requisitos de economia e justiça expressos pelo usuário

- Evitar que saldo inicial zero impeça todo uso da rede.
- Recompensar recursos disponibilizados mesmo sem tarefas, com comprovação de disponibilidade.
- Não permitir que um participante monopolize a capacidade por ter mais créditos.
- Aproveitar capacidade ociosa quando não houver outras tarefas.
- Distribuir o processamento de forma justa entre usuários ativos.
- Validar os registros e transações pelos próprios participantes.

## Decisões do usuário e implementação atual

- Não haverá compra/venda em dinheiro. Créditos são de uso e obtidos pela contribuição da máquina.
- Franquia diária pequena, renovável à meia-noite, com tokens restantes e contribuição no painel.
- A meta é participação pública e defesa pelos participantes. Não prometer imunidade a problemas pela simples presença de modelos.
- Primeira política implementada: 20.000 tokens/dia configuráveis, America/Sao_Paulo, sem acúmulo da franquia; extras sem expiração. Entrada/saída consomem tokens equivalentes. A remuneração é dividida entre as partições externas, sem autorremuneração.

## Ainda exige projeto e validação

- Remuneração de disponibilidade ociosa com prova de recurso útil, sem contar a mesma memória várias vezes.
- Fila justa por usuário e tarefas grandes divididas em etapas, sem prioridade por saldo.
- Consenso, identidades resistentes a fraude e verificação de execução contra participantes hostis.
- Calibrar a franquia com modelo útil e medições reais; 20.000 é uma configuração inicial, não promessa de horas de uso.

## Estado real da base

Implementados: GPT-2 e Qwen2 particionados, Qwen2.5-Coder-0.5B-Instruct com tarefa inicial de código validada, cache, chat template, streaming, recursos, contas, franquia diária e contribuição. Há turnos por conta no coordenador, arquivos privados, revisão/diff e testes Python em Docker opt-in.

A descoberta entre pares autorizados usa gossip assinado e resistiu à perda do contato inicial. No modo P2P, comandos e recibos também têm assinaturas individuais. Identidade/recibo não são prova neural nem consenso.

Pendente: execução física entre máquinas (sem segundo host disponível), desempenho em escala/GPU, descoberta pública/DHT/NAT, alocação automática, recuperação em outro worker, consenso distribuído dos créditos, proteção contra Sybil/conluio e privacidade em workers hostis. A fila é local a cada solicitante; justiça global e a experiência completa de um agente como Codex seguem em desenvolvimento. Ver docs/FUNCTIONAL_STATUS.md.
