#!/usr/bin/env python3
import socket, json, time, sys
BROKER = "10.0.0.2"
PORTS = {"sports": 5001, "weather": 5002, "news": 5003}
topic = sys.argv[1]
count = int(sys.argv[2]) if len(sys.argv) > 2 else 100
interval = float(sys.argv[3]) if len(sys.argv) > 3 else 0.1
s = socket.create_connection((BROKER, PORTS[topic]))
s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
for i in range(count):
    m = {"type": "PUBLISH", "topic": topic, "seq": i, "ts": time.time(), "payload": f"{topic} msg {i}"}
    s.sendall((json.dumps(m) + "\n").encode())
    time.sleep(interval)
s.close()
print(f"published {count} messages on {topic}")
