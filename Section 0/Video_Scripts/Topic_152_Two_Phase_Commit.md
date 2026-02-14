# Two-Phase Commit (2PC): How It Works

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

"Can everyone come to Pizza Palace Saturday?" The organizer asks. One by one, people check their schedules. Yes. Yes. Yes. All clear. "Let's go!" Everyone commits. But what if someone says no? "Cancelled." No one goes. Two phases. Ask first. Then decide. That's not just dinner planning. That's two-phase commit.

---

## The Story

Picture a group dinner. Six friends. One organizer. Everyone must agree on the restaurant. Phase one: **PREPARE.** The organizer asks each person: "Can you come to Pizza Palace on Saturday?" Each person checks their schedule. "Yes, I can." Or "No, I can't." That's the vote. Phase two: **COMMIT.** If everyone said yes, the organizer announces: "We're going! See you there." If anyone said no, the organizer says: "Cancelled. We'll pick another day." Everyone follows the organizer's final call. No one acts until the decision is made. Two phases. Prepare, then commit. That's 2PC.

---

## Another Way to See It

Think of it like a treaty signing. Each country's representative must agree. Phase one: everyone reads the treaty and signals "I'm ready to sign" or "I have concerns." Phase two: if all are ready, everyone signs at once. If anyone has concerns, no one signs. No partial treaties. All or nothing. The coordinator—the one organizing the signing—makes the final call. Everyone waits for that call.

---

## Connecting to Software

In 2PC, we have a **coordinator** (transaction manager) and **participants** (databases or services). The coordinator runs the show.

**Phase 1 — PREPARE:** The coordinator sends a PREPARE message to every participant. Each participant locks the resources it needs. Does the work—reserves the row, allocates the value—but doesn't commit. It votes: YES (I'm ready) or NO (I can't do this). The vote is sent back to the coordinator. Why "prepare" first? Because once you commit, you can't take it back. Prepare lets everyone signal readiness without committing. A safety check. "Can we all do this?" If yes, we proceed. If no, we abort. No one has committed yet. Clean.

**Phase 2 — COMMIT or ABORT:** If EVERY participant voted YES, the coordinator sends COMMIT. Everyone commits. If ANY participant voted NO, the coordinator sends ABORT. Everyone rolls back. Releases locks. Done. Clean. All or nothing.

The key: no participant commits on its own. Everyone waits for the coordinator. The coordinator decides. Single point of control. This is both the strength and the weakness of 2PC. One coordinator. One decision. But if that coordinator fails, everyone is stuck. We'll dig into that pain in the next video. For now, understand: two phases. Prepare. Vote. Then commit or abort. No one moves until the coordinator says so.

---

## Let's Walk Through the Diagram

```
    TWO-PHASE COMMIT

    COORDINATOR                    PARTICIPANTS
         |                              |
         |-------- PREPARE ------------>| A: lock, vote
         |-------- PREPARE ------------>| B: lock, vote
         |-------- PREPARE ------------>| C: lock, vote
         |                              |
         |<------- YES -----------------| A
         |<------- YES -----------------| B
         |<------- YES -----------------| C
         |                              |
         |  All YES? → COMMIT           |
         |-------- COMMIT ------------->| A: commit
         |-------- COMMIT ------------->| B: commit
         |-------- COMMIT ------------->| C: commit
         |                              |
```

If any participant votes NO, coordinator sends ABORT. Everyone rolls back. The diagram shows: prepare, vote, then commit. Two rounds. One decision. The protocol is simple. Elegant. It works when everyone is healthy. The problem is the real world. Coordinators crash. Networks partition. Participants hold locks forever. That's when 2PC shows its dark side. We'll see it next.

---

## Real-World Examples (2-3)

**Example 1: XA transactions.** Java's XA interface. Database vendors support it. MySQL, PostgreSQL, Oracle. You start a global transaction. Enlist multiple resources. 2PC under the hood. COMMIT triggers prepare on all, then commit. Industry standard for decades.

**Example 2: Distributed databases.** CockroachDB. YugabyteDB. They use 2PC internally to coordinate writes across nodes. You write once. The system handles the protocol. You get ACID. They pay the complexity.

**Example 3: Payment + inventory.** Reserve stock in DB1. Reserve funds in DB2. Both must succeed. 2PC: prepare on both. Both vote yes. Coordinator commits both. One failure? Abort both. Clean. This works when both resources are in the same administrative domain. Same team. Same deployment. When they're in different microservices, owned by different teams, 2PC gets harder. Coordination. Versioning. "Does your service support 2PC?" Not everyone does. The pattern is powerful. The operational reality is complex. Know both.

---

## Let's Think Together

**Coordinator sends PREPARE. Participant A votes YES. Participant B votes YES. Coordinator crashes before sending COMMIT. What happens?**

Participants are stuck. They voted YES. They're holding locks. They're waiting for COMMIT or ABORT. The coordinator is dead. They can't commit—they need the coordinator's decision. They can't abort—same problem. They're blocked. Indefinitely. This is the famous "blocking" problem of 2PC. We'll dig into it next.

---

## What Could Go Wrong? (Mini Disaster Story)

A bank used 2PC for transfers across two legacy systems. One day: coordinator process died. Mid-transaction. After prepare. Ten million dollars. Locks held. Both participants waiting. Nobody could commit. Nobody could abort. Manual intervention. Database admins had to decide. Hours of downtime. The lesson: 2PC works when the coordinator works. When it doesn't, you're blocked. Plan for coordinator failure.

---

## Surprising Truth / Fun Fact

2PC was formalized in 1979. Jim Gray's paper. The same Jim Gray who did foundational work on databases and won a Turing Award. 2PC is old. It's proven. It's also painful. Most modern systems avoid it for cross-service transactions. But inside a single distributed database? Still widely used.

---

## Quick Recap (5 bullets)

- **2PC** = two phases: PREPARE (vote) and COMMIT/ABORT (decide).
- **Coordinator** sends PREPARE; participants lock and vote YES/NO.
- **All YES** → COMMIT. Any NO → ABORT. Coordinator decides.
- **Blocking problem:** If coordinator dies after prepare, participants wait. Forever.
- **Use:** XA transactions, some distributed DBs. Not ideal for microservices.

---

## One-Liner to Remember

**2PC: Ask everyone first. All say yes? Commit. Anyone says no? Abort. The coordinator decides. Everyone waits.**

---

## Next Video

But what happens when the coordinator dies? When participants hold locks and wait forever? 2PC has a dark side. Why it's painful in practice. That's next. See you there.
