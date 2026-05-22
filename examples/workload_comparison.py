"""
Workload Pattern Comparison Demo

Compares different workload patterns on same two-tier topology:
- Uniform random
- Zipfian (skewed)
- Hotspot (extreme skew)
"""

from src.topology import create_topology
from src.routing.strategy import ECMPRouting
from src.workload import create_workload
from src.simulation import FabricSimulation
from src.analysis import MetricsCollector
from src.analysis.plots import plot_latency_cdf

def run_workload_experiment(workload_name, workload_params, topology):
    """Run single experiment with given workload"""
    
    # Create fresh metrics and simulation for each experiment
    metrics = MetricsCollector(topology)
    sim = FabricSimulation(topology, metrics_collector=metrics)
    
    # Create workload
    workload = create_workload(workload_name, **workload_params)
    
    print(f"\n--- Running {workload_name.upper()} workload ---")
    stats = sim.run_workload(workload, duration_ns=10000, requests_per_host=100)
    
    # Print results
    stats.print_summary()
    
    total_dropped = sum(s.total_packets_dropped for s in topology.switches)
    print(f"Total packets dropped: {total_dropped}")
    
    return stats, metrics

if __name__ == "__main__":
    print("=== Workload Comparison ===")
    
    # Define topology
    topo_params = {
        "num_spines": 2,
        "num_leaves": 3,
        "hosts_per_leaf": 2,
        "devices_per_leaf": 2,
        "queue_depth": 16,
        "routing_strategy": ECMPRouting()
    }
    
    experiments = [
        ("uniform", {}),
        ("zipfian", {"alpha": 1.2, "hot_device_fraction": 0.2}),
        ("hotspot", {"hotspot_fraction": 0.9}),
    ]
    
    results = {}
    for name, params in experiments:
        # Recreate topology for fresh state
        topology = create_topology("two_tier", **topo_params)
        stats, metrics = run_workload_experiment(name, params, topology)
        results[name] = stats

    print("\n=== Final Comparison ===")
    for name, stats in results.items():
        print(f"{name:10}: {stats.avg_latency():.2f} ns avg latency, {stats.percentile_latency(99):.2f} ns p99")
