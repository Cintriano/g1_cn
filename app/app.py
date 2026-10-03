import fcntl
import json
import os
import threading
import uuid
from datetime import datetime, timezone

import requests
from flask import Flask, jsonify, request

app = Flask(__name__)

INSTANCE = os.environ.get("INSTANCE_NAME", "app")
PEERS = [p.strip() for p in os.environ.get("PEERS", "").split(",") if p.strip()]
DATA_DIR = os.environ.get("DATA_DIR", "/data")
LOG_FILE = os.path.join(DATA_DIR, f"{INSTANCE}.log")
TIMEOUT = float(os.environ.get("PEER_TIMEOUT", "3"))

os.makedirs(DATA_DIR, exist_ok=True)
_lock = threading.Lock()


def read_messages():
    """Lê todas as mensagens do log desta instância."""
    if not os.path.exists(LOG_FILE):
        return []
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def store(msg):
    """Grava a mensagem no log (ignora duplicadas pelo id).

    Retorna True se gravou, False se já existia.
    """
    with _lock:
        if any(m["id"] == msg["id"] for m in read_messages()):
            return False
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            f.write(json.dumps(msg, ensure_ascii=False) + "\n")
            f.flush()
            fcntl.flock(f, fcntl.LOCK_UN)
        return True


@app.get("/health")
def health():
    return jsonify(status="ok", instance=INSTANCE)


@app.post("/send")
def send():
    """Recebe a mensagem, grava localmente e replica para os peers."""
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or not str(body.get("message", "")).strip():
        return jsonify(error='JSON inválido: envie {"message": "texto"}'), 400

    msg = {
        "id": str(uuid.uuid4()),
        "message": body["message"],
        "origin": INSTANCE,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    store(msg)

    # Replica para os outros containers via endpoint interno /replicate
    # (que só grava e NÃO replica de novo -> evita loop infinito).
    replication = {}
    for peer in PEERS:
        try:
            r = requests.post(f"http://{peer}/replicate", json=msg, timeout=TIMEOUT)
            replication[peer] = "ok" if r.ok else f"erro HTTP {r.status_code}"
        except requests.RequestException as exc:
            replication[peer] = f"falha: {type(exc).__name__}"

    return jsonify(status="stored", id=msg["id"], instance=INSTANCE,
                   replication=replication), 201


@app.post("/replicate")
def replicate():
    """Endpoint interno: recebe cópia de outra instância. Não repropaga."""
    msg = request.get_json(silent=True)
    if not isinstance(msg, dict) or "id" not in msg or "message" not in msg:
        return jsonify(error="mensagem inválida"), 400
    created = store(msg)
    return jsonify(status="stored" if created else "duplicate"), 200


@app.get("/messages")
def messages():
    """Retorna todas as mensagens armazenadas por esta instância."""
    msgs = read_messages()
    return jsonify(instance=INSTANCE, count=len(msgs), messages=msgs)


@app.get("/verify")
def verify():
    """Compara o conjunto de ids deste log com o de cada peer."""
    mine = {m["id"] for m in read_messages()}
    report, consistent = {}, True
    for peer in PEERS:
        try:
            r = requests.get(f"http://{peer}/messages", timeout=TIMEOUT)
            theirs = {m["id"] for m in r.json()["messages"]}
            missing_there = sorted(mine - theirs)
            missing_here = sorted(theirs - mine)
            ok = not missing_there and not missing_here
            report[peer] = {"ok": ok, "count": len(theirs),
                            "missing_in_peer": missing_there,
                            "missing_here": missing_here}
        except (requests.RequestException, ValueError, KeyError) as exc:
            ok = False
            report[peer] = {"ok": False, "error": type(exc).__name__}
        consistent &= ok
    return jsonify(instance=INSTANCE, count=len(mine),
                   consistent=consistent, peers=report)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
