"""Unit tests for core simulation components."""

import pytest
from src.core import (
    CXLPacket, CXLTransactionType, SimulationEvent,
    SimulationEngine, CXLSwitch, Host, Priority
)


class TestPacket:
    """Test CXL packet creation and methods"""
    
    def test_packet_creation(self):
        packet = CXLPacket(
            packet_id=1,
            tx_type=CXLTransactionType.MEM_READ,
            src_host=0,
            dst_device=1,
            address=0x1000,
            timestamp=100.0
        )
        
        assert packet.packet_id == 1
        assert packet.tx_type == CXLTransactionType.MEM_READ
        assert packet.size == 64  # Default cache line size
        assert packet.route == []
    
    def test_packet_latency(self):
        packet = CXLPacket(
            packet_id=1,
            tx_type=CXLTransactionType.MEM_READ,
            src_host=0,
            dst_device=1,
            address=0x1000,
            timestamp=100.0
        )
        
        latency = packet.latency_at(250.0)
        assert latency == 150.0


class TestSimulationEngine:
    """Test discrete-event simulation engine"""
    
    def test_engine_creation(self):
        engine = SimulationEngine()
        assert engine.current_time == 0.0
        assert len(engine.event_queue) == 0
    
    def test_schedule_event(self):
        engine = SimulationEngine()
        
        event = SimulationEvent(
            timestamp=100.0,
            event_type="test"
        )
        
        engine.schedule_event(event)
        assert len(engine.event_queue) == 1
    
    def test_event_ordering(self):
        engine = SimulationEngine()
        
        # Schedule out of order
        engine.schedule_event(SimulationEvent(timestamp=200.0, event_type="second"))
        engine.schedule_event(SimulationEvent(timestamp=100.0, event_type="first"))
        engine.schedule_event(SimulationEvent(timestamp=300.0, event_type="third"))
        
        # Events should be processed in timestamp order
        events_fired = []
        
        def handler(event):
            events_fired.append(event.event_type)
        
        engine.register_handler("first", handler)
        engine.register_handler("second", handler)
        engine.register_handler("third", handler)
        
        engine.run(until=400.0)
        
        assert events_fired == ["first", "second", "third"]


class TestSwitch:
    """Test CXL switch functionality"""
    
    def test_switch_creation(self):
        switch = CXLSwitch(switch_id=0, num_ports=4, queue_depth=32)
        assert switch.switch_id == 0
        assert switch.num_ports == 4
        assert len(switch.ports) == 4
    
    def test_routing_table(self):
        switch = CXLSwitch(switch_id=0, num_ports=4)
        switch.set_route(dst_target=0, output_port=2)
        
        assert switch.routing_table[0] == [2]
    
    def test_queue_overflow(self):
        switch = CXLSwitch(switch_id=0, num_ports=2, queue_depth=2)
        engine = SimulationEngine()
        
        # Try to enqueue 3 packets when queue depth is 2
        for i in range(3):
            packet = CXLPacket(
                packet_id=i,
                tx_type=CXLTransactionType.MEM_READ,
                src_host=0,
                dst_device=0,
                address=0x1000 * i
            )
            switch.routing_table[0] = [1]  # Route to port 1
            switch.route_packet(packet, arrival_port=0, sim_engine=engine)
        
        # With CBFC, packets are not dropped. They are queued in egress, 
        # but only 2 packets can be transmitted due to tx_credits=2.
        assert switch.total_packets_dropped == 0
        
        # Manually dequeue to simulate transmission
        p1 = switch.ports[1].dequeue_egress(0.0)
        p2 = switch.ports[1].dequeue_egress(0.0)
        p3 = switch.ports[1].dequeue_egress(0.0)
        
        assert p1 is not None
        assert p2 is not None
        assert p3 is None  # Third packet cannot be transmitted, no credits!


class TestHost:
    """Test host traffic generation"""
    
    def test_host_creation(self):
        host = Host(host_id=0, connected_switch=0)
        assert host.host_id == 0
        assert host.packets_sent == 0
    
    def test_request_generation(self):
        host = Host(host_id=0, connected_switch=0)
        
        packet = host.generate_memory_request(
            dst_device=1,
            address=0x1000,
            is_read=True,
            timestamp=100.0
        )
        
        assert packet.src_host == 0
        assert packet.dst_device == 1
        assert packet.tx_type == CXLTransactionType.MEM_READ
        assert host.packets_sent == 0 # Sent is 0 until transmitted
        assert len(host.egress_queues[packet.vc_id]) == 1
        assert host.num_outstanding == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
