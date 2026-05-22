# TraceCXL: TraceCXL

A high-fidelity discrete-event simulator for studying congestion, QoS, and routing in CXL memory fabric architectures.

## Architecture

```
src/
├── core/           # Event loop, packet models, base classes
├── topology/       # Fabric layouts (tree, mesh, custom)
├── routing/        # Routing algorithms (shortest-path, ECMP)
├── workload/       # Traffic generators, trace replay
└── analysis/       # Metrics collection, visualization
```

## Quick Start

```bash
# Setup
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run simple example
python examples/simple_fabric.py
```

## Why TraceCXL? (Rapid Algorithmic Prototyping)

TraceCXL occupies a highly specific, much-needed gap between heavy architectural simulators and lightweight software memory-injection tools:

1. **Topology & Congestion Focus**: Simulators like gem5 model the CPU caches and memory controllers beautifully, but struggle to model complex multi-tier switched fabrics (spines, leaves) at scale due to computational overhead. TraceCXL abstracts away the CPU pipeline and focuses *entirely* on the physical network fabric, flit serialization, and link-layer credit flow.
2. **Speed and Scalability**: Written in Python using discrete-event scheduling, researchers can simulate massive datacenter-scale topologies incredibly quickly. 
3. **Trace-Driven Replay**: You can capture a trace from `CXLMemSim` (or Intel PIN/QEMU) running a real application (like LLMs or Key-Value stores), and feed that empirical trace into TraceCXL to see exactly how physical switch buffers and flow-control mechanisms handle real-world congestion.
4. **Rapid Prototyping**: Researchers can prototype new flow-control algorithms (like Adaptive Rate Controllers or ECN) in 50 lines of Python, run it in seconds, and generate a latency CDF graph instantly, before committing months to implementing it in gem5 or RTL.

```bash
# Run tests
pytest tests/
```

## License

MIT License - See LICENSE file
