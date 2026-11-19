# Publish–Subscribe Messaging System over SDN

A TCP publish–subscribe system running on a Mininet network controlled by a Ryu OpenFlow controller. Each topic uses its own TCP port, so the controller can classify traffic by topic and move it between a fast primary path and a slower alternate path: on request, on link failure, on congestion, or when the broker asks for it.

**Course:** Computer Networks, Jackfruit SDN Mininet Project (Section H)

## Team

| Name | SRN |
|---|---|
| Lochana Ashok J | PES1UG25AM497 |
| Vignesh K S | PES1UG25AM447 |
| Dharshan N | PES1UG25AM483 |
| Kiran Kumar Melinamani | PES1UG25AM490 |

## Features

- TCP publisher, broker and subscribers built on low-level sockets, with newline-delimited JSON messages
- Topic-based delivery (sports, weather, news) and dynamic subscribe/unsubscribe at runtime
- Concurrent connections: one thread per connection and a lock on the subscriber table
- Per-topic traffic classification in the switches (TCP port 5001 = sports, 5002 = weather, 5003 = news)
- Manual path change for a topic while TCP connections stay open
- Automatic failover when the primary link goes down
- Congestion detection by port-statistics polling (reroute above 70% load, return below 30%)
- Application-driven rerouting: the adaptive broker requests the alternate path when latency is high
- Experiments comparing static routing with dynamic SDN, plus a scalability test up to 100 subscribers

## Architecture

```
Application layer : publisher (h1) -> broker (h2) -> subscribers (h3, h4)      [Python TCP sockets]
SDN control layer : Ryu controller (OpenFlow 1.3, 127.0.0.1:6653)
Data plane        : Mininet + Open vSwitch  s1, s2, s3
```

**Topology**

- h1 (publisher, 10.0.0.1), h3 and h4 (subscribers, 10.0.0.3 and 10.0.0.4) attach to s1
- h2 (broker, 10.0.0.2) attaches to s3
- Primary path: s1–s3, 5 ms, 10 Mbps
- Alternate path: s1–s2–s3, 10 ms + 10 ms, 10 Mbps

**Ports:** 5000 subscribers, 5001 sports, 5002 weather, 5003 news.

**How topics are separated:** the switch never reads the JSON payload. `publisher.py` sends each topic to its own TCP port, so the destination port in the TCP header is the topic label. The controller installs priority-100 rules matching that port (and priority-10 rules matching destination IP). Rerouting a topic means changing the output port of its rules.

## Files

| File | Purpose |
|---|---|
| `broker.py` | TCP broker (ports 5000–5003). `--adaptive` requests a reroute when the average latency of the last 5 messages exceeds 60 ms |
| `publisher.py` | `python3 publisher.py <topic> <count> <interval>` |
| `subscriber.py` | `python3 subscriber.py <name> <topics...>`; type `sub <topic>` or `unsub <topic>` at runtime; Ctrl+C prints a latency summary |
| `topo.py` | Mininet topology (link order fixes the port numbers) |
| `topic_controller.py` | Ryu controller: flow rules, failover, congestion monitor, static/dynamic/app modes |
| `loadtest.py` | Scalability test with N subscribers |
| `plot.py` | Draws `scalability.png` from `results.csv` |
| `experiment.py` | Automated static vs dynamic vs app comparison (writes `compare_raw.csv`) |
| `plot_compare.py` | Averages the raw results and draws `comparison.png` |

**Shared files in `/tmp` (controller interface):**

- `/tmp/sdn_mode`: `static`, `dynamic` or `app`
- `/tmp/topic_paths.json`: reroute requests, for example `{"sports":"alt"}`
- `/tmp/sdn_events.log`: timestamped controller decisions

## Requirements

- Ubuntu with Mininet, Open vSwitch, xterm, iperf and matplotlib
- Ryu 4.34 in a Python 3.9 virtual environment (Ryu does not install on newer Python versions)

```bash
sudo apt update
sudo apt install -y mininet openvswitch-switch xterm iperf python3-pip python3-matplotlib
sudo systemctl enable --now openvswitch-switch

# Ryu in a Python 3.9 environment (using uv)
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env
uv python install 3.9
uv venv --seed --python 3.9 ryuenv
source ryuenv/bin/activate
pip install "setuptools==65.5.0" wheel pbr
pip install --no-build-isolation eventlet==0.30.2 ryu
ryu-manager --version
```

## How to run

Use three terminals: **T1** (controller), **T2** (Mininet), **T3** (normal shell).

