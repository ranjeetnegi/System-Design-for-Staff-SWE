# What is a Reverse Proxy?

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

A guest walks into a hotel. They want room service. They need a taxi. They have a complaint. But they never walk to the kitchen. They never call the taxi company directly. Someone stands between them and the chaos behind the scenes. Who? The concierge. And here's the twist — that concierge doesn't just help. It protects. It hides. It decides. Every request flows through one person. That's a reverse proxy.

---

## The Story

Imagine a luxury hotel. Hundreds of guests. A kitchen with ten chefs. A fleet of taxis. Housekeeping. Maintenance. But guests don't wander into the kitchen. They don't negotiate with taxi drivers. They go to the front desk. The concierge.

"I'd like dinner." The concierge routes that to the kitchen. "I need a ride to the airport." The concierge calls a taxi. "My room is too cold." The concierge contacts maintenance. The guest never sees the chef. Never meets the driver. Never knows which internal team fixed the AC. The concierge is the SHIELD. The single face. The gateway.

Here's where things get interesting. The concierge doesn't just route. They decide. "Kitchen is busy — send this order to the backup kitchen." "This guest is VIP — prioritize them." "That request looks suspicious — block it." The concierge protects the staff from the guests. And the guests never even know how many people work behind the scenes. The concierge can also handle things the staff shouldn't worry about. SSL? The concierge speaks encrypted language to guests. The kitchen gets plain requests. The heavy decryption work happens at the front. Caching? The concierge remembers common requests. "Room service menu? I have that. No need to ask the kitchen." That concierge? A reverse proxy.

---

## Another Way to See It

Forward proxy vs reverse proxy. A forward proxy: YOU hire a bodyguard. You want to buy something from a shop, but you don't want the shop to see you. So the bodyguard goes to the shop FOR you. The shop sees the bodyguard, not you. You're hidden. Reverse proxy: The hotel has a concierge. Guests come TO the hotel. The concierge stands in front. The guests never see the kitchen, the staff, the back offices. The SERVERS are hidden. Different direction. Same idea — someone in the middle.

---

## Connecting to Software

In software, a reverse proxy sits in front of your web servers. Users send requests to the proxy. The proxy forwards them to the right backend server. Users think they're talking to one server. They're actually talking to a proxy that routes to many. The proxy can route, load balance, terminate SSL, cache, compress, and block threats. Your internal servers stay hidden and protected.

---

## Let's Walk Through the Diagram

```
    USER                    REVERSE PROXY                    INTERNAL SERVERS
      |                          |                                 |
      |  "I want homepage"       |                                 |
      |------------------------->|                                 |
      |                          |  Routes to Server 1              |
      |                          |--------------------------------->|
      |                          |                                 |
      |                          |<---------------------------------|
      |                          |  Response from Server 1           |
      |<-------------------------|                                 |
      |                          |                                 |
      |  "I want /api/data"      |                                 |
      |------------------------->|  Routes to Server 2 (API)        |
      |                          |--------------------------------->|
      |                          |                                 |
```

**What the user sees:** One address. One server.  
**What really happens:** The proxy picks which backend handles each request. Users never see Server 1, Server 2, or Server 3. The proxy can also terminate SSL — meaning it receives encrypted traffic from users, decrypts it, and then talks to backend servers (optionally in plain text or re-encrypted). This offloads the heavy SSL work from your application servers. Compression? The proxy can gzip responses before sending to users. Caching? The proxy can store static responses and serve them without touching the backend at all. Security? The proxy hides your internal topology. Attackers see one IP. They don't see how many servers you have or where they live.

---

## Real-World Examples (2-3)

**1. Nginx:** One of the most popular reverse proxies. Handles millions of sites. Fast, lightweight.

**2. Cloudflare:** Sits in front of websites worldwide. Does routing, DDoS protection, caching, and SSL. You rarely talk directly to the origin server.

**3. AWS Application Load Balancer (ALB):** Routes traffic to EC2 instances or containers. Routes by path, host, or rules you define.

---

## Let's Think Together

**Question:** You have 5 backend servers. A user sends a request. Who decides WHICH server handles it?

**Pause. Think about it...**

**Answer:** The reverse proxy (or the load balancer, which often lives inside or alongside it). The proxy uses rules: round-robin, least connections, path-based routing. Maybe /api goes to servers 1–2, /images to server 3, and /videos to servers 4–5. The proxy makes that decision. The user never chooses — they just send a request to one address.

---

## What Could Go Wrong? (Mini Disaster Story)

The concierge collapses. Heart attack. Panic. Guests are at the desk. "Where's our food? Our taxi?" Nobody answers. The kitchen is fine. The taxis are fine. But there's no one to connect them. Chaos.

That's a single point of failure. If your reverse proxy goes down, users can't reach ANY of your backend servers. Even if all 50 servers are healthy, the proxy is the bottleneck. No proxy, no routing, no access. That's why high-availability setups use multiple proxies, health checks, and failover. The concierge must never be alone.

---

## Surprising Truth / Fun Fact

Most websites you visit — you **never** talk directly to the actual server. A reverse proxy (or CDN edge, which often acts like one) almost always sits in between. When you hit amazon.com, Netflix, or your local blog, your request goes to an edge node first. The real origin might be thousands of miles away. You're talking to a proxy. And you never even notice.

---

## Quick Recap (5 bullets)

- A reverse proxy sits in front of your servers and receives all user requests.
- It routes requests to the right backend, load balances, and can handle SSL and caching.
- Forward proxy hides the CLIENT. Reverse proxy hides the SERVER.
- Real examples: Nginx, Cloudflare, AWS ALB.
- The reverse proxy can become a single point of failure — design for redundancy.

---

## One-Liner to Remember

> **The reverse proxy is the concierge. Every request goes through it. Your servers stay behind the desk.**

---

## Next Video

The proxy routes. But HOW does it decide which server gets the next request? Round-robin? Busiest first? There's a host at the door, directing traffic — and the algorithm matters. Next: What is a load balancer?
