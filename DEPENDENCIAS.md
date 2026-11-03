# Dependências e instalação

O executor de microblocos para computadores pode ser instalado separadamente com requirements-tile.txt, sem Torch ou Transformers. Ele precisa de Python, NumPy e bibliotecas HTTP. ESP32 e celular ainda exigem adaptadores próprios; não instalar o ambiente Python principal nesses aparelhos como se já fossem suportados. Para a comparação MoE de desenvolvimento, use um ambiente isolado com Transformers 4.51.3 e tools/make_moe_reference.py. O runtime principal continua em 4.44.2.

A plataforma é independente de Codex e Claude. Quem já usa esses assistentes pode utilizá-los para ajudar na instalação ou no desenvolvimento, mas eles são opcionais: não fornecem os pesos do modelo, não substituem Python/Docker e não são chamados pela inferência desta plataforma. Nenhuma chave de API de IA é necessária para o perfil local.

## Obrigatórias

- Python 3.11 de 64 bits, com pip e venv. Windows é o ambiente validado nesta etapa.
- Navegador atualizado para a interface.
- Git para clonar/atualizar, ou baixar ZIP do repositório.
- Internet na instalação para dependências e checkpoint; depois de preparado, o perfil usa pesos locais. Não promete instalação desconectada sem cache prévio.
- Espaço em disco para ambiente, download original e partições; o fluxo novo baixa só a partição de cada worker e grava FP32; reserve espaço para essa partição. O prepare legado carrega o modelo inteiro e é apenas diagnóstico pequeno. Reserve alguns GB para o perfil de 0,5B e acompanhe a memória disponível. O computador de validação tem 32 GB; isso não estabelece requisito mínimo universal.
- Bibliotecas e versões em requirements.txt: PyTorch, Transformers, FastAPI, Uvicorn, HTTPX, psutil, cryptography, tzdata e pytest. requirements-dev.txt acrescenta dependências de desenvolvimento.

Não atualize Transformers isoladamente sem executar as regressões: os adaptadores de camadas/KV dependem das APIs da versão fixada. GPU é opcional no perfil CPU; execução com GPU e placas heterogêneas ainda não foi validada.

## Instalação Windows

```powershell
git clone https://github.com/ArthurCarlosF/IA_COLABORATIVA.git
cd IA_COLABORATIVA
py -3.11 -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
powershell -NoProfile -ExecutionPolicy Bypass -File .\run-coder.ps1
```

Na primeira execução o lançador planeja Qwen2.5-Coder-0.5B-Instruct na revisão fixada e entrega uma atribuição a cada um dos dois workers, que baixam somente suas partes. Abra http://127.0.0.1:8400 e use o user_token do arquivo runtime/network/config.json. Esse arquivo é privado e nunca deve ser publicado. Workers locais em dois endereços/portas executam partes reais do mesmo modelo; isso valida processos separados, não dois computadores físicos. Dados e credenciais persistem em runtime/network.

## Opcionais

- Docker para unittest isolado. Prepare a imagem oficial python:3.11-slim; o lançador aceita somente ID local SHA-256 e exige uma execução restrita de prova; desabilita o executor quando a consulta ou execução falha. Limites, montagem somente leitura e rede desativada estão em mesh/workspace.py.
- Comandos no computador do solicitante: inicie run-coder.ps1 -AllowHostCommands. Cada comando proposto exige aprovação individual pela interface, com argumentos e pasta apresentados. Isso executa com os direitos do usuário, não é isolamento. Não habilita execução de comandos nos computadores de outros participantes. Desativado por padrão.
- Node.js para conferir sintaxe do JavaScript durante desenvolvimento; a aplicação não depende de um servidor Node.
- Codex/Claude como assistentes opcionais de desenvolvimento, sem integrar serviços pagos ao funcionamento.

## Outros computadores e modelos maiores

Cada participante executor precisa do worker, suas dependências, sua partição e configuração/identidade autorizada. Uma aba do navegador é um cliente, não substitui um worker Python. Para LAN use HTTPS com certificados confiáveis e VPN/rede privada conforme README e SECURITY.md. Ainda é necessário um operador para preparar a distribuição e configurar os participantes.

A seleção abaixo da caixa permite solicitar preparação e troca coordenada. Perfis ausentes são identificados; a inferência só usa o checkpoint ativo. Recursos insuficientes impedem baixar pesos. O adaptador suporta GPT-2 e Qwen2 sem sliding window. Arquiteturas diferentes, quantização, precisão reduzida continuam pendentes; o novo fluxo já planeja e baixa intervalos por participante sem carregar o checkpoint inteiro. O modelo de 0,5B é de validação e não foi demonstrado equivalente aos modelos do Codex. Um checkpoint maior só pode ser anunciado como funcional após download, capacidade agregada suficiente e testes reais.
