#!/usr/bin/env python3

"""Workload generation for CXL fabric simulations."""

from .patterns import (
    WorkloadPattern,
    MemoryRequest,
    UniformRandomWorkload,
    ZipfianWorkload,
    HotspotWorkload,
    BurstyWorkload,
    SequentialWorkload,
    TraceReplayWorkload,
    create_workload,
)
from .trace_export import export_trace

__all__ = [
    'WorkloadPattern',
    'MemoryRequest',
    'UniformRandomWorkload',
    'ZipfianWorkload',
    'HotspotWorkload',
    'BurstyWorkload',
    'SequentialWorkload',
    'TraceReplayWorkload',
    'create_workload',
    'export_trace',
]
