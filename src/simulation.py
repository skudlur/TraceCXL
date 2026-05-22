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
        self.engine.register_handler("host_generate", self.handle_host_generate)
        self.engine.register_handler("host_transmit", self.handle_host_transmit)
        self.engine.register_handler("switch_arrive", self.handle_switch_arrive)
        self.engine.register_handler("crossbar_process", self.handle_crossbar_process)
        self.engine.register_handler("switch_transmit", self.handle_switch_transmit)
        self.engine.register_handler("device_response", self.handle_device_response)
        self.engine.register_handler("host_receive", self.handle_host_receive)
        self.engine.register_handler("credit_return", self.handle_credit_return)
        
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
        
        for req in requests:
            host = self.topology.hosts[req.host_id]
            packet = host.generate_memory_request(
                dst_device=req.device_id,
                address=req.address,
                is_read=req.is_read,
                timestamp=req.timestamp
            )
            event = SimulationEvent(
                timestamp=req.timestamp,
                event_type="host_generate",
                packet=packet,
                metadata={"host_id": host.host_id}
            )
            self.engine.schedule_event(event)
            
        logger.info(f"Scheduled {len(requests)} initial events.")
        logger.info("Running simulation...")
        stats = self.engine.run(until=duration_ns + 50000)
        return stats

    def get_switch_arrival_port(self, host_id: int, switch_id: int) -> int:
        if hasattr(self.topology, 'num_spines'):
            hosts_on_leaf = [h.host_id for h in self.topology.hosts if self.topology.host_to_switch[h.host_id] == switch_id]
            host_index = hosts_on_leaf.index(host_id)
            return self.topology.num_spines + host_index
        return host_id

    def get_device_arrival_port(self, dev_id: int, switch_id: int) -> int:
        if hasattr(self.topology, 'num_spines'):
            devices_on_leaf = [d for d in self.topology.cxl_devices if self.topology.device_to_switch[d] == switch_id]
            dev_index = devices_on_leaf.index(dev_id)
            return self.topology.num_spines + dev_index
        return len(self.topology.hosts) + dev_id

    def handle_host_generate(self, event: SimulationEvent):
        """Host generates a packet and attempts to transmit."""
        host_id = event.metadata["host_id"]
        host = self.topology.hosts[host_id]
        
        # Check rate controller
        if not host.rate_controller.should_send(self.engine.current_time):
            # Throttle: Reschedule generation for next window
            event.timestamp = host.rate_controller.window_start + host.rate_controller.window_duration_ns
            self.engine.schedule_event(event)
            return
            
        # If not transmitting, trigger transmit loop
        if not host.is_transmitting and host.has_transmittable_packets():
            self._schedule_host_transmit(host)

    def _schedule_host_transmit(self, host):
        host.is_transmitting = True
        tx_time = max(self.engine.current_time, host.next_available_time)
        event = SimulationEvent(
            timestamp=tx_time,
            event_type="host_transmit",
            metadata={"host_id": host.host_id}
        )
        self.engine.schedule_event(event)

    def handle_host_transmit(self, event: SimulationEvent):
        """Host transmits packet from its egress queue if credits allow."""
        host_id = event.metadata["host_id"]
        host = self.topology.hosts[host_id]
        
        packet = host.transmit_request()
        if not packet:
            host.is_transmitting = False
            return
            
        switch_id = self.topology.host_to_switch[host_id]
        arrival_port = self.get_switch_arrival_port(host_id, switch_id)
        
        # Serialization delay logic
        serialization_ns = (packet.size * 8) / (64.0 * 1e9) * 1e9
        host.next_available_time = self.engine.current_time + serialization_ns
        
        # Packet arrives at switch
        arrive_event = SimulationEvent(
            timestamp=self.engine.current_time + CXL_SWITCH_LATENCY,
            event_type="switch_arrive",
            packet=packet,
            switch_id=switch_id,
            metadata={"arrival_port": arrival_port, "sender_type": "host", "sender_id": host_id}
        )
        self.engine.schedule_event(arrive_event)
        
        if host.has_transmittable_packets():
            self._schedule_host_transmit(host)
        else:
            host.is_transmitting = False

    def handle_switch_arrive(self, event: SimulationEvent):
        """Packet arrives at switch ingress."""
        packet = event.packet
        switch_id = event.switch_id
        arrival_port = event.metadata["arrival_port"]
        switch = self.topology.switches[switch_id]
        
        # Place in ingress queue
        switch.ports[arrival_port].enqueue_ingress(packet)
        
        # Schedule crossbar processing
        crossbar_event = SimulationEvent(
            timestamp=self.engine.current_time + 10.0, # 10ns crossbar delay
            event_type="crossbar_process",
            packet=packet,
            switch_id=switch_id,
            metadata=event.metadata
        )
        self.engine.schedule_event(crossbar_event)

    def handle_crossbar_process(self, event: SimulationEvent):
        """Switch moves packet from ingress to egress, emits credit return."""
        packet = event.packet
        switch_id = event.switch_id
        arrival_port = event.metadata["arrival_port"]
        switch = self.topology.switches[switch_id]
        
        # Pop from ingress
        if switch.ports[arrival_port].ingress_queues[packet.vc_id]:
            switch.ports[arrival_port].ingress_queues[packet.vc_id].popleft()
        
        # Route to egress
        switch.route_packet(packet, arrival_port, self.engine)
        
        # Emit credit return to upstream sender
        sender_type = event.metadata.get("sender_type")
        sender_id = event.metadata.get("sender_id")
        
        if sender_type and sender_id is not None:
            # Send credit return back
            credit_event = SimulationEvent(
                timestamp=self.engine.current_time + CXL_SWITCH_LATENCY,
                event_type="credit_return",
                metadata={"receiver_type": sender_type, "receiver_id": sender_id, "vc_id": packet.vc_id, "port_id": event.metadata.get("sender_port")}
            )
            self.engine.schedule_event(credit_event)

    def handle_credit_return(self, event: SimulationEvent):
        """Process credit return at sender."""
        rtype = event.metadata["receiver_type"]
        rid = event.metadata["receiver_id"]
        vc_id = event.metadata["vc_id"]
        
        if rtype == "host":
            host = self.topology.hosts[rid]
            was_stalled = not host.has_transmittable_packets()
            host.receive_credit(vc_id)
            if was_stalled and host.has_transmittable_packets() and not host.is_transmitting:
                self._schedule_host_transmit(host)
                
        elif rtype == "switch":
            switch = self.topology.switches[rid]
            port_id = event.metadata["port_id"]
            switch.receive_credit(port_id, vc_id, self.engine)

    def handle_switch_transmit(self, event: SimulationEvent):
        """Switch transmits packet from egress queue."""
        switch_id = event.switch_id
        output_port = event.metadata["output_port"]
        switch = self.topology.switches[switch_id]
        
        packet = switch.transmit_packet(output_port, self.engine)
        if packet is None:
            return
            
        next_hop = self.topology.get_next_hop(switch_id, output_port)
        
        if next_hop is not None:
            # To another switch
            next_switch_id, arrival_port = next_hop
            arrive_event = SimulationEvent(
                timestamp=self.engine.current_time + CXL_SWITCH_LATENCY,
                event_type="switch_arrive",
                packet=packet,
                switch_id=next_switch_id,
                metadata={"arrival_port": arrival_port, "sender_type": "switch", "sender_id": switch_id, "sender_port": output_port}
            )
            self.engine.schedule_event(arrive_event)
        else:
            # To endpoint (Host or Device)
            if packet.is_response:
                host_event = SimulationEvent(
                    timestamp=self.engine.current_time + CXL_SWITCH_LATENCY,
                    event_type="host_receive",
                    packet=packet,
                    metadata={"sender_type": "switch", "sender_id": switch_id, "sender_port": output_port}
                )
                self.engine.schedule_event(host_event)
            else:
                resp_event = SimulationEvent(
                    timestamp=self.engine.current_time + CXL_SWITCH_LATENCY + CXL_DEVICE_LATENCY,
                    event_type="device_response",
                    packet=packet,
                    metadata={"sender_type": "switch", "sender_id": switch_id, "sender_port": output_port}
                )
                self.engine.schedule_event(resp_event)

    def handle_device_response(self, event: SimulationEvent):
        """Device processes request and creates response."""
        original_packet = event.packet
        dev_id = original_packet.dst_device
        
        # Credit return to the switch that sent it to the device
        sender_type = event.metadata.get("sender_type")
        sender_id = event.metadata.get("sender_id")
        sender_port = event.metadata.get("sender_port")
        if sender_type == "switch":
            credit_event = SimulationEvent(
                timestamp=self.engine.current_time,
                event_type="credit_return",
                metadata={"receiver_type": "switch", "receiver_id": sender_id, "vc_id": original_packet.vc_id, "port_id": sender_port}
            )
            self.engine.schedule_event(credit_event)
        
        # Generate response packet
        response_packet = original_packet.create_response(self.engine.current_time, self.next_response_id)
        self.next_response_id += 1
        
        device_switch_id = self.topology.device_to_switch[dev_id]
        device_switch = self.topology.switches[device_switch_id]
        arrival_port = self.get_device_arrival_port(dev_id, device_switch_id)
        
        # Device is not modeled with credits currently, it just injects directly to switch ingress
        device_switch.ports[arrival_port].enqueue_ingress(response_packet)
        
        crossbar_event = SimulationEvent(
            timestamp=self.engine.current_time + 10.0,
            event_type="crossbar_process",
            packet=response_packet,
            switch_id=device_switch_id,
            metadata={"arrival_port": arrival_port, "sender_type": "device", "sender_id": dev_id}
        )
        self.engine.schedule_event(crossbar_event)

    def handle_host_receive(self, event: SimulationEvent):
        """Host receives response packet."""
        packet = event.packet
        host = self.topology.hosts[packet.src_host]
        host.receive_response(packet)
        self.engine.stats.record_packet_completion(packet, self.engine.current_time)
        
        # Credit return to switch
        sender_type = event.metadata.get("sender_type")
        sender_id = event.metadata.get("sender_id")
        sender_port = event.metadata.get("sender_port")
        if sender_type == "switch":
            credit_event = SimulationEvent(
                timestamp=self.engine.current_time,
                event_type="credit_return",
                metadata={"receiver_type": "switch", "receiver_id": sender_id, "vc_id": packet.vc_id, "port_id": sender_port}
            )
            self.engine.schedule_event(credit_event)
