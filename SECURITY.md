# Segurança da versão inicial

O serviço de microblocos exige segredo próprio, HMAC com timestamp, recibo vinculado ao corpo e limites de tamanho/memória. Fora de loopback, exige TLS. Ele executa apenas multiplicação FP32, sem ferramentas ou shell. Checkpoints lentos não incluem o segredo, mas guardam prompts/tokens e ativações: mantenha a pasta privada. Hashes detectam corrupção local e respostas alteradas em trânsito, sem provar correção de cálculo ou proteger contra um participante autorizado hostil.

No modo lento, o provedor dos pesos observa os intervalos solicitados. As linhas de embeddings e os especialistas acessados dependem da entrada; esse modo não oferece privacidade do padrão de acesso contra o provedor.

O painel de blocos exige token do operador e acesso local. Os perfis são predefinidos e o navegador não configura endpoints, caminhos nem comandos. A pergunta vai ao subprocesso por arquivo local, fora da linha de comando. Preserve as permissões da pasta de trabalhos e não exponha essas rotas por proxy reverso.

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

## Agente de projeto e comandos opcionais

O agente trata respostas do modelo como propostas JSON sujeitas a esquemas e revisões de arquivo. Arquivos de cada conta ficam separados. Textos de arquivos e saída de processos são dados não confiáveis: a instrução de ignorar prompt injection ajuda o modelo, mas não constitui proteção comprovada contra instruções maliciosas.

run-coder.ps1 -AllowHostCommands é uma opção do operador local; permanece desligada por padrão. Cada proposta mostra argv e diretório e exige aprovação humana de uso único, vinculada ao estado de todos os arquivos do projeto. Mudanças entre proposta e execução exigem nova proposta. Somente local-user em origem loopback pode aprovar. A verificação de origem não substitui proteger o token e a configuração. Não encaminhar o serviço publicamente.

O subprocesso recebe argumentos sem shell implícito e ambiente reduzido, tempo limite e limite de saída. Porém o programa aprovado pode abrir rede, acessar arquivos externos, lançar outros programas ou invocar um shell por seus próprios argumentos. Executa com os direitos do usuário e não é uma sandbox. Não habilitar essa opção em serviços expostos ou para pessoas não confiáveis. Tokens do coordenador não são persistidos no histórico do agente nem repassados no ambiente mínimo do comando; ainda assim o processo tem os direitos de acesso aos arquivos do usuário. Os trabalhadores de terceiros não executam ferramentas do agente.

No reinício, tarefas em andamento ficam interrompidas e aprovações pendentes expiram. Não há replay automático de comandos. Histórico local não é criptografado em repouso nem possui sincronização/consenso público. Verificação sintática/estrutural não prova correção funcional nem segurança do arquivo gerado.

## Preparação parcial e troca de checkpoints

O novo catálogo restringe repos/revisões e arquitetura; tokenizer usa trust_remote_code=False. Cada worker recebe apenas o blueprint de sua partição e só busca intervalos de byte no provedor do perfil autorizado. Range deve retornar 206 e Content-Range exato, dentro do limite de bloco. Não aceitar fallback de download inteiro. Hash de cada arquivo local é verificado antes do mapeamento; o fingerprint do blueprint vincula atribuição/revisão às chamadas de inferência. Isso detecta corrupção local e mistura acidental de modelos. Não há prova Merkle do intervalo contra o hash completo do provedor nem prova de execução neural.

Somente o operador local pode trocar o modelo global; exige ausência de sessões/agentes e bloqueia novas gerações até fim ou recuperação. A transação registra intenção, partições anteriores e seleção persistida. Falha de restauração deixa inferência bloqueada. A recuperação explícita revalida os fingerprints das partições anteriores. Orçamentos de memória são estimativas de participantes autorizados; um peer hostil pode mentir. Não anunciar proteção Sybil/consenso nem garantias de disponibilidade.

Configuração remota do worker deve conter só segredo de transporte, endpoints públicos/privados autorizados e seu próprio arquivo de identidade, além das chaves públicas necessárias. Não copiar o arquivo de configuração do coordenador contendo user_token/accounts nem sua chave privada. O CLI de worker não exige tokens de usuários. Cada máquina deve proteger seu cache e diretório de execução. O preparador legado prepare pode usar pickle local seguro de PyTorch e checkpoint inteiro; não usá-lo para instalar modelos grandes em participantes.
