"""
CXL Switch model with proper queue-driven transmission.
"""

from collections import deque, defaultdict
from dataclasses import dataclass
from typing import Optional, List, Dict, Any

from .packet import CXLPacket, SimulationEvent, CXL_SWITCH_LATENCY, Priority


@dataclass
class SwitchPort:
    """Single port on a CXL switch"""
    port_id: int
    max_queue_depth: int = 32
    bandwidth_gbps: float = 64.0

    def __post_init__(self):
        self.queues = {
            Priority.CRITICAL: deque(),
            Priority.HIGH: deque(),
            Priority.MEDIUM: deque(),
            Priority.LOW: deque()
        }
        self.packets_processed = 0
        self.packets_dropped_by_priority = {p: 0 for p in Priority}
        self.total_queue_time = 0.0
        self.is_transmitting = False  # Is port currently busy?
        self.next_available_time = 0.0

    def enqueue(self, packet: CXLPacket) -> bool:
        """Enqueue packet based on priority. Returns True if successful."""
        if self.is_full:
            self.packets_dropped_by_priority[packet.priority] += 1
            return False

        self.queues[packet.priority].append(packet)
        return True

    def dequeue(self, current_time: float) -> Optional[CXLPacket]:
        """Remove and return head packet from highest priority queue."""
        for priority in [Priority.CRITICAL, Priority.HIGH, Priority.MEDIUM, Priority.LOW]:
            if self.queues[priority]:
                self.packets_processed += 1
                packet = self.queues[priority].popleft()
                self.total_queue_time += (current_time - packet.timestamp)
                return packet
        return None

    @property
    def occupancy(self) -> int:
        """Current number of packets across all priority queues."""
        return sum(len(q) for q in self.queues.values())

    @property
    def is_full(self) -> bool:
        """Check if total occupancy reached limit."""
        return self.occupancy >= self.max_queue_depth

    @property
    def has_packets(self) -> bool:
        """Check if any packets are queued."""
        return self.occupancy > 0


class CXLSwitch:
    """Models a CXL fabric switch with proper queueing."""

    def __init__(self, switch_id: int, num_ports: int, queue_depth: int = 32, ecn_threshold: float = 0.6, routing_strategy=None):
        self.switch_id = switch_id
        self.num_ports = num_ports
        self.ports = [SwitchPort(i, queue_depth) for i in range(num_ports)]
        self.routing_table: Dict[Any, List[int]] = defaultdict(list)
        self.total_packets_processed = 0
        self.total_packets_dropped = 0
        self.ecn_threshold = ecn_threshold
        self.routing_strategy = routing_strategy

    def set_route(self, dst_target: Any, output_port: int):
        if output_port >= self.num_ports:
            raise ValueError(f"Invalid port {output_port}")
        if output_port not in self.routing_table[dst_target]:
            self.routing_table[dst_target].append(output_port)

    def route_packet(self, packet: CXLPacket, arrival_port: int, sim_engine) -> bool:
        """
        Route incoming packet to output port.
        Only schedules transmission if queue was empty.
        """
        self.total_packets_processed += 1

        # Determine logical destination (device or host)
        # For forward path, dst_device is an int. For response, we'll use a string or tuple
        # But wait, let's just use a property `target` which we can set on the packet
        target = getattr(packet, 'target', packet.dst_device)
        
        if target not in self.routing_table or not self.routing_table[target]:
            self.total_packets_dropped += 1
            return False

        available_ports = self.routing_table[target]
        
        if self.routing_strategy:
            output_port_id = self.routing_strategy.get_output_port(self, packet, available_ports)
        else:
            output_port_id = available_ports[0] # Static default
            
        port = self.ports[output_port_id]

        # Check if queue was empty before enqueue
        was_empty = not port.has_packets

        # Try to enqueue
        if not port.enqueue(packet):
            self.total_packets_dropped += 1
            return False

        # ECN marking
        if (port.occupancy / port.max_queue_depth) > self.ecn_threshold:
            packet.ecn_marked = True

        # Only schedule transmission if this is the first packet in queue
        if was_empty and not port.is_transmitting:
            self._schedule_port_transmission(output_port_id, sim_engine)

        return True

    def _schedule_port_transmission(self, output_port_id: int, sim_engine):
        """Schedule transmission of head packet from port queue."""
        port = self.ports[output_port_id]

        if not port.has_packets:
            port.is_transmitting = False
            return

        port.is_transmitting = True

        # Switch processing delay + serialization
        current_time = sim_engine.current_time

        # Ensure we don't schedule in the past
        if port.next_available_time > current_time:
            tx_start = port.next_available_time
        else:
            tx_start = current_time + CXL_SWITCH_LATENCY

        # Schedule the transmission event
        event = SimulationEvent(
            timestamp=tx_start,
            event_type="switch_transmit",
            packet=None,  # Will dequeue in handler
            switch_id=self.switch_id,
            metadata={"output_port": output_port_id}
        )
        sim_engine.schedule_event(event)

    def transmit_packet(self, output_port: int, sim_engine) -> Optional[CXLPacket]:
        """
        Transmit head packet from queue.
        Then schedule next packet if queue not empty.
        """
        port = self.ports[output_port]
        packet = port.dequeue(sim_engine.current_time)

        if packet:
            packet.route.append(self.switch_id)

            # Calculate serialization delay for this packet
            serialization_ns = (packet.size * 8) / (port.bandwidth_gbps * 1e9) * 1e9

            # Update when port will be free
            port.next_available_time = sim_engine.current_time + serialization_ns

            # If more packets in queue, schedule next transmission
            if port.has_packets:
                self._schedule_port_transmission(output_port, sim_engine)
            else:
                port.is_transmitting = False
        else:
            port.is_transmitting = False

        return packet

    def get_congestion_metrics(self) -> dict:
        return {
            "switch_id": self.switch_id,
            "total_processed": self.total_packets_processed,
            "total_dropped": self.total_packets_dropped,
            "drop_rate": self.total_packets_dropped / max(1, self.total_packets_processed),
            "port_occupancies": [p.occupancy / p.max_queue_depth for p in self.ports],
            "avg_occupancy": sum(p.occupancy / p.max_queue_depth for p in self.ports) / len(self.ports),
        }

    def print_status(self):
        print(f"\nSwitch {self.switch_id}:")
        print(f"  Processed: {self.total_packets_processed}, Dropped: {self.total_packets_dropped}")
        for port in self.ports:
            drops_str = ", ".join(f"{p.name}: {v}" for p, v in port.packets_dropped_by_priority.items() if v > 0)
            drops_msg = f" (Drops: {drops_str})" if drops_str else ""
            print(f"  Port {port.port_id}: {port.occupancy}/{port.max_queue_depth} queued, "
                  f"{port.packets_processed} processed{drops_msg}")
