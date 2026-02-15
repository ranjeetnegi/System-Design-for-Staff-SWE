# Consistency Models: Linearizability, Causal, and More

## Video Length: ~4-5 minutes | Level: Staff

---

## The Hook (20-30 seconds)

A whiteboard in a meeting room. Ten people. Someone writes "Meeting at 3 PM." Every person in that room sees it. Instantly. Same moment. No delay. No "I'll check the other board." That's linearizability—the strongest consistency model. Now: a group chat. You send "What's for lunch?" Your friend replies "Pizza." The reply must come AFTER the question. Causality. But another friend's message about the weather? Could appear before or after. Unrelated. Causal consistency preserves cause and effect. Not total order. Different models. Different guarantees. Let me walk you through them.

---

## The Story

**Linearizability** is the gold standard. Every read returns the value from the most recent write. As if there's ONE copy. One source of truth. Real-time. If Alice writes X=5 at 10:00:01 and Bob reads at 10:00:02, Bob sees 5. No stale read. Expensive. Requires coordination. Locks. Consensus. Use for: register values, locks, leader identity. Implementing linearizability means every operation has a global order. As if a single thread executed them. That global order is costly to maintain across replicas. But for critical data, it's worth it.

**Sequential consistency** is slightly weaker. All nodes see operations in the SAME order. But not necessarily real-time. The order could be different from wall-clock time. Easier to implement. Still strong.

**Causal consistency** preserves cause and effect. If operation A causes operation B (e.g., reply follows message), everyone sees A before B. Unrelated events can appear in any order. More relaxed. More performant. Good for: chat, collaborative editing, social graphs.

**Eventual consistency** is the weakest. Replicas converge eventually. No ordering guarantees. No "I'll see your write before mine" promise. Fast. Scales. Use when approximate is fine: likes, views, recommendations. The spectrum from linearizable to eventual is a sliding scale of guarantees vs performance. Each step down the scale buys you latency and throughput. Each step up costs you coordination. The art is choosing the weakest model that still satisfies your correctness requirements. Don't pay for linearizability when causal is enough. Don't use eventual when causal is required.

---

## Another Way to See It

**Linearizability:** Live TV broadcast. Everyone watches the same frame at the same moment. Synchronized. **Causal:** Email thread. Reply appears under the original. Order preserved for related messages. **Eventual:** Graffiti on a wall. Someone adds. Someone else adds. Eventually everyone sees both. Order doesn't matter.

---

## Connecting to Software

**Linearizability:** Bank balance. Distributed lock. "Who has the lock?" Configuration that must be globally agreed. Implement with: consensus (Paxos, Raft), single leader with synchronous replication. Cost: latency, throughput limits.

**Sequential:** Some distributed caches. Weaker than linearizable but simpler. Rarely explicitly chosen; usually a step toward eventual.

**Causal:** Chat apps (WhatsApp, Slack). Collaborative docs (Google Docs). Social feeds. "Show me replies after the post." Need cause-effect. Don't need total order. Implement with: vector clocks, version vectors. More scalable than linearizable.

**Eventual:** Counters (likes, views). Recommendation scores. Non-critical metadata. Implement with: conflict resolution, CRDTs, last-write-wins. Cheapest. Fastest.

---

## Let's Walk Through the Diagram

```
    CONSISTENCY MODELS (STRONG → WEAK)

    Linearizability:     Read always sees latest write. Real-time.
    ┌────┐  write X=5   ┌────┐  read     ┌────┐
    │ A  │ ───────────► │Sys │ ────────► │ B  │  sees 5. Always.
    └────┘              └────┘           └────┘

    Causal:             If A causes B, everyone sees A before B.
    ┌────┐  "Question"  ┌────┐  "Reply"   ┌────┐
    │ A  │ ───────────► │Chat│ ─────────► │ B  │  Reply after Question.
    └────┘              └────┘            └────┘  Unrelated msgs: any order.

    Eventual:           Replicas converge. No ordering guarantee.
    ┌────┐  like        ┌────┐   sync     ┌────┐
    │ A  │ ───────────► │Node│ ◄────────► │Node│  999 → 1000... eventually.
    └────┘              └────┘            └────┘
```

Strong to weak: linearizable gives the most. Eventual gives the least. You pay for strength in latency and complexity. Choose the weakest model that satisfies your requirements. Over-engineering with linearizability when causal works? You're burning money and adding latency. Under-engineering with eventual when causal is needed? You'll have bugs. Match the model to the need.

---

## Real-World Examples (2-3)

**Example 1: Bank transfer.** Linearizable. The moment you see "transfer complete," every node agrees. Balance is consistent. No "eventually." Strongest model. Necessary.

**Example 2: WhatsApp message order.** Causal. Your reply appears under the message you're replying to. Always. But messages from different chats? Order doesn't matter. Causal is enough. Saves coordination cost.

**Example 3: Instagram like count.** Eventual. 999,998 vs 1,000,000. Doesn't matter. No ordering. No cause-effect between like events. Weakest model. Maximum scale. Instagram serves billions of likes per day. Strong consistency would require global coordination on every like. Impossible. Eventual lets each region count independently. Sync in the background. The number is "about right." Good enough for a vanity metric. Design is about knowing when "about right" is right enough.

---

## Let's Think Together

Which consistency model for each? **Bank transfers?** Linearizable. Money must be exact. No ambiguity. **Chat messages?** Causal. Replies after originals. Unrelated chats can be flexible. **Social media likes?** Eventual. Count is approximate. Order of likes is irrelevant. The pattern: correctness-critical = linearizable. Order matters for relations = causal. Scale and approximate = eventual. Match the model to the need. Don't over-engineer. Don't under-engineer.

---

## What Could Go Wrong? (Mini Disaster Story)

A team built a chat app. "We'll use eventual consistency. Scale!" Messages appeared out of order. User A: "Let's meet at 3." User B: "Sure." User A: "Actually, make it 4." User B saw: "Sure" then "Let's meet at 3" then "Actually, make it 4." Confusing. Nonsensical. They needed causal consistency. Replies and edits must follow their parents. Eventual wasn't enough. They added vector clocks. Fixed. Lesson: understand your ordering requirements. "Eventually" isn't always "good enough."

---

## Surprising Truth / Fun Fact

Linearizability has another name: **atomic consistency**. And it's equivalent to "one-copy serializability" for single-object operations. The academic literature uses these terms interchangeably. When you see "strong consistency" in a database's marketing, ask: linearizable? Or something weaker? Many "strong" offerings are actually sequential or "read-your-writes." True linearizability is rare and expensive. Know what you're getting.

---

## Quick Recap (5 bullets)

- **Linearizability:** Strongest. Every read sees latest write. Real-time. Expensive.
- **Sequential:** Same order everywhere. Weaker than linearizable. Simpler.
- **Causal:** Cause-effect preserved. Reply after message. Good for chat, collaborative editing.
- **Eventual:** Weakest. Converge over time. No ordering. Fast. Scale.
- Choose the weakest model that meets your correctness needs. Don't overpay.

---

## One-Liner to Remember

**Linearizability: One whiteboard, everyone sees it now. Causal: Reply under the message. Eventual: We'll agree sometime. Pick the right one.**

---

## Next Video

Next: **Network partition.** What happens when the link fails? Two houses. One road. A tree falls. They can't talk. In distributed systems, that's not rare. It's inevitable. See you there.
