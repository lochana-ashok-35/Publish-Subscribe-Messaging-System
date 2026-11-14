#!/usr/bin/env python3
import socket, threading, json, time, os, sys
from collections import deque
SUB_PORT = 5000
PUB_PORTS = [5001, 5002, 5003]          # sports, weather, news
ADAPTIVE = "--adaptive" in sys.argv     # application-driven rerouting
HIGH_MS = 60.0                          # publisher->broker latency threshold
REQUEST_FILE = "/tmp/topic_paths.json"
subs = {}
lock = threading.Lock()
recent = {}
requested = set()

def forward(topic, raw):
    with lock:
        dead = []
        for s in subs.get(topic, set()):
            try: s.sendall(raw)
            except OSError: dead.append(s)
        for s in dead:
            for group in subs.values(): group.discard(s)

def request_alt(topic, avg):
    if topic in requested: return
    requested.add(topic)
    try:
        try:
            with open(REQUEST_FILE) as f: cfg = json.load(f)
        except Exception:
            cfg = {}
        cfg[topic] = "alt"
        tmp = REQUEST_FILE + ".tmp"
        with open(tmp, "w") as f: json.dump(cfg, f)
        os.chmod(tmp, 0o666)
        os.replace(tmp, REQUEST_FILE)
        print(f"[broker] latency on {topic} is {avg:.0f} ms -> requesting alternate path", flush=True)
    except OSError as e:
        print(f"[broker] could not write request: {e}", flush=True)

def monitor(topic, msg):
    d = recent.setdefault(topic, deque(maxlen=5))
    d.append((time.time() - msg["ts"]) * 1000)
    if len(d) == 5 and sum(d) / 5 > HIGH_MS:
        request_alt(topic, sum(d) / 5)

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
                if ADAPTIVE: monitor(topic, msg)
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
print("[broker] listening on 5000 (subscribers), 5001-5003 (publishers)"
      + (" [adaptive]" if ADAPTIVE else ""), flush=True)
threading.Event().wait()
