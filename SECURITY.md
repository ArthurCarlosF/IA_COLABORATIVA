# Segurança da versão inicial

A base é um protótipo para computadores confiáveis. Não disponibilizar como rede pública de participantes anônimos.

- Loopback por padrão. Serviços remotos exigem HTTPS com validação de certificado.
- HMAC interno com segredo compartilhado e lista permitida de workers/URLs.
- Token de usuário para chat, telemetria e créditos.
- Mensagens com limites e tensores validados; sem pickle de rede.
- Pesos locais carregados com weights_only=True.
- Segredos, certificados, modelos, bancos e logs devem permanecer fora do Git.

## Limitações

Não há identidade criptográfica individual por worker, consenso distribuído nem prova infalível de execução. Um participante com o segredo do cluster pode se passar por outro participante. A cadeia de hashes do SQLite não impede que um administrador reescreva todo o banco; ancoragem externa ainda não existe. Particionar o modelo não garante confidencialidade dos prompts/ativações diante de workers maliciosos.

Não incluir segredos reais em issues, logs públicos, capturas ou relatórios. Falhas com detalhes sensíveis devem ser comunicadas por um canal privado autorizado pelo responsável pelo repositório.

## Créditos e identidades

Carteiras e franquias exigem identidades provisionadas; não há registro público. Token de usuário não autoriza escolher worker_owners, saldo ou conta pagadora no corpo de requisições. Trabalho da própria conta não gera extras. Recibos por sessão/iteração previnem duplicação e reservas evitam gastos concorrentes acima do saldo. Históricos privados não incluem prompts nem tokens de acesso.

Essas medidas não resolvem conluio entre identidades, relógio/administrador malicioso, prova criptográfica da inferência ou consenso público. Uma franquia pode financiar trabalho de uma conta associada; ampliar a rede exige proteção contra esse cenário. Tokens Bearer devem ser tratados como identidade da conta. Não compartilhar contas/segredos entre usuários; usar HTTPS para acesso remoto.
