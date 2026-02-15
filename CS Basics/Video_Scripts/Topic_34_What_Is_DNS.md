# What is DNS and How Does It Work?

## Video Length: ~4-5 minutes | Level: Beginner

---

## The Hook (20-30 seconds)

You need to visit your friend. You know their name: Priya Sharma. But the taxi driver needs an address. "Where do I go?" You don't know the street. You check your phone. Contacts. "Priya Sharma → 42, MG Road, Bangalore." Your phone translates the name into an address. Now imagine every website worked that way. You'd have to memorize 142.250.190.46 instead of google.com. 93.184.216.34 instead of example.com. A nightmare. DNS is the phone book that saves us.

---

## The Story

You're in a new city. You want to visit your friend Priya. You tell the taxi driver: "Take me to Priya Sharma's house." The driver stares. "I need an address." You know the name. You don't know the address. So you open your phone. Contacts. You search "Priya Sharma." There it is: 42, MG Road, Bangalore. You give that to the driver. Problem solved.

Your phone's contact list did something crucial. It translated a NAME into an ADDRESS. Names are for humans. Addresses are for the system. Taxis need addresses. The internet needs IP addresses. But humans can't remember 142.250.190.46. We need names. google.com. facebook.com. amazon.in. Imagine typing 2620:0:862:ed1a::1 instead of netflix.com. Or 13.107.42.14 instead of microsoft.com. Impossible. DNS is the translation layer that makes the internet human-usable. Without it, the web would collapse. Every link would be a number. Every bookmark would be a number. DNS is invisible infrastructure. We take it for granted. But it holds the internet together.

DNS — Domain Name System — is that contact list for the entire internet. You type "google.com." DNS looks it up. Returns 142.250.190.46. Your browser uses that IP to connect. You never see the number. You just type the name. DNS is invisible. But without it, the web would be unusable. Let that sink in.

---

## Another Way to See It

A library. Thousands of books. You want "The Great Gatsby." You don't memorize shelf 12, row 7, position 3. You go to the catalog. You look up the title. The catalog gives you the location. DNS is the catalog. Domain names are the titles. IP addresses are the shelf locations.

---

## Connecting to Software

When you type a URL, your browser doesn't know the IP. It asks the OS. The OS asks a DNS resolver (often your ISP's or router's). The resolver walks a hierarchy: root servers → TLD servers (.com, .org) → authoritative servers for that domain. Eventually, an IP comes back. It gets cached — in your browser, your OS, your router — so the next lookup is faster. The whole process usually takes milliseconds.

---

## Let's Walk Through the Diagram

```
  YOU (Browser)  →  "What is google.com?"
       |
       v
  [Browser Cache] → Hit? Return IP. Miss? Continue.
       |
       v
  [OS Cache] → Hit? Return IP. Miss? Continue.
       |
       v
  [Router Cache] → Hit? Return IP. Miss? Continue.
       |
       v
  [ISP DNS Resolver] → "I don't know. Let me ask..."
       |
       v
  [Root Nameserver] → "For .com, ask the .com server. Here's its address."
       |
       v
  [.com TLD Server] → "For google.com, ask Google's server. Here's its address."
       |
       v
  [Google's Authoritative Server] → "google.com = 142.250.190.46"
       |
       v
  IP returned. Cached at every step. Browser connects.
```

**Hierarchy:** Root (.) → TLD (.com, .org, .in) → Domain (google.com) → Subdomain (mail.google.com). Each level delegates to the next.

**TTL (Time To Live):** How long a resolver can cache the answer before checking again. "Remember this address for 300 seconds." Lower TTL means more frequent lookups but faster propagation when you change IPs. Higher TTL means fewer lookups and less load on DNS servers, but slower updates when something changes. It's a trade-off.

**Subdomains:** mail.google.com, drive.google.com, maps.google.com — all different subdomains under google.com. Each can point to different IPs. DNS handles that hierarchy. You query for the full name, and the authoritative server for that zone returns the right address.

---

## Real-World Examples (2-3)

**1. Google.com:** You type it. DNS returns an IP (or several, for load balancing). You connect. You never think about it.

**2. Cloudflare 1.1.1.1:** A public DNS resolver. Faster for many users than their ISP's default.

**3. Any app that uses a domain:** Netflix, Spotify, your bank — all resolve domain names to IPs via DNS before connecting.

---

## Let's Think Together

**Question:** You change your server's IP address. You update DNS. But users still see the old site. Why? How long will this last?

**Pause. Think about it...**

**Answer:** Caching. The old IP was cached — in users' browsers, their OS, their ISP's resolvers. Those caches have a TTL. Until the TTL expires, they keep serving the old IP. So users hit the old server. Could be minutes. Could be hours. Depends on the TTL you set. When you change IPs, you often lower TTL first (e.g., to 60 seconds), wait for caches to expire, then change the IP. That way the transition is smoother.

---

## What Could Go Wrong? (Mini Disaster Story)

DNS hijacking. Someone poisons the phone book. You look up "google.com." The address you get? A criminal's server. It looks like Google. Same layout. Same login form. You type your password. You're not on Google. You're on a fake. Your password is stolen. Your account is compromised. All because the "address" was wrong. DNS security matters. DNSSEC helps. Careful resolvers help. But the risk is real — the phone book can be forged.

---

## Surprising Truth / Fun Fact

The entire internet depends on 13 root DNS server clusters. Not 13 physical machines — 13 logical roots, each replicated globally. If all 13 were somehow taken down, the internet would slowly stop working. New lookups would fail. Cached entries would eventually expire. The web would degrade. Thirteen. That's how fragile and how powerful the system is.

---

## Quick Recap (5 bullets)

- DNS translates domain names (google.com) to IP addresses (142.250.190.46).
- Resolution: browser cache → OS cache → router → ISP → root → TLD → authoritative server.
- Hierarchy: Root → TLD (.com, .org) → Domain → Subdomain.
- TTL controls how long answers are cached before re-checking.
- DNS hijacking can redirect users to fake sites — security matters.

---

## One-Liner to Remember

> **DNS is the internet's phone book. Names in, addresses out.**

---

## Next Video

You found the server. But it's in Virginia. You're in Mumbai. Every request crosses an ocean. Latency. Slow loads. What if the website had a copy closer to you? A warehouse in your city. Next: What is a CDN?
