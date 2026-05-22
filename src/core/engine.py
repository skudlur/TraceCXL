"""
Discrete-event simulation engine for CXL fabric.

Implements a priority-queue based event loop that processes
network events in timestamp order.
"""

import heapq
import logging
from typing import Callable, Dict, List
from collections import defaultdict

from .packet import SimulationEvent, CXLPacket

logger = logging.getLogger(__name__)


class SimulationEngine:
    """
    Core discrete-event simulation engine.
    
    Manages the event queue and dispatches events to registered handlers.
    """
    
    def __init__(self, metrics_collector=None):
        self.current_time = 0.0  # Current simulation time (ns)
        self.event_queue = []     # Min-heap of events
        self.event_handlers: Dict[str, List[Callable]] = defaultdict(list)
        self.stats = SimulationStats()
        self.metrics_collector = metrics_collector
        
    def schedule_event(self, event: SimulationEvent):
        """Add event to the queue"""
        if event.timestamp < self.current_time:
            raise ValueError(f"Cannot schedule event in the past: {event.timestamp} < {self.current_time}")
            
        heapq.heappush(self.event_queue, event)
    
    def register_handler(self, event_type: str, handler: Callable):
        """Register callback for specific event type"""
        self.event_handlers[event_type].append(handler)
    
    def run(self, until: float = None, max_events: int = None):
        """
        Run simulation until stopping condition.
        
        Args:
            until: Stop at this simulation time (ns)
            max_events: Stop after processing this many events
        """
        events_processed = 0
        
        while self.event_queue:
            event = heapq.heappop(self.event_queue)
            
            # Check stopping conditions
            if until is not None and event.timestamp > until:
                heapq.heappush(self.event_queue, event)  # Put it back
                break
            
            if max_events is not None and events_processed >= max_events:
                heapq.heappush(self.event_queue, event)
                break
            
            # Advance time
            self.current_time = event.timestamp
            
            # Dispatch to handlers
            for handler in self.event_handlers[event.event_type]:
                handler(event)
            
            events_processed += 1
            
            if events_processed % 10000 == 0:
                logger.debug(f"Processed {events_processed} events, sim_time={self.current_time:.2f}ns")
                if self.metrics_collector:
                    self.metrics_collector.collect_switch_snapshot(self.current_time)
        
        self.stats.total_events = events_processed
        self.stats.final_time = self.current_time
        return self.stats


class SimulationStats:
    """Collect simulation-wide statistics"""
    
    def __init__(self):
        self.total_events = 0
        self.final_time = 0.0
        self.packets_sent = 0
        self.packets_received = 0
        self.total_latency = 0.0
        self.latencies = []  # Per-packet latencies
        self._sorted_latencies = None # Cached sorted latencies
        self.queue_depths = defaultdict(list)  # switch_id -> [depths over time]
        
    def record_packet_completion(self, packet: CXLPacket, completion_time: float):
        """Record completed packet for statistics"""
        latency = packet.latency_at(completion_time)
        self.packets_received += 1
        self.total_latency += latency
        self.latencies.append(latency)
        self._sorted_latencies = None # Invalidate cache
    
    def avg_latency(self) -> float:
        """Average end-to-end latency"""
        if self.packets_received == 0:
            return 0.0
        return self.total_latency / self.packets_received
    
    def percentile_latency(self, p: float) -> float:
        """Calculate p-th percentile latency (p in [0, 100])"""
        if not self.latencies:
            return 0.0
        if self._sorted_latencies is None:
            self._sorted_latencies = sorted(self.latencies)
        idx = int(len(self._sorted_latencies) * p / 100.0)
        return self._sorted_latencies[min(idx, len(self._sorted_latencies) - 1)]
    
    def print_summary(self):
        """Print simulation summary"""
        print("\n=== Simulation Statistics ===")
        print(f"Total events: {self.total_events}")
        print(f"Simulation time: {self.final_time:.2f} ns ({self.final_time / 1e6:.2f} ms)")
        print(f"Packets sent: {self.packets_sent}")
        print(f"Packets received: {self.packets_received}")
        if self.packets_received > 0:
            print(f"Avg latency: {self.avg_latency():.2f} ns")
            print(f"P50 latency: {self.percentile_latency(50):.2f} ns")
            print(f"P99 latency: {self.percentile_latency(99):.2f} ns")
        print("=" * 30)
