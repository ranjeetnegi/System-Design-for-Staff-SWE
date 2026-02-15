# Stale Reads: When Acceptable

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

Your weather app. Shows 25°C. You step outside. The thermometer says 25.3°C. Is that a problem? No. Weather doesn't change in seconds. A few minutes of staleness is fine. Now imagine your bank app. Balance shows Rs 10,000. Actual balance: Rs 500. You just got charged. You didn't see it. You spend Rs 8,000 thinking you have it. Overdraft. Fees. Disaster. Stale reads are acceptable for some data. Catastrophic for others. Knowing the difference—that's engineering maturity. Let's break it down.

---

## The Story

A stale read is simple: you read data that's slightly out of date. The cache has an old value. The read replica hasn't caught up with the primary. The CDN is serving yesterday's page. You get something that was true—but isn't anymore. Staleness. How much? Seconds. Minutes. Hours. Depends on the system. The question: when does it matter?

Weather: 10 minutes old? Fine. Stock price: 15 seconds old? For a long-term investor, maybe fine. For a day trader? Not fine. Bank balance: 1 second old? Dangerous. Inventory count: "5 left in stock"—but really 1? Two users see 5. Both buy. Oversold. Stale reads cause real harm. Or they don't. Context is everything.

---

## Another Way to See It

A newspaper. Yesterday's news. You read it with coffee. It's stale. But you don't care. You're not trading on it. Now imagine the same newspaper for your exam results. "You passed!" But the database says you failed. They printed the wrong list. Stale. Critical. The data type determines whether staleness is acceptable. News vs. decision-critical. Same concept. Different stakes.

---

## Connecting to Software

**Stale read sources:** Cache (TTL-based, might serve old value). Read replica (replication lag, milliseconds to seconds). CDN (edge cache, can be minutes). Eventually consistent systems (designed for staleness).

**When acceptable:** Social media feeds (a few seconds delay—fine). Product listings (price updated within minutes—usually OK). Analytics dashboards (minutes or hours of lag—normal). Weather, news, recommendations. Non-critical. Eventually consistent is a feature.

**When NOT acceptable:** Bank balance. Inventory count (overselling risk). Security permissions (revoked access still active). Payment status. Medical dosages. Anything where a wrong decision has immediate serious consequence. These need strong consistency. Read from primary. Or linearizable reads. No staleness.

**Trade-off:** Accepting staleness lets you use caches, read replicas, CDNs. Massive performance gain. Reduced load. Lower cost. The trick is knowing where the line is. Draw it wrong—too strict—and you pay in performance. Too loose—and you pay in correctness. Draw it right—and you get both.

**Consistency spectrum:** Strong (linearizable) → sequential → causal → eventual. Strong = no staleness, ever. Eventual = stale is fine, will converge. Most apps use a mix. Critical path: strong. Non-critical: eventual. Design per-use-case. A single "consistency level" for the whole app is rarely right.

---

## Let's Walk Through the Diagram

```
                    STALE ACCEPTABLE          STALE NOT OK
                    (read from replica,       (read from primary,
                     cache, CDN)               no cache)
                          |                          |
   Social feed       -----+-----              Bank balance
   Product page      -----+-----              Inventory count
   Analytics         -----+-----              Permissions
   Weather           -----+-----              Payment status
   Recommendations   -----+-----

   Same system. Different data. Different rules.
   Route by criticality.
```

---

## Real-World Examples (2-3)

**Twitter/LinkedIn feed:** Read from read replica. Lag: 1–5 seconds. You might miss the very latest tweet. Usually fine. Scale benefits: huge. Replicas serve the load. Primary handles writes. Trade-off accepted.

**Banking:** Balance from primary. Or from replica with "read your writes" consistency—your own writes are always visible. Never stale for your own data. Critical. No trade-off.

**E-commerce product page:** Often cached. Price might be a few minutes old. For most products, OK. For flash sales or limited inventory? Dangerous. Some systems: product info cached, inventory read through to primary. Hybrid. Match consistency to the field. Title, description, images—cache for hours. Price, stock—shorter TTL or real-time at checkout.

**Gaming leaderboards:** Often eventually consistent. You submit a score. Leaderboard updates in a few seconds. You might not see your name immediately. Usually fine. Real-time leaderboards for esports? Different—need strong consistency. Casual game vs. competitive—different requirements.

---

## Let's Think Together

**Question:** E-commerce. Product page shows "5 left in stock." Two users see this. Both click buy. Real stock: 1. What happens?

**Answer:** Overselling. Both think 5. Both order. One gets it. One gets "sorry, out of stock" at checkout. Or worse: both get it. You ship 2. You had 1. Inventory goes negative. Customer anger. The fix: inventory check at checkout must be consistent. Read from primary. Or use optimistic locking—verify at commit. Never trust cached inventory for the final purchase decision. Stale is OK for display ("approximately 5"). Not OK for the transaction.

---

## What Could Go Wrong? (Mini Disaster Story)

A user's admin access is revoked. Security team updates the database. Read replicas lag. 30 seconds. User hits a cached page or a replica. Still sees admin UI. Still has access. In that window, they export sensitive data—customer PII, financial records. The revoke was effective in the primary. But the user read from stale source. Incident. Forensic review. The lesson: security-sensitive data—permissions, access—must be consistent. No replicas for critical checks. Or use "critical read" path that hits primary. Never risk security for performance. Route auth and permission checks to the source of truth.

---

## Surprising Truth / Fun Fact

Amazon's DynamoDB has "eventually consistent reads" and "strongly consistent reads." Same table. You choose per request. Cheap, fast reads—eventual. Expensive, slower—strong. They charge differently. They're telling you: consistency has a cost. Use it when you need it. Skip it when you don't. The best systems let you choose. Same pattern in Cassandra, ScyllaDB, and others. One API, multiple consistency levels. Design your reads consciously. Default to eventual when safe. Opt into strong when critical. Document the choices so the next engineer understands. Stale reads are a tool. Use them where safe. Avoid them where dangerous. The map is in your head—put it in the code and docs too.

---

## Quick Recap (5 bullets)

- **Stale read** = data slightly out of date; cache, replica lag, CDN
- **Acceptable** = feeds, product info, analytics, weather; seconds/minutes OK
- **Not acceptable** = balance, inventory, permissions, payment status
- **Trade-off** = staleness enables cache, replicas, scale; use where safe
- **Rule** = match consistency to criticality; display can lag, transaction cannot

---

## One-Liner to Remember

**Stale reads: fine for feeds and product pages, fatal for balances and inventory—route by criticality.**

---

## Next Video

Up next: We've covered payments, media, databases, caching, and consistency. What topic should we tackle next? Drop a comment. And if this helped, like and subscribe. See you in the next one.
