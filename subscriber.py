#!/usr/bin/env python3
import socket, json, time, sys, threading
BROKER, PORT = "10.0.0.2", 5000
name = sys.argv[1]; topics = sys.argv[2:]
s = socket.create_connection((BROKER, PORT))
s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
def send(typ, topic):
    s.sendall((json.dumps({"type": typ, "topic": topic}) + "\n").encode())
for t in topics: send("SUBSCRIBE", t)
def commands():
    for line in sys.stdin:
        p = line.split()
        if len(p) == 2 and p[0] in ("sub", "unsub"):
            send("SUBSCRIBE" if p[0] == "sub" else "UNSUBSCRIBE", p[1])
threading.Thread(target=commands, daemon=True).start()
out = open(f"/tmp/{name}_latency.csv", "w"); out.write("recv_time,topic,seq,latency_ms\n")
lats = {}
try:
    for raw in s.makefile('rb'):
        now = time.time(); m = json.loads(raw)
        lat = (now - m["ts"]) * 1000
        lats.setdefault(m["topic"], []).append(lat)
        out.write(f"{now},{m['topic']},{m['seq']},{lat:.3f}\n"); out.flush()
        print(f"[{name}] {m['topic']} #{m['seq']}  {lat:.2f} ms", flush=True)
except KeyboardInterrupt:
    pass
print("\n--- latency summary ---")
for t, v in lats.items():
    print(f"{t}: n={len(v)} avg={sum(v)/len(v):.2f} ms min={min(v):.2f} max={max(v):.2f}")
