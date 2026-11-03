# Inferência por blocos com retomada

O perfil **Qwen3-Coder-480B-A35B-Instruct** usa atenção, roteadores e especialistas MoE. Seu índice público tem 30.321 tensores em 241 arquivos. O adaptador usa o [checkpoint e a configuração oficiais da Qwen](https://huggingface.co/Qwen/Qwen3-Coder-480B-A35B-Instruct), com revisão fixa.

Há dois modos complementares:

- **Rede com partes residentes:** cada computador baixa as linhas de matrizes e os especialistas que lhe foram atribuídos. O coordenador transmite ativações, reúne resultados parciais e despacha somente os especialistas escolhidos. A atenção e o KV ficam no worker correspondente. O padrão dos perfis grandes em grafo limita cada participante a 1 bilhão de parâmetros de pesos FP32, além da memória necessária para execução.
- **Modo lento com pesos em trânsito:** o programa executa o grafo em um computador, ou entrega pequenas multiplicações a executores configurados. Ele lê somente as linhas **e colunas** necessárias à operação atual por HTTP Range. Não mantém o checkpoint inteiro no disco ou em RAM. SQLite em WAL guarda a próxima coluna, a soma parcial, os tokens produzidos e o cache de atenção. O mesmo diretório pode continuar depois de fechar o processo ou reiniciar.

O limite de memória dos blocos cobre arrays de cálculo. O Python, as bibliotecas, a conexão HTTPS, os metadados e o contexto/KV exigem memória adicional. Buscar novamente pesos e gravar checkpoints aumenta muito o tempo e o tráfego.

## Planejar o 480B sem baixar pesos

```powershell
.\.venv\Scripts\python -m mesh plan-model --model-profile coder-480b --parts 1024 --max-parameters 1000000000 --root runtime/plans/coder-480b-1024
```

O plano gera um assignment por participante. Use os comandos de rede e TLS descritos em MODELOS.md. Os planos de 512, 1.024 e 4.096 participantes foram calculados com o índice real, sem provisionar pesos. A divisão tem 10.074 operações internas. A maior atribuição tem, respectivamente, 943.841.280, 471.920.640 e 163.584.256 parâmetros. O planejador é heurístico e a memória precisa acomodar a parte de cada participante. A rede física com milhares de computadores ainda não foi validada.

## Iniciar, pausar e retomar na interface

Inicie `run-coder.ps1` e abra `http://127.0.0.1:8400` com o token do operador local. Ao lado de **Parar** no chat, abra **Modo lento**. Escolha o modelo, escreva a pergunta e defina quantos blocos o lote pode calcular (1 a 1.024). Para uma primeira leitura parcial do 480B, use um bloco.

**Pausar** sinaliza o subprocesso para parar numa fronteira segura. **Executar próximo lote** continua o mesmo trabalho. Fechar a janela permite que o lote siga até atingir o limite. Após reiniciar o coordenador, reabra o trabalho no histórico e inicie outro lote. A tela mostra a posição, a saída acumulada e as métricas do último lote terminado. Mantenha a pasta `runtime/network/coordinator/runtime/slow-jobs` em disco local e privada.

Este painel executa localmente na CPU, em subprocesso separado. Há um lote por coordenador de cada vez. A seleção do painel é independente do checkpoint ativo no chat, e a execução local tem contabilidade separada. Para usar executores de blocos configurados em outros computadores, use a CLI abaixo.

## Iniciar, pausar e retomar pela CLI

Experimento limitado a **um bloco**, para conferir a leitura parcial:

```powershell
.\.venv\Scripts\python -m mesh slow-run --model-profile coder-480b --job runtime/slow-480b --prompt "Olá" --tokens 1 --tile-rows 4 --tile-columns 64 --max-tiles 1
.\.venv\Scripts\python -m mesh slow-run --job runtime/slow-480b --max-tiles 1
```

A segunda invocação continua o mesmo trabalho. Sem `--max-tiles`, prossegue até o fim dos tokens solicitados ou até `Ctrl+C`, que pede pausa na próxima fronteira segura. Se o processo cair antes de confirmar um bloco, só aquele cálculo pendente poderá ser repetido. A soma parcial e a coluna seguinte são gravadas juntas.

Não há expiração por duração. Preserve a pasta do trabalho, o ambiente numérico e o acesso à revisão dos pesos. Uma pausa de um ano não foi testada; a retomada de processo foi. A quantidade de tokens/contexto continua limitada pelo motor. Saídas intermediárias e KV consomem disco conforme a tarefa progride.

`last-result.json` informa se terminou ou pausou, posição, tokens e bytes de pesos lidos nessa invocação. `source_weight_bytes` exclui metadados e tokenizer. O modo lento não debita nem distribui créditos de rede nesta fase.

## Dividir pequenos cálculos entre aparelhos

O serviço `tile-worker` recebe somente uma multiplicação FP32 pequena. Não importa PyTorch e não instala um modelo.

```powershell
.\.venv\Scripts\python -m mesh tile-init --config runtime/tile/config.json
.\.venv\Scripts\python -m mesh tile-worker --config runtime/tile/config.json --tile-kib 2 --port 8600
```

Para usar esse executor num trabalho novo:

```powershell
.\.venv\Scripts\python -m mesh slow-run --model-profile coder-480b --job runtime/slow-offload --prompt "Olá" --tokens 1 --tile-rows 4 --tile-columns 64 --tile-kib 2 --max-tiles 1 --tile-endpoint http://127.0.0.1:8600 --tile-config runtime/tile/config.json
```

Repita `--tile-endpoint` para mais executores. O programa alterna os endpoints e tenta outro participante autorizado se não receber uma resposta válida. Na retomada, informe novamente `--tile-config`; o segredo não fica no checkpoint. Use TLS e certificados confiáveis para conexões fora de loopback (`--cert`, `--key` no executor e `--ca` no solicitante). O segredo do executor é separado das credenciais de chat.

### Protocolo para portar a ESP32 e celular

`POST /tile/matmul`, versão 1. A mensagem JSON contém `version`, `maximum_bytes`, `inputs` e `weights`. Cada matriz contém `shape` com duas dimensões e `data`, bytes FP32 little-endian em base64. O cálculo é `inputs[M,K] × weights[N,K]ᵀ`, retornando `tensor[M,N]` e `working_bytes`. O limite dos arrays é `4 × (M×K + N×K + 4×M×N)` bytes, separado do transporte. Entradas e resultados devem ser finitos.

O pedido usa `X-Time` em segundos Unix e `X-Signature` HMAC-SHA256 em hexadecimal sobre os bytes `timestamp + "." + corpo`; a janela é de 30 segundos. `X-Tile-Receipt` assina `sha256_hex(corpo_do_pedido) + "." + corpo_da_resposta`. O transporte remoto exige HTTPS. A assinatura autentica a resposta, mas não prova que uma máquina hostil calculou corretamente.

Já existe o executor de referência para computadores e um ensaio com um bloco de 1.344 bytes de arrays. Ainda não há firmware ESP32, aplicativo celular nem teste em placa/aparelho físico. Esses adaptadores podem implementar o protocolo sem carregar o modelo, o tokenizer ou o KV. O computador que coordena o trabalho conserva o estado global.

## O que foi demonstrado

- **Painel, via HTTP:** um novo trabalho real do 480B confirmou um bloco por lote e retomou da coluna 4.096 até a 6.144 da primeira projeção. A carteira do chat ficou intacta. Um pedido de pausa durante outro lote confirmou mais dois blocos antes de parar. Nenhum token completo foi produzido.
- **480B real, parcial:** dois blocos da mesma matriz calculados em duas invocações. O SQLite avançou de 64 para 128 colunas. Cada invocação leu 25.088 bytes de pesos (embedding, normalização e bloco da matriz). Nenhuma resposta completa do 480B foi gerada.
- **Dois executores leves:** os mesmos dois blocos reais do 480B foram enviados a dois processos HTTP separados, um bloco por processo. Cada bloco ocupou 1.344 bytes de arrays, sob orçamento de 2 KiB. A soma parcial foi idêntica bit a bit à execução local. Foram lidos 25.600 bytes de pesos nessa invocação. Para repetir, use `tools/verify_real_tiles.py --job PASTA` e uma referência local parada em exatamente dois blocos.
- **Grafo MoE pequeno sintético:** dois processos worker HTTP reais, quatro passos, erro máximo dos logits de aproximadamente 2,24×10⁻⁸ contra Transformers 4.51.3. Isso verifica a matemática e o transporte, não a qualidade do 480B.
- **Geração lenta pequena sintética:** duas pausas e retomadas; quatro tokens finais iguais à referência. Reabrir o trabalho já concluído não voltou a buscar pesos.
- **Interrupção de processo:** uma matriz retomou da coluna já confirmada após saída abrupta; o resultado correspondeu à multiplicação completa. Erros de integridade e orçamento insuficiente foram recusados.

Os modelos 72B e 480B ainda precisam de validação integral em hardware real. Não é possível inferir desempenho ou tempo final a partir dos ensaios acima.
