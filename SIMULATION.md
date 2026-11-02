# Dois workers como hosts lógicos no mesmo computador

## Executar

```powershell
cd D:\Projetos\RedeInferencia
.\.venv\Scripts\python.exe tools/simulate_hosts.py --serve
```

O comando verifica as três portas antes de iniciar, cria uma pasta exclusiva de execução, configura certificados de teste locais, inicia os serviços, testa falha/reinício de um worker e compara logits com o modelo completo. Só apresenta VALIDADO se essas verificações passarem. `--serve` mantém os processos e o chat ativos; sem a opção, encerra os próprios serviços após validar. Ctrl+C encerra este ambiente.

| Serviço | Endereço | Trabalho |
|---|---|---|
| Coordenador/chat | http://127.0.0.1:8200 | Registro, encaminhamento e tokens |
| pc-a | https://127.0.0.2:8201 | Embeddings + camada 0 |
| pc-b | https://127.0.0.3:8202 | Camada 1 + normalização + cabeça |

Workers têm identidades, processos, sockets, cache e pastas próprios. Cada pasta worker contém apenas os pesos de sua parte. O coordenador conserva as referências do modelo na preparação/validação de hashes. O tráfego real de ativações passa por TCP/HTTPS. Não há resposta neural simulada.

Esses IPs são locais ao próprio computador. Não é necessário instalar placa virtual, configurar firewall, disponibilizar serviço na LAN ou instalar certificado na confiança global do sistema. O chat utiliza HTTP somente em loopback; os workers usam HTTPS com confiança explícita na CA de teste. Não acessar as URLs dos workers no navegador nem contornar alertas de certificado: elas são endpoints internos.

## Acessar esta execução

Chat: http://127.0.0.1:8200

Pasta: `D:/Projetos/RedeInferencia/runtime/simulation/20261102-150404-3782b3`

Token: campo `user_token` em `config.json` nessa pasta. Não compartilhar os segredos. A interface pede esse token e mostra pc-a/pc-b online. Para descobrir a pasta da execução mais recente, leia `runtime/simulation/latest.json`.

O painel registra uma falha intencional: o teste encerra pc-b para demonstrar a dependência de sua camada e depois o reinicia. Novas gerações após a recuperação devem terminar normalmente. O tiny-gpt2 gera texto repetitivo por ser um checkpoint de validação.

## Evidência

`report.json`: endpoints, PIDs dos serviços na inicialização, camadas, diretórios, rejeição TLS, falha induzida e resultados após reinício. `inference-evidence.json`: comparação de oito passos, chat e créditos. Logs separados por serviço ficam na pasta da execução.

Resultado executado: oito passos, erro máximo dos logits 0.0, geração de 12 tokens em 2.500 s e recuperação confirmada. O livro contém trabalho concluído antes da falha, além das gerações bem-sucedidas.

## Limites

São dois hosts **lógicos** no mesmo Windows, usando a mesma CPU e RAM físicas. Pastas diferentes não são uma barreira de acesso entre processos do mesmo usuário. Esta execução não valida redes físicas, isolamento de máquinas virtuais, velocidade entre computadores, GPUs nem escalabilidade. Para isso, repetir o protocolo em duas máquinas reais conforme DEPLOY_LAN.md.
