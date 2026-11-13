#!/usr/bin/env python3
import socket, json, time, sys, threading
BROKER, PORT = "10.0.0.2", 5000
n = int(sys.argv[1]); topic = sys.argv[2]; duration = float(sys.argv[3])
lats = []; lock = threading.Lock(); stop = time.time() + duration
def sub():
    try:
        s = socket.create_connection((BROKER, PORT))
        s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        s.sendall((json.dumps({"type": "SUBSCRIBE", "topic": topic}) + "\n").encode())
        s.settimeout(1.0); buf = b""
        while time.time() < stop:
            try: data = s.recv(65536)
            except socket.timeout: continue
            if not data: break
            buf += data
            *lines, buf = buf.split(b"\n")
            now = time.time()
            with lock:
                for l in lines:
                    if l: lats.append((now - json.loads(l)["ts"]) * 1000)
        s.close()
    except OSError:
        pass
ts = [threading.Thread(target=sub) for _ in range(n)]
for t in ts: t.start()
for t in ts: t.join()
lats.sort()
if lats:
    avg = sum(lats) / len(lats); p95 = lats[int(0.95 * (len(lats) - 1))]; mx = lats[-1]
    print(f"subscribers={n} received={len(lats)} avg={avg:.2f}ms p95={p95:.2f}ms max={mx:.2f}ms")
    with open("results.csv", "a") as f:
        f.write(f"{n},{topic},{len(lats)},{avg:.2f},{p95:.2f},{mx:.2f}\n")
else:
    print("no messages received")
