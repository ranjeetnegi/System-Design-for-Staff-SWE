# What is Anycast Routing?

## Video Length: ~4-5 minutes | Level: Staff

---

## The Hook (20-30 seconds)

Emergency number 911. You're in San Francisco. Someone's hurt. You dial 911. You reach the San Francisco emergency center. At the exact same moment, someone in New York dials 911. Same number. They reach the New York center. ONE number. Different buildings. The network knows. It routes each call to the NEAREST center. Automatically. No human operator. No menu. The phone system does it. That's Anycast. And the internet uses it for everything that matters.

---

## The Story

Most of the internet works like mail. One address. One destination. That's Unicast — one-to-one. Broadcast sends to everyone. Multicast sends to a group. But Anycast? One address. MULTIPLE servers. The network picks the nearest one. For you.

Here's how it works. A company — say Cloudflare — has servers in 300 cities. They want ONE IP address for their DNS: 1.1.1.1. But 300 servers can't have the same IP. Or can they? They can. Each server — in Tokyo, London, New York — announces the same IP to the internet's routing system. BGP. BGP is the internet's GPS. It's how routers learn how to reach any address. Every router builds a table: "To reach 1.1.1.1, here are the paths — via Tokyo, via London, via New York." For a user in Tokyo, the shortest path might be to the Tokyo server. For a user in London, the London server. Same IP. Different physical destinations. BGP picks the shortest path. You get routed automatically. No configuration. No Geo-DNS. The network topology does the work. It's routing 101 — shortest path wins.

**Unicast:** One IP → one server. **Anycast:** One IP → nearest of many servers. The "any" means "any one will do — give me the closest." You don't choose the server. The network chooses. Based on routing tables. Based on topology. Based on what BGP has learned about the shortest path. It's automatic. It's distributed. And it's why the internet scales. One logical address. Hundreds of physical locations.

---

## Another Way to See It

Imagine 100 pizza delivery drivers. All wearing the same uniform. Same company name. You call "Pizza Express." The dispatcher doesn't pick a random driver. They send the one CLOSEST to you. You don't choose. The system chooses. Anycast is the internet's version of that — routers are the dispatchers, BGP is the logic.

---

## Connecting to Software

Anycast powers critical infrastructure. **DNS root servers** — the 13 addresses that resolve every domain on earth — use Anycast. There aren't 13 physical servers. There are 1,500+. All announcing the same 13 addresses. **CDNs** use Anycast. **DDoS protection** uses Anycast — attack traffic gets distributed across hundreds of servers. One IP. Massive resilience.

---

## Let's Walk Through the Diagram

```
                    ONE IP: 1.1.1.1
                           |
              BGP Routing (Internet's GPS)
                           |
    +----------+-----------+-----------+----------+
    |          |           |           |          |
[User Tokyo] [User London] [User NYC] [User Sydney]
    |          |           |           |          |
    v          v           v           v          v
 Tokyo      London       Virginia    Sydney
 Server     Server       Server      Server
 (same IP)  (same IP)   (same IP)   (same IP)
```

Each user hits the same IP. Each gets the nearest server. The routing table does the magic. No application logic. Pure network.

---

## Real-World Examples (2-3)

**1. Cloudflare 1.1.1.1:** The "fastest DNS" in the world. One IP. 300+ locations. When you query 1.1.1.1, you hit the nearest Cloudflare data center. Often under 10ms. Anycast makes it possible.

**2. Root DNS servers:** a.root-servers.net through m.root-servers.net. 13 addresses. 1,500+ physical machines. Anycast. When the internet resolves a domain, it hits one of those 13. You get the nearest copy. The system has never gone down. That's Anycast resilience. Think about that — the entire domain name system depends on 13 logical points. Replicated globally. Anycast made it possible.

**3. AWS Global Accelerator:** You attach your application to an Anycast IP. Traffic enters at the nearest AWS edge. Then gets routed to your origin. Lower latency. DDoS protection. Anycast under the hood. You pay for the traffic. AWS handles the routing. One IP. Global reach.

---

## Let's Think Together

A DDoS attack sends 1 billion requests per second to one IP address. That IP is behind Anycast — 500 servers worldwide. What happens?

*Pause. Think.*

The traffic gets distributed. Each region's routers send requests to the nearest Anycast node. 1 billion requests ÷ 500 servers ≈ 2 million per server. Still a lot. But manageable. Without Anycast? One server. One billion requests. Obliterated. Anycast spreads the load. It's a built-in DDoS mitigator. The attack hits 500 targets instead of one. Each target survives. That's why CDNs and DNS use it. Resilience by design.

---

## What Could Go Wrong? (Mini Disaster Story)

A company runs a WebSocket app — real-time chat. They put it behind Anycast. Works great. Users connect. Messages flow. Then BGP updates. A route changes. User's connection gets rerouted. Mid-session. Their next packet goes to a DIFFERENT server. A server that doesn't have their session state. Connection drops. "Why did I get disconnected?!" Anycast + stateful connections = danger. Anycast assumes requests are independent. WebSockets, TLS sessions, TCP connections — they have memory. If routing changes, you can land on a server that doesn't know you. Lesson: stateless services love Anycast. Stateful services? Be careful.

---

## Surprising Truth / Fun Fact

The 13 root DNS server clusters use Anycast. You learned there are 13. But there are actually 1,500+ physical servers behind those 13 addresses. The letter "a" through "m" — that's it. The entire domain name system depends on 13 logical points. And they're replicated globally. The internet is more resilient than you think. One address. Thousands of copies. Anycast made it possible. Think about that.

---

## Quick Recap (5 bullets)

- **Anycast** = one IP address, multiple servers. BGP routes you to the NEAREST one
- **Unicast** (one-to-one) vs **Broadcast** (one-to-all) vs **Anycast** (one-to-nearest) vs **Multicast** (one-to-group)
- Used for: DNS, CDNs, DDoS protection — anything that benefits from "nearest server" routing
- **BGP** — the internet's routing protocol — does the work. No application logic needed
- Warning: **Stateful connections** (WebSockets, long TCP) can break if routing changes mid-session

---

## One-Liner to Remember

> Anycast: one address, many doors. The network opens the one nearest to you.

---

## Next Video

We've been talking networks. Let's switch. Data. You have users. Products. Orders. How do you store them? Not in random files. In TABLES. Rows and columns. Connected. That's a relational database. And it's been powering the world since 1970. Next.
