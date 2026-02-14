# BASE: Basically Available, Soft State, Eventual Consistency

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

ACID is like a strict boarding school. Rules. Discipline. Everything correct. Always. One student breaks a rule—whole school knows in minutes. Order. Predictability. BASE is like a flexible startup. "Move fast. Things might be slightly messy. They'll sort themselves out." No strict rules. High energy. Maybe a few loose ends. But they ship. Most of the large-scale internet—Facebook, Amazon, Netflix—runs on BASE thinking. Not ACID. Why? Because ACID doesn't scale to billions of users. BASE does. Let me explain.

---

## The Story

**BASE** stands for:

**Basically Available:** The system always responds. Always. Even if the response is degraded. Even if some data is stale. Even if some features are limited. You get SOMETHING. No "system down." No "try again later" for hours. Availability over perfection.

**Soft state:** The system's state can change without new input. Why? Because of eventual propagation. Replicas are syncing. Data is flowing. What you see now might not be what you see in 5 seconds. The state is "soft"—not frozen. Not guaranteed until convergence.

**Eventually consistent:** If no new updates arrive, all replicas will eventually converge to the same value. Given enough time. No new writes? Replicas sync. They agree. "Eventually" might be seconds. Might be minutes. But they'll get there. No permanent inconsistency. BASE doesn't promise WHEN. It promises THAT. The system will converge. The "when" depends on load, network, and design. High-traffic systems might converge in milliseconds. Cross-continent replication might take seconds. Plan for the worst case. Accept the average case.

---

## Another Way to See It

ACID: A bank vault. Every transaction logged. Every balance exact. Every transfer atomic. Correct or nothing. BASE: A whiteboard in a busy office. Someone writes. Someone else writes. Eventually everyone sees everything. Might take a minute. Might have temporary overlap. But the system keeps going. No locks. No waiting. Different philosophy. ACID = correctness first. BASE = availability and speed first. Accept some mess. Clean it up later.

---

## Connecting to Software

**ACID:** Strong guarantees. Atomicity, Consistency, Isolation, Durability. Traditional relational databases. PostgreSQL, MySQL (in default mode). Lower throughput. Higher latency. Scales vertically. Perfect for: banking, inventory, anything where wrong = disaster. ACID has been the gold standard for decades. It works. It's correct. But at internet scale—billions of users, global distribution—ACID's coordination overhead becomes the bottleneck. That's when BASE enters.

**BASE:** Weaker guarantees. High throughput. High availability. Scales horizontally. Perfect for: social feeds, recommendations, session data, analytics, anything where "good enough" is good enough. Most NoSQL databases lean BASE. Cassandra, DynamoDB, MongoDB (in certain modes). They're not enemies. Different tools. Different problems. Pick the right one. A system can even use both: ACID database for transactions, BASE cache for reads. Hybrid architectures are common. Know which piece needs which guarantee.

---

## Let's Walk Through the Diagram

```
    ACID vs BASE

    ACID:
    ┌─────────────────────────────────────┐
    │  Write → Lock → Commit → Confirm    │
    │  All or nothing. Correct.           │
    │  Slow. Vertical scale.              │
    └─────────────────────────────────────┘

    BASE:
    ┌─────────────────────────────────────┐
    │  Write → Accept → Replicate async   │
    │  Available. Fast. Eventually correct│
    │  Horizontal scale.                  │
    └─────────────────────────────────────┘

    Base of the CAP Triangle:
    ACID aims for C (Consistency). BASE aims for A (Availability).
    Both give up something. Choose based on your needs.
```

ACID blocks. BASE flows. The diagram shows: one path is narrow, precise. The other is wide, approximate. Both reach a destination. Different trade-offs.

---

## Real-World Examples (2-3)

**Example 1: Amazon shopping cart.** BASE. Add item. Might take a moment to sync across devices. Remove item. Same. Cart can be "soft" for a few seconds. When you checkout? That's ACID. Payment. Inventory. Must be correct. One system. Two philosophies. Right place for each.

**Example 2: Netflix recommendations.** "Because you watched X." Stale by an hour? User doesn't care. BASE. Fast. Scale. Eventually consistent. **Example 3: Google Search index.** Web crawls. Updates propagate. Index is "eventually" correct. New page might not appear for days. BASE. Acceptable. Scale demands it. Google indexes billions of pages. Strong consistency would mean every crawler, every data center, every replica agrees before serving. Impossible at that scale. BASE lets them crawl, index, propagate. You search. You get "good enough" results. Maybe your new blog post isn't in yet. Refresh tomorrow. The trade-off is explicit. And accepted.

---

## Let's Think Together

Shopping cart on Amazon. ACID or BASE?

BASE. Add to cart. Remove. Sync across devices. Slight delay? Fine. Merge conflicts? "User added X on phone, removed on laptop"—merge. Application handles it. Cart is soft. Eventually consistent.

What about the final payment step?

ACID. Charge card. Deduct inventory. Update order. Must be atomic. Must be correct. No "eventually" for money. So: cart = BASE. Payment = ACID. One flow. Two models. Design is choosing the right tool for each step.

---

## What Could Go Wrong? (Mini Disaster Story)

A company built their entire order system on BASE. "Scale!" Order placement. Inventory deduction. Payment. All eventual. Network glitch. Order placed. Inventory decremented on one node. Payment processed on another. Replication lag. Conflict. Order "completed" but inventory not updated everywhere. Oversold. Customer charged. No product. Refund. Investigation. Root cause: payment and inventory need ACID. They used BASE everywhere. Lesson: not everything can be BASE. Identify the critical path. Use ACID there. BASE everywhere else.

---

## Surprising Truth / Fun Fact

Dan Pritchett from eBay coined BASE in 2008. He was explaining how eBay's architecture differed from traditional databases. ACID was the standard. eBay needed something else. Scale. Availability. They traded consistency for speed. BASE put a name to it. Now it's textbook. The abbreviation is a bit forced—"Basically Available" isn't always "soft" in the literal sense. But the idea stuck. And it describes most of the web.

---

## Quick Recap (5 bullets)

- **BASE:** Basically Available (always respond), Soft state (can change without input), Eventually consistent (replicas converge).
- **ACID** = strong guarantees, lower throughput. **BASE** = weaker guarantees, higher throughput, horizontal scale.
- Not enemies. Different tools. Use ACID for money, inventory. BASE for feeds, sessions, recommendations.
- Most large-scale systems (Amazon, Netflix, social) use BASE for most operations.
- Cart = BASE. Payment = ACID. Design per operation. Not one-size-fits-all.

---

## One-Liner to Remember

**BASE: Move fast. Accept temporary mess. Replicas will converge. Use when "good enough" is good enough. Use ACID when it's not.**

---

## Next Video

Next: **Leader-follower replication.** The news anchor and the assistant anchors. One reads the news. Three repeat it in different cities. How writes propagate. What happens when the main anchor's studio catches fire. See you there.
