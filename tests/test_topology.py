"""Tests for topology builder and routing tables."""

from src.topology.builder import create_topology
from src.routing.strategy import StaticRouting, ECMPRouting

def test_single_tier_topology():
    topo = create_topology("single", num_hosts=2, num_devices=2)
    assert len(topo.switches) == 1
    assert len(topo.hosts) == 2
    assert len(topo.cxl_devices) == 2
    
    switch = topo.switches[0]
    # Check routes to devices
    assert switch.routing_table[0] == [2]
    assert switch.routing_table[1] == [3]
    # Check routes to hosts
    assert switch.routing_table["host_0"] == [0]
    assert switch.routing_table["host_1"] == [1]

def test_two_tier_topology_ecmp():
    topo = create_topology(
        "two_tier", 
        num_spines=2, 
        num_leaves=3, 
        hosts_per_leaf=2, 
        devices_per_leaf=2,
        routing_strategy=ECMPRouting()
    )
    
    assert len(topo.switches) == 5  # 2 spines + 3 leaves
    assert len(topo.hosts) == 4     # 2 host leaves * 2 hosts
    assert len(topo.cxl_devices) == 2 # 1 device leaf * 2 devices
    
    host_leaf = topo.switches[2] # Leaf 0
    # Host leaf should have paths to both spines for the device
    assert len(host_leaf.routing_table[0]) == 2
    assert set(host_leaf.routing_table[0]) == {0, 1}
    
    device_leaf = topo.switches[4] # Leaf 2
    # Device leaf should have path to device locally
    assert device_leaf.routing_table[0] == [2] # Port 2 connects to Dev0
