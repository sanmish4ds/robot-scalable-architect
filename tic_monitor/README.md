# TIC Monitor (reference implementation)

This is a small, software-only reference implementation of:

- **TIC Monitor**: loads a TIC contract (JSON), consumes a timestamped stream, computes rolling-window percentiles and contract status.
- **CAAI Supervisor**: consumes TIC monitor signals and selects an active tier (1/2/3) with dwell-time + hysteresis.

It is designed to work with any timestamped stream (e.g., ROS 2 topic traces) but **does not require ROS 2**.

## Install (editable)

```bash
cd tic_monitor
python3 -m pip install -e .
```

## Quickstart

Run the monitor on the provided example inputs:

```bash
python3 examples/generate_events_example.py
tic-monitor run \
  --contract examples/tic_contract_example.json \
  --events examples/events_example_long.csv \
  --out artifacts/run_out
```

Outputs:

- `artifacts/run_out/summary.json`: aggregated p50/p95/p99/max + miss rate + RTI-score + status
- `artifacts/run_out/status_trace.csv`: per-window status and selected tier

## Input formats

### Contract JSON
See `examples/tic_contract_example.json`.

### Events CSV
See `examples/events_example.csv`.

Required columns:

- `t_s`: event time (seconds, monotonic)
- `latency_ms`: end-to-end latency for the critical path
- `uncertainty`: scalar uncertainty summary (0..1)
- `drift`: scalar drift score (0..1)

## License

MIT

