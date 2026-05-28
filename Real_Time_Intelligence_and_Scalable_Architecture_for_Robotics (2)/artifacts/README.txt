This folder contains small, reproducible measurement artifacts generated locally.

- host_trace_latency_ms.csv: per-cycle callback execution latency (ms) with phase labels
  (nominal/stress/recovery) produced by host_trace_measure.py.

- des_outputs/: discrete-event simulation summaries (30 runs) from des_simulation.py.
- des_outputs/des_plot_samples.csv: per-cycle latency samples for figure generation.
- plot_des_figures.py: regenerates fig_pilot_latency_cdf.png, fig_pilot_latency_bars.png,
  and fig_tiertrace.png in the paper directory.

