"""Integration tests for end-to-end fabric simulation."""

from src.topology.builder import create_topology
from src.workload.patterns import create_workload
from src.simulation import FabricSimulation
from src.analysis.metrics import MetricsCollector

def test_end_to_end_simulation():
    # Small single-tier topology
    topo = create_topology("single", num_hosts=2, num_devices=2)
    metrics = MetricsCollector(topo)
    sim = FabricSimulation(topo, metrics_collector=metrics)
    
    # 10 requests per host, 2 hosts = 20 requests total
    # Since each has a response, we expect 20 sent, 20 received
    workload = create_workload("uniform")
    stats = sim.run_workload(workload, duration_ns=1000, requests_per_host=10)
    
    # Wait until all requests are done
    assert topo.hosts[0].packets_sent == 10
    assert topo.hosts[1].packets_sent == 10
    
    # Responses should arrive
    assert topo.hosts[0].packets_received == 10
    assert topo.hosts[1].packets_received == 10
    
    # Metrics should be collected
    assert len(sim.engine.stats.latencies) == 20
    assert metrics.collect_host_stats()[0]["sent"] == 10
