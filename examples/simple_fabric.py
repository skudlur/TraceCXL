"""
Simple CXL fabric simulation example using the unified simulation framework.

Topology: Single-tier with 2 hosts and 2 CXL devices.
Workload: Uniform random requests.
"""

from src.topology import create_topology
from src.workload import create_workload
from src.simulation import FabricSimulation
from src.analysis import MetricsCollector

if __name__ == "__main__":
    print("=== Simple CXL Fabric Simulation ===\n")
    
    # Create topology: 2 hosts, 2 CXL devices on 1 switch
    topology = create_topology("single", num_hosts=2, num_devices=2, queue_depth=16)
    
    # Create metrics collector
    metrics = MetricsCollector(topology)
    
    # Create simulation framework
    sim = FabricSimulation(topology, metrics_collector=metrics)
    
    # Create workload
    workload = create_workload("uniform")
    
    # Run workload
    print("Generating and running uniform traffic...")
    stats = sim.run_workload(workload, duration_ns=10_000, requests_per_host=100)
    
    # Print results
    print("\n" + "="*50)
    stats.print_summary()
    
    # Print switch status
    for switch in topology.switches:
        switch.print_status()
        
    print("\n" + "="*50)
    print("Simulation complete! ✓")
