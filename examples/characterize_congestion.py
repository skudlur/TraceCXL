"""Characterize congestion vs load"""

from src.topology import create_topology
from src.routing.strategy import ECMPRouting
from src.workload import create_workload
from src.simulation import FabricSimulation
from src.analysis import MetricsCollector
import plotly.express as px

def run_load_test(load, queue_depth=8):
    topology = create_topology(
        "two_tier", 
        num_spines=2, 
        num_leaves=3,
        hosts_per_leaf=2,
        devices_per_leaf=2,
        queue_depth=queue_depth,
        routing_strategy=ECMPRouting()
    )
    
    metrics = MetricsCollector(topology)
    sim = FabricSimulation(topology, metrics_collector=metrics)
    workload = create_workload("uniform")
    
    # Higher load = more requests in same time window
    requests = int(50 * load)
    
    stats = sim.run_workload(workload, duration_ns=10000, requests_per_host=requests)
    
    total_dropped = sum(s.total_packets_dropped for s in topology.switches)
    throughput = stats.packets_received / 10000.0  # requests per ns
    
    return throughput, stats.avg_latency(), total_dropped

if __name__ == "__main__":
    loads = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]
    throughputs = []
    latencies = []
    
    for load in loads:
        print(f"\nRunning load factor {load}x...")
        t, l, d = run_load_test(load)
        throughputs.append(t)
        latencies.append(l)
        print(f"Throughput: {t:.4f} req/ns, Latency: {l:.1f} ns, Drops: {d}")
    
    # Simple Plotly plot output message
    print("\nDone! In a real environment, you can use plotly to plot these values:")
    print("x = loads")
    print(f"y1 = throughputs = {throughputs}")
    print(f"y2 = latencies = {latencies}")
