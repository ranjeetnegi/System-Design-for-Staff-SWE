# Section 0: Simplified Learning Guide — Foundations for L6 System Design

---

## About This Guide

These notes are a simplified, beginner-friendly rewrite of the original Section 0 chapters. They are designed for engineers preparing for Google Staff Engineer (L6) system design interviews.

**Who is this for:**
- Recent graduates or early-career engineers who know programming fundamentals
- Engineers who want to build the intuition that normally takes years of industry experience
- Anyone preparing for Staff-level system design interviews

**How to use this guide:**
- Read chapters in order — each one builds on the previous
- Focus on understanding the **why** before the **how**
- After each chapter, try to explain the concepts out loud without looking at the notes
- Practice the interview questions at the end of each chapter

---

## Chapter Map

| Chapter | Topic | Core Question It Answers |
|---------|-------|--------------------------|
| [Chapter 1](Chapter_1_Systems_Servers_Clients.md) | Systems, Servers, Clients | What is a system? What happens when you type a URL? |
| [Chapter 2](Chapter_2_APIs_Frontend_Backend_DB.md) | APIs, Frontend, Backend, Databases | How do parts of a system communicate and store data? |
| [Chapter 3](Chapter_3_OS_Fundamentals.md) | OS Fundamentals | Why does my server run out of memory? Why is it slow? |
| [Chapter 4](Chapter_4_Networking_Foundations.md) | Networking Foundations | How do requests travel across the internet? |
| [Chapter 5](Chapter_5_Numbers_Estimation.md) | Numbers and Estimation | How many servers do I need? Will this design handle the load? |
| [Chapter 6](Chapter_6_Core_Building_Blocks.md) | Core Building Blocks | What are the reusable patterns in every distributed system? |

---

## Learning Path

### Week 1: Fundamentals
- Chapter 1: Understand systems, clients, servers, and the URL journey
- Chapter 4: Understand TCP, UDP, HTTP, bandwidth vs latency
- **Practice**: Explain "what happens when you type google.com" in detail

### Week 2: Architecture Basics
- Chapter 2: APIs as contracts, REST design, database fundamentals
- Chapter 3: Process, threads, memory, and why they matter for capacity
- **Practice**: Design a simple REST API for a blog and choose the right database

### Week 3: Scale and Estimation
- Chapter 5: Master back-of-envelope calculations
- Review Chapters 1–4 with numbers in mind
- **Practice**: Estimate QPS, storage, and servers for WhatsApp, Twitter, YouTube

### Week 4: Building Blocks
- Chapter 6: Hash, cache, state, idempotency, queues, sync/async
- **Practice**: Apply the 6-block checklist to a payment system and a chat system

---

## The L5 → L6 Mental Shift

The biggest difference between a Senior (L5) and Staff (L6) engineer is not technical knowledge — it is **scope of thinking**.

| L5 thinks... | L6 thinks... |
|-------------|-------------|
| "I built this component" | "How does this component affect the whole system?" |
| "We handle 10K QPS" | "We handle 10K user QPS, but each request triggers 5 internal calls — we are responsible for 50K internal QPS" |
| "The database is the bottleneck" | "The database is the bottleneck; here is the read/write ratio, why replication lag matters, and the migration path to sharding" |
| "We'll add more servers" | "We'll need sharding before 50 million users; we designed the schema for it now" |
| "We'll retry on failure" | "All write APIs accept idempotency keys; we deduplicate for 24 hours; payments use it" |

The goal of these chapters is to build L6 intuition — not just technical facts.

---

## Quick Reference: Numbers You Must Know

```
86,400   = seconds per day
3–5x     = typical peak-to-average QPS ratio
10–20x   = typical fan-out factor (one user request → 10–20 internal calls)

Latency reference:
  RAM access:          100 ns
  SSD random read:     100 μs   (1,000x slower than RAM)
  HDD seek:            10 ms    (100,000x slower than RAM)
  Same datacenter:     0.5 ms
  Cross-country (US):  40 ms
  Transatlantic:       80 ms
  Transpacific:        140 ms

Availability:
  99%    = 3.65 days downtime/year
  99.9%  = 8.76 hours downtime/year  ← most products target this
  99.99% = 52 minutes downtime/year  ← enterprise grade
  
Storage:
  1 KB = short text message
  1 MB = one photo
  1 GB = one HD movie
  1 TB = ~1 billion kilobytes
  1 PB = ~1 million gigabytes
```

---

## Quick Reference: The 6-Block Checklist

Run this for every system you design:

```
□ Hash:        How is data distributed? Consistent hashing? What is the shard key?
□ Cache:       What is cached? TTL? Invalidation? What happens on miss?
□ State:       Are services stateless? Where does state live?
□ Idempotency: Which writes need retry safety? Are idempotency keys used?
□ Queue:       What work is async? What queue system? DLQ configured?
□ Sync/Async:  Which flows are sync (user waits)? Which are async (side effects)?
```

---

## Quick Reference: Scale Thresholds

| Users | QPS (approx) | What you likely need |
|-------|-------------|---------------------|
| 10K | ~100 | 1 server + 1 database |
| 100K | ~1,000 | + cache + read replica |
| 1M | ~10,000 | + load balancer + CDN |
| 10M | ~100,000 | + sharding + queues |
| 100M+ | ~1M+ | multi-region + custom infra |
