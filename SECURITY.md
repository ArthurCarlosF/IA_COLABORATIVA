# Segurança da versão inicial

A base é um protótipo para computadores confiáveis. Não disponibilizar como rede pública de participantes anônimos.

- Loopback por padrão. Serviços remotos exigem HTTPS com validação de certificado.
- HMAC interno com segredo compartilhado e lista permitida de workers/URLs.
- Token de usuário para chat, telemetria e créditos.
- Mensagens com limites e tensores validados; sem pickle de rede.
- Pesos locais carregados com weights_only=True.
- Segredos, certificados, modelos, bancos e logs devem permanecer fora do Git.

## Limitações

O modo antigo sem P2P não tem identidade individual de worker. No modo P2P autorizado, anúncios, comandos e recibos usam Ed25519 com chaves fixadas por endpoint; possuir somente o segredo compartilhado não basta para se passar por outro participante. Ainda não há consenso de créditos nem prova de correção neural. A cadeia de hashes do SQLite não impede que um administrador reescreva todo o banco; ancoragem externa ainda não existe. Particionar o modelo não garante confidencialidade dos prompts/ativações diante de workers maliciosos.

Não incluir segredos reais em issues, logs públicos, capturas ou relatórios. Falhas com detalhes sensíveis devem ser comunicadas por um canal privado autorizado pelo responsável pelo repositório.

## Créditos e identidades

Carteiras e franquias exigem identidades provisionadas; não há registro público. Token de usuário não autoriza escolher worker_owners, saldo ou conta pagadora no corpo de requisições. Trabalho da própria conta não gera extras. Recibos por sessão/iteração previnem duplicação e reservas evitam gastos concorrentes acima do saldo. Históricos privados não incluem prompts nem tokens de acesso.

Essas medidas não resolvem conluio entre identidades, relógio/administrador malicioso, prova criptográfica da inferência ou consenso público. Uma franquia pode financiar trabalho de uma conta associada; ampliar a rede exige proteção contra esse cenário. Tokens Bearer devem ser tratados como identidade da conta. Não compartilhar contas/segredos entre usuários; usar HTTPS para acesso remoto.

## Descoberta e recibos

O diretório gossip limita identidades a uma lista autorizada, fixa URLs e chaves, valida assinaturas/expiração/replay e limita mensagens/contatos. Não consulta URLs fornecidas por desconhecidos. As chaves privadas pertencem ao próprio nó; distribuir só chaves públicas aos demais. Na demonstração, todas as identidades estão no mesmo computador para teste, não para produção.

Recibos autenticam o digest da requisição e do resultado. Um worker malicioso ainda pode assinar um resultado incorreto. Não habilitar registro público ou tratar recibos como prova matemática da inferência. O modelo e as ativações não ficam automaticamente confidenciais por estarem particionados.

## Arquivos e execução

Arquivos ficam em diretórios próprios por conta, com limites, recusa de travessia/links e revisão otimista. O endpoint de testes é desativado sem sandbox_image aprovado por ID SHA-256. Com essa opção, aceita somente unittest em imagem local, sem shell livre, sem rede, montagem do projeto somente leitura, usuário 65534, cap-drop ALL e limites de CPU/RAM/processos/tempo/saída. Não monta socket Docker nem diretórios externos do usuário.

Containers não são garantia contra falhas do kernel/runtime. Uma rede pública de código hostil exige auditoria e possivelmente isolamento mais forte. O processo coordenador com acesso ao Docker deve continuar sob controle do operador. Créditos de tokens não contabilizam o custo de testes locais nesta versão; executor serial e limites reduzem abuso, mas não substituem política de uso pública.
