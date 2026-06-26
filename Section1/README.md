# Section 1 — Foundations

The vocabulary and mental models every system design answer builds on. If you can't estimate QPS or explain why a TCP connection is expensive, your design answers will sound hollow. These 6 chapters eliminate that gap.

---

## Chapters

| Chapter | Title | Key Topic |
|---|---|---|
| [Ch9](Chapter_9_Systems_Servers_Clients.md) | Systems, Servers, Clients | How the internet works end-to-end |
| [Ch10](Chapter_10_APIs_Frontend_Backend_DB.md) | APIs, Frontend, Backend, DB | The standard web stack from client to DB |
| [Ch11](Chapter_11_OS_Fundamentals.md) | OS Fundamentals | Processes, threads, syscalls, memory |
| [Ch12](Chapter_12_Networking_Foundations.md) | Networking Foundations | TCP/UDP, DNS, TLS, HTTP/2, WebSockets |
| [Ch13](Chapter_13_Numbers_and_Estimation.md) | Numbers & Estimation | Latency numbers, back-of-envelope math, capacity planning |
| [Ch14](Chapter_14_Core_Building_Blocks.md) | Core Building Blocks | Load balancers, caches, queues, CDNs, databases |

---

## Core Themes

- **Estimation fluency** — Ch13 is the most practical chapter here; internalize the latency numbers table before your first mock
- **Networking intuition** — knowing when to use TCP vs UDP, long polling vs WebSockets comes up in every design
- **Building block vocabulary** — Ch14 gives you the nouns every later chapter uses

---

## Key Latency Numbers (from Ch13)

| Operation | Latency |
|---|---|
| L1 cache hit | 0.5 ns |
| RAM read | 100 ns |
| SSD random read | 100 µs |
| Network round-trip (same DC) | 500 µs |
| Network round-trip (cross-region) | 150 ms |
| HDD seek | 10 ms |
