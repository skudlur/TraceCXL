"""Metrics collection for the TraceCXL."""

from typing import Dict, List, Any
from collections import defaultdict

class MetricsCollector:
    """Collects time-series metrics during simulation."""
    
    def __init__(self, topology):
        self.topology = topology
        self.queue_occupancy_history: Dict[int, Dict[int, List[tuple]]] = defaultdict(lambda: defaultdict(list))
        self.latencies: List[float] = []
        self.total_dropped = 0
        self.ecn_marks = 0

    def collect_switch_snapshot(self, current_time: float):
        """Record queue depth for all ports on all switches."""
        for switch in self.topology.switches:
            for port in switch.ports:
                # Store (timestamp, occupancy_fraction)
                frac = port.egress_occupancy / max(1, port.max_queue_depth * port.num_vcs)
                self.queue_occupancy_history[switch.switch_id][port.port_id].append((current_time, frac))

    def record_packet_latency(self, latency: float):
        self.latencies.append(latency)

    def collect_host_stats(self) -> Dict[str, Any]:
        stats = {}
        for host in self.topology.hosts:
            stats[host.host_id] = {
                "sent": host.packets_sent,
                "received": host.packets_received,
                "outstanding": host.num_outstanding,
                "ecn_count": host.rate_controller.ecn_count
            }
        return stats
