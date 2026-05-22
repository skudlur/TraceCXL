"""Analysis and visualization module for TraceCXL."""

from .metrics import MetricsCollector
from .plots import plot_latency_cdf, plot_queue_occupancy_heatmap, plot_drop_rate_by_switch
from .validator import ProtocolValidator, CXLProtocolError

__all__ = [
    'MetricsCollector',
    'plot_latency_cdf',
    'plot_queue_occupancy_heatmap',
    'plot_drop_rate_by_switch',
    'ProtocolValidator',
    'CXLProtocolError',
]
