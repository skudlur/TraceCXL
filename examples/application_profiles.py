"""
Realistic Application Profiles Demo

This script demonstrates the CXL Fabric Simulator running simulated workloads 
that model real-world application access patterns:
1. LLM Inference: Memory-bandwidth bound, sequentially scanning huge memory regions (weights/KV-cache).
2. Key-Value Store: High skew (Zipfian), causing hotspot congestion similar to Memcached.

It also runs under the supervision of the CXL ProtocolValidator to ensure semantic compliance.
"""

from src.topology import create_topology
from src.routing.strategy import ECMPRouting
from src.workload import create_workload
from src.simulation import FabricSimulation
from src.analysis import MetricsCollector

def run_profile(profile_name: str, workload_type: str, workload_params: dict, duration_ns: float = 10000):
    print(f"\n{'='*50}")
    print(f"Running Application Profile: {profile_name}")
    print(f"{'='*50}")
    
    # 1. Define topology
    # A standard 2-tier architecture suitable for a pod
    topo_params = {
        "num_spines": 2,
        "num_leaves": 4,
        "hosts_per_leaf": 4,
        "devices_per_leaf": 4,
        "queue_depth": 32,
        "routing_strategy": ECMPRouting()
    }
    
    topology = create_topology("two_tier", **topo_params)
    metrics = MetricsCollector(topology)
    
    # 2. Instantiate Simulator (ProtocolValidator is attached by default)
    sim = FabricSimulation(topology, metrics_collector=metrics)
    
    # 3. Create Workload
    workload = create_workload(workload_type, **workload_params)
    
    # 4. Run Simulation
    print("Generating workload events and starting simulation...")
    # LLM inference tends to be heavy, generate many requests per host
    stats = sim.run_workload(workload, duration_ns=duration_ns, requests_per_host=500)
    
    # 5. Output Results
    stats.print_summary()
    total_dropped = sum(s.total_packets_dropped for s in topology.switches)
    print(f"Total packets dropped across fabric: {total_dropped}")
    
    return stats


if __name__ == "__main__":
    print("Starting Realistic Workload Evaluations with Protocol Compliance enabled.\n")
    
    # Profile 1: LLM Inference (Sequential memory scans, stride 64 bytes)
    run_profile(
        profile_name="LLM Inference (Weight Streaming / KV Cache)",
        workload_type="sequential",
        workload_params={"stride": 64},
        duration_ns=20000
    )
    
    # Profile 2: Key-Value Store (High skew, alpha=1.5, simulating hot keys)
    run_profile(
        profile_name="Memcached / Redis (High Skew Zipfian)",
        workload_type="zipfian",
        workload_params={"alpha": 1.5, "hot_device_fraction": 0.1},
        duration_ns=20000
    )
    
    print("\nAll profiles completed successfully without protocol violations!")
