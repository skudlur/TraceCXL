"""
Host (CPU) model that generates CXL memory traffic.

Represents a compute host that issues memory requests
to CXL-attached devices.
"""

from typing import List
import random

from .packet import CXLPacket, CXLTransactionType, SimulationEvent, Priority
from collections import deque
from typing import Dict, Optional


class Host:
    """
    Models a compute host issuing CXL memory requests.
    """
    
    def __init__(self, host_id: int, connected_switch: int):
        self.host_id = host_id
        self.connected_switch = connected_switch
        self.next_packet_id = 0
        
        # Statistics
        self.packets_sent = 0
        self.packets_received = 0
        self.outstanding_requests = {}  # packet_id -> packet
        self.rate_controller = AdaptiveRateController()
        
        # Credit-Based Flow Control state
        self.num_vcs = 8
        self.egress_queues: Dict[int, deque] = {vc: deque() for vc in range(self.num_vcs)}
        # Host tracks tx_credits for the switch it is connected to (assume depth 16 per VC)
        self.tx_credits: Dict[int, int] = {vc: 16 for vc in range(self.num_vcs)}
        self.is_transmitting = False
        self.next_available_time = 0.0
        
    def generate_memory_request(
        self,
        dst_device: int,
        address: int,
        is_read: bool = True,
        priority: Priority = Priority.MEDIUM,
        timestamp: float = 0.0
    ) -> CXLPacket:
        """
        Create a new CXL memory request packet.
        
        Args:
            dst_device: Target CXL memory device ID
            address: Memory address to access
            is_read: True for read, False for write
            priority: QoS priority
            timestamp: Creation timestamp
        """
        tx_type = CXLTransactionType.MEM_READ if is_read else CXLTransactionType.MEM_WRITE
        
        packet = CXLPacket(
            packet_id=self.next_packet_id,
            tx_type=tx_type,
            src_host=self.host_id,
            dst_device=dst_device,
            address=address,
            priority=priority,
            timestamp=timestamp
        )
        
        self.next_packet_id += 1
        self.outstanding_requests[packet.packet_id] = packet
        self.egress_queues[packet.vc_id].append(packet)
        return packet
        
    def has_transmittable_packets(self) -> bool:
        """Check if we have packets AND credits to send them."""
        for vc in range(self.num_vcs - 1, -1, -1):
            if self.egress_queues[vc] and self.tx_credits[vc] > 0:
                return True
        return False
        
    def transmit_request(self) -> Optional[CXLPacket]:
        """Dequeue a packet to send if credits are available."""
        for vc in range(self.num_vcs - 1, -1, -1):
            if self.egress_queues[vc] and self.tx_credits[vc] > 0:
                packet = self.egress_queues[vc].popleft()
                self.tx_credits[vc] -= 1
                self.packets_sent += 1
                return packet
        return None
        
    def receive_credit(self, vc_id: int):
        """Receive credit return from connected switch."""
        self.tx_credits[vc_id] += 1
    
    def receive_response(self, packet: CXLPacket):
        """Process received response packet"""
        self.packets_received += 1
        if packet.packet_id in self.outstanding_requests:
            del self.outstanding_requests[packet.packet_id]
        self.rate_controller.process_ecn_feedback(packet)
    
    @property
    def num_outstanding(self) -> int:
        """Number of in-flight requests"""
        return len(self.outstanding_requests)


class TrafficGenerator:
    """
    Generates synthetic CXL memory traffic patterns.
    """
    
    def __init__(self, hosts: List[Host], cxl_devices: List[int]):
        self.hosts = hosts
        self.cxl_devices = cxl_devices
    
    def generate_uniform_traffic(
        self,
        sim_engine,
        duration_ns: float,
        requests_per_host: int
    ):
        """
        Generate uniform random traffic across all devices.
        
        Args:
            sim_engine: Simulation engine to schedule events
            duration_ns: Time window for traffic generation
            requests_per_host: Total requests each host will issue
        """
        for host in self.hosts:
            # Space requests evenly over duration
            interval = duration_ns / requests_per_host
            
            for i in range(requests_per_host):
                timestamp = i * interval + random.uniform(0, interval * 0.1)
                dst_device = random.choice(self.cxl_devices)
                address = random.randint(0, 1 << 30)  # Random 1GB address space
                
                packet = host.generate_memory_request(
                    dst_device=dst_device,
                    address=address,
                    timestamp=timestamp
                )
                
                # Schedule host_send event
                event = SimulationEvent(
                    timestamp=timestamp,
                    event_type="host_send",
                    packet=packet,
                    metadata={"host_id": host.host_id}
                )
                sim_engine.schedule_event(event)
    
    def generate_hotspot_traffic(
        self,
        sim_engine,
        duration_ns: float,
        requests_per_host: int,
        hotspot_device: int,
        hotspot_fraction: float = 0.8
    ):
        """
        Generate traffic with hotspot concentration.
        
        Args:
            hotspot_device: CXL device that receives most traffic
            hotspot_fraction: Fraction of traffic going to hotspot (0.0-1.0)
        """
        for host in self.hosts:
            interval = duration_ns / requests_per_host
            
            for i in range(requests_per_host):
                timestamp = i * interval + random.uniform(0, interval * 0.1)
                
                # Route to hotspot device with given probability
                if random.random() < hotspot_fraction:
                    dst_device = hotspot_device
                else:
                    # Uniform distribution across other devices
                    other_devices = [d for d in self.cxl_devices if d != hotspot_device]
                    dst_device = random.choice(other_devices) if other_devices else hotspot_device
                
                address = random.randint(0, 1 << 30)
                
                packet = host.generate_memory_request(
                    dst_device=dst_device,
                    address=address,
                    timestamp=timestamp
                )
                
                event = SimulationEvent(
                    timestamp=timestamp,
                    event_type="host_send",
                    packet=packet,
                    metadata={"host_id": host.host_id}
                )
                sim_engine.schedule_event(event)
    
    def print_status(self):
        """Print traffic generator statistics"""
        print("\n=== Traffic Statistics ===")
        for host in self.hosts:
            print(f"Host {host.host_id}: sent={host.packets_sent}, "
                  f"received={host.packets_received}, outstanding={host.num_outstanding}")

class AdaptiveRateController:
    """Rate controls host traffic based on ECN feedback"""
    def __init__(self, initial_rate=100, window_duration_ns=1000.0):
        self.current_rate = float(initial_rate)  # packets per time window
        self.ecn_count = 0
        self.total_sent = 0
        self.window_duration_ns = window_duration_ns
        self.window_start = 0.0

    def should_send(self, current_time: float) -> bool:
        """Check if we can send based on rate limit"""
        # Reset window if expired
        if current_time >= self.window_start + self.window_duration_ns:
            self.window_start = current_time
            self.total_sent = 0
            
        if self.total_sent < self.current_rate:
            self.total_sent += 1
            return True
        return False

    def process_ecn_feedback(self, packet: CXLPacket):
        if packet.ecn_marked:
            self.ecn_count += 1
            # Multiplicative decrease (drop to 50%)
            self.current_rate = max(1.0, self.current_rate * 0.5)
        else:
            # Additive increase (+1 packet per window)
            self.current_rate += 1.0
