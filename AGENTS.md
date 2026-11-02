# Regras
- Executar inferência real; nunca simular respostas.
- Serviços locais por padrão; TLS obrigatório para LAN.
- Executar testes e registrar resultados reais.
- Atualizar PROGRESS.md, TEST_RESULTS.md e NEXT_STEPS.md.
- Nunca desserializar pickle recebido pela rede.

## Apresentação obrigatória do projeto

- Manter `LEIA-ME-PRIMEIRO.txt` na raiz, em português e UTF-8, como apresentação para quem baixar o repositório.
- Revisar e atualizar esse TXT na mesma alteração de qualquer mudança relevante de visão, escopo, arquitetura, funcionalidades, política de créditos, segurança, instalação ou resultados de validação.
- Manter data e fase atual corretas. Conferir coerência com README.md, ROADMAP.md, PROGRESS.md e TEST_RESULTS.md.
- Explicar a ambição e o impacto pretendido sem apresentar metas futuras como funcionalidades entregues. Nunca prometer segurança absoluta, eficiência ou qualidade de modelo ainda não demonstradas.

## Agente e modelos
- Separar testes do executor com respostas programadas de avaliações do modelo real.
- Não exibir modelo ausente como disponível nem alegar equivalência ao Codex sem avaliação comparável.
- Comandos no host exigem habilitação explícita e aprovação por proposta; nunca executar comandos de projeto nos workers de terceiros.
- Manter DEPENDENCIAS.md e MODELOS.md coerentes com o executor e os perfis.
