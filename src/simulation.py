import logging
from typing import Optional, Dict

from src.core import (
    SimulationEngine, SimulationEvent, 
    CXL_DEVICE_LATENCY, CXL_SWITCH_LATENCY, 
    CXLPacket, Host, CXLSwitch
)
from src.topology.builder import FabricTopology
from src.workload.patterns import WorkloadPattern, MemoryRequest

logger = logging.getLogger(__name__)

class FabricSimulation:
    """Encapsulates a CXL fabric simulation run."""
    
    def __init__(self, topology: FabricTopology, metrics_collector=None):
        self.topology = topology
        self.metrics_collector = metrics_collector
        self.engine = SimulationEngine(metrics_collector=metrics_collector)
        
        # Register handlers
        self.engine.register_handler("host_send", self.handle_host_send)
        self.engine.register_handler("switch_arrive", self.handle_switch_arrive)
        self.engine.register_handler("switch_transmit", self.handle_switch_transmit)
        self.engine.register_handler("device_response", self.handle_device_response)
        self.engine.register_handler("host_receive", self.handle_host_receive)
        
        self.next_response_id = 1000000 # Offset for response IDs

    def run_workload(self, workload: WorkloadPattern, duration_ns: float, requests_per_host: int = 1000):
        """Run a workload on the fabric."""
        logger.info(f"Generating workload...")
        requests = workload.generate_requests(
            num_hosts=len(self.topology.hosts),
            num_devices=len(self.topology.cxl_devices),
            duration_ns=duration_ns,
            requests_per_host=requests_per_host
        )
        
        # Schedule initial host requests
        for req in requests:
            host = self.topology.hosts[req.host_id]
            packet = host.generate_memory_request(
                dst_device=req.device_id,
                address=req.address,
                is_read=req.is_read,
                timestamp=req.timestamp
            )
            # engine.stats.packets_sent is incremented inside engine or here?
            # the original examples didn't increment it, let's just let it track
            event = SimulationEvent(
                timestamp=req.timestamp,
                event_type="host_send",
                packet=packet,
                metadata={"host_id": host.host_id}
            )
            # The first packet is already scheduled, we don't increment engine.stats.packets_sent here 
            # because the new SimulationEngine.schedule_event increments it when it's event_type=="host_send".
            self.engine.schedule_event(event)
            
        logger.info(f"Scheduled {len(requests)} initial events.")
        
        logger.info("Running simulation...")
        # Run until all packets have had time to finish or max timeout
        stats = self.engine.run(until=duration_ns + 50000)
        return stats

    def handle_host_send(self, event: SimulationEvent):
        """Host sends packet into fabric"""
        packet = event.packet
        host_id = event.metadata["host_id"]
        host = self.topology.hosts[host_id]
        
        # Check rate controller
        if not host.rate_controller.should_send(self.engine.current_time):
            # Throttle: Reschedule this packet for next window
            event.timestamp = host.rate_controller.window_start + host.rate_controller.window_duration_ns
            self.engine.schedule_event(event)
            return
            
        # Find which switch this host connects to
        host_switch_id = self.topology.host_to_switch[host_id]
        
        # Determine arrival port on the switch
        # For simplicity, if we know the topology we could find the exact port,
        # but the builder mapped hosts to port (num_spines + index).
        # We can just iterate over switch_links to find the exact port, 
        # but in builder we know host port is (num_spines + host_index).
        # A simpler way: we'll use a hack or topological query.
        arrival_port = 0 # Dummy for now, usually switch.route_packet handles arrival port loosely except for stats
        if hasattr(self.topology, 'num_spines'): # Two tier
            hosts_on_leaf = [h.host_id for h in self.topology.hosts if self.topology.host_to_switch[h.host_id] == host_switch_id]
            host_index = hosts_on_leaf.index(host_id)
            arrival_port = self.topology.num_spines + host_index
        else:
            arrival_port = host_id
        
        # Route packet immediately at the first switch
        host_switch = self.topology.switches[host_switch_id]
        success = host_switch.route_packet(packet, arrival_port, self.engine)
        if not success:
            pass # Dropped at edge

    def handle_switch_arrive(self, event: SimulationEvent):
        """Packet arrives at a downstream switch"""
        packet = event.packet
        switch_id = event.switch_id
        arrival_port = event.metadata["arrival_port"]
        
        switch = self.topology.switches[switch_id]
        success = switch.route_packet(packet, arrival_port, self.engine)
        if not success:
            pass

    def handle_switch_transmit(self, event: SimulationEvent):
        """Switch transmits packet from output queue"""
        switch_id = event.switch_id
        output_port = event.metadata["output_port"]
        switch = self.topology.switches[switch_id]
        
        packet = switch.transmit_packet(output_port, self.engine)
        if packet is None:
            return
            
        # Is this an internal link, or to an endpoint?
        next_hop = self.topology.get_next_hop(switch_id, output_port)
        
        if next_hop is not None:
            # Internal link to another switch
            next_switch_id, arrival_port = next_hop
            arrive_time = self.engine.current_time + CXL_SWITCH_LATENCY
            
            arrive_event = SimulationEvent(
                timestamp=arrive_time,
                event_type="switch_arrive",
                packet=packet,
                switch_id=next_switch_id,
                metadata={"arrival_port": arrival_port}
            )
            self.engine.schedule_event(arrive_event)
        else:
            # Reached an endpoint (host or device)
            # If it's a response packet, it goes to host
            if packet.is_response:
                arrive_time = self.engine.current_time + CXL_SWITCH_LATENCY
                host_event = SimulationEvent(
                    timestamp=arrive_time,
                    event_type="host_receive",
                    packet=packet
                )
                self.engine.schedule_event(host_event)
            else:
                # Forward packet, goes to device
                response_time = self.engine.current_time + CXL_SWITCH_LATENCY + CXL_DEVICE_LATENCY
                resp_event = SimulationEvent(
                    timestamp=response_time,
                    event_type="device_response",
                    packet=packet
                )
                self.engine.schedule_event(resp_event)

    def handle_device_response(self, event: SimulationEvent):
        """CXL device responds, creates response packet"""
        original_packet = event.packet
        dev_id = original_packet.dst_device
        
        # Create response
        response_packet = original_packet.create_response(self.engine.current_time, self.next_response_id)
        self.next_response_id += 1
        
        # Inject response back into fabric
        device_switch_id = self.topology.device_to_switch[dev_id]
        device_switch = self.topology.switches[device_switch_id]
        
        # Calculate arrival port
        arrival_port = 0
        if hasattr(self.topology, 'num_spines'):
            devices_on_leaf = [d for d in self.topology.cxl_devices if self.topology.device_to_switch[d] == device_switch_id]
            dev_index = devices_on_leaf.index(dev_id)
            arrival_port = self.topology.num_spines + dev_index
        else:
            arrival_port = len(self.topology.hosts) + dev_id
            
        success = device_switch.route_packet(response_packet, arrival_port, self.engine)
        if not success:
            pass

    def handle_host_receive(self, event: SimulationEvent):
        """Host receives response packet"""
        packet = event.packet
        host = self.topology.hosts[packet.src_host]
        host.receive_response(packet)
        self.engine.stats.record_packet_completion(packet, self.engine.current_time)
