# Chapter 82: Capacity Planning

> TODO: Full chapter to be written.

---

## Planned Coverage

**Core thesis:** Capacity planning is not guessing how many servers you need. It is the discipline of understanding your system's limits before users find them, and building headroom for growth without wasteful over-provisioning.

**Topics to cover:**

### Part 1: Why Capacity Planning Fails
- Two failure modes: under-provisioned (outage) and over-provisioned (wasted money)
- The "we'll scale when we need to" trap: scaling takes time, failures don't wait
- Why linear extrapolation fails: systems have non-linear breaking points
- The difference between capacity planning and performance optimization

### Part 2: Understanding Your System's Limits
- Theoretical limits vs empirical limits — measure, don't calculate
- Load testing to find the breaking point: how to design the test
- The three bottlenecks: CPU, memory, I/O — which is yours?
- Queuing theory basics: Little's Law (L = λW), utilization and latency cliff
- Why utilization above 70% causes disproportionate latency increases

### Part 3: The Capacity Planning Model
- Step 1: Measure current capacity (what is the system doing now at what load?)
- Step 2: Project future demand (traffic growth, new features, seasonal peaks)
- Step 3: Calculate headroom needed (2x? 3x? what is your safety margin?)
- Step 4: Plan the provisioning (when to add capacity, lead time for hardware/instances)
- Step 5: Set the alert threshold (alert at 70%, act at 80%, emergency at 90%)

### Part 4: Right-Sizing Services
- The cost of over-provisioning: real money, real waste
- How to right-size a service: load test at expected traffic, find the minimum viable instance
- Autoscaling: what it solves and what it doesn't (cold start, database connections)
- The "crush test": what happens when you get 10x traffic unexpectedly?

### Part 5: Database Capacity Planning
- Database scaling is different: you cannot just add instances
- Read replicas for read-heavy workloads
- Sharding: when you need it, what it costs in complexity
- Connection pool planning: how many connections can your DB handle?
- Disk growth planning: how fast is your data growing and when do you run out?

### Part 6: SLOs and Capacity
- SLOs define what "enough capacity" means: 99.9% availability at p99 < 200ms
- Error budget as a capacity signal: if you're burning your error budget, you're under capacity
- Capacity planning for peak events: Black Friday, product launches, viral moments
- Pre-scaling vs reactive scaling: when to do each

### Real Examples
- Netflix: capacity planning for a new country launch
- Amazon: Black Friday capacity planning (days of peak traffic pre-provisioned)
- Slack: capacity planning failure during COVID remote work surge (2020)
- How to estimate capacity for a URL shortener (links to Section 5 Ch 42 numbers)

### Exercises
- Given a service's current metrics, calculate how many instances it needs to handle 5x traffic
- Design the load test plan for a payment service before a Black Friday launch
- Calculate the database connection pool size for a service with 50 pods

---

*Status: TODO — placeholder only*
