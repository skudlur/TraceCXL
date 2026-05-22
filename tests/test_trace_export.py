import pytest
import tempfile
import os

from src.workload import create_workload, export_trace

def test_trace_export_and_replay():
    # 1. Create a uniform workload and export it
    workload = create_workload("uniform", seed=42, read_ratio=0.5)
    
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv') as f:
        trace_path = f.name
        
    try:
        # Generate 10 requests total
        num_exported = export_trace(
            workload=workload,
            filepath=trace_path,
            num_hosts=2,
            num_devices=2,
            duration_ns=1000.0,
            requests_per_host=5
        )
        assert num_exported == 10
        
        # 2. Replay the trace using TraceReplayWorkload
        replay_workload = create_workload("trace", trace_file=trace_path)
        replayed_requests = replay_workload.generate_requests(
            num_hosts=2,
            num_devices=2,
            duration_ns=2000.0, # Large enough to read all
            requests_per_host=0 # Ignored by trace workload
        )
        
        assert len(replayed_requests) == 10
        
        # Original requests generated directly (for comparison)
        orig_workload = create_workload("uniform", seed=42, read_ratio=0.5)
        orig_requests = orig_workload.generate_requests(2, 2, 1000.0, 5)
        orig_requests.sort(key=lambda req: req.timestamp)
        
        # 3. Compare exported vs originally generated
        for orig, replayed in zip(orig_requests, replayed_requests):
            # Timestamps are formatted to 2 decimal places in CSV
            assert f"{orig.timestamp:.2f}" == f"{replayed.timestamp:.2f}"
            assert orig.host_id == replayed.host_id
            assert orig.device_id == replayed.device_id
            assert orig.address == replayed.address
            assert orig.is_read == replayed.is_read
            
    finally:
        os.unlink(trace_path)