```bash
# T2 – clean old state (this also kills Ryu, so start T1 afterwards)
sudo mn -c

# T3 – reset shared files
sudo rm -f /tmp/sdn_mode /tmp/topic_paths.json /tmp/sdn_events.log

# T1 – controller
source ryuenv/bin/activate
ryu-manager topic_controller.py

# T2 – network
sudo python3 topo.py
```

At the `mininet>` prompt:

```
pingall                                         # 0% dropped
sh ovs-ofctl -O OpenFlow13 dump-flows s1        # base and topic rules
xterm h1 h2 h3 h4
```

In the host terminals:

| Host | Command |
|---|---|
| h2 | `python3 broker.py` |
| h3 | `python3 subscriber.py sub1 sports weather` |
| h4 | `python3 subscriber.py sub2 weather news` |
| h1 | `python3 publisher.py sports 20 0.5` (then `weather`, `news`) |

## Demos

**Dynamic subscription** – in the h3 terminal type `sub news`, then `unsub sports`.

**Manual path change** (T3, while a long publisher runs):
```bash
echo '{"sports":"alt"}' > /tmp/topic_paths.json   # latency about 13 ms -> 28 ms
echo '{}' > /tmp/topic_paths.json                  # back to the primary path
```

**Automatic link failover** (T2):
```
link s1 s3 down
link s1 s3 up
```

**Static baseline** – `echo static > /tmp/sdn_mode`, then repeat the link failure: delivery stalls until the link returns. Reset with `echo dynamic > /tmp/sdn_mode`.

**Congestion rerouting** (T2, server first):
```
h2 iperf -s -p 9000 > /tmp/iperf_s.txt &
h1 iperf -c 10.0.0.2 -p 9000 -t 25 > /tmp/iperf_c.txt &
```
Port 9000 avoids a clash with the sports port 5001.

**Application-driven rerouting:**
```bash
echo app > /tmp/sdn_mode
python3 broker.py --adaptive      # in h2
```
Then repeat the congestion test. The broker logs `requesting alternate path` and the controller moves the topic.

## Experiments

```bash
# Scalability (restart the broker before each run)
python3 loadtest.py 5 sports 30       # in h3; start publisher.py sports 200 0.1 in h1 right after
python3 plot.py

# Static vs dynamic vs app comparison (exit Mininet first, keep the controller running)
sudo python3 experiment.py 3
python3 plot_compare.py
```

## Results

Averages over 3 runs per combination.

| Scenario | Mode | Avg latency (ms) | p95 (ms) | Longest gap (s) |
|---|---|---|---|---|
| Normal | Static | 22.2 | 58.0 | 0.29 |
| Normal | Dynamic | 22.3 | 58.5 | 0.32 |
| Congestion | Static | 131.8 | 245.0 | 0.32 |
| Congestion | Dynamic | 35.8 | 120.9 | 0.27 |
| Congestion | App-driven | 30.7 | 60.0 | 0.26 |
| Link failure | Static | 3005.1 | 10645.1 | 11.93 |
| Link failure | Dynamic | 33.5 | 74.3 | 0.36 |

- Baseline latency is about 13 ms on the primary path and about 28 ms on the alternate path.
- Scalability: average latency rises from 16.2 ms (5 subscribers) to 23.4 ms (100 subscribers) with no message loss.
- Delivery stays near 100% because TCP retransmits, so the cost of a bad path is delay, not loss.
- One normal-load dynamic run delivered 89.5% (an outlier). App-driven mode was tested only under congestion.

## Limitations

- The broker-to-controller channel is a shared file in `/tmp` (a REST API would be used in production).
- Only publisher-to-broker traffic is classified per topic; the broker-to-subscriber leg follows the default route.
- In app mode the broker requests the alternate path but never asks to return to the primary.
- One thread per connection; a single controller; results come from a VirtualBox VM.

## Troubleshooting

| Problem | Fix |
|---|---|
| `pingall` shows 100% dropped | The controller is not running. Restart T1, then `sudo mn -c` and `sudo python3 topo.py` |
| `RTNETLINK answers: File exists` | `sudo mn -c`, restart the controller, retry |
| `Permission denied` on `/tmp/sdn_mode` | `sudo rm -f /tmp/sdn_mode /tmp/topic_paths.json` |
| `ryu-manager: command not found` | `source ryuenv/bin/activate` |
| iperf `Address already in use` | `h2 pkill iperf`, then start the server again |
