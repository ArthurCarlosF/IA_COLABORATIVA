# Modelos por partição e troca real

**Atualização:** [modo lento e grafo interno](docs/MODO-LENTO.md) descreve a divisão de matrizes/especialistas, o perfil Qwen3-Coder-480B e a retomada durável. O perfil 480B está disponível para preparar em uma rede com orçamento suficiente; apenas blocos parciais desse checkpoint foram executados nesta etapa.

O objetivo é executar um único checkpoint maior que a capacidade individual dos participantes. Cada máquina mantém somente seus pesos e KV cache. O coordenador guarda configurações, tokenizer, nomes/formatos/intervalos dos tensores e atribuições, não precisa guardar todos os pesos.

## Seleção na interface

O seletor abaixo da mensagem oferece perfis com revisão fixa: Qwen2.5-Coder 0,5B, 1,5B e 32B, Qwen2.5 geral 0,5B e 72B e Qwen3-Coder-480B. Os modelos ausentes aparecem como “preparar na rede”. Somente o operador local pode alterar o checkpoint global. Nesta versão a rede executa um checkpoint por vez; não há pools de modelos simultâneos.

O painel **Modo lento** tem seleção própria. Um trabalho local carrega pesos por pequenos intervalos e mantém a revisão escolhida ao retomar. Escolher um modelo nesse painel não ativa o checkpoint para o chat distribuído.

Escolher um perfil inicia uma tarefa de preparação. A rede exige que todas as sessões e agentes estejam encerrados, consulta recursos dos workers e calcula partições contíguas conforme o orçamento disponível. RAM do mesmo host e VRAM do mesmo dispositivo não devem ser contadas novamente por processo. Estimativas reservam margem para execução; não são garantia contra mudanças de uso dos outros programas ou falhas do hardware.

Se não couber, a troca é recusada antes de baixar pesos. Se couber, cada worker recebe apenas seu assignment e busca os intervalos HTTP correspondentes aos seus tensores. Respostas HTTP que tentem entregar um arquivo inteiro são recusadas sem consumir o corpo. Blocos de transferência limitados a 8 MiB são convertidos para FP32 e gravados diretamente em arquivos locais. Não há AutoModelForCausalLM completo neste fluxo. Mesmo um arquivo safetensors de origem que contenha várias partições é acessado somente pelos intervalos necessários.

Os workers preparam em disco antes de ativar. A geração fica bloqueada durante a transação. Depois da preparação, cada worker descarrega a partição anterior e carrega sua nova partição por mapeamento de arquivos, mantendo o resto do modelo nos outros computadores. Mensagens de inferência vinculam o fingerprint da partição; a geração recomeça com KV novo após a troca. Falha na ativação dispara retorno às partições anteriores. Se não for possível restaurar todos, o serviço bloqueia inferência e oferece recuperação explícita. Journal e seleção persistem; aprovações/tarefas de agente não são retomadas automaticamente.

## Planejar um modelo grande sem instalar seus pesos

```powershell
.\.venv\Scripts\python -m mesh plan-model --model-profile coder-32b --parts 32 --root runtime/plans/coder-32b
```

Esse comando consulta configurações, índice e cabeçalhos dos safetensors e salva somente metadados/tokenizer. Gera manifest.json e assignment-0.json até assignment-31.json. Não cria pesos nem carrega a rede completa. Opcionalmente use --memory-mb com os orçamentos de pesos separados por vírgulas para ajustar as divisões. A estimativa usa FP32, sem quantização.

Para execução física, configure o coordenador com exatamente os endpoints/identidades dos workers do plano e certificados HTTPS válidos em LAN/VPN. Inicie o coordenador com --root apontando para a pasta de metadados. Cada participante recebe somente seu assignment-N.json e uma configuração de worker, sem tokens de usuários nem chave privada do coordenador:

