# CAP: Why You Can't Have All Three

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

Two bank branches. Same account. Same customer. The network between them goes down. A tree falls on the fiber line. Or a router fails. Doesn't matter. Branch 1 and Branch 2 can't talk. Now: customer deposits Rs 10,000 at Branch 1. His wife checks the balance at Branch 2. What does she see? The correct new balance? The old balance? An error? Pick one. You can't have both "correct" and "always available" when the two branches are disconnected. That's not a limitation of banks. That's math. Let me show you why.

---

## The Story

Imagine the scenario clearly. Branch 1: customer hands over Rs 10,000. Teller updates the ledger. Balance: Rs 50,000. Branch 2: hasn't received this update. Still shows Rs 40,000. The branches can't communicate. Partition.

**Option A – Consistency:** Branch 2 says "System unavailable. We can't verify your balance. Try later or visit Branch 1." Safe. The wife doesn't get wrong information. But she's angry. "I just need to check!"

**Option B – Availability:** Branch 2 shows Rs 40,000. The old balance. Fast. She gets an answer. But it's WRONG. The account has Rs 50,000. She might make decisions based on incorrect data. Overdraw. Or complain when she finds out.

You CANNOT show the correct balance AND guarantee a response during a partition. The data is in Branch 1. Branch 2 can't reach it. To show correct, Branch 2 must either wait (unavailable) or say "I don't know" (unavailable). To be available, Branch 2 must respond with what it has—which might be wrong. No third option exists.

---

## Another Way to See It

Two friends on different islands. No boat. No phone. One friend has the "plans for Saturday" written in a notebook. The other friend doesn't have it. Someone asks the second friend: "What are we doing Saturday?" She can say "I don't know—can't reach the other island" (consistent but unhelpful). Or she can guess based on last week's plans (available but possibly wrong). She cannot know the truth without communication. The partition makes it impossible. Same with distributed data.

---

## Connecting to Software

**Without a partition:** You CAN have both Consistency and Availability. All nodes talk. Writes propagate. Reads return fresh data. Life is good. Most of the time, systems run here.

**With a partition:** You must choose. CP: Refuse to serve when you can't guarantee correctness. Better to error than lie. AP: Always respond. Use whatever data you have. Might be stale. Both sides might even have conflicting writes. When the partition heals, you resolve. But during the partition: correct or available. Not both.

Partitions are INEVITABLE. Servers crash. Networks fail. Data centers disconnect. So you MUST design for the choice. Not hope it never happens.

---

## Let's Walk Through the Diagram

```
    WHY NOT ALL THREE?

    NORMAL OPERATION (no partition):
    ┌──────────┐  ◄──────►  ┌──────────┐
    │ Branch 1 │   network  │ Branch 2 │
    │ Balance: │   working  │ Balance: │
    │ 50,000   │            │ 50,000   │
    └──────────┘            └──────────┘
    C + A: Both possible. Sync works.

    PARTITION (network down):
    ┌──────────┐    X     ┌──────────┐
    │ Branch 1 │  (can't  │ Branch 2 │
    │ Deposit  │   talk)  │ Old data │
    │ 50,000   │          │ 40,000   │
    └──────────┘          └──────────┘

    Wife at Branch 2 asks: "Balance?"
    CP: "Unavailable." (correct - we don't know)
    AP: "40,000." (wrong - but we answered)

    Cannot have: Correct AND Available. Impossible.
```

The diagram shows the fork: partition happens, you're on one path or the other. No middle road. The network is the bottleneck. When it's gone, information can't flow. So consistency and availability can't coexist in that moment.

---

## Real-World Examples (2-3)

**Example 1: ZooKeeper (CP).** Used for configuration, leader election. During partition, if a node can't reach the majority, it stops serving. Better to have no leader than two leaders. Unavailable but correct.

**Example 2: Cassandra (AP).** Each node serves reads and writes locally. Partition? No problem. Keep going. Writes might conflict when partition heals. But you're always available. Resolution later.

**Example 3: Spanner (CP with tricks).** Google's Spanner uses atomic clocks to reduce coordination. But when true partition happens, it still chooses consistency over availability for critical operations. CP at the core.

---

## Let's Think Together

During a partition: **Banking system—CP or AP?**

CP. You cannot show a wrong balance. People make financial decisions. Wrong data = wrong decisions = lawsuits. Unavailable is annoying. Wrong is dangerous.

**Social media timeline—CP or AP?**

AP. Showing a tweet from 5 minutes ago instead of 2 minutes ago? User scrolls. No one dies. Better to always show something than to show "error, try again." Feeds can tolerate staleness. Banks cannot.

The choice is use-case driven. Always ask: what's worse? Stale data or no data?

---

## What Could Go Wrong? (Mini Disaster Story)

A healthcare app stored patient allergies in a distributed database. AP mode. Network partition. Nurse at one clinic adds "penicillin allergy" to a patient record. The update stays local. Doctor at another clinic (different partition) pulls the record. No allergy listed. Prescribes penicillin. Patient has a reaction. Hospital investigates. Root cause: AP during partition. Stale read. The lesson: some data must be CP. Medical records. Financial transactions. Safety-critical systems. "Available" is not enough when "wrong" can kill.

---

## Surprising Truth / Fun Fact

The CAP theorem was famously "proof" by Seth Gilbert and Nancy Lynch in 2002. They formalized Brewer's conjecture. The proof is subtle: in an asynchronous system with a partition, you cannot implement a register that is both linearizable (consistent) and always available. It's not engineering. It's computer science. Proven impossible. So when someone says "we have all three," they've relaxed one of the definitions. Partition-tolerant, available, AND strongly consistent during partition? Not in this universe.

---

## Quick Recap (5 bullets)

- **Without partition:** C + A both possible. Nodes sync. All good.
- **With partition:** Must choose. CP = correct but sometimes unavailable. AP = available but sometimes stale.
- **Partitions are inevitable.** Design for them. Don't hope they don't happen.
- Use case decides: banking = CP. Social feeds = AP. Medical records = CP.
- You cannot have correct data AND always respond when nodes can't communicate. Proven.

---

## One-Liner to Remember

**Why not all three? Because when the network splits, the data can't cross. Correct or available. Pick one. Math doesn't allow both.**

---

## Next Video

Next: **CP vs AP in practice.** Two doctors. One always correct but sometimes says "come back tomorrow." One always sees you now but sometimes wrong. Which for a life-threatening condition? Which for a minor symptom? See you there.
