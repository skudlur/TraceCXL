"""
Realistic workload patterns for CXL memory fabric simulation.

Implements common memory access patterns:
- Zipfian (skewed, like memcached)
- Uniform random
- Sequential scans
- Bursty/periodic
"""

import random
import csv
from typing import List, Tuple
from dataclasses import dataclass

@dataclass
class MemoryRequest:
    """Single memory request specification"""
    timestamp: float      # When to issue (ns)
    host_id: int         # Which host issues
    device_id: int       # Target CXL device
    address: int         # Memory address
    is_read: bool = True # Read or write


class WorkloadPattern:
    """Base class for workload patterns"""
    
    def __init__(self, seed: int = None):
        self.seed = seed
        if seed is not None:
            random.seed(seed)
    
    def generate_requests(
        self,
        num_hosts: int,
        num_devices: int,
        duration_ns: float,
        requests_per_host: int
    ) -> List[MemoryRequest]:
        """
        Generate memory requests for simulation.
        
        Args:
            num_hosts: Number of compute hosts
            num_devices: Number of CXL memory devices
            duration_ns: Time window for request generation
            requests_per_host: Total requests each host issues
        
        Returns:
            List of MemoryRequest objects
        """
        raise NotImplementedError


class UniformRandomWorkload(WorkloadPattern):
    """
    Uniform random access pattern.
    
    All devices and addresses equally likely.
    Represents well-balanced, unpredictable workload.
    """
    
    def generate_requests(
        self, num_hosts, num_devices, duration_ns, requests_per_host
    ) -> List[MemoryRequest]:
        requests = []
        devices = list(range(num_devices))
        address_space = 1 << 30  # 1GB address space per device
        
        for host_id in range(num_hosts):
            # Evenly space requests over time
            interval = duration_ns / requests_per_host
            
            for i in range(requests_per_host):
                timestamp = i * interval + random.uniform(0, interval * 0.1)
                device_id = random.choice(devices)
                address = random.randint(0, address_space - 1)
                
                requests.append(MemoryRequest(
                    timestamp=timestamp,
                    host_id=host_id,
                    device_id=device_id,
                    address=address
                ))
        
        return requests


class ZipfianWorkload(WorkloadPattern):
    """
    Zipfian (power-law) access pattern.
    
    Follows Zipf distribution: popularity rank k has probability ∝ 1/k^α
    Models skewed workloads like memcached (80/20 rule).
    
    Args:
        alpha: Zipf exponent (default 1.0, higher = more skewed)
        hot_device_fraction: Fraction of devices that are "hot" (default 0.2)
    """
    
    def __init__(self, alpha: float = 1.0, hot_device_fraction: float = 0.2, seed=None):
        super().__init__(seed)
        self.alpha = alpha
        self.hot_device_fraction = hot_device_fraction
    
    def generate_requests(
        self, num_hosts, num_devices, duration_ns, requests_per_host
    ) -> List[MemoryRequest]:
        requests = []
        
        # Determine hot vs cold devices
        num_hot_devices = max(1, int(num_devices * self.hot_device_fraction))
        hot_devices = list(range(num_hot_devices))
        cold_devices = list(range(num_hot_devices, num_devices))
        
        # Pre-compute Zipfian probabilities for devices
        device_probs = self._zipf_probabilities(num_devices)
        
        for host_id in range(num_hosts):
            interval = duration_ns / requests_per_host
            
            for i in range(requests_per_host):
                timestamp = i * interval + random.uniform(0, interval * 0.1)
                
                # Select device according to Zipfian distribution
                device_id = self._zipf_sample(device_probs)
                
                # Addresses within device also follow Zipfian pattern
                address = self._zipf_address(1 << 30)
                
                requests.append(MemoryRequest(
                    timestamp=timestamp,
                    host_id=host_id,
                    device_id=device_id,
                    address=address
                ))
        
        return requests
    
    def _zipf_probabilities(self, n: int) -> List[float]:
        """Compute Zipfian probability distribution"""
        probs = [1.0 / (k ** self.alpha) for k in range(1, n + 1)]
        total = sum(probs)
        return [p / total for p in probs]
    
    def _zipf_sample(self, probs: List[float]) -> int:
        """Sample from Zipfian distribution"""
        r = random.random()
        cumsum = 0.0
        for i, p in enumerate(probs):
            cumsum += p
            if r < cumsum:
                return i
        return len(probs) - 1
    
    def _zipf_address(self, address_space: int) -> int:
        """Generate Zipfian-distributed address"""
        # Simplified: assume 1000 "pages", pick one via Zipf
        num_pages = 1000
        page_probs = self._zipf_probabilities(num_pages)
        hot_page = self._zipf_sample(page_probs)
        
        # Random offset within page
        page_size = address_space // num_pages
        return hot_page * page_size + random.randint(0, page_size - 1)


