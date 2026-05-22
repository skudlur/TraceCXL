"""
CXL Switch model with Virtual Channels and Credit-Based Flow Control (CBFC).
"""

from collections import deque, defaultdict
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

from .packet import CXLPacket, CXLFlit, SimulationEvent, CXL_SWITCH_LATENCY, Priority


@dataclass
class SwitchPort:
    """Single port on a CXL switch representing link-local tx/rx queues."""
    port_id: int
    max_queue_depth: int = 16  # Credits per VC
    bandwidth_gbps: float = 64.0
    
    def __post_init__(self):
        # 8 Virtual Channels: 0-3 for Requests, 4-7 for Responses
        self.num_vcs = 8
        
        # Ingress buffers (Rx side)
        self.ingress_queues: Dict[int, deque] = {vc: deque() for vc in range(self.num_vcs)}
        
        # Egress buffers (Tx side)
        self.egress_queues: Dict[int, deque] = {vc: deque() for vc in range(self.num_vcs)}
        
        # Tx Credits (how many flits/packets we can send to the downstream neighbor)
        # Initialized to the max_queue_depth for each VC
        self.tx_credits: Dict[int, int] = {vc: self.max_queue_depth for vc in range(self.num_vcs)}
        
        # Stats
        self.packets_processed = 0
        self.packets_dropped = 0  # Should be 0 with CBFC
        self.total_queue_time = 0.0
        
        # Tx State
        self.is_transmitting = False
        self.next_available_time = 0.0
        
    def enqueue_ingress(self, flit: CXLFlit) -> bool:
        """Receive flit from upstream link into ingress queue."""
        vc = flit.vc_id
        if len(self.ingress_queues[vc]) >= self.max_queue_depth:
            # Under CBFC, this should NEVER happen unless credits are mismanaged
            self.packets_dropped += 1
            return False
            
        self.ingress_queues[vc].append(flit)
        return True

    def enqueue_egress(self, flit: CXLFlit):
        """Move flit from crossbar into egress queue."""
        self.egress_queues[flit.vc_id].append(flit)

    def dequeue_egress(self, current_time: float) -> Optional[CXLFlit]:
        """
        Remove and return head flit from highest priority egress queue
        THAT ALSO HAS TX CREDITS AVAILABLE.
        """
        for vc in range(self.num_vcs - 1, -1, -1):
            if self.egress_queues[vc] and self.tx_credits[vc] > 0:
                flit = self.egress_queues[vc].popleft()
                self.tx_credits[vc] -= 1  # Consume a credit
                if flit.is_tail:
                    self.packets_processed += 1
                self.total_queue_time += (current_time - flit.packet.timestamp)
                return flit
        return None

    @property
    def egress_occupancy(self) -> int:
        return sum(len(q) for q in self.egress_queues.values())
        
    @property
    def ingress_occupancy(self) -> int:
        return sum(len(q) for q in self.ingress_queues.values())

    @property
    def has_transmittable_packets(self) -> bool:
        """Check if we have packets AND credits to send them."""
        for vc in range(self.num_vcs - 1, -1, -1):
            if self.egress_queues[vc] and self.tx_credits[vc] > 0:
                return True
        return False


