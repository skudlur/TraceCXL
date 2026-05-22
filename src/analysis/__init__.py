"""Analysis and visualization module for CXL fabric simulator."""

from .metrics import MetricsCollector
from .plots import plot_latency_cdf, plot_queue_occupancy_heatmap, plot_drop_rate_by_switch

__all__ = [
    'MetricsCollector',
    'plot_latency_cdf',
    'plot_queue_occupancy_heatmap',
    'plot_drop_rate_by_switch',
]
