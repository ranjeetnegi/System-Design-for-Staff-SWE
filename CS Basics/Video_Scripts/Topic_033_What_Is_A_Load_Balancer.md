# What is a Load Balancer?

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

Lunch rush. 200 people. One cashier. The line stretches out the door. People are leaving. The owner panics — they hire 4 more cashiers. Five cashiers now. But here's the problem. All 200 people still walk to cashier #1. Habit. The other four stand there, idle. The line doesn't move. What do you need? Someone at the door. "You — counter 1. You — counter 2. You — counter 3." Distributing the crowd. That someone? A load balancer.

---

## The Story

A restaurant. Popular. One cashier. She's drowning. Orders pile up. Customers wait 20 minutes. Some leave. The owner thinks: "I'll hire more people." So they hire 5 cashiers. Problem solved, right?

Wrong. On opening day, everyone still goes to cashier #1. She's used to it. She's friendly. The regulars know her. Cashiers 2, 3, 4, and 5? Empty. One person is overwhelmed. Four are bored. The system is broken — not from lack of resources, but from bad distribution. The owner didn't realize that having capacity means nothing if you don't USE it. Five cashiers with one line is the same as one cashier. Maybe worse — you're paying four people to stand around. The bottleneck moved. It's no longer the number of cashiers. It's the fact that nobody is directing traffic.

The fix? A host at the door. "Next in line — counter 2. Next — counter 3. Next — counter 1." No one gets to choose. The host directs. Suddenly, all five cashiers work. The line moves. Wait time drops from 20 minutes to 4. The host doesn't take orders. The host doesn't cook. The host just DISTRIBUTES. That host is the load balancer.

---

## Another Way to See It

Think of a traffic cop at a multi-lane intersection. Cars used to pile up in one lane. The cop waves: "You, lane 2. You, lane 3." Traffic flows. Same roads. Same cars. Better distribution. The load balancer is the traffic cop.

---

## Connecting to Software

You have 5 servers. They're identical. They can all handle requests. But if you don't control who gets what, users might all hit server 1 (maybe it's the default, or cached in DNS). Server 1 melts. Servers 2–5 sit idle. A load balancer sits in front. Every incoming request goes to the load balancer. It picks a server using an algorithm — round-robin, least connections, IP hash — and forwards the request. Work is spread. No single server drowns.

---

## Let's Walk Through the Diagram

```
         USERS
           |
           |  Request 1, 2, 3, 4, 5...
           v
    +-------------+
    |   LOAD      |
    |  BALANCER   |
    +------+------+
           |
     +-----+-----+-----+-----+
     |     |     |     |     |
     v     v     v     v     v
  Server 1  2    3    4    5
```

**Round-robin:** Request 1 → Server 1. Request 2 → Server 2. Request 3 → Server 3. Request 4 → Server 4. Request 5 → Server 5. Request 6 → Server 1 again. Take turns.

**Least connections:** Send to the server with the fewest active connections. The least busy one.

**IP hash:** Same user (same IP) always goes to the same server. Good for sessions.

**Weighted:** Server 1 is bigger, so it gets 2x the traffic. Stronger servers get more work.

**Layer 4 vs Layer 7:** Layer 4 load balancing works at the TCP level. It looks at IP and port. Fast. Simple. Layer 7 works at the HTTP level. It can look at the URL path, headers, cookies. "Send /api to these servers, send /images to those." More intelligent routing. Slightly more overhead. Most modern systems use Layer 7 when they need path-based or header-based routing.

---

## Real-World Examples (2-3)

**1. AWS Elastic Load Balancer (ELB):** Distributes traffic across EC2 instances. Used by most AWS-backed apps.

**2. Nginx:** Can work as a reverse proxy AND load balancer. Simple config, huge scale.

**3. HAProxy / Cloudflare:** Battle-tested load balancers. Power many high-traffic sites. Cloudflare especially adds DDoS protection — the load balancer can absorb and filter malicious traffic before it ever reaches your servers.

**Sticky sessions:** Sometimes you need the same user to always hit the same server. Maybe their session is stored in memory there. IP hash does that. Or the load balancer can set a cookie — "next time, go to server 3." That's session affinity. Useful when state matters.

---

## Let's Think Together

**Question:** One of your 5 servers crashes. What should the load balancer do?

**Pause. Think about it...**

**Answer:** Stop sending traffic to it. The load balancer needs health checks. Every few seconds it pings each server: "Are you alive?" If server 3 doesn't respond, the balancer marks it as dead and stops routing there. Traffic goes to 1, 2, 4, 5. When server 3 recovers, health checks pass again — traffic resumes. Without health checks? The balancer keeps sending requests to a dead server. Users get errors. Half your capacity is wasted on a corpse.

---

## What Could Go Wrong? (Mini Disaster Story)

No health checks. Server 3 died an hour ago. The load balancer doesn't know. It keeps sending 20% of traffic to a black hole. Users hit that server. Timeout. Error. "Site is broken." Support gets flooded. The other 4 servers are fine — but 1 in 5 users are getting failures. The load balancer is doing its job. Distributing. But it's distributing to a ghost. Health checks aren't optional. They're how the balancer learns who's actually alive.

---

## Surprising Truth / Fun Fact

Google handles millions of queries per second. Their load balancing system — **Maglev** — was built from scratch. Why? Nothing off-the-shelf could handle their scale. When you search on Google, your request goes through a custom load balancing layer that had to be invented because existing tools weren't fast or scalable enough. That's the scale we're talking about.

---

## Quick Recap (5 bullets)

- A load balancer distributes incoming requests across multiple servers.
- Algorithms: round-robin, least connections, IP hash, weighted.
- Layer 4 (TCP) balances at the connection level. Layer 7 (HTTP) can look at URLs and headers.
- Health checks are critical — without them, traffic goes to dead servers.
- Real examples: AWS ELB, Nginx, HAProxy, Cloudflare.

---

## One-Liner to Remember

> **The load balancer is the host at the door. It doesn't serve — it distributes.**

---

## Next Video

The load balancer sends you to a server. But how did you find the load balancer in the first place? You typed "google.com" — not an IP address. There's a phone book that translates names to addresses. And it runs the entire internet. Next: What is DNS?
