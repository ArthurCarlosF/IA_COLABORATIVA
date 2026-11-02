# Dois computadores físicos — procedimento ainda não executado

Pré-condições: duas máquinas sob controle do usuário, acesso autorizado, Python 3.11, rede privada/VPN e certificados assinados por uma CA confiável, com SANs dos nomes/IPs usados. Não desativar validação TLS. Não abrir portas no roteador. Não alterar firewall sem autorização específica.

Exemplo de topologia: máquina A contém coordenador e worker-0; máquina B contém worker-1. Endereços e caminhos abaixo são exemplos, substituir pelos reais.

## Preparação

1. Em A, preparar o checkpoint e executar `mesh init` como no README.
2. Em B, instalar as dependências. Copiar código `mesh/`, `requirements.txt` e **somente** `data/model/part-1/`. B não precisa das demais camadas nem do tokenizer. Para simplificar, mantenha a pasta com o mesmo caminho relativo.
3. Em A e B, configurar `runtime/config.json` com o mesmo cluster_secret e mapeamento de endpoints. O token do usuário só é necessário ao coordenador; na configuração B pode ser uma string aleatória de 32+ caracteres, não usada pelo worker.

```json
{
  "cluster_secret": "SEGREDO_ALEATORIO_DE_64_CARACTERES",
  "user_token": "TOKEN_ALEATORIO_DE_64_CARACTERES",
  "coordinator": "https://maquina-a:8000",
  "workers": {
    "worker-0": "https://maquina-a:8100",
    "worker-1": "https://maquina-b:8101"
  }
}
```

Não usar literalmente esses placeholders. Proteger arquivos com permissões de acesso adequadas. Copiar pesos e segredos somente por canal seguro e autorizado. Coordenador A precisa do tokenizer, manifesto, configuração do modelo e partições para calcular os hashes de referência no início.

## Inicialização

Na máquina A:

```powershell
.\.venv\Scripts\python -m mesh coordinator --host IP_PRIVADO_A --cert tls/a.pem --key tls/a-key.pem --ca tls/ca.pem
.\.venv\Scripts\python -m mesh worker --id worker-0 --part 0 --host IP_PRIVADO_A --cert tls/a.pem --key tls/a-key.pem --ca tls/ca.pem
```

Na máquina B:

```powershell
.\.venv\Scripts\python -m mesh worker --id worker-1 --part 1 --host IP_PRIVADO_B --cert tls/b.pem --key tls/b-key.pem --ca tls/ca.pem
```

Usar IP específico de interface privada, não 0.0.0.0. O programa exige HTTPS para URLs remotas e certificado/chave ao escutar fora de loopback. Não modifica firewall. O navegador deve confiar na CA de forma aprovada pelo administrador; não contornar avisos de segurança.

## Critérios de validação física

- Abrir https://maquina-a:8000 e ver ambos os workers online com recursos e camadas diferentes.
- Enviar pergunta e registrar streaming, tokens/s e créditos dos dois workers.
- Em A, executar `python tools/verify_remote.py --config runtime/config.json --ca tls/ca.pem --output runtime/physical-evidence.json` com HF_HOME correto. O script requer o checkpoint de referência já no cache local.
- Interromper o processo worker-1 e verificar erro explícito, liberação do cache acessível e recusa 503 após o heartbeat expirar. Reiniciar e confirmar nova geração.
- Desconexão física da rede deve ser testada pelo responsável pela máquina, para não cortar o próprio acesso administrativo.
- Registrar CPU/GPU, RAM/VRAM, sistema operacional, RTT e resultados. Somente então marcar etapa física concluída.

Limitação atual: confiança compartilhada de cluster, um usuário, sem mTLS/atestado de execução. Adequado à validação em máquinas próprias; não a uma rede pública hostil.
