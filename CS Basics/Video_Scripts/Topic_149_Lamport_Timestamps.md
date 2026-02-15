# Logical Clocks: Lamport Timestamps

## Video Length: ~4-5 minutes | Level: Staff

---

## The Hook (20-30 seconds)

No clocks? No problem. Forget wall-clock time. Use a counter. Event happens? Increment. Send a message? Attach your counter. Receive a message? Take the max of yours and theirs. Add one. Now: if event A caused event B, A's timestamp is always less than B's. You don't need clocks. You need ordering. Causality. That's Lamport timestamps. Logical time. No hardware. No sync. Just rules. Let me show you how it works.

---

## The Story

**Lamport timestamps** solve the ordering problem without physical clocks. Each node has a counter. Initially zero. **Rule 1:** Before each local event, increment the counter. **Rule 2:** When sending a message, attach your current counter. **Rule 3:** When receiving a message, set counter = max(your counter, received counter) + 1. That's it. Three rules. Every event gets a timestamp. Ordering is preserved.

**What it guarantees:** If A happened-before B (causally), then timestamp(A) < timestamp(B). Causality is preserved. We can order dependent events. **What it doesn't guarantee:** If timestamp(A) < timestamp(B), we cannot say A happened before B. They might be concurrent. Unrelated. Lamport timestamps order causal events. They don't detect concurrency. For that, we need vector clocks. Later.

**Why it works:** Sending a message creates causality. Receiver's event happens after sender's. The max + 1 rule ensures receiver's timestamp is greater. Local events increment. So any causal chain has monotonically increasing timestamps. Simple. Elegant.

**Happened-before:** Lamport defined "happened-before" as a partial order. Event A happened before B if: (1) A and B are on the same process and A occurred first, or (2) A is the send of a message and B is the receive of that message, or (3) there exists event C such that A happened before C and C happened before B. Transitive. Lamport timestamps respect this. If A happened before B, then L(A) < L(B). The reverse is not true. L(A) < L(B) does not imply A happened before B.

---

## Another Way to See It

Think of ticket numbers at a deli. You take a number. 42. Someone else takes 43. The order is clear. You don't need to know "what time" each person arrived. Just the order. Lamport timestamps are like that. Sequence numbers. Ordering. Not time. The counter is the "ticket." Events get numbers. Order preserved. No clock required.

---

## Connecting to Software

**Implementation:** Each process has a variable L. On local event: L = L + 1. On send: attach L to message; L = L + 1. On receive: L = max(L, message_timestamp) + 1. Simple. No distributed sync. Each node does local math. Messages carry the "time."

**Use cases:** Distributed debugging. "Event A (ts=5) before Event B (ts=8)." Log ordering. Distributed systems. Anywhere you need causal order without trusting physical clocks. Database systems. Message queues. Replication. Foundational.

**Limitation:** Timestamp order doesn't mean causal order. (A=3, B=5) could mean A caused B. Or they're concurrent. You can't tell. For "did these happen concurrently?" you need vector clocks.

**Total order:** Lamport gives partial order (causal). To get total order—unique ordering of all events—tie-break with process ID. (timestamp, process_id). Now every event has unique (L, pid). Sort by L first, then pid. Total order. Useful for distributed locking. "Lower (L, pid) wins." Ensures fairness. No starvation.

---

## Let's Walk Through the Diagram

```
    LAMPORT TIMESTAMPS

    Node A                    Node B
    L=0                       L=0
    
    Event (L=1)               
    Send msg(1) ──────────►   Recv: L=max(0,1)+1=2
    L=2                           
                              Event (L=3)
                              Send msg(3) ──► 
    
    If A happened before B (causally),
    then ts(A) < ts(B). Guaranteed.
    
    If ts(A) < ts(B), A might or might not have
    caused B. Could be concurrent. Can't tell.
```

The diagram shows: messages carry timestamps. Receive: max + 1. Causal order preserved. Concurrency not detected.

---

## Real-World Examples (2-3)

**Example 1: Distributed tracing.** Spans have timestamps. Often logical. Or hybrid. Order events across services. "Request hit A, then B, then C." Lamport-style ordering. Debugging distributed systems.

**Example 2: Distributed databases.** Version vectors. Logical clocks. Order updates. Detect conflicts. Foundation for consistency. Many systems use Lamport or extensions.

**Example 3: Message queues.** Ordering guarantees. "Process in order." Lamport timestamps can enforce causal order. Simpler than physical time. No clock sync.

---

## Let's Think Together

Node A has counter=5. Sends message to Node B with counter=3. Node B receives. What's B's new counter?

B's new counter = max(B's current, 3) + 1. We don't know B's current. If B had 0: max(0,3)+1 = 4. If B had 6: max(6,3)+1 = 7. The key: B takes the maximum. So B's counter is always >= 4 (since 3 was received). And strictly greater than both. The +1 ensures B's event is after the receive. Always. The rule is clear. The result depends on B's prior state. But the invariant holds: causality preserved.

---

## What Could Go Wrong? (Mini Disaster Story)

A system used Lamport timestamps for distributed locking. "Lower timestamp wins." Bug: when two nodes had the same timestamp (different nodes, same value—possible for concurrent events), the tiebreaker was node ID. Fine. But they forgot: Lamport timestamps can have gaps. Node A: 1, 2, 5 (skipped 3, 4 due to receives). Node B: 1, 2, 3. Comparing 5 and 3: 3 "wins" by being smaller. But 3 might be concurrent with 5. Wrong order. They switched to vector clocks for conflict detection. Lesson: Lamport gives causal order. Same timestamp or unrelated timestamps don't imply order. Use carefully. Know the guarantees.

---

## Surprising Truth / Fun Fact

Leslie Lamport published this in 1978. The same Lamport who invented Paxos. And LaTeX. And won the Turing Award. One of the most influential computer scientists ever. Lamport timestamps. Simple idea. Three rules. Solved the "order without clocks" problem. Still used today. Almost 50 years later. Good ideas last.

---

## Quick Recap (5 bullets)

- **Lamport timestamps:** Counter per node. Local event: +1. Send: attach. Receive: max + 1.
- **Guarantee:** If A caused B, ts(A) < ts(B). Causal ordering.
- **No guarantee:** ts(A) < ts(B) does NOT mean A caused B. Could be concurrent.
- **No clocks needed.** No sync. Pure logic. Messages carry the "time."
- **Lamport:** Same person as Paxos, LaTeX. Turing Award. 1978. Still relevant.

---

## One-Liner to Remember

**Lamport timestamps: No clocks. Just a counter. Increment. Max on receive. Causal order preserved. Concurrency not detected.**

---

## Next Video

Next: **Vector Clocks.** Lamport says order. Vector says "concurrent." Each node tracks every node's counter. Compare two vectors: before, after, or concurrent? Conflict detection. Dynamo. The next level. See you there.
