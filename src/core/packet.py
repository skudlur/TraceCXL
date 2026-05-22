"""
Core data structures for CXL fabric simulation.

This module defines the fundamental building blocks:
- CXL packets (memory read/write requests)
- Simulation events
- Transaction types
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional


class CXLTransactionType(Enum):
    """CXL.mem transaction types"""
    MEM_READ = auto()      # Memory read request
    MEM_WRITE = auto()     # Memory write request
    MEM_READ_RESP = auto() # Read response with data
    MEM_WRITE_ACK = auto() # Write acknowledgment


class Priority(Enum):
    """QoS priority levels"""
    LOW = 0
    MEDIUM = 1
    HIGH = 2
    CRITICAL = 3


@dataclass
class CXLPacket:
    """
    Represents a single CXL transaction packet.
    
    Attributes:
        packet_id: Unique identifier
        tx_type: Transaction type (read/write/response)
        src_host: Source host ID
        dst_device: Target CXL memory device ID
        address: Memory address being accessed
        size: Transfer size in bytes (typically 64B cache line)
        priority: QoS priority level
        timestamp: Creation timestamp (ns)
        route: List of switch IDs in the packet's path
    """
    packet_id: int
    tx_type: CXLTransactionType
    src_host: int
    dst_device: int
    address: int
    size: int = 64  # Default CXL cache line size
    priority: Priority = Priority.MEDIUM
    timestamp: float = 0.0
    route: list[int] = field(default_factory=list)
    ecn_marked: bool = False
    is_response: bool = False
    
    @property
    def vc_id(self) -> int:
        """
        Virtual Channel ID based on direction and QoS Priority.
        Requests: VC 0-3 (LOW to CRITICAL)
        Responses: VC 4-7 (LOW to CRITICAL)
        """
        base = 4 if self.is_response else 0
        return base + self.priority.value

    @property
    def target(self):
        """Logical routing target for this packet"""
        if self.is_response:
            return f"host_{self.src_host}"
        return self.dst_device

    def latency_at(self, current_time: float) -> float:
        """Calculate end-to-end latency"""
        return current_time - self.timestamp

    def create_response(self, current_time: float, response_id: int) -> 'CXLPacket':
        """Create a response packet for this request."""
        tx_type = CXLTransactionType.MEM_READ_RESP if self.tx_type == CXLTransactionType.MEM_READ else CXLTransactionType.MEM_WRITE_ACK
        return CXLPacket(
            packet_id=response_id,
            tx_type=tx_type,
            src_host=self.src_host,
            dst_device=self.dst_device,
            address=self.address,
            size=64 if tx_type == CXLTransactionType.MEM_READ_RESP else 0,
            timestamp=current_time,
            priority=self.priority,
            is_response=True
        )


@dataclass
class SimulationEvent:
    """
    Discrete event for the simulation engine.
    
    Events are processed in timestamp order by the event loop.
    """
    timestamp: float           # When this event should fire (ns)
    event_type: str           # Event type identifier
    packet: Optional[CXLPacket] = None
    switch_id: Optional[int] = None
    metadata: dict = None
    
    def __lt__(self, other):
        """Enable priority queue ordering by timestamp"""
        return self.timestamp < other.timestamp
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


# CXL.mem protocol parameters
CXL_FLIT_SIZE = 64          # Bytes per flit
CXL_LINK_SPEED_GBPS = 64.0  # PCIe Gen5 x16
CXL_SERIALIZATION_DELAY = (CXL_FLIT_SIZE * 8) / (CXL_LINK_SPEED_GBPS * 1e9) * 1e9  # ns

# Latency constants
LOCAL_DRAM_LATENCY = 100.0   # ns
CXL_SWITCH_LATENCY = 30.0    # ns per hop
CXL_DEVICE_LATENCY = 150.0   # ns (device-side processing)