class CXLSwitch:
    """Models a CXL fabric switch with CBFC."""

    def __init__(self, switch_id: int, num_ports: int, queue_depth: int = 16, ecn_threshold: float = 0.6, routing_strategy=None):
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

    def route_packet(self, packet: CXLPacket, flits: List[CXLFlit], arrival_port: int, sim_engine) -> bool:
        """
        Route packet and its constituent flits from Ingress queue to Egress queue (simulating Crossbar).
        """
        self.total_packets_processed += 1

        target = getattr(packet, 'target', packet.dst_device)
        
        if target not in self.routing_table or not self.routing_table[target]:
            self.total_packets_dropped += 1
            return False

        available_ports = self.routing_table[target]
        
        if self.routing_strategy:
            output_port_id = self.routing_strategy.get_output_port(self, packet, available_ports)
        else:
            output_port_id = available_ports[0]
            
        out_port = self.ports[output_port_id]

        could_transmit_before = out_port.has_transmittable_packets

        if (out_port.egress_occupancy / (out_port.max_queue_depth * out_port.num_vcs)) > self.ecn_threshold:
            packet.ecn_marked = True

        for flit in flits:
            out_port.enqueue_egress(flit)

        if not could_transmit_before and out_port.has_transmittable_packets and not out_port.is_transmitting:
            self._schedule_port_transmission(output_port_id, sim_engine)

        return True

    def _schedule_port_transmission(self, output_port_id: int, sim_engine):
        """Schedule transmission of head packet from port queue."""
        port = self.ports[output_port_id]

        if not port.has_transmittable_packets:
            port.is_transmitting = False
            return

        port.is_transmitting = True

        current_time = sim_engine.current_time

        if port.next_available_time > current_time:
            tx_start = port.next_available_time
        else:
            tx_start = current_time + CXL_SWITCH_LATENCY

        event = SimulationEvent(
            timestamp=tx_start,
            event_type="switch_transmit",
            packet=None,
            switch_id=self.switch_id,
            metadata={"output_port": output_port_id}
        )
        sim_engine.schedule_event(event)

    def transmit_packet(self, output_port: int, sim_engine) -> Optional[CXLFlit]:
        """
        Transmit flit from egress queue (consumes tx_credit).
        Then schedule next flit if transmittable.
        """
        port = self.ports[output_port]
        flit = port.dequeue_egress(sim_engine.current_time)

        if flit:
            if flit.is_tail and self.switch_id not in flit.packet.route:
                flit.packet.route.append(self.switch_id)

            # Serialization delay for 1 flit (e.g. 68 bytes for CXL)
            # We use 64 bytes for simplicity matching CXL_FLIT_SIZE
            serialization_ns = (64 * 8) / (port.bandwidth_gbps * 1e9) * 1e9
            port.next_available_time = sim_engine.current_time + serialization_ns

            if port.has_transmittable_packets:
                self._schedule_port_transmission(output_port, sim_engine)
            else:
                port.is_transmitting = False
        else:
            port.is_transmitting = False

        return flit
        
    def receive_credit(self, output_port: int, vc_id: int, sim_engine):
        """Receive credit return from downstream neighbor."""
        port = self.ports[output_port]
        could_transmit_before = port.has_transmittable_packets
        
        port.tx_credits[vc_id] += 1
        
        # If we couldn't transmit before, but now we have a credit, we should check!
        if not could_transmit_before and port.has_transmittable_packets and not port.is_transmitting:
            # We can start transmitting again!
            # The port is idle right now, we can schedule it starting from current time
            self._schedule_port_transmission(output_port, sim_engine)

    def get_congestion_metrics(self) -> dict:
        total_drops = sum(p.packets_dropped for p in self.ports)
        return {
            "switch_id": self.switch_id,
            "total_processed": self.total_packets_processed,
            "total_dropped": self.total_packets_dropped + total_drops,
            "drop_rate": (self.total_packets_dropped + total_drops) / max(1, self.total_packets_processed),
            "port_occupancies": [p.egress_occupancy / (p.max_queue_depth * p.num_vcs) for p in self.ports],
            "avg_occupancy": sum(p.egress_occupancy / (p.max_queue_depth * p.num_vcs) for p in self.ports) / len(self.ports),
        }

    def print_status(self):
        print(f"\nSwitch {self.switch_id}:")
        print(f"  Processed: {self.total_packets_processed}, Dropped: {self.total_packets_dropped}")
        for port in self.ports:
            print(f"  Port {port.port_id}: Egress={port.egress_occupancy}, Ingress={port.ingress_occupancy}, "
                  f"Processed={port.packets_processed}, Dropped={port.packets_dropped}, "
                  f"Tx_Credits=[{','.join(str(c) for c in port.tx_credits.values())}]")
