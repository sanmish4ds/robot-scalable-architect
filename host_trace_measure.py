import os
import time
import csv
from multiprocessing import Event, Process


DEADLINE_MS = 25.0
HZ = 30.0
PERIOD_S = 1.0 / HZ


def burner(stop: Event) -> None:
    x = 0.0
    while not stop.is_set():
        x = (x + 3.14159) * 0.999999


def run_phase(seconds: float, compute_ms: float) -> list[float]:
    n = int(seconds * HZ)
    lats: list[float] = []
    next_t = time.perf_counter()
    for _ in range(n):
        next_t += PERIOD_S

        start = time.perf_counter()
        end_work = start + compute_ms / 1000.0
        while time.perf_counter() < end_work:
            pass
        end = time.perf_counter()

        lats.append((end - start) * 1000.0)

        sleep = next_t - time.perf_counter()
        if sleep > 0:
            time.sleep(sleep)
    return lats


def pct(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return float("nan")
    k = (len(sorted_vals) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(sorted_vals) - 1)
    if f == c:
        return float(sorted_vals[f])
    return float(sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f))


def summarize(lats: list[float]) -> dict[str, float]:
    l = sorted(lats)
    miss = sum(1 for x in l if x > DEADLINE_MS) / len(l)
    return {
        "p50": pct(l, 50),
        "p95": pct(l, 95),
        "p99": pct(l, 99),
        "max": float(max(l)),
        "miss": float(miss),
        "n": float(len(l)),
    }


def main() -> None:
    # Nominal phase: moderate compute
    nom = run_phase(30, compute_ms=6)

    # Stress phase: increase compute + add CPU contention.
    stop = Event()
    burners: list[Process] = []
    for _ in range(max(2, (os.cpu_count() or 4) // 2)):
        p = Process(target=burner, args=(stop,), daemon=True)
        p.start()
        burners.append(p)

    stress = run_phase(30, compute_ms=10)

    stop.set()
    for p in burners:
        p.join(timeout=0.5)

    rec = run_phase(15, compute_ms=6)

    pooled = nom + stress + rec

    out_dir = os.path.join(
        os.path.dirname(__file__),
        "Real_Time_Intelligence_and_Scalable_Architecture_for_Robotics (2)",
        "artifacts",
    )
    os.makedirs(out_dir, exist_ok=True)
    out_csv = os.path.join(out_dir, "host_trace_latency_ms.csv")
    with open(out_csv, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["phase", "latency_ms"])
        for x in nom:
            w.writerow(["nominal", f"{x:.9f}"])
        for x in stress:
            w.writerow(["stress", f"{x:.9f}"])
        for x in rec:
            w.writerow(["recovery", f"{x:.9f}"])

    print("platform", os.uname().sysname, os.uname().machine, "cpu_count", os.cpu_count())
    print("deadline_ms", DEADLINE_MS, "hz", HZ)
    print("nom", summarize(nom))
    print("stress", summarize(stress))
    print("recovery", summarize(rec))
    print("pooled", summarize(pooled))
    print("raw_csv", out_csv)


if __name__ == "__main__":
    main()

