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

## Propostas ainda não aprovadas

- Franquia básica renovável e limitada para garantir acesso.
- Créditos adicionais por trabalho verificado e disponibilidade útil comprovada.
- Emissão limitada para disponibilidade ociosa, com proteção contra identidades falsas e dupla contagem de memória.
- Fila justa por usuário, limites de concorrência e tarefas grandes divididas em etapas.
- Créditos internos sem negociação financeira na primeira fase.
- Rede inicial com computadores convidados antes de participação anônima.

Essas propostas não são regras implementadas nem decisões econômicas concluídas. Ainda é necessário definir acesso de quem não contribui, emissão, transferência, consenso e tratamento de participantes maliciosos.

## Estado real da base

Implementado: GPT-2 pequeno dividido em camadas, coordenador único, workers CPU (opção CUDA não validada), cache KV, streaming, recursos, autenticação e livro SQLite com cadeia de hashes. Testado entre processos separados e entre dois hosts lógicos loopback com IPs distintos.

Ainda não implementado: rede P2P sem coordenador obrigatório, consenso distribuído, pagamentos, proteção contra identidades falsas, provas de execução, disponibilidade remunerada, múltiplos usuários com fila justa e uma interface completa semelhante ao Codex. O modelo tiny-gpt2 valida a execução distribuída; não oferece qualidade conversacional útil.
