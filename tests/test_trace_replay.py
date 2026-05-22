import pytest
import tempfile
import os
from src.workload.patterns import TraceReplayWorkload, MemoryRequest

def test_trace_replay_parsing():
    # Create a temporary trace file
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv') as f:
        f.write("timestamp_ns,host_id,device_id,address,is_read\n")
        f.write("100.5,0,1,0x1000,1\n")
        f.write("200.0,1,0,4096,0\n")
        f.write("300.0,0,1,0x2000,true\n")
        f.write("400.0,2,2,8192,false\n")  # Out of bounds host/device
        f.write("500.0,0,0,0x3000,read\n")
        trace_path = f.name
        
    try:
        workload = TraceReplayWorkload(trace_file=trace_path)
        
        # We assume 2 hosts and 2 devices, so the 400.0 request should be ignored
        requests = workload.generate_requests(
            num_hosts=2, 
            num_devices=2, 
            duration_ns=1000.0, 
            requests_per_host=10  # This param should be ignored by trace replay
        )
        
        assert len(requests) == 4
        
        # Check first request
        assert requests[0].timestamp == 100.5
        assert requests[0].host_id == 0
        assert requests[0].device_id == 1
        assert requests[0].address == 4096  # 0x1000
        assert requests[0].is_read is True
        
        # Check second request
        assert requests[1].timestamp == 200.0
        assert requests[1].host_id == 1
        assert requests[1].device_id == 0
        assert requests[1].address == 4096
        assert requests[1].is_read is False
        
        # Check third request
        assert requests[2].timestamp == 300.0
        assert requests[2].address == 8192  # 0x2000
        assert requests[2].is_read is True
        
        # Check fourth request
        assert requests[3].timestamp == 500.0
        assert requests[3].address == 12288 # 0x3000
        assert requests[3].is_read is True
        
    finally:
        os.unlink(trace_path)

def test_trace_replay_duration_cutoff():
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv') as f:
        f.write("timestamp_ns,host_id,device_id,address,is_read\n")
        f.write("100.0,0,0,0x1000,1\n")
        f.write("500.0,0,0,0x2000,1\n")
        f.write("1500.0,0,0,0x3000,1\n")
        trace_path = f.name
        
    try:
        workload = TraceReplayWorkload(trace_file=trace_path)
        
        # Cut off at 1000ns
        requests = workload.generate_requests(2, 2, duration_ns=1000.0, requests_per_host=10)
        
        assert len(requests) == 2
        assert requests[-1].timestamp == 500.0
        
    finally:
        os.unlink(trace_path)
