"""
Trace Replay Demo

Demonstrates how to run a simulation driven by a CSV memory trace file.
"""

import os
from src.topology import create_topology
from src.routing.strategy import ECMPRouting
from src.workload import create_workload
from src.simulation import FabricSimulation
from src.analysis import MetricsCollector

def run_trace_replay():
    print("=== Workload Trace Replay Demo ===")
    
    # 1. Define topology to match the trace constraints
    # Our sample trace uses host_id in [0, 1] and device_id in [0, 1]
    topo_params = {
        "num_hosts": 2,
        "num_devices": 2,
        "queue_depth": 16,
        "routing_strategy": ECMPRouting()
    }
    
    topology = create_topology("single", **topo_params)
    metrics = MetricsCollector(topology)
    sim = FabricSimulation(topology, metrics_collector=metrics)
    
    # 2. Path to our trace file
    trace_path = os.path.join(os.path.dirname(__file__), "sample_trace.csv")
    
    # 3. Create trace workload
    workload = create_workload("trace", trace_file=trace_path)
    
    print(f"\nLoading trace from: {trace_path}")
    print("Running simulation...")
    
    # Duration needs to be long enough to cover the timestamps in the trace.
    # The sample trace goes up to 2500 ns. We set duration to 10000 ns to be safe.
    stats = sim.run_workload(workload, duration_ns=10000)
    
    # 4. Print results
    stats.print_summary()
    
if __name__ == "__main__":
    run_trace_replay()
