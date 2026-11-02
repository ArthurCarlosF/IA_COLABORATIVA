# Como continuar

1. Leia AGENTS.md, ARCHITECTURE.md, PROGRESS.md e TEST_RESULTS.md.
2. Abra D:/Projetos/RedeInferencia. Se os serviços não estiverem ativos, execute run-local.ps1.
3. Abra http://127.0.0.1:8000; token está em runtime/config.json (não publicar esse arquivo).
4. Execute testes com HF_HOME apontando para data/hf e `.venv/Scripts/python -m pytest -q --basetemp=runtime/pytest`.
5. Para concluir a etapa física, obter endereço/acesso autorizado de uma segunda máquina e seguir DEPLOY_LAN.md. Não declarar essa etapa concluída antes do teste real.
6. Executar o verificador remoto `tools/verify_remote.py` no coordenador para comparar oito passos com o checkpoint local e obter métricas do chat. Salvar resultado e atualizar TEST_RESULTS.md.
7. Para melhorar respostas, adicionar adaptador de modelo pequeno instruído. tiny-gpt2 valida distribuição, não utilidade de conversação.

Estado de serviços desta sessão: lançador local iniciado com dois workers CPU em 8100/8101 e coordenador em 8000. Pode encerrar ao fim da sessão de execução; run-local.ps1 reabre tudo. Antes de reiniciar, verifique se a página ainda responde para evitar conflito de portas.

Não modificar outros projetos de D:/Projetos. Não reutilizar segredos do ambiente de testes em implantação externa. Não remover verificação TLS para fazer a LAN funcionar.

## Prioridade atual: computadores

O usuário corrigiu a referência ao celular: era de outro chat. Não desenvolver worker móvel agora. O ambiente com dois hosts lógicos está validado e pode ser repetido com `.venv/Scripts/python tools/simulate_hosts.py --serve`. Consultar SIMULATION.md. Para teste físico, obter um segundo computador e seguir DEPLOY_LAN.md.

## Estrutura base do repositório

Preparada publicação em ArthurCarlosF/IA_COLABORATIVA, com empacotamento Python, rotina de CI, premissas e limites de segurança. Dados de runtime, pesos, ambiente virtual e credenciais ficam ignorados. A execução de CI no GitHub só pode ser confirmada após a publicação e consulta ao resultado.

## Próxima sessão: carteira e política diária

Leia docs/CREDIT_PLAN.md. Funcionalidade implementada e validada com 43 testes; o painel novo tem somente checagem sintática, porque o navegador recusou acesso à demonstração. Não tentar contornar essa recusa. O usuário pode abrir localhost:8300 e conferir manualmente.

Iniciar demonstração: `.venv/Scripts/python tools/simulate_hosts.py --credits-demo --port 8300 --serve`. Caminho de configuração e relatório em runtime/simulation/latest.json. user_token autentica local-user; accounts.peer-user autentica peer-user. Não publicar esses tokens nem copiar config para o Git. A versão antiga em localhost:8000/8200, se ainda ativa, pode não conter o painel atualizado.

Continuar com avaliação visual autorizada, fila justa, identidade pública/consenso e modelo pequeno instruído. Não ativar remuneração por memória anunciada nem cadastro público sem verificação contra fraude. Não vender créditos: decisão explícita do usuário.
