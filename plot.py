import csv, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
rows = list(csv.DictReader(open("results.csv")))
n = [int(r["subscribers"]) for r in rows]
plt.plot(n, [float(r["avg_ms"]) for r in rows], "o-", label="average")
plt.plot(n, [float(r["p95_ms"]) for r in rows], "s-", label="95th percentile")
plt.xlabel("Number of subscribers"); plt.ylabel("Latency (ms)")
plt.title("Pub-Sub scalability"); plt.legend(); plt.grid(True)
plt.savefig("scalability.png", dpi=150); print("saved scalability.png")
