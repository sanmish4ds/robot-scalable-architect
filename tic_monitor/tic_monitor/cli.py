from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from .caai import CAAIState, step_caai
from .models import CAAIConfig
from .monitor import TICMonitor, load_contract, load_events_csv


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def cmd_run(args: argparse.Namespace) -> int:
    contract = load_contract(args.contract)
    events = load_events_csv(args.events)
    caai_cfg = CAAIConfig(window_cycles=args.window_cycles, dwell_min=args.dwell_min)

    mon = TICMonitor(contract=contract, caai=caai_cfg)
    wins = mon.compute_windows(events)

    state = CAAIState(tier=1, dwell=0)
    trace_rows = []
    for w in wins:
        state = step_caai(
            state,
            caai_cfg,
            deadline_ms=mon.deadline_ms,
            p99_latency_ms=w.p99_ms,
            miss_rate=w.miss_rate,
            uncertainty=w.ece_proxy,  # proxy in absence of labels
            drift=w.drift_proxy,
            consecutive_misses=w.max_consecutive_misses,
        )
        trace_rows.append(
            {
                "start_t_s": w.start_t_s,
                "end_t_s": w.end_t_s,
                "p99_ms": w.p99_ms,
                "miss_rate": w.miss_rate,
                "drift_proxy": w.drift_proxy,
                "status": w.status,
                "rti_score": w.rti_score,
                "tier": state.tier,
            }
        )

    out_dir = Path(args.out)
    _ensure_dir(out_dir)

    pd.DataFrame(trace_rows).to_csv(out_dir / "status_trace.csv", index=False)

    # Aggregate summary from last window (most recent state)
    last = trace_rows[-1]
    summary = {
        "component": contract.component.model_dump(),
        "deadline_ms": mon.deadline_ms,
        "window_cycles": args.window_cycles,
        "last_window": last,
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="tic-monitor")
    sub = p.add_subparsers(dest="cmd", required=True)

    run = sub.add_parser("run", help="Run TIC monitor on events CSV")
    run.add_argument("--contract", required=True)
    run.add_argument("--events", required=True)
    run.add_argument("--out", required=True)
    run.add_argument("--window-cycles", type=int, default=120)
    run.add_argument("--dwell-min", type=int, default=60)
    run.set_defaults(func=cmd_run)

    return p


def main() -> None:
    p = build_parser()
    args = p.parse_args()
    rc = args.func(args)
    raise SystemExit(rc)


if __name__ == "__main__":
    main()

