#!/usr/bin/env bash
# Teste do fluxo do enunciado (rode depois de: docker compose up -d --build)
set -e
echo "1) POST /send na instância 1 (porta 5001)"
curl -s -X POST -H "Content-Type: application/json" \
     -d '{"message":"hello"}' http://localhost:5001/send; echo
sleep 1
for p in 5001 5002 5003; do
  echo "2) GET /messages na porta $p"; curl -s http://localhost:$p/messages; echo
done
echo "3) Verificação de replicação (/verify na 5002)"
curl -s http://localhost:5002/verify; echo
echo "4) Logs no volume compartilhado"
docker compose exec app1 sh -c 'ls -l /data && wc -l /data/*.log'