class HotspotWorkload(WorkloadPattern):
    """
    Hotspot concentration pattern.
    
    Most traffic goes to a single "hot" device.
    Models extreme imbalance scenarios.
    
    Args:
        hotspot_device: Which device is the hotspot (default 0)
        hotspot_fraction: Fraction of traffic to hotspot (default 0.8)
    """
    
    def __init__(self, hotspot_device: int = 0, hotspot_fraction: float = 0.8, seed=None):
        super().__init__(seed)
        self.hotspot_device = hotspot_device
        self.hotspot_fraction = hotspot_fraction
    
    def generate_requests(
        self, num_hosts, num_devices, duration_ns, requests_per_host
    ) -> List[MemoryRequest]:
        requests = []
        other_devices = [d for d in range(num_devices) if d != self.hotspot_device]
        address_space = 1 << 30
        
        for host_id in range(num_hosts):
            interval = duration_ns / requests_per_host
            
            for i in range(requests_per_host):
                timestamp = i * interval + random.uniform(0, interval * 0.1)
                
                # Route to hotspot with given probability
                if random.random() < self.hotspot_fraction:
                    device_id = self.hotspot_device
                else:
                    device_id = random.choice(other_devices) if other_devices else self.hotspot_device
                
                address = random.randint(0, address_space - 1)
                
                requests.append(MemoryRequest(
                    timestamp=timestamp,
                    host_id=host_id,
                    device_id=device_id,
                    address=address
                ))
        
        return requests


class BurstyWorkload(WorkloadPattern):
    """
    Bursty/periodic access pattern.
    
    Traffic comes in bursts separated by idle periods.
    Models batch processing or synchronized applications.
    
    Args:
        burst_size: Requests per burst
        burst_interval_ns: Time between burst starts
    """
    
    def __init__(self, burst_size: int = 10, burst_interval_ns: float = 1000.0, seed=None):
        super().__init__(seed)
        self.burst_size = burst_size
        self.burst_interval_ns = burst_interval_ns
    
    def generate_requests(
        self, num_hosts, num_devices, duration_ns, requests_per_host
    ) -> List[MemoryRequest]:
        requests = []
        devices = list(range(num_devices))
        address_space = 1 << 30
        
        for host_id in range(num_hosts):
            num_bursts = requests_per_host // self.burst_size
            
            for burst_id in range(num_bursts):
                burst_start = burst_id * self.burst_interval_ns
                
                if burst_start > duration_ns:
                    break
                
                # Generate burst of requests close together in time
                for i in range(self.burst_size):
                    timestamp = burst_start + i * 10  # 10ns apart within burst
                    device_id = random.choice(devices)
                    address = random.randint(0, address_space - 1)
                    
                    requests.append(MemoryRequest(
                        timestamp=timestamp,
                        host_id=host_id,
                        device_id=device_id,
                        address=address
                    ))
        
        return requests


class SequentialWorkload(WorkloadPattern):
    """
    Sequential scan pattern.
    
    Each host sequentially scans through device memory.
    Models analytics/batch processing workloads.
    
    Args:
        stride: Bytes between accesses (default 64 = cache line)
    """
    
    def __init__(self, stride: int = 64, seed=None):
        super().__init__(seed)
        self.stride = stride
    
    def generate_requests(
        self, num_hosts, num_devices, duration_ns, requests_per_host
    ) -> List[MemoryRequest]:
        requests = []
        
        for host_id in range(num_hosts):
            # Each host scans a different device
            device_id = host_id % num_devices
            
            interval = duration_ns / requests_per_host
            base_address = 0
            
            for i in range(requests_per_host):
                timestamp = i * interval
                address = base_address + (i * self.stride)
                
                requests.append(MemoryRequest(
                    timestamp=timestamp,
                    host_id=host_id,
                    device_id=device_id,
                    address=address
                ))
        
        return requests


class TraceReplayWorkload(WorkloadPattern):
    """
    Trace replay pattern.
    
    Reads memory access requests from a CSV trace file.
    CSV format: timestamp_ns, host_id, device_id, address, is_read
    
    Args:
        trace_file: Path to the trace CSV file.
    """
    
    def __init__(self, trace_file: str, seed=None):
        super().__init__(seed)
        self.trace_file = trace_file
        
    def generate_requests(
        self, num_hosts, num_devices, duration_ns, requests_per_host
    ) -> List[MemoryRequest]:
        requests = []
        
        with open(self.trace_file, mode='r') as f:
            reader = csv.reader(f)
            # Skip header if present
            header = next(reader, None)
            if header and header[0].strip().lower() != 'timestamp_ns':
                # No header, process it
                f.seek(0)
                reader = csv.reader(f)
                
            for row in reader:
                if not row or not row[0].strip():
                    continue
                
                timestamp = float(row[0].strip())
                if timestamp > duration_ns:
                    break
                    
                host_id = int(row[1].strip())
                device_id = int(row[2].strip())
                address = int(row[3].strip(), 16) if 'x' in row[3] else int(row[3].strip())
                
                is_read_str = row[4].strip().lower()
                is_read = is_read_str in ('1', 'true', 'read', 'r')
                
                # Check bounds
                if host_id >= num_hosts or device_id >= num_devices:
                    continue
                    
                requests.append(MemoryRequest(
                    timestamp=timestamp,
                    host_id=host_id,
                    device_id=device_id,
                    address=address,
                    is_read=is_read
                ))
                
        return requests


# Helper function to create workload by name
def create_workload(workload_type: str, **kwargs) -> WorkloadPattern:
    """
    Factory function to create workload patterns.
    
    Args:
        workload_type: One of "uniform", "zipfian", "hotspot", "bursty", "sequential"
        **kwargs: Workload-specific parameters
    
    Returns:
        WorkloadPattern instance
    """
    workloads = {
        "uniform": UniformRandomWorkload,
        "zipfian": ZipfianWorkload,
        "hotspot": HotspotWorkload,
        "bursty": BurstyWorkload,
        "sequential": SequentialWorkload,
        "trace": TraceReplayWorkload,
    }
    
    if workload_type not in workloads:
        raise ValueError(f"Unknown workload type: {workload_type}. "
                        f"Choose from: {list(workloads.keys())}")
    
    return workloads[workload_type](**kwargs)
