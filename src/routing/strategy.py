"""
Routing strategies for CXL fabric switches.
"""
import random
from typing import List
from src.core.packet import CXLPacket

class RoutingStrategy:
    """Base class for routing strategies."""
    def get_output_port(self, switch, packet: CXLPacket, available_ports: List[int]) -> int:
        """
        Determine which output port to use for the given packet.
        
        Args:
            switch: The CXLSwitch making the routing decision
            packet: The packet to route
            available_ports: List of valid output ports for the packet's destination
            
        Returns:
            Selected output port index
        """
        raise NotImplementedError

class StaticRouting(RoutingStrategy):
    """Always picks the first available port (e.g., spine 0)."""
    def get_output_port(self, switch, packet: CXLPacket, available_ports: List[int]) -> int:
        if not available_ports:
            raise ValueError(f"No available ports to route packet {packet.packet_id}")
        return available_ports[0]

class ECMPRouting(RoutingStrategy):
    """
    Equal-Cost Multi-Path routing.
    Hashes flow parameters to consistently route same flow on same path.
    """
    def get_output_port(self, switch, packet: CXLPacket, available_ports: List[int]) -> int:
        if not available_ports:
            raise ValueError(f"No available ports to route packet {packet.packet_id}")
        
        # Flow is defined by source, destination, and address
        flow_hash = hash((packet.src_host, packet.dst_device, packet.address))
        
        # Pick port based on hash
        idx = flow_hash % len(available_ports)
        return available_ports[idx]

class WeightedRouting(RoutingStrategy):
    """
    Load-aware routing.
    Picks the port with the lowest current queue occupancy.
    """
    def get_output_port(self, switch, packet: CXLPacket, available_ports: List[int]) -> int:
        if not available_ports:
            raise ValueError(f"No available ports to route packet {packet.packet_id}")
        
        # Find port with minimum occupancy
        best_port = available_ports[0]
        min_occupancy = float('inf')
        
        for port_idx in available_ports:
            port = switch.ports[port_idx]
            if port.occupancy < min_occupancy:
                min_occupancy = port.occupancy
                best_port = port_idx
                
        return best_port
