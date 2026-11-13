#!/usr/bin/env python3
import socket, threading, json
SUB_PORT = 5000
PUB_PORTS = [5001, 5002, 5003]          # sports, weather, news
subs = {}                               # topic -> set of subscriber sockets
lock = threading.Lock()

def forward(topic, raw):
    with lock:
        dead = []
        for s in subs.get(topic, set()):
            try: s.sendall(raw)
            except OSError: dead.append(s)
        for s in dead:
            for group in subs.values(): group.discard(s)

def handle(conn, addr, port):
    print(f"[broker] connection from {addr[0]}:{addr[1]} on port {port}", flush=True)
    try:
        for raw in conn.makefile('rb'):
            try: msg = json.loads(raw)
            except ValueError: continue
            t = msg.get("type"); topic = msg.get("topic")
            if t == "SUBSCRIBE":
                with lock: subs.setdefault(topic, set()).add(conn)
                print(f"[broker] {addr[0]} subscribed to {topic}", flush=True)
            elif t == "UNSUBSCRIBE":
                with lock: subs.get(topic, set()).discard(conn)
                print(f"[broker] {addr[0]} unsubscribed from {topic}", flush=True)
            elif t == "PUBLISH":
                forward(topic, raw)
    except OSError:
        pass
    finally:
        with lock:
            for group in subs.values(): group.discard(conn)
        conn.close()

def serve(port):
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", port)); srv.listen(256)
    while True:
        c, a = srv.accept()
        c.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        threading.Thread(target=handle, args=(c, a, port), daemon=True).start()

for p in [SUB_PORT] + PUB_PORTS:
    threading.Thread(target=serve, args=(p,), daemon=True).start()
print("[broker] listening on 5000 (subscribers), 5001-5003 (publishers)", flush=True)
threading.Event().wait()
