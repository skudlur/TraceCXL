# TraceCXL Documentation

Welcome to the TraceCXL documentation. This simulator is a lightweight, discrete-event packet-level network model tailored for evaluating memory fabrics, topologies, and congestion control algorithms.

## Developer & User Guides

Understanding the internal mechanics of the simulator is essential for extending it or analyzing its output. Please refer to the following deep-dive documents for complex architectural features:

- [Virtual Channels & Credit-Based Flow Control (CBFC)](cbfc.md) - Details how the simulator achieves lossless networking and models Head-of-Line (HoL) blocking.
- [Routing Strategies](routing.md) - Explains how the switch crossbars route packets (Static, ECMP, and Weighted).
- **Simulation Engine** - Coming Soon (Details on the discrete event min-heap loop).

## Getting Started

To run the simulator, activate your virtual environment and execute one of the examples:

```bash
cd cxl-fabric-sim
source venv/bin/activate
python examples/workload_comparison.py
```
