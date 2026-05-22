"""Plotly visualizations for CXL fabric simulator."""

import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import numpy as np

def plot_latency_cdf(latencies: list[float], title="End-to-End Latency CDF"):
    """Plot an interactive CDF of packet latencies."""
    if not latencies:
        print("No latencies to plot.")
        return None
        
    sorted_lats = np.sort(latencies)
    p = 1.0 * np.arange(len(sorted_lats)) / (len(sorted_lats) - 1)
    
    fig = px.line(x=sorted_lats, y=p, title=title, labels={'x': 'Latency (ns)', 'y': 'Cumulative Probability'})
    return fig

def plot_queue_occupancy_heatmap(metrics_collector, switch_id: int):
    """Plot an interactive heatmap of port occupancy over time for a given switch."""
    history = metrics_collector.queue_occupancy_history.get(switch_id)
    if not history:
        print(f"No history for switch {switch_id}")
        return None
        
    # Find common timestamps
    all_times = set()
    for port_data in history.values():
        all_times.update(t for t, _ in port_data)
    times = sorted(list(all_times))
    
    data = []
    ports = sorted(history.keys())
    for port_id in ports:
        port_history = dict(history[port_id])
        row = [port_history.get(t, 0.0) for t in times]
        data.append(row)
        
    fig = go.Figure(data=go.Heatmap(
        z=data,
        x=times,
        y=[f"Port {p}" for p in ports],
        colorscale='Viridis'
    ))
    fig.update_layout(title=f"Queue Occupancy (Switch {switch_id})", xaxis_title="Time (ns)", yaxis_title="Port")
    return fig

def plot_drop_rate_by_switch(topology):
    """Plot a bar chart of drop rates for all switches."""
    switches = []
    drop_rates = []
    
    for switch in topology.switches:
        metrics = switch.get_congestion_metrics()
        switches.append(f"Switch {switch.switch_id}")
        drop_rates.append(metrics["drop_rate"])
        
    fig = px.bar(x=switches, y=drop_rates, title="Drop Rate by Switch", labels={'x': 'Switch', 'y': 'Drop Rate'})
    return fig
