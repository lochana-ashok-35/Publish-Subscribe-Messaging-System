import csv, collections, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
rows = list(csv.DictReader(open("compare_raw.csv")))
agg = collections.defaultdict(list)
for r in rows: agg[(r["scenario"], r["mode"])].append(r)
def mean(k, key):
    v = [float(r[key]) for r in agg[k]]
    return sum(v) / len(v) if v else 0
scen = ["normal", "congestion", "failure"]
modes = [("static", "Static (baseline)"), ("dynamic", "Dynamic SDN"), ("app", "App-driven")]
metrics = [("avg_ms", "Average latency (ms)"), ("p95_ms", "95th percentile latency (ms)"),
           ("max_gap_s", "Longest delivery gap (s)")]
fig, axes = plt.subplots(1, 3, figsize=(15, 4.5))
w = 0.26
for ax, (key, title) in zip(axes, metrics):
    for j, (m, label) in enumerate(modes):
        vals = [mean((s, m), key) for s in scen]
        ax.bar([i + (j - 1) * w for i in range(len(scen))], vals, w, label=label)
    ax.set_xticks(range(len(scen))); ax.set_xticklabels(scen)
    ax.set_title(title); ax.grid(axis="y"); ax.legend(fontsize=8)
plt.tight_layout(); plt.savefig("comparison.png", dpi=150)
print(f"{'scenario':11s}{'mode':9s}{'deliv%':>7s}{'avg':>9s}{'p95':>9s}{'max':>10s}{'gap(s)':>8s}")
for (s, m), _ in sorted(agg.items()):
    print(f"{s:11s}{m:9s}{mean((s,m),'delivery_pct'):7.1f}{mean((s,m),'avg_ms'):9.1f}"
          f"{mean((s,m),'p95_ms'):9.1f}{mean((s,m),'max_ms'):10.1f}{mean((s,m),'max_gap_s'):8.2f}")
print("saved comparison.png")
