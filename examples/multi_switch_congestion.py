"""
Multi-switch CXL fabric simulation demonstrating congestion.

Topology: Two-tier spine-leaf with 2 spines, 3 leaves.
"""

from src.topology import create_topology
from src.routing.strategy import ECMPRouting
from src.workload import create_workload
from src.simulation import FabricSimulation
from src.analysis import MetricsCollector

if __name__ == "__main__":
    print("=== Multi-Switch Congestion Demo ===\n")
    
    # Create two-tier topology with ECMP routing
    topology = create_topology(
        "two_tier", 
        num_spines=2, 
        num_leaves=3, 
        hosts_per_leaf=2, 
        devices_per_leaf=2,
        queue_depth=16,
        routing_strategy=ECMPRouting()
    )
    
    topology.print_topology()
    
    # Create metrics collector and simulation
    metrics = MetricsCollector(topology)
    sim = FabricSimulation(topology, metrics_collector=metrics)
    
    # Create heavy bursty workload
    workload = create_workload("bursty", burst_size=20, burst_interval_ns=500.0)
    
    # Run workload
    stats = sim.run_workload(workload, duration_ns=15_000, requests_per_host=1500000)
    
    # Print results
    stats.print_summary()
    
    for switch in topology.switches:
        switch.print_status()
