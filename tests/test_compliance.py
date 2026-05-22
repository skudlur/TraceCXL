import pytest

from src.core.packet import CXLPacket, CXLTransactionType, SimulationEvent
from src.analysis.validator import ProtocolValidator, CXLProtocolError
from src.core.engine import SimulationEngine

def test_unaligned_address():
    engine = SimulationEngine()
    validator = ProtocolValidator(engine)
    
    # 0x1000 is 4096 (aligned to 64). 0x1001 is unaligned.
    packet = CXLPacket(
        packet_id=1,
        tx_type=CXLTransactionType.MEM_READ,
        src_host=0,
        dst_device=0,
        address=0x1001,
        size=64
    )
    
    event = SimulationEvent(timestamp=0, event_type="host_generate", packet=packet)
    
    with pytest.raises(CXLProtocolError, match="Unaligned address"):
        # Dispatching event manually to trigger the validator hook
        for handler in engine.event_handlers["host_generate"]:
            handler(event)

def test_invalid_request_size():
    engine = SimulationEngine()
    validator = ProtocolValidator(engine)
    
    packet = CXLPacket(
        packet_id=2,
        tx_type=CXLTransactionType.MEM_WRITE,
        src_host=0,
        dst_device=0,
        address=0x1000,
        size=128 # Must be exactly 64
    )
    
    event = SimulationEvent(timestamp=0, event_type="host_generate", packet=packet)
    
    with pytest.raises(CXLProtocolError, match="Invalid request size"):
        for handler in engine.event_handlers["host_generate"]:
            handler(event)

def test_invalid_read_response_size():
    engine = SimulationEngine()
    validator = ProtocolValidator(engine)
    
    packet = CXLPacket(
        packet_id=3,
        tx_type=CXLTransactionType.MEM_READ_RESP,
        src_host=0,
        dst_device=0,
        address=0x1000,
        size=128, # Must be 64
        is_response=True
    )
    
    event = SimulationEvent(timestamp=0, event_type="crossbar_process", packet=packet)
    
    with pytest.raises(CXLProtocolError, match="expected 64 bytes"):
        for handler in engine.event_handlers["crossbar_process"]:
            handler(event)

def test_invalid_write_ack_size():
    engine = SimulationEngine()
    validator = ProtocolValidator(engine)
    
    packet = CXLPacket(
        packet_id=4,
        tx_type=CXLTransactionType.MEM_WRITE_ACK,
        src_host=0,
        dst_device=0,
        address=0x1000,
        size=64, # Must be 0
        is_response=True
    )
    
    event = SimulationEvent(timestamp=0, event_type="crossbar_process", packet=packet)
    
    with pytest.raises(CXLProtocolError, match="expected 0 bytes"):
        for handler in engine.event_handlers["crossbar_process"]:
            handler(event)
