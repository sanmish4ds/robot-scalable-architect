from __future__ import annotations

import csv
import math
import random
from pathlib import Path


def main() -> None:
    out = Path(__file__).with_name("events_example_long.csv")
    random.seed(7)

    hz = 30.0
    n = 600  # 20 seconds @ 30Hz
    deadline_ms = 25.0

    rows = []
    for i in range(n):
        t_s = i / hz
        # Three phases: nominal -> stress -> recovery
        if i < 200:
            base = 6.0
            drift_mu = 0.10
            unc_mu = 0.28
        elif i < 450:
            base = 10.0
            drift_mu = 0.30
            unc_mu = 0.45
        else:
            base = 6.0
            drift_mu = 0.14
            unc_mu = 0.30

        # Latency with occasional spikes
        spike = 0.0
        if random.random() < 0.02:
            spike = random.uniform(10.0, 35.0)
        lat = base + random.gauss(0.0, 0.15) + spike

        # uncertainty/drift signals (0..1)
        unc = max(0.0, min(1.0, unc_mu + random.gauss(0.0, 0.06)))
        drift = max(0.0, min(1.0, drift_mu + random.gauss(0.0, 0.05)))

        rows.append((t_s, lat, unc, drift))

    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["t_s", "latency_ms", "uncertainty", "drift"])
        for r in rows:
            w.writerow([f"{r[0]:.6f}", f"{r[1]:.6f}", f"{r[2]:.6f}", f"{r[3]:.6f}"])

    print(str(out))


if __name__ == "__main__":
    main()

