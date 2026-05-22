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
        
        if not host.rate_controller.should_send(self.engine.current_time):
            event.timestamp = host.rate_controller.window_start + host.rate_controller.window_duration_ns
            self.engine.schedule_event(event)
            return
            
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
        """Host transmits flit from its egress queue if credits allow."""
        host_id = event.metadata["host_id"]
        host = self.topology.hosts[host_id]
        
        flit = host.transmit_request()
        if not flit:
            host.is_transmitting = False
            return
            
        if flit.is_tail:
            self.engine.stats.packets_sent += 1
            
        switch_id = self.topology.host_to_switch[host_id]
        arrival_port = self.get_switch_arrival_port(host_id, switch_id)
        
        serialization_ns = (64 * 8) / (64.0 * 1e9) * 1e9
        host.next_available_time = self.engine.current_time + serialization_ns
        
        arrive_event = SimulationEvent(
            timestamp=self.engine.current_time + CXL_SWITCH_LATENCY,
            event_type="switch_arrive",
            flit=flit,
            switch_id=switch_id,
            metadata={"arrival_port": arrival_port, "sender_type": "host", "sender_id": host_id}
        )
        self.engine.schedule_event(arrive_event)
        
        if host.has_transmittable_packets():
            self._schedule_host_transmit(host)
        else:
            host.is_transmitting = False

    def handle_switch_arrive(self, event: SimulationEvent):
        """Flit arrives at switch ingress."""
        flit = event.flit
        switch_id = event.switch_id
        arrival_port = event.metadata["arrival_port"]
        switch = self.topology.switches[switch_id]
        
        switch.ports[arrival_port].enqueue_ingress(flit)
        
        # When tail flit arrives, the whole packet is ready to be routed
        if flit.is_tail:
            crossbar_event = SimulationEvent(
                timestamp=self.engine.current_time + 10.0,
                event_type="crossbar_process",
                packet=flit.packet,
                switch_id=switch_id,
                metadata=event.metadata
            )
            self.engine.schedule_event(crossbar_event)

    def handle_crossbar_process(self, event: SimulationEvent):
        """Switch moves all flits of a packet from ingress to egress."""
        packet = event.packet
        switch_id = event.switch_id
        arrival_port = event.metadata["arrival_port"]
        switch = self.topology.switches[switch_id]
        
        flits = []
        ingress_queue = switch.ports[arrival_port].ingress_queues[packet.vc_id]
        # Since PCIe enforces flits of a packet stay contiguous on the same VC,
        # we can just pop the flits for this packet from the queue.
        # However, to be safe against interleaved bugs, we just pull the expected number of flits
        # from the front. Wait, what if there's another packet's flits interleaved?
        # That's an error in our model if it happens. Let's assume contiguous.
        while ingress_queue:
            f = ingress_queue.popleft()
            flits.append(f)
            if f.is_tail:
                break
                
        switch.route_packet(packet, flits, arrival_port, self.engine)
        
        sender_type = event.metadata.get("sender_type")
        sender_id = event.metadata.get("sender_id")
        
        if sender_type and sender_id is not None:
            # Emit a single credit return event that restores N credits
            credit_event = SimulationEvent(
                timestamp=self.engine.current_time + CXL_SWITCH_LATENCY,
                event_type="credit_return",
                metadata={
                    "receiver_type": sender_type, 
                    "receiver_id": sender_id, 
                    "vc_id": packet.vc_id, 
                    "port_id": event.metadata.get("sender_port"),
                    "num_credits": len(flits)
                }
            )
            self.engine.schedule_event(credit_event)

    def handle_credit_return(self, event: SimulationEvent):
        """Process credit return at sender."""
        rtype = event.metadata["receiver_type"]
        rid = event.metadata["receiver_id"]
        vc_id = event.metadata["vc_id"]
        num_credits = event.metadata.get("num_credits", 1)
        
        if rtype == "host":
            host = self.topology.hosts[rid]
            for _ in range(num_credits):
                was_stalled = not host.has_transmittable_packets()
                host.receive_credit(vc_id)
                if was_stalled and host.has_transmittable_packets() and not host.is_transmitting:
                    self._schedule_host_transmit(host)
                
        elif rtype == "switch":
            switch = self.topology.switches[rid]
            port_id = event.metadata["port_id"]
            for _ in range(num_credits):
                switch.receive_credit(port_id, vc_id, self.engine)

    def handle_switch_transmit(self, event: SimulationEvent):
        """Switch transmits flit from egress queue."""
        switch_id = event.switch_id
        output_port = event.metadata["output_port"]
        switch = self.topology.switches[switch_id]
        
        flit = switch.transmit_packet(output_port, self.engine)
        if flit is None:
            return
            
        next_hop = self.topology.get_next_hop(switch_id, output_port)
        
        if next_hop is not None:
            next_switch_id, arrival_port = next_hop
            arrive_event = SimulationEvent(
                timestamp=self.engine.current_time + CXL_SWITCH_LATENCY,
                event_type="switch_arrive",
                flit=flit,
                switch_id=next_switch_id,
                metadata={"arrival_port": arrival_port, "sender_type": "switch", "sender_id": switch_id, "sender_port": output_port}
            )
            self.engine.schedule_event(arrive_event)
        else:
            if flit.packet.is_response:
                host_event = SimulationEvent(
                    timestamp=self.engine.current_time + CXL_SWITCH_LATENCY,
                    event_type="host_receive",
                    flit=flit,
                    metadata={"sender_type": "switch", "sender_id": switch_id, "sender_port": output_port}
                )
                self.engine.schedule_event(host_event)
            else:
                # Flits arrive at device. Device only processes when tail arrives.
                resp_event = SimulationEvent(
                    timestamp=self.engine.current_time + CXL_SWITCH_LATENCY,
                    event_type="device_response",
                    flit=flit,
                    metadata={"sender_type": "switch", "sender_id": switch_id, "sender_port": output_port}
                )
                self.engine.schedule_event(resp_event)

    def handle_device_response(self, event: SimulationEvent):
        """Device processes request flits. Generates response when tail arrives."""
        flit = event.flit
        original_packet = flit.packet
        dev_id = original_packet.dst_device
        
        sender_type = event.metadata.get("sender_type")
        sender_id = event.metadata.get("sender_id")
        sender_port = event.metadata.get("sender_port")
        
        if sender_type == "switch":
            credit_event = SimulationEvent(
                timestamp=self.engine.current_time,
                event_type="credit_return",
                metadata={"receiver_type": "switch", "receiver_id": sender_id, "vc_id": original_packet.vc_id, "port_id": sender_port, "num_credits": 1}
            )
            self.engine.schedule_event(credit_event)
        
        if flit.is_tail:
            response_packet = original_packet.create_response(self.engine.current_time, self.next_response_id)
            self.next_response_id += 1
            
            device_switch_id = self.topology.device_to_switch[dev_id]
            device_switch = self.topology.switches[device_switch_id]
            arrival_port = self.get_device_arrival_port(dev_id, device_switch_id)
            
            # The device generates all flits for the response and injects them instantly
            # into the switch's ingress queue (assuming device has infinite Tx credits).
            resp_flits = response_packet.generate_flits()
            for f in resp_flits:
                device_switch.ports[arrival_port].enqueue_ingress(f)
                
            crossbar_event = SimulationEvent(
                timestamp=self.engine.current_time + CXL_DEVICE_LATENCY,
                event_type="crossbar_process",
                packet=response_packet,
                switch_id=device_switch_id,
                metadata={"arrival_port": arrival_port, "sender_type": "device", "sender_id": dev_id}
            )
            self.engine.schedule_event(crossbar_event)

    def handle_host_receive(self, event: SimulationEvent):
        """Host receives response flit."""
        flit = event.flit
        packet = flit.packet
        host = self.topology.hosts[packet.src_host]
        
        sender_type = event.metadata.get("sender_type")
        sender_id = event.metadata.get("sender_id")
        sender_port = event.metadata.get("sender_port")
        if sender_type == "switch":
            credit_event = SimulationEvent(
                timestamp=self.engine.current_time,
                event_type="credit_return",
                metadata={"receiver_type": "switch", "receiver_id": sender_id, "vc_id": packet.vc_id, "port_id": sender_port, "num_credits": 1}
            )
            self.engine.schedule_event(credit_event)
            
        if flit.is_tail:
            host.receive_response(packet)
            self.engine.stats.record_packet_completion(packet, self.engine.current_time)
