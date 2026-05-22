"""Tests for routing strategies."""

import pytest
from src.core.switch import CXLSwitch
from src.core.packet import CXLPacket, CXLTransactionType
from src.routing.strategy import StaticRouting, ECMPRouting, WeightedRouting

def test_ecmp_routing():
    switch = CXLSwitch(switch_id=0, num_ports=4)
    strategy = ECMPRouting()
    
    packet1 = CXLPacket(1, CXLTransactionType.MEM_READ, src_host=0, dst_device=0, address=0x1000)
    packet2 = CXLPacket(2, CXLTransactionType.MEM_READ, src_host=0, dst_device=0, address=0x1000)
    packet3 = CXLPacket(3, CXLTransactionType.MEM_READ, src_host=1, dst_device=0, address=0x2000)
    
    # Packets in same flow should hash to same port
    port1 = strategy.get_output_port(switch, packet1, [0, 1])
    port2 = strategy.get_output_port(switch, packet2, [0, 1])
    assert port1 == port2

def test_weighted_routing():
    switch = CXLSwitch(switch_id=0, num_ports=4)
    strategy = WeightedRouting()
    
    packet = CXLPacket(1, CXLTransactionType.MEM_READ, src_host=0, dst_device=0, address=0x1000)
    
    # Enqueue packets on port 0 to make it congested
    switch.ports[0].queues[packet.priority].append(packet)
    switch.ports[0].queues[packet.priority].append(packet)
    
    # Port 1 is empty, so it should be chosen
    port = strategy.get_output_port(switch, packet, [0, 1])
    assert port == 1