```powershell
python -m mesh worker --id worker-7 --part 7 --assignment assignment-7.json --config worker-config.json --ca ca.pem --cert worker.pem --key worker-key.pem --host ENDERECO_PRIVADO --port PORTA
```

Os argumentos ENDERECO_PRIVADO/PORTA são exemplos a substituir. Cada máquina usa seu próprio diretório de execução, venv, cache e identidade. O worker baixa somente a atribuição local para runtime/model-parts. O coordenador não distribui um arquivo de pesos inteiro. Outros participantes não precisam instalar o checkpoint global. Configuração inicial da rede/certificados continua a cargo do operador; ainda não há adesão pública automática, NAT/DHT nem consenso de créditos.

O lançador run-coder.ps1 continua sendo validação local com dois processos, não uma rede de dois computadores físicos. Em instalações novas ele usa o plano por metadados e atribuições por worker. O comando prepare antigo permanece para regressões pequenas e pode baixar/carregar um modelo inteiro: não o use para modelos grandes. Modelos já preparados pelo caminho antigo continuam compatíveis.

## Resultados e limites atuais

- Troca real executada de Qwen2.5-Coder-0.5B-Instruct para Qwen2.5-0.5B-Instruct, com camadas 0–11 no primeiro worker e 12–23 no segundo. Cada worker buscou aproximadamente 601 MiB da origem e gravou aproximadamente 1,17 GiB FP32. O novo modelo gerou “2+2 equals 4.” pela rede.
- Planejamento real do Coder 32B com 32 partições: aproximadamente 122,05 GiB FP32 no total, partições entre 3,63 e 6,53 GiB, antes de runtime/KV. A pasta do plano ocupou 11,31 MiB e continha zero arquivos de pesos. A fonte foi acessada somente para metadados.
- Pedido de troca para 32B nos dois workers atuais foi recusado por memória insuficiente. Nenhuma nova partição foi baixada; checkpoint ativo e consumo de créditos foram preservados.
- 32B e 72B não foram executados. Não existe segundo computador físico nesta sessão. Listar um perfil ou gerar seu plano não demonstra sua inferência, velocidade nem qualidade.
- Execução atual usa FP32, contexto de até 4096 tokens e saída de até 512 no Qwen; KV por worker tem orçamento próprio. Quantização, transporte comprimido, contexto ampliado, GPU/heterogeneidade e testes físicos ainda precisam de trabalho/validação.

Arquiteturas suportadas: Qwen2 sem sliding window e o grafo Qwen3 MoE do perfil autorizado, com revisões fixas. 72B e 480B usam o grafo no planejamento padrão; outros Qwen2 podem usar a opção --graph. Arquiteturas diferentes exigem adaptadores. Hashes locais detectam corrupção; HTTPS e intervalos validados protegem o transporte. Não há prova Merkle dos intervalos contra o hash do checkpoint completo, prova de correção neural, privacidade contra workers hostis nem segurança pública sem confiança.

Um modelo maior não implica equivalência ao Codex. Qualidade precisa de tarefas e avaliações comparáveis. O agente de ferramentas continua experimental; os sucessos de troca, distribuição e transporte não substituem a avaliação da sua autonomia.

Reinício real após seleção: o Qwen geral escolhido foi preservado e os dois workers voltaram usando suas próprias partições mapeadas. Créditos/ganhos e reservas foram preservados; pedido com identificador do checkpoint antigo retornou 409. A pasta selecionada do coordenador continha zero arquivos de pesos. Evidência: runtime/network/model-persistence-evidence.json. Sem novo download integral nem carga de referência para reiniciar. JavaScript passou em node --check; inspeção visual segue não realizada.

Para repetir uma troca pela API: `python tools/switch_model.py --profile coder-0.5b --prompt "What is 2+2?"`. O helper registra job e geração em runtime/model-switch-report.json; exige um perfil diferente do atual. Sua ajuda e sintaxe foram verificadas; a demonstração real desta etapa foi feita diretamente nas mesmas APIs.
