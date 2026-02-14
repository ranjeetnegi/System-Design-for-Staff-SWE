# Health Checks: Liveness vs Readiness

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

Hospital patient monitoring. Two monitors. Monitor 1: "Is the patient alive?" Heart beating? Yes—alive. No—code blue. Emergency. Monitor 2: "Is the patient ready for visitors?" Awake? Alert? Not in surgery? Yes—allow visitors. No—wait. Being alive is not the same as being ready. A server can be alive—process running—but not ready. Still loading data. Database connection pending. Cache warming. Two different questions. Two different checks.

---

## The Story

**Liveness:** Is the process alive? Is it running? Not deadlocked? Not stuck? If the liveness check fails, the orchestrator—Kubernetes, ECS, whatever—assumes the process is dead. It kills the container. Restarts it. Fresh start. Liveness answers: "Should we restart this?"

**Readiness:** Can this instance handle requests? Is it fully initialized? Database connected? Cache loaded? Dependencies healthy? If the readiness check fails, the load balancer removes this instance from rotation. No new traffic. It stays alive. It just doesn't receive requests until ready. Readiness answers: "Should we send traffic to this?"

A server can be live but not ready. Process started. Liveness: pass. But it's still loading 50GB of cache into memory. That takes 2 minutes. During those 2 minutes, it can't serve requests correctly. Readiness: fail. Load balancer holds traffic. When cache is loaded, readiness: pass. Traffic flows. Two checks. Two jobs.

---

## Another Way to See It

Think of a restaurant. Liveness: is the chef in the building? Yes—don't call an ambulance. Readiness: is the kitchen set up? Ingredients in? Oven hot? Can the chef actually cook? No—don't seat customers. Chef is alive. Kitchen is not ready. Two checks.

Or an airplane. Liveness: are the engines running? Readiness: are we at the gate? Doors closed? Seatbelts on? Ready for takeoff? Engines can run while we're still boarding. Alive. Not ready. Different questions.

---

## Connecting to Software

**Endpoints:** `GET /health/live` returns 200 if the process is alive. Simple. Can be a no-op. Just "I'm running." `GET /health/ready` returns 200 if the instance can handle requests. Check DB. Check cache. Check dependencies. More complex. More expensive. Run less frequently if needed.

**Kubernetes:** `livenessProbe`—fails? Restart pod. `readinessProbe`—fails? Remove from Service. No traffic. Pod stays. When readiness passes again, traffic returns. Both matter. Both different.

**Common mistake:** Using liveness for everything. Liveness fails when DB is down. Restart. Restart. Restart. DB is down for everyone. Restarting doesn't help. You're killing healthy processes. Use readiness for "can't serve." Use liveness for "I'm actually dead." Liveness should be cheap. Readiness can check dependencies.

---

## Let's Walk Through the Diagram

```
    LIVENESS vs READINESS

    Liveness Check                    Readiness Check
    "Am I alive?"                     "Can I handle requests?"
           │                                   │
           │  Pass → keep running               │  Pass → receive traffic
           │  Fail → RESTART                    │  Fail → NO traffic (stay alive)
           │                                    │
           ▼                                    ▼
    [Process]                            [Dependencies]
    - Am I running?                      - DB connected?
    - Not deadlocked?                    - Cache loaded?
    - Heartbeat?                         - Warm?
```

Different questions. Different actions. Don't confuse them.

---

## Real-World Examples (2-3)

**Example 1: Kubernetes default.** Kubelet runs liveness and readiness probes. Liveness: process responds to HTTP on a port. Readiness: same or different endpoint. Fail liveness 3 times? Container killed. Restarted. Fail readiness? Pod removed from endpoints. No new connections. Existing connections may drain. Standard pattern. Every K8s user.

**Example 2: Database with connection pool.** Server starts. Liveness: pass—process is up. Readiness: fail—connection pool still establishing 50 DB connections. Takes 10 seconds. During those 10 seconds, if you sent traffic, requests would fail. Readiness holds. Connections ready. Readiness passes. Traffic flows. Prevents thundering herd of failures on a cold start.

**Example 3: Cache-heavy service.** Service loads 10GB of data into memory on startup. 2 minutes. Liveness: pass. Readiness: fail until load complete. Without readiness, load balancer would send traffic. Service would return errors or stale data. With readiness, traffic waits. Service comes up clean. No errors. No confusion.

---

## Let's Think Together

**Server starts. Passes liveness. But it's still loading 50GB of cache data. Should it receive traffic?**

No. Liveness says "I'm running." Readiness should say "I'm not ready." Cache loading? Readiness fails. Load balancer holds traffic. When cache is loaded, readiness passes. Traffic flows. If you only had liveness, you'd send traffic to a half-initialized server. Errors. Timeouts. Bad experience. Readiness is the gate. Liveness is the "am I dead?" check. Both needed. Different roles.

---

## What Could Go Wrong? (Mini Disaster Story)

A team used one health check for both liveness and readiness. The check hit the database. Database had a blip. All instances failed the check. Kubernetes restarted all of them. At once. Thundering herd. Database now had zero clients. Then all clients reconnected. Simultaneously. Database overloaded. More failures. Cascade. Lesson: liveness should not depend on external services. If DB is down, restarting your app doesn't help. Liveness: "am I running?" Readiness: "can I serve?" Keep them separate. Keep liveness local. Readiness can check dependencies. But if readiness fails, don't restart. Just stop sending traffic.

---

## Surprising Truth / Fun Fact

Kubernetes added separate liveness and readiness in early versions. Before that, one probe. Confusion. "My pod keeps restarting when the DB is slow." Why? Liveness was checking DB. DB slow = liveness fail = restart. No help. The split was a critical design. Now it's standard. Docker Swarm, ECS, Nomad—all have similar concepts. The pattern spread. Because it solves a real problem.

---

## Quick Recap (5 bullets)

- **Liveness** = "Is the process alive?" Fail → restart. Kubernetes kills and restarts the pod.
- **Readiness** = "Can this instance handle requests?" Fail → remove from load balancer. No traffic.
- **Different actions:** Liveness = restart. Readiness = stop sending traffic. Don't restart.
- **Endpoints:** `/health/live` and `/health/ready`. Or similar. Separate. Both matter.
- **Liveness should be cheap and local.** Readiness can check DB, cache, dependencies.

---

## One-Liner to Remember

**Liveness: am I dead? Restart me. Readiness: am I ready? Send me traffic. Two questions. Two different answers.**

---

## Next Video

Next: **Graceful Degradation**—what to shed first when the system is overloaded. Prioritize. Survive. Stay tuned.
