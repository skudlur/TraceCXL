"""
Trace Generation and Replay Demo

This script demonstrates how to configure a statistical workload generator
(with a specific seed and read/write ratio), export the generated requests to 
a physical CSV file, and then immediately replay that trace through the simulator.
"""

import os
from src.topology import create_topology
from src.routing.strategy import ECMPRouting
from src.workload import create_workload, export_trace
from src.simulation import FabricSimulation
from src.analysis import MetricsCollector

def run_generate_and_replay():
    print("=== Trace Generation and Export Demo ===")
    
    # 1. Configuration
    trace_path = os.path.join(os.path.dirname(__file__), "generated_workload.csv")
    num_hosts = 4
    num_devices = 4
    duration_ns = 10000.0
    requests_per_host = 250
    
    # 2. Create a statistical workload generator
    # We'll use a highly skewed Zipfian with a fixed seed and 75% read ratio.
    generator = create_workload(
        "zipfian",
        alpha=1.2,
        seed=1337,
        read_ratio=0.75
    )
    
    # 3. Export to CSV
    print(f"\n[1] Exporting synthetic workload to {trace_path}...")
    num_exported = export_trace(
        workload=generator,
        filepath=trace_path,
        num_hosts=num_hosts,
        num_devices=num_devices,
        duration_ns=duration_ns,
        requests_per_host=requests_per_host
    )
    print(f"    Exported {num_exported} memory requests to CSV.")
    
    # 4. Set up Simulator topology
    print("\n[2] Setting up CXL Fabric Simulator...")
    topo_params = {
        "num_spines": 2,
        "num_leaves": 2,
        "hosts_per_leaf": 2,    # 2 * 2 = 4 Hosts
        "devices_per_leaf": 2,  # 2 * 2 = 4 Devices
        "queue_depth": 32,
        "routing_strategy": ECMPRouting()
    }
    
    topology = create_topology("two_tier", **topo_params)
    metrics = MetricsCollector(topology)
    sim = FabricSimulation(topology, metrics_collector=metrics)
    
    # 5. Load the generated trace for replay
    print(f"\n[3] Loading {trace_path} via TraceReplayWorkload...")
    trace_workload = create_workload("trace", trace_file=trace_path)
    
    # 6. Execute
    print("\n[4] Running Simulation with Replayed Trace...")
    # The trace is deterministic, so requests_per_host parameter is ignored here
    stats = sim.run_workload(trace_workload, duration_ns=duration_ns + 50000)
    
    stats.print_summary()
    total_dropped = sum(s.total_packets_dropped for s in topology.switches)
    print(f"Total packets dropped: {total_dropped}")


if __name__ == "__main__":
    run_generate_and_replay()
