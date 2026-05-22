# Credit-Based Flow Control (CBFC) and Virtual Channels

In physical PCIe and CXL networks, packets are practically never dropped due to congestion. Dropping a memory packet would require complex end-to-end timeout and retransmission protocols (like TCP) that are far too slow for nano-second memory accesses. 

Instead, CXL uses **Credit-Based Flow Control (CBFC)** to create a lossless network. This document explains how our simulator models this behavior.

## Core Concepts

### 1. Virtual Channels (VCs)
To prevent protocol-level deadlocks (e.g., a stalled request blocking a response that would free up the very resources needed to process the request), traffic is separated into Virtual Channels.

Our simulator uses an **8-VC Model**:
- **VC 0 - 3**: Reserved for **Requests** (Mapped to QoS Priorities: `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`)
- **VC 4 - 7**: Reserved for **Responses** (Mapped to QoS Priorities: `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`)

A packet is strictly assigned to a VC upon creation.

### 2. Ingress and Egress Queues
A `SwitchPort` in the simulator is not just a single FIFO. It contains:
- **Ingress Queues (Rx)**: 8 distinct queues (one per VC) where packets land immediately upon arriving from an upstream link.
- **Egress Queues (Tx)**: 8 distinct queues (one per VC) where packets sit after the switch has performed route-lookup, waiting to traverse the downstream link.

### 3. Credit Accounting (`tx_credits`)
Every transmitter (both `Host` and `SwitchPort`) maintains a `tx_credits` dictionary. This dictionary tracks exactly how much buffer space is available in the **Ingress Queue** of the downstream receiver.

* **Transmission**: A packet can only be popped from the Egress Queue and transmitted if `tx_credits[packet.vc_id] > 0`. When transmitted, the credit is decremented.
* **Credit Returns**: When the receiver processes the packet (e.g., the switch's crossbar moves the packet from the Ingress Queue to the Egress Queue), it emits a `credit_return` event back to the transmitter, which increments the credit counter.

## The Event Lifecycle

The lifecycle of a packet interacting with the CBFC system involves several discrete simulation events:

1. **`host_generate`**: A compute host generates a memory request and places it in its local Egress Queue.
2. **`host_transmit`**: If the Host has `tx_credits` for the connected switch, it transmits the packet (incorporating serialization delay) and decrements its credit.
3. **`switch_arrive`**: The packet arrives at the Switch's Ingress Queue.
4. **`crossbar_process`**: The Switch's internal crossbar routes the packet from the Ingress Queue to the appropriate Egress Queue. At this moment, the Switch schedules a **`credit_return`** event sent back to the Host.
5. **`switch_transmit`**: If the Switch has `tx_credits` for the next hop, it transmits the packet from the Egress Queue.

## Why this matters: Head-of-Line (HoL) Blocking

Because packets are never dropped, a congested downstream port will run out of `tx_credits`. When this happens, the transmitter stalls. Packets back up in the Egress Queue, which eventually consumes all `tx_credits` of the *previous* hop, causing the backpressure to propagate backward through the fabric. 

This leads to **Head-of-Line (HoL) Blocking**, where a packet destined for an uncongested port is stuck in a queue behind a packet destined for a congested port. This accurately models the long tail-latencies seen in real physical fabrics under heavy load.
