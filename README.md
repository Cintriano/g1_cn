# G1 – Sistema de mensagens distribuído (Flask + Docker Compose)

Três containers da **mesma imagem** (`app1`, `app2`, `app3`) trocam mensagens
entre si e gravam seus logs em um **volume compartilhado**.

## Estrutura
| Arquivo | Função |
|---|---|
| `app.py` | API REST (Flask): envio, replicação, consulta e verificação |
| `Dockerfile` | Imagem enxuta (`python:3.12-slim`), expõe a porta 5000 |
| `docker-compose.yml` | 3 instâncias, volume `messages_data`, rede bridge `msgnet` |
| `requirements.txt` | Apenas `Flask`, `requests` e `gunicorn` |
| `test.sh` | Roteiro de teste do exemplo do enunciado |

## Como executar
```bash
docker compose up -d --build
./test.sh                       # ou os curls abaixo
docker compose down             # (use -v para apagar o volume)
```

## Endpoints
| Método | Rota | Descrição |
|---|---|---|
| POST | `/send` | Recebe `{"message": "..."}`, grava localmente e replica para os 2 peers |
| GET | `/messages` | Devolve as mensagens do log da própria instância |
| POST | `/replicate` | **Interno**: recebe a cópia de outro container; só grava, não repropaga |
| GET | `/verify` | Compara os ids deste log com os dos peers (`consistent: true/false`) |
| GET | `/health` | Healthcheck |

```bash
curl -X POST -H "Content-Type: application/json" -d '{"message":"hello"}' http://localhost:5001/send
curl http://localhost:5002/messages
curl http://localhost:5003/verify
```

## Decisões de projeto
- **Replicação sem loop:** `/send` replica via `/replicate`, que apenas grava.
  Se os peers reenviassem para `/send`, a mensagem circularia indefinidamente.
- **Idempotência:** cada mensagem tem um `id` (UUID); `/replicate` ignora ids já gravados.
- **Um log por container** no volume (`/data/app1.log`, `app2.log`, `app3.log`),
  em JSON Lines, com `flock` + lock de thread para evitar escrita concorrente corrompida.
- **Comunicação entre containers** usa o nome do serviço e a porta *interna*
  (`app2:5000`), não as portas publicadas (5001–5003), que valem só para o host.
- **Tolerância a falhas:** `timeout` de 3 s e `try/except` nas chamadas aos peers;
  se um peer estiver fora, o `/send` ainda responde 201 e indica a falha em `replication`.
  O `/verify` mostrará `consistent: false` até o peer ser reconciliado.
- **Boas práticas Docker:** só as dependências necessárias, `.dockerignore`,
  execução com usuário não-root, healthcheck, `gunicorn` em vez do servidor de desenvolvimento,
  configuração por variáveis de ambiente (`INSTANCE_NAME`, `PEERS`, `DATA_DIR`).
