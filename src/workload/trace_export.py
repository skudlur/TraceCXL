"""
Workload Trace Export Utility

Dumps mathematically generated memory requests into a physical CSV trace file.
"""

import csv
import logging
from typing import Optional

from .patterns import WorkloadPattern

logger = logging.getLogger(__name__)

def export_trace(
    workload: WorkloadPattern,
    filepath: str,
    num_hosts: int,
    num_devices: int,
    duration_ns: float,
    requests_per_host: int
):
    """
    Generate requests using a workload pattern and export them to a CSV file.
    
    Args:
        workload: The workload pattern to generate requests from
        filepath: Output CSV file path
        num_hosts: Number of simulated hosts
        num_devices: Number of simulated devices
        duration_ns: Generation duration window (ns)
        requests_per_host: Number of requests per host
    """
    # 1. Generate requests in memory
    logger.info(f"Generating requests for trace export...")
    requests = workload.generate_requests(
        num_hosts=num_hosts,
        num_devices=num_devices,
        duration_ns=duration_ns,
        requests_per_host=requests_per_host
    )
    
    # 2. Sort requests by timestamp (since they were generated per-host)
    requests.sort(key=lambda req: req.timestamp)
    
    # 3. Write to CSV
    logger.info(f"Writing {len(requests)} requests to {filepath}...")
    with open(filepath, mode='w', newline='') as f:
        writer = csv.writer(f)
        # Write header
        writer.writerow(['timestamp_ns', 'host_id', 'device_id', 'address', 'is_read'])
        
        # Write data
        for req in requests:
            writer.writerow([
                f"{req.timestamp:.2f}",
                req.host_id,
                req.device_id,
                f"0x{req.address:X}",
                "1" if req.is_read else "0"
            ])
            
    logger.info("Trace export complete.")
    return len(requests)
