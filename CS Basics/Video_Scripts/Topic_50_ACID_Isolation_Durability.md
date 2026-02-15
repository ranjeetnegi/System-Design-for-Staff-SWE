# ACID: Isolation and Durability

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

Two chefs. One kitchen. Chef A is making a cake. Chef B is making soup. Chef B reaches for the salt. Chef A already has it. They bump. Cake hits the floor. Soup splatters everywhere. Chaos. Now imagine the same kitchen — but each chef has their own station. Own tools. Own space. They don't interfere. That's isolation. And when Chef A finishes? The cake goes in a fireproof cabinet. Building burns down. Cake survives. That's durability. Let's go deeper.

---

## The Story — Isolation

Two chefs in one kitchen. Both working. Chef A: cake. Chef B: soup. They share counters. Share ingredients. Chef B needs salt. Reaches. Chef A's elbow. Crash. The cake — three hours of work — is on the floor. The soup pours into the cake batter. Neither dish is salvageable. That's what happens when transactions interfere.

**Isolation says: each transaction works as if it's the ONLY one running.** Each chef gets their own space. Their own view of the database. They don't see each other's half-finished work. Transaction A updates a row. Transaction B can't see that update until A commits. No bumping. No interference. Each transaction runs in isolation — like exam students in separate booths. Can't see each other's answers.

Here's the crazy part. Databases offer different isolation levels. Trade-offs between safety and speed.

**Read Uncommitted:** You can see another transaction's unfinished work. Dirty reads. Transaction A changes a value. Transaction B reads it. Then A rolls back. B read data that never existed. Dangerous.

**Read Committed:** You only see committed data. Safer. No dirty reads. But you might see different values if you read the same row twice — another transaction committed in between.

**Repeatable Read:** You see the same data throughout your transaction. Consistent snapshot. Even if others commit changes, your view doesn't change.

**Serializable:** The safest. As if transactions run one at a time. No interference at all. Also the slowest. Most databases default to Read Committed — a balance.

---

## The Story — Durability

You finish your exam. Three hours of writing. You submit the answer sheet. Walk out. Feel the relief. Then — the building catches fire. Your heart stops. Your answers! But the teacher already locked them in a fireproof cabinet. Safe. Your work survives.

**Durability means: once you COMMIT, the data survives anything.** Power outage. Server crash. Disk failure (if you have backups). The database writes to permanent storage. Not just memory. Disk. Often a Write-Ahead Log — WAL — that records every change before applying it. If the system crashes, it replays the log. Your committed data comes back.

Carving in stone vs writing on sand. Commit = carve in stone. Permanent. Durability is the promise: your money transfer, your order, your reservation — once confirmed, it stays confirmed.

---

## Another Way to See It

**Isolation:** Exam hall. Each student in a booth. Own desk. Own paper. Can't see others. Can't copy. Independent. That's how transactions see the database — as if they're alone.

**Durability:** Carving in stone. You write "I owe you 100 rupees" on paper — wind blows it away. You carve it in stone — centuries later, still there. Commit = carve. Permanent.

---

## Connecting to Software

Isolation levels control how transactions see each other. Most apps use Read Committed. Financial apps might need Serializable. The trade-off: stricter isolation = more locking = slower. Choose based on your needs.

Durability: data goes to disk. WAL (Write-Ahead Logging) — write the change to a log BEFORE updating the actual data. Crash? Replay the log. Replicated systems write to multiple machines. One dies? Others have the data. Durability = survive the crash.

---

## Let's Walk Through the Diagram

```
ISOLATION:                          DURABILITY:

Transaction A          Transaction B    Commit
    |                        |              |
    |--- Update row 1        |              |--- Write to WAL (log)
    |    (uncommitted)       |              |--- Write to disk
    |                        |              |--- CRASH
    |                        |--- Read?     |
    |    (B can't see A's     |   (B sees   |--- Reboot
    |     uncommitted data    |    old value)|--- Replay WAL
    |     with Read           |              |--- Data RESTORED ✓
    |     Committed)          |              |
    |--- COMMIT               |              |
    |                        |--- Read again|
    |                        |   (Now sees  |
    |                        |    A's value)|
```

Isolation: B doesn't see A until A commits. Durability: committed data survives the crash.

---

## Real-World Examples (2-3)

**1. Banking:** Two people transfer money from the same account. Isolation ensures they don't see each other's pending transfers. Durability ensures once the transfer confirms, it's permanent. Power failure? Transfer still there.

**2. E-commerce:** User A and B view "last item in stock." Isolation: proper locking. One gets it. One gets "sold out." No double-sell. Durability: order committed? Written to disk. Server crashes before sending confirmation email? Order still exists. Email retries later.

**3. Booking system:** User books a hotel. Commit. Durability: that reservation survives. Database crashes. Restarts. Reservation is still there. Hotel can't double-book.

---

## Let's Think Together

Two users update the same row at the same time. User A sets price to 100. User B sets it to 200. What's the final value?

*Pause. Think about it.*

It depends on isolation and timing. Last write wins? Could be 100 or 200 — whichever commits last. With proper isolation and locking, one transaction waits. Serial order. First to update wins. Second might overwrite — or get a "conflict" error. The database ensures no corrupt state. One value. Consistent. The exact behavior depends on your isolation level and application logic.

---

## What Could Go Wrong? (Mini Disaster Story)

Low isolation. Read Uncommitted. A finance app. Transaction A updates a stock price. Transaction B reads it — before A commits. B makes a trade based on that price. Then A rolls back. The price never existed. B traded on a phantom value. Wrong trade. Lost money. Lawsuits. Dirty reads destroy trust. One transaction's unfinished work poisoned another's decision. Isolation exists to prevent exactly this. Use it.

---

## Surprising Truth / Fun Fact

Most databases default to "Read Committed" isolation. A balance. Safe enough for most apps. Fast enough. Very few applications actually use "Serializable" — the strictest level. Why? Too slow. Too much locking. Transactions wait on each other. Throughput drops. Most apps accept a little risk for a lot of speed. Know your default. Know when to change it.

---

## Quick Recap (5 bullets)

- **Isolation:** Each transaction runs as if alone. No interference. Different levels: Read Uncommitted, Read Committed, Repeatable Read, Serializable
- **Durability:** Once committed, data survives crashes. Written to disk. WAL. Replication
- **Read Committed** is the common default — balance of safety and speed
- **Serializable** is safest but slowest — few apps use it
- Isolation prevents dirty reads. Durability prevents data loss after commit.

---

## One-Liner to Remember

> Isolation: each chef has their own kitchen. Durability: the cake survives the fire. No interference. No loss.

---

## Next Video

You now understand ACID. Your database is reliable. But here's the question: what happens when ONE database isn't enough? When your single notebook fills up? When queries slow down? When the machine can't keep up? That's when you need to think bigger. That's next.
