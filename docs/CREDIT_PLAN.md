# Plano de implementação de franquia e contribuição

## Regras iniciais (configuráveis)
1. Franquia de 20.000 tokens por identidade autorizada/dia, renovada às 00:00 de America/Sao_Paulo. Não acumula. Valor inicial, sem garantia de horas de uso.
2. Créditos por contribuição não expiram; usar primeiro franquia, depois extra. Mostrar os dois saldos, reservas, consumo e contribuição acumulada.
3. Entrada tokenizada e cada token de saída calculado (incluindo EOS) consomem saldo. Primeiro passo custa entrada + uma saída; seguintes custam uma saída cada. Falha antes de completar todas as camadas não liquida esse passo.
4. Dividir o crédito de cada token completo entre as partições proporcionalmente às camadas. Usar inteiros de milionésimos de token; soma das partes nunca excede débito. Mesmo modelo e revisão para todos.
5. Trabalho da própria identidade não gera crédito extra. Vários workers do mesmo proprietário são agregados. Identidades e proprietários são provisionados na configuração, não declarados pelo heartbeat.
6. Não remunerar ociosidade nesta etapa: exigir prova de disponibilidade e política de emissão antes de habilitar. Não há vendas, transferências ou pagamentos.

## Passos
1. Persistir contas, dias, reservas, liquidações e histórico auditável SQLite, separado do histórico antigo em token-layer.
2. Reservar entrada + saída máxima antes de aceitar geração. Reduzir saída máxima se só houver saldo para uma resposta menor; recusar com 402 se não couber nem entrada + uma saída.
3. Liquidar cada passo completo atomicamente com consumo diário/extra e repasse aos proprietários externos. Idempotência por sessão/iteração. Rejeitar repetição conflitante.
4. Liberar reservas ao terminar, cancelar ou falhar. Recuperar reservas abandonadas ao reiniciar um coordenador exclusivo do banco. Reservas em andamento atravessando meia-noite usam apenas o orçamento já reservado no dia anterior.
5. Configurar usuários por tokens distintos, worker_owners e política de franquia; manter compatibilidade com user_token local existente. Não oferecer cadastro público.
6. Endpoints autenticados para saldo, contribuição e auditoria; nunca expor tokens de acesso nem histórico privado de terceiros.
7. Cartão de uso inspirado na referência: fonte do uso, franquia diária em tokens restantes, próxima renovação, créditos extras, contribuição e gerenciar uso. Atualizar durante streaming; trocar identidade com desconexão explícita do chat.
8. Testar meia-noite/fuso, não acumulação, persistência, reservas, saldo insuficiente, arredondamento, duplicação, autoconsumo, múltiplos donos e acesso isolado.
9. Testar inferência real entre dois processos: débito de A → contribuição a B, gasto de B, falha, cancelamento e reinício. Comparar logits local/distribuído novamente.
10. Validar no navegador com contas distintas; salvar evidência e atualizar documentação. Commit da implementação após os testes.

## Problemas e limites
- Créditos não garantem capacidade instantânea: rede congestionada continua limitada. Não prometer horas de uso por um número fixo de tokens.
- A mesma contagem não equivale ao mesmo custo entre modelos/contextos. Esta política cobre um único modelo por coordenador; ponderação entre modelos é trabalho futuro.
- Franquia gratuita pode ser convertida em crédito por contas em conluio. Rejeitar autorremuneração ajuda, mas não resolve identidades falsas; rede aberta exige proteção adicional. Sem cadastro público nesta versão.
- Consenso contábil não prova execução neural. HMAC e confiança compartilhada atuais não tornam seguro abrir workers hostis.
- Operação aceita pode ser concluída/cobrada mesmo se a conexão cair antes de entregar a resposta; passo parcial não é cobrado. Falha de processo entre cálculo e commit não remunera o cálculo não persistido.
- Banco e relógio ainda têm uma autoridade local. Histórico encadeado não resiste a reescrita integral por administrador. Consenso, prova de disponibilidade, privacidade em workers hostis e fila justa distribuída continuam pendentes.
- A franquia é um direito contábil, não uma reserva de toda a rede. A trava atual limita uma geração e rejeita concorrência; escalonador multiusuário justo é um estágio próprio, não alegar que já existe.

## Verificação executada até agora

Primeira suíte completa: 42 testes passaram em 74,00 s; inclui 12 testes de carteira e 16 integrações HTTP/HTTPS, com contas distintas. Adicionada depois uma proteção por revisão para atualizações de saldo atrasadas: 13 testes de carteira passaram em 0,60 s. Suíte completa final: **43 testes passaram em 101,06 s**, incluindo a proteção por revisão; detalhes em TEST_RESULTS.md.

Demonstração real em localhost:8300: local-user consumiu 17 tokens e recebeu 4,5 extras por trabalho externo; peer-user consumiu 9 e recebeu 8,5 extras. Comparação numérica de oito passos com erro máximo 0,0; auditoria íntegra. Valores são dessa execução, não créditos fictícios.

A abertura do navegador em localhost:8300 foi recusada pela autorização da ferramenta. JavaScript passou em node --check; a conferência visual da nova interface não foi executada. Não contornar a recusa nem apresentar captura antiga como evidência desta interface.
