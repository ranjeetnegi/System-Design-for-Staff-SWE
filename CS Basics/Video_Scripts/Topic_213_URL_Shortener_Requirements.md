# URL Shortener: Problem and Requirements

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

Your friend sends you a link. You open the message. Your eyes go wide. A wall of text so long it feels like a paragraph:

`https://www.example.com/products/electronics/smartphones/samsung-galaxy-s24-ultra-256gb-phantom-black?ref=email&campaign=summer2024`

Ugly. Won't fit in a tweet. Won't fit on a poster. You can't neatly write it on a business card. What if you could turn it into this: `https://short.ly/abc123`? Same destination. Tiny link. That's a URL shortener. Let's design one together.

---

## The Story

URL shortening isn't new. Bitly launched in 2008. TinyURL even earlier. But the problem hasn't changed: the web is full of long, messy URLs. Social media has character limits. Print has physical limits. And humans? We love short, shareable links.

Think of it like a nickname. Your full name might be "Alexander Christopher Montgomery III." But your friends call you "Alex." Same person. Shorter label. A URL shortener does that for web addresses—it gives every long URL a short alias that points to the same place.

The magic is simple: you store a mapping. Short code "abc123" maps to long URL "https://www.example.com/...". When someone clicks the short link, you look up the mapping and send them to the real destination. That's the core. Everything else is making it fast, reliable, and massive. The requirements phase is where we decide what we are building and what we are not. Get this right, and the design flows naturally. Skip it, and you will regret it later.

---

## Another Way to See It

Imagine a massive library where every book has a long, detailed title. Instead of saying "The Complete History of the Roman Empire, Volume 3, Chapter 7, Section 2," the librarian hands you a slip: "Aisle 7, Shelf 3, Slot 42." You walk there. The slip is tiny. The book is still the whole book. The shortener is the slip system—compact references to full destinations.

---

## Connecting to Software

Let's nail down what we're building. **Functional requirements:** shorten a long URL into a short URL. Redirect short URL clicks to the original. That's the minimum. Nice-to-haves: custom aliases (e.g., short.ly/mybrand), expiration dates, and basic analytics—how many clicks, when, from where.

**Non-functional requirements** matter just as much. Redirect latency: under 100 milliseconds. Users expect instant. High availability: 99.99%—shorteners power ads, emails, campaigns; downtime costs money. Scale: assume 100 million URLs stored, 10,000 writes per second, 100,000 reads per second. Reads dominate. We'll lean on caching hard.

**Estimation—short URL length.** How many characters do we need? Use 7 chars from [a-zA-Z0-9]—62 options per character. That's 62^7 = 3.5 TRILLION combinations. More than enough. Even at 10,000 writes per second, we would run for over a year before exhausting a fraction of the space. The math is overwhelmingly on our side. Six characters would give 62^6 = 56 billion—still plenty for most use cases, but seven buys headroom and keeps URLs compact.

---

## Let's Walk Through the Diagram

```
┌─────────┐     POST /shorten      ┌─────────────┐     Store     ┌──────────┐
│  User   │ ───────────────────► │  API       │ ─────────────► │ Database │
│         │  { "url": "https://   │  Server    │   short_code   │  (KV)    │
└─────────┘     example.com/..." }└─────────────┘   long_url     └──────────┘
      │                │                   │
      │                │                   └── Returns: https://short.ly/abc123
      │                │
      │     GET /abc123 │
      │ ◄──────────────┤
      │  301 Redirect  │
      │  Location: https://example.com/...
      ▼
  Original URL
```

Capacity estimate: 100M URLs at 500 bytes each is 50GB of storage. A single database can handle that. Reads at 100K/sec need caching. Writes at 10K/sec need sharding or connection pooling. The write path: user submits long URL, API generates a short code, stores the mapping, returns the short URL. The read path: user hits short URL, API looks up the code, responds with a 301 redirect to the long URL. Simple. But every detail—code generation, storage, caching—will matter at scale.

---

## Real-World Examples

**Bitly** started with Twitter's 140-character limit. Today it handles billions of redirects, powers analytics, custom-branded short domains. **TinyURL** is the minimalist—no account, no analytics, just shorten and go. **Twitter's t.co** shortens every link automatically to prevent phishing and track clicks. **Google's goo.gl** (retired in 2019) served 20 billion redirects per month at its peak. Each serves a different need. Core idea is identical: map short to long, redirect fast.

---

## Let's Think Together

**"If we generate 1000 short URLs per second, how long until we exhaust 62^7 combinations?"**

62^7 = about 3.5 trillion. At 1000 per second: 3.5 trillion ÷ 1000 ÷ 60 ÷ 60 ÷ 24 ≈ 40,000 days. Over 100 years. We're safe. Even at 100,000 per second, we'd last months. The math is on our side.

---

## What Could Go Wrong? (Mini Disaster Story)

Launch day. Your URL shortener goes live. A celebrity tweets one of your links. Traffic explodes. Your database cannot handle the read load. Redirects take 5 seconds. Users think the link is broken. They click competitors instead. Your monitoring alerts fire. The team scrambles. By the time you add caching, the moment has passed. You lose credibility in an hour. The lesson: design for read-heavy load from day one. Cache everything hot. Plan for virality before it hits. Assume every link could go viral.

---

## Surprising Truth / Fun Fact

TinyURL's first link, created in 2002, still works. It points to a CNN article. Over two decades of redirects, and it's never broken. That's the power of simple, focused design—when you do one thing well, it lasts.

---

## Quick Recap

- URL shortener maps short codes to long URLs; redirect is the core behavior.
- Functional: shorten, redirect, optional custom aliases, expiration, analytics.
- Non-functional: <100ms redirect, 99.99% availability, 100M URLs, 10K writes/sec, 100K reads/sec.
- 7 chars [a-zA-Z0-9] = 62^7 ≈ 3.5 trillion combinations—more than enough at 1K–10K writes/sec.
- Design for read-heavy: caching and fast lookups are critical. Plan for virality. Assume every link could go viral tomorrow. Requirements are the foundation. Get them right before writing a single line of design. Clarify ambiguities. Custom aliases: who can create them? Expiration: default TTL or per-URL? Analytics: what exactly do we track? Clicks, referrers, timestamps, geo? Requirements drive everything. Answers shape the design.

---

## One-Liner to Remember

*A URL shortener is a giant lookup table: short code in, long URL out—designed for speed and scale.*

---

## Next Video

Next, we'll dive into the high-level design: how to generate unique codes, which database to use, and how the write and redirect flows really work. Requirements first, design second. We have a clear picture of what we are building. Now we build it. See you there.
