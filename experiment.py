#!/usr/bin/env python3
import os, sys, time, json, csv
from mininet.log import setLogLevel
from topo import build_net

BASE = os.path.dirname(os.path.abspath(__file__))
N_MSGS, INTERVAL = 200, 0.1          # 20 s of publishing
EVENT_AT, DRAIN = 5, 10              # event at t=5 s, then 10 s to drain
MODE_FILE, REQ_FILE = "/tmp/sdn_mode", "/tmp/topic_paths.json"
COMBOS = [("normal", "static"), ("normal", "dynamic"),
          ("congestion", "static"), ("congestion", "dynamic"), ("congestion", "app"),
          ("failure", "static"), ("failure", "dynamic")]

def write(path, text):
    with open(path, "w") as f: f.write(text)
    os.chmod(path, 0o666)

def analyse():
    try: rows = list(csv.DictReader(open("/tmp/exp_latency.csv")))
    except OSError: rows = []
    if not rows: return dict(received=0, avg=0, p95=0, mx=0, gap=0)
    lats = sorted(float(r["latency_ms"]) for r in rows)
    times = sorted(float(r["recv_time"]) for r in rows)
    gap = max((b - a for a, b in zip(times, times[1:])), default=0)
    return dict(received=len({int(r["seq"]) for r in rows}),
                avg=sum(lats) / len(lats), p95=lats[int(0.95 * (len(lats) - 1))],
                mx=lats[-1], gap=gap)

def cleanup(h):
    h.cmd('pkill -f subscriber.py; pkill -f publisher.py; pkill -f broker.py; pkill -f iperf')
    time.sleep(1)

def run_once(net, scenario, mode):
    h1, h2, h3 = net.get('h1', 'h2', 'h3')
    cleanup(h1)
    write(MODE_FILE, mode)
    write(REQ_FILE, json.dumps({t: "primary" for t in ("sports", "weather", "news")}))
    time.sleep(3)                                   # controller reads files every second
    if os.path.exists("/tmp/exp_latency.csv"): os.remove("/tmp/exp_latency.csv")
    flag = " --adaptive" if mode == "app" else ""
    h2.cmd(f'python3 {BASE}/broker.py{flag} < /dev/null > /tmp/exp_broker.out 2>&1 &')
    if scenario == "congestion":
        h2.cmd('iperf -s -p 9000 < /dev/null > /tmp/exp_iperf_s.out 2>&1 &')
    time.sleep(2)
    h3.cmd(f'python3 {BASE}/subscriber.py exp sports < /dev/null > /tmp/exp_sub.out 2>&1 &')
    time.sleep(1)
    start = time.time()
    h1.cmd(f'python3 {BASE}/publisher.py sports {N_MSGS} {INTERVAL} < /dev/null > /tmp/exp_pub.out 2>&1 &')
    time.sleep(EVENT_AT)
    if scenario == "congestion":
        h1.cmd('iperf -c 10.0.0.2 -p 9000 -t 12 < /dev/null > /tmp/exp_iperf_c.out 2>&1 &')
    elif scenario == "failure":
        net.configLinkStatus('s1', 's3', 'down')
        time.sleep(7)
        net.configLinkStatus('s1', 's3', 'up')
    time.sleep(max(0, N_MSGS * INTERVAL + DRAIN - (time.time() - start)))
    res = analyse()
    cleanup(h1)
    return res

def main():
    reps = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    setLogLevel('warning')
    net = build_net(); net.start(); time.sleep(5)
    if net.pingAll() > 0:
        print("pingall failed: is the controller (T1) running with no errors?")
        net.stop(); return
    out = os.path.join(BASE, "compare_raw.csv")
    with open(out, "w") as f:
        f.write("scenario,mode,rep,sent,received,delivery_pct,avg_ms,p95_ms,max_ms,max_gap_s\n")
    for scenario, mode in COMBOS:
        for rep in range(1, reps + 1):
            r = run_once(net, scenario, mode)
            pct = 100.0 * r["received"] / N_MSGS
            print(f"{scenario:10s} {mode:8s} rep{rep}: delivered={pct:5.1f}% avg={r['avg']:7.1f}ms "
                  f"p95={r['p95']:7.1f}ms max={r['mx']:8.1f}ms gap={r['gap']:5.2f}s", flush=True)
            with open(out, "a") as f:
                f.write(f"{scenario},{mode},{rep},{N_MSGS},{r['received']},{pct:.1f},"
                        f"{r['avg']:.1f},{r['p95']:.1f},{r['mx']:.1f},{r['gap']:.2f}\n")
    write(MODE_FILE, "dynamic")
    write(REQ_FILE, "{}")
    net.stop()
    print("done -> compare_raw.csv")

if __name__ == '__main__':
    main()
