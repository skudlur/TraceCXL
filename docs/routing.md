# Routing Strategies

The TraceCXL implements a modular routing infrastructure based on the Strategy Pattern. This allows different switches (or the entire fabric) to utilize different algorithms for determining the best output port for a given packet.

All routing strategies are located in `src/routing/strategy.py` and must inherit from the `RoutingStrategy` base class.

## Available Strategies

### 1. Static Routing (`StaticRouting`)
The simplest form of routing. The switch looks up the logical destination (the CXL memory device ID, or the Host ID for responses) in its internal routing table and strictly selects the first available port. 

* **Pros:** Computationally trivial; guarantees in-order delivery.
* **Cons:** Extremely susceptible to congestion; cannot load balance across spine switches.

### 2. Equal-Cost Multi-Path (`ECMPRouting`)
Essential for Spine-Leaf (Two-Tier) topologies. When there are multiple equal-cost paths to a destination (e.g., a Leaf switch connected to 4 Spine switches), the router must load balance the traffic. 

ECMP achieves this deterministically by hashing packet header fields (Source ID, Destination ID, Memory Address).
* **Pros:** Evenly distributes traffic flows across the fabric; deterministic hashing prevents packet reordering within the same memory flow.
* **Cons:** "Elephant flows" (large, sustained transfers between two specific endpoints) will hash to a single path, potentially causing isolated congestion on one spine link while others sit idle.

### 3. Weighted / Dynamic Routing (`WeightedRouting`)
A form of adaptive routing. The switch evaluates all valid output ports for a destination and selects the port with the lowest **Egress Occupancy**. 

* **Pros:** Dynamically routes around localized congestion and elephant flows.
* **Cons:** Can cause severe packet re-ordering, which degrades performance in real cache-coherent systems or requires massive reorder buffers at the destination.

## Implementing a Custom Strategy

To create a new routing algorithm (e.g., a Deflection Router or an Adaptive ECMP), subclass `RoutingStrategy`:

```python
from src.routing.strategy import RoutingStrategy
from src.core.packet import CXLPacket
from typing import List

class MyCustomRouting(RoutingStrategy):
    def get_output_port(self, switch, packet: CXLPacket, available_ports: List[int]) -> int:
        # Your custom logic here!
        return available_ports[0]
```
