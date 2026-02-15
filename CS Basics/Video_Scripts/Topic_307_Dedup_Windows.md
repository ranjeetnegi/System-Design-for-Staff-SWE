# Deduplication Windows in Event Systems

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

A classroom. The teacher calls names. "Ranjeet?" "Present!" But the mic echoes. The system hears "Present! Present!" Two entries for one student. The system needs to ignore the duplicate. "If Ranjeet said 'Present' twice within 5 seconds, count it as one." That's a deduplication window—a time period where we remember what we've seen and discard repeats. Simple idea. Critical in distributed systems.

## The Story

In distributed systems, events can be delivered **more than once**. Network retries. Producer retries. Consumer reprocessing after a crash. Kafka at-least-once? You might process the same message twice. Duplicates aren't exceptional. They're normal. You have to plan for them.

A **deduplication window** is: "For the last N minutes, keep a set of event IDs I've already seen. When a new event arrives, check. In the set? Duplicate. Discard. Not in the set? Process it. Add its ID to the set."

The window is a time period. 5 minutes. 10 minutes. An hour. Depends on your system. "How late can a duplicate possibly arrive?" If your Kafka consumer can lag by 10 minutes, your window better be at least 10 minutes. Otherwise, a late duplicate slips through.

## Another Way to See It

Like a bouncer's list. "Have I seen this ID in the last hour?" Yes → can't enter again. No → come in, I'll add you to the list. The list only holds the last hour. After that, you "forget" — same ID could be a new event (e.g., user logged in again). The bouncer doesn't need a permanent record. Just recent history. That's the window. Recent enough to catch duplicates. Short enough to be manageable.

## Connecting to Software

Where do you store the IDs? Options:

- **In-memory set**: Fast. But if the process restarts, you lose everything. Duplicates that arrive after restart slip through. Fine for best-effort dedup.
- **Redis**: Fast. Survives restarts. TTL on keys = your window. `SET event_id 1 EX 600` — 10 min TTL. Perfect.
- **Database**: Durable. Slower. Good for critical dedup (payments). Query: "SELECT 1 FROM processed_events WHERE id = ? AND created_at > now() - interval '10 min'"

Trade-off: window too short → late duplicates get through. Window too long → more memory, more storage. And consider retention: if you use Redis with TTL, keys expire automatically. If you use a DB, you need a cleanup job to delete old IDs. Otherwise the table grows forever. A 10-minute window with 10K events/sec means you're inserting 10K rows per second and deleting 10K rows per second. Design your schema and indexes for that write pattern. And: if you process 10K events per second with a 10-minute window, you're tracking 10K × 600 = 6 million IDs. Plan for that.

## Let's Walk Through the Diagram

```
  Event Stream                    Dedup Layer

  event-001 ──> In window? NO ──> Process, store ID, t=0
  event-002 ──> In window? NO ──> Process, store ID, t=1
  event-001 ──> In window? YES ──> DISCARD (duplicate)
  event-003 ──> In window? NO ──> Process, store ID, t=5
  ...
  (10 min later)
  event-001 ──> In window? NO ──> Process (ID evicted from window)
```

Late duplicates within the window: caught. After the window: treated as new. Depends on your use case whether that's OK.

## Real-World Examples (2-3)

- **Payment events**: "Charge succeeded" from payment gateway. Duplicate = double credit. Dedup window: hours. Store in DB.
- **Analytics**: "User clicked button." Duplicate = slight overcount. Dedup window: 5 min. Redis. Best-effort OK.
- **Kafka consumer**: At-least-once delivery. Process, commit offset. If you crash before commit, you reprocess. Same message, twice. Dedup window catches that. Store message ID (or offset + partition) in your dedup store. Second time: duplicate, discard. Continue. Exactly-once semantics in Kafka are possible but complex. Dedup is the practical path for many teams.
- **Webhook receivers**: Stripe sends "payment.succeeded" twice (retry). Same event ID. Dedup by event ID in a 24-hour window. Process once. Return 200 both times. Idempotent. Safe.

## Let's Think Together

**Event system processes 10K events per second. Dedup window = 10 minutes. How many event IDs must you track?**

10,000 × 600 seconds = 6 million IDs. In Redis, that's 6M keys. At ~100 bytes per key (ID + overhead), ~600 MB. Manageable. But if your window is 24 hours? 10K × 86400 = 864 million. Bigger problem. Redis would need GBs. Size your window to your reality. And consider: do all events need dedup? Maybe only payments and critical state changes. Analytics events? Maybe a shorter window or in-memory only. Let the rest be best-effort. Not every event is worth the same level of rigor.

## What Could Go Wrong? (Mini Disaster Story)

Your dedup window is 5 minutes. Your Kafka consumer lags. One day, a broker issue causes 15 minutes of lag. Consumer catches up. Re-processes 15 minutes of messages. Your dedup window only held 5. Duplicates from 6–15 minutes ago slip through. You process them again. Double charges. Double notifications. Fix: size your window to max expected lag. Or use exactly-once semantics if your system supports it. Know your bounds.

## Surprising Truth / Fun Fact

Exactly-once processing is hard. Most systems are at-least-once. Dedup is the practical solution. "We might get duplicates. We'll catch them." It's not perfect—after the window, you might miss one. Late duplicates from a Kafka consumer that was down for a day? Could slip through with a 10-minute window. But for most workloads—payments, notifications, analytics—a well-sized window is good enough. Better than no dedup at all. And remember: the window size should match your system's reality. Know your max lag. Size accordingly.

---

## Quick Recap (5 bullets)

- Dedup window: time period where we remember event IDs and discard duplicates
- Duplicates are normal in distributed systems—retries, reprocessing, at-least-once delivery
- Window too short: late duplicates slip through. Too long: more memory/storage
- Storage: in-memory (fast, lost on restart), Redis (fast, durable), DB (durable, slower)
- Size window to max expected lag; 10K/sec × 10 min = 6M IDs to track; Redis TTL or DB cleanup required

## One-Liner to Remember

*Remember what you've seen, but not forever—the dedup window.*

Size the window to your system's max lag. Too short, duplicates slip through. Too long, memory and storage explode. Tune it. Monitor duplicate rate. If you're catching many, your window is working. If you're seeing "processed twice" in production, expand the window or check your storage.

---

## Next Video

Up next: Redundant requests—when to dedupe and when it's not worth it. See you there.
