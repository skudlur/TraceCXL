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
]
