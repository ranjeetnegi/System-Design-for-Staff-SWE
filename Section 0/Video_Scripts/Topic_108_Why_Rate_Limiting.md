# Why Rate Limiting? Overload and Abuse

## Video Length: ~4-5 minutes | Level: Beginner

---

## The Hook (20-30 seconds)

A supermarket has a free sample counter. One sample per person. Fair. But one person doesn't leave. They come back. Again. Again. Fifty times. The tray is empty. Everyone else gets nothing. The store could do nothing—and watch one person ruin it for everyone. Or they could add a rule: "Maximum two samples per person." That's **rate limiting**. One simple rule. Everyone gets fair access. The system doesn't collapse. Your API needs the same protection. Let me show you why.

---

## The Story

Without rate limiting, one bad actor can consume everything. A bot sends 10,000 requests per second. Your server has a limit. Maybe 1,000 requests per second total. The bot takes it all. Legitimate users get nothing. Timeouts. Errors. "Service unavailable." One user. One bot. Everyone suffers. That's **abuse**. Or picture a different scenario. Your app goes viral. Suddenly 100,000 real users hit your server at once. No malice. Just success. Your server can't handle it. It crashes. That's **overload**. Rate limiting helps with both. It caps how much any single entity—user, IP, or globally—can consume. Abuse gets throttled. Overload gets smoothed. The system stays up. Everyone gets a fair share. Think of it as traffic lights for your API. Without them, everyone rushes at once. Gridlock. With them, orderly flow. Slower for some, but everyone gets through.

---

## Another Way to See It

Think of a buffet. No rules. One person loads five plates, goes back ten times. Others get scraps. Rate limiting: "Two trips per person." Everyone eats. Or a highway. Rush hour. Too many cars. Traffic jam. Toll that limits entry? Or ramp metering—let in a few cars per second. Prevents total gridlock. Rate limiting is flow control. It prevents one or many from drowning the system.

---

## Connecting to Software

**Reason 1: Protect from abuse.** Bots. Scrapers. Credential stuffing—trying millions of password combinations. DDoS—flooding your server with requests. Attackers don't play fair. Rate limiting says: "You can only try so many times." Login attempts: 5 tries, then lockout. API: 100 requests per minute per user. Slow down the attacker. Or stop them. Without rate limiting, a credential stuffing attack could try millions of passwords against your login endpoint. With it, they're capped. You buy time. You detect the pattern. You block them. **Reason 2: Protect from overload.** Legit traffic spike. Product launch. News article. Everyone hits your site. Rate limiting queues or rejects excess. Prevents cascade failure. Server stays up. Some users wait. Better than everyone failing. A graceful 429 with "Try again later" beats a timeout or 500 error. At least the user knows what happened.

---

## Let's Walk Through the Diagram

```
    WITHOUT RATE LIMITING                    WITH RATE LIMITING

    ┌──────────┐                              ┌──────────┐
    │  User 1  │ 10,000 req/sec               │  User 1  │ 100 req/min max
    └────┬─────┘                              └────┬─────┘
         │                                         │
         │    ═══════════════►                     │    ─────►
         │    ALL bandwidth                        │    Fair share
         │    consumed                             │
         │                                         │
    ┌────┴─────┐                              ┌────┴─────┐
    │ User 2-N │ 0 req/sec                     │ User 2-N │ 100 req/min each
    │ (blocked)│  😞                           │ (served) │  😊
    └──────────┘                              └──────────┘

    One user kills it for everyone.         Everyone gets fair access.
```

---

## Real-World Examples (2-3)

**Example 1: Twitter API.** 900 requests per 15 minutes for the free tier. Rate limited. Prevents scrapers from downloading the entire platform. Fair use. Protects their infrastructure.

**Example 2: GitHub API.** 5,000 requests per hour for authenticated users. Need more? Pay for it. Or optimize. Rate limits force efficiency. They also prevent abuse.

**Example 3: Login attempts.** Most sites: 5 wrong passwords, then "Try again in 15 minutes." Rate limiting on login. Stops brute force. One attack vector closed. Simple. Effective. Without it, an attacker could try 1000 passwords per second. With it, they're stuck at 5 per 15 minutes. The math makes the attack impractical. Rate limiting turns "possible" into "impossible."

---

## Let's Think Together

Your API has no rate limit. A competitor writes a bot that calls your API one million times per day. They scrape your data. They clone your product. What happens?

Your server gets hammered. CPU. Bandwidth. Database. All stressed. Costs go up. Real users see slowdowns. Maybe you have to scale—expensive. Or maybe the competitor's bot is the final straw that pushes your system over. Downtime. Lost revenue. And you might not even know it's a competitor. It could look like "normal" traffic. Rate limiting would cap them. 1000 requests/hour? Fine. 1 million? Blocked. You protect your system. You protect your costs. You protect real users. Rate limiting isn't optional for public APIs. It's survival.

---

## What Could Go Wrong? (Mini Disaster Story)

A startup launches a free API. No rate limits. "We want to be developer-friendly." A cryptocurrency trader discovers their API has real-time data. He writes a script. 100,000 requests per minute. His script gets the data. The API bill explodes. The startup's cloud costs go from $500 to $50,000 in a week. They didn't budget for it. They shut down the API. All developers—including the good ones—lose access. One abuser. No rate limit. Total collapse. The fix? Rate limit from day one. Even generous limits. 10,000/hour. Something. Protect yourself before you need to.

---

## Surprising Truth / Fun Fact

Some of the biggest DDoS attacks in history could have been softened by rate limiting. Not stopped—distributed attacks come from many IPs—but per-IP limits would have reduced the impact. Rate limiting is one layer. It's not a silver bullet. Combine it with WAFs, CDNs, and scaling. Defense in depth. But don't skip it. It's cheap. It's simple. It saves systems every day. And here's something most people forget: rate limiting also protects you from your own bugs. A bug in a mobile app that fires 1000 requests in a loop? Rate limit catches it. Costs stay under control. Users don't exhaust their data plans. Your mistake doesn't become a crisis.

---

## Quick Recap (5 bullets)

- **Rate limiting** = cap how many requests an entity can make (user, IP, or global).
- **Two reasons**: (1) Abuse—bots, scrapers, DDoS. (2) Overload—too many legit users at once.
- **Without it**: one user can consume all resources. Everyone else fails.
- **Examples**: Twitter (900/15min), GitHub (5000/hr), login lockout (5 tries).
- **Public APIs**: rate limiting is essential. Not optional.

---

## One-Liner to Remember

**Rate limiting: One person can't empty the tray. Everyone gets a fair share. Your system survives.**

---

## Next Video

How do you actually implement it? Buckets. Tokens. Windows. Next: **Token bucket algorithm**—the parking garage that controls the flow. See you there.
