# Sync vs Async Replication: Trade-offs

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

You send an important email. You press Send. Now — do you WAIT? Stare at the screen until it says "Delivered and read"? Or do you trust it? Move on. "Sent!" The difference between those two moments — wait or don't wait — is the difference between synchronous and asynchronous replication. And that choice? It decides whether your data survives a crash. Or disappears forever. Let me show you.

---

## The Story

Scenario 1. **Synchronous.** You press Send on that email. Your app does NOT say "Sent!" immediately. It waits. It waits for the recipient's server to receive it. To confirm. "I got it." Only then does your app say "Delivered." You stood there. 10 seconds. 30 seconds. Maybe more. But you KNOW. They have it. Safe. Certain. If your computer crashes right after "Delivered," the email is safe. It is on their server.

Scenario 2. **Asynchronous.** You press Send. Your app says "Sent!" Immediately. You move on. Check another tab. But did they receive it? Maybe. Maybe it is still traveling. In a queue. On a server somewhere. Your computer crashes. The email? Might be lost. Might be stuck. You don't know. Fast. But uncertain.

That is the trade-off. **Synchronous replication:** Leader waits for the follower to confirm the write BEFORE responding to the client. Strong consistency. You know the data is safe. But slower. **Asynchronous replication:** Leader responds to the client immediately AFTER writing locally. Follower catches up later. Faster. But if the leader crashes before the follower receives it? Data loss.

---

## Another Way to See It

**Sync:** Handing a document to someone face-to-face. You hand it. They take it. They read the first line. They nod. "I have it." Only then do you walk away. You know they have it. But you waited.

**Async:** Sliding the document under their door. You slide it. You walk away. "Done." Did they pick it up? You don't know. Maybe they were sleeping. Maybe it got stuck under the door. Fast. But no guarantee.

---

## Connecting to Software

**Synchronous replication:** Leader writes. Sends to follower. WAITS for follower to persist and acknowledge. "I got it." Only then does the leader respond to the client. "Write successful." If the leader crashes before the client gets a response, the write might still be on the follower. Safe. The cost? Latency. Every write waits for the slowest follower. Network round-trip. Disk write on follower. Adds milliseconds. Sometimes seconds.

**Asynchronous replication:** Leader writes locally. Responds to client immediately. "Write successful." Follower receives the data in the background. Catches up. If the leader crashes one second later, the follower might not have that write. Data lost. The benefit? Speed. No waiting. Lowest possible write latency.

**Semi-synchronous:** A middle ground. Leader waits for ONE follower to acknowledge. Not all. If you have 5 followers, one ACK is enough. Balance of safety and speed. One copy is safe. Don't wait for all five.

**The fundamental trade-off:** Consistency vs latency. Sync = safe but slow. Async = fast but risky. You cannot have both for free.

---

## Let's Walk Through the Diagram

```
SYNCHRONOUS:
Client -- Write --> Leader -- Send to Follower --> Follower
                                                      |
                                              [Follower persists]
                                              [Follower ACK]
                                                      |
Leader <---------------------------------------------+
  |
  v
Client <-- "Success" (after waiting)

Total time = Leader write + Network + Follower write + Network back
SLOW but SAFE.


ASYNCHRONOUS:
Client -- Write --> Leader [writes locally]
  |                           |
  |                           v
  |                    Leader -- Send to Follower (background)
  |
  v
Client <-- "Success" (immediately!)

Follower catches up later. FAST but RISKY if leader crashes.
```

---

## Real-World Examples (2-3)

**1. Banking** — When you transfer money, the bank uses synchronous replication. They CANNOT afford to lose your transaction. They wait. A few hundred milliseconds. Worth it. Your money is safe.

**2. Social media** — When you post a photo, async is fine. If the primary crashes and loses your post? You can repost. Annoying. Not catastrophic. Speed matters more. Millions of posts per second.

**3. Analytics and logs** — Async all the way. Losing 1-2 seconds of log data? Acceptable. Throughput is king.

---

## Let's Think Together

**Question:** A bank uses async replication. The leader crashes right after a customer deposits 10,000 rupees. The follower has not received that write yet. What happens to the deposit?

**Pause. Think.**

**Answer:** The deposit could be LOST. The customer saw "Deposit successful." The bank's leader had the money. Then the leader died. The follower becomes the new primary. It never received that transaction. The customer's balance? No deposit. The money? Gone from the old leader's memory. Never replicated. This is why banks use SYNC. They wait for the follower. They never respond "Success" until at least one copy exists. Async for money? Never.

---

## What Could Go Wrong? (Mini Disaster Story)

A payments startup. Fast growth. They use async replication. "Our writes are so fast!" Users love it. Then — one Tuesday — the primary database crashes. A disk failure. The new primary (a promoted replica) comes up. But it was 2 seconds behind. Two seconds of transactions. Payments. Refunds. Deposits. All lost. Users see "Payment successful" but their orders are not fulfilled. Money deducted. No record. Support is drowning. Legal gets involved. The root cause? Async. They wanted speed. They got data loss. For payments, sync is non-negotiable.

---

## Surprising Truth / Fun Fact

**Google Spanner** uses synchronous replication ACROSS CONTINENTS. Yes. Sync. Across oceans. How? They use atomic clocks and GPS to synchronize time globally. They minimize the "wait" by using precise timestamps. TrueTime. They proved that sync does not have to mean "slow" — with enough engineering. But it takes a Google-sized team. For the rest of us? Pick the right trade-off. Bank? Sync. Social? Async.

---

## Quick Recap (5 bullets)

- **Sync:** Leader waits for follower to confirm before responding. Safe. Slower.
- **Async:** Leader responds immediately. Follower catches up later. Fast. Risk of data loss.
- **Semi-sync:** Wait for ONE follower. Balance.
- **Trade-off:** Consistency vs latency. You choose based on your use case.
- **When sync:** Banking. Payments. Critical data. **When async:** Social. Logs. Analytics.

---

## One-Liner to Remember

> Sync: wait until you know they have it. Async: send and hope. Choose based on what you cannot afford to lose.

---

## Next Video

So you chose. Sync or async. Replicas are running. But wait — the replicas are BEHIND. A few milliseconds. Sometimes seconds. Sometimes more. And that delay? It causes weird bugs. "I just posted that! Where did it go?" "The price says 500 but I saw 1000!" Next: **Replication Lag** — why your notebook does not match the whiteboard. And what to do about it.
