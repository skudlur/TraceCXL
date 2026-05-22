"""Core simulation components for TraceCXL."""

from .packet import (
    CXLPacket, CXLTransactionType, SimulationEvent, Priority,
    CXL_DEVICE_LATENCY, CXL_SWITCH_LATENCY, LOCAL_DRAM_LATENCY
)
from .engine import SimulationEngine, SimulationStats
from .switch import CXLSwitch, SwitchPort
from .host import Host, TrafficGenerator

__all__ = [
    'CXLPacket',
    'CXLTransactionType',
    'SimulationEvent',
    'Priority',
    'SimulationEngine',
    'SimulationStats',
    'CXLSwitch',
    'SwitchPort',
    'Host',
    'TrafficGenerator',
    'CXL_DEVICE_LATENCY',
    'CXL_SWITCH_LATENCY',
    'LOCAL_DRAM_LATENCY',
]
