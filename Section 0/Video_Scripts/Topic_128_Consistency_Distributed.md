# What Is Consistency in Distributed Systems?

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

Three notice boards. One in each building of a school. The principal walks to Building 1, pins up a notice: "Holiday on Friday." She walks away, satisfied. Students in Building 2 and 3 never see it. Their boards still say "No holiday." Friday comes. Half the school shows up. Angry. Confused. "The principal said holiday!" The boards told different stories. That moment—that mismatch—is exactly what we mean when we say **inconsistency**. And in distributed systems, it's one of the hardest problems in all of computer science.

---

## The Story

The school has three buildings. Three notice boards. Same school. Different copies of the same information. The principal posts "Holiday on Friday" on board 1. She's busy. She doesn't walk to Building 2 and 3 to update those boards. Maybe she will later. Maybe someone else will. But right now: Board 1 says holiday. Board 2 and 3 say no holiday.

Students in Building 2 read their board. They come to school. Students in Building 1 read their board. They stay home. Same school. Same decision. Different outcomes. Because the data—the notices—were inconsistent.

**Consistency** in distributed systems means: ALL copies of data show the SAME thing at the SAME time. When you write something, everyone who reads it should get the same value. No surprises. No "I thought I updated that." In software, we have multiple servers holding copies of data. Keeping them consistent—that's the challenge. The moment you have more than one copy, you have the problem: how do you keep them in sync?

---

## Another Way to See It

Imagine a library with three branches. Someone returns a book at Branch A. The librarian marks it "available." But Branch B and C still show it as "checked out." A student goes to Branch B, asks for the book. "Sorry, it's out." The student leaves. The book is literally sitting on a shelf at Branch A. Same book. Different truth. That's inconsistency. Consistency would mean: the moment the book is returned at any branch, ALL branches know. Instantly. Or eventually. But they must agree.

---

## Connecting to Software

In distributed systems, data lives on multiple machines. Why? Scale. Availability. Geographic spread. User in Mumbai hits Server A. User in Delhi hits Server B. Both servers have a copy of the same user profile. User updates their name on Server A. Server B still has the old name. User switches to a different server—reads their profile. They see the OLD name. "I just changed it!" Frustration.

Consistency is the guarantee we want: after a write, all reads return the new value. Simple to say. Hard to achieve. Because servers must coordinate. Communicate. Agree. And networks fail. Machines crash. Messages get delayed. Keeping multiple copies in sync, in real time, is one of the fundamental challenges of distributed computing.

---

## Let's Walk Through the Diagram

```
    CONSISTENCY: ALL COPIES AGREE

    WITHOUT CONSISTENCY:
    ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
    │  Server A   │     │  Server B   │     │  Server C   │
    │  "Holiday"  │     │ "No Holiday"│     │ "No Holiday"│
    └─────────────┘     └─────────────┘     └─────────────┘
           │                    │                    │
           └────────────────────┴────────────────────┘
                    Different copies. Confusion.

    WITH CONSISTENCY:
    ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
    │  Server A   │     │  Server B   │     │  Server C   │
    │  "Holiday"  │◄───►│  "Holiday"  │◄───►│  "Holiday"  │
    └─────────────┘     └─────────────┘     └─────────────┘
           Same value everywhere. Predictable.
```

The diagram shows the problem: three servers, three copies. Without consistency—each can show something different. With consistency—they coordinate. They agree. When one updates, the others follow. That coordination is costly. But it's what we mean by consistency.

---

## Real-World Examples (2-3)

**Example 1: Bank balance.** You withdraw Rs 5,000 at an ATM. The system MUST update all copies of your balance. If one server still shows the old balance, you could withdraw again. Double-spend. Banks need strong consistency. No compromises.

**Example 2: Social media like count.** You like a post. The count goes from 999 to 1,000. Does every user need to see exactly 1,000 at the same instant? Or is 998, 999, 1,001 fine for a few seconds? Most social apps use eventual consistency. Fast. Good enough. Not bank-level strict.

**Example 3: DNS.** When you register a new domain, it takes time to propagate. Hours. Sometimes days. Different DNS servers show different results. That's inconsistency by design. Eventually, they converge. Classic eventual consistency.

---

## Let's Think Together

User updates their profile on Server A. Name change. "Rahul" to "Rahul Kumar." Server A writes it. Done. One second later, the user switches networks. Their request hits Server B. Server B hasn't received the update yet. Replication is still in progress.

What does the user see?

The OLD name. "Rahul." The user just changed it. They'll think it didn't save. Confusion. Anger. This is the read-your-writes problem. After YOU write, you expect to read your own update. But in a distributed system with replication lag, you might hit a different server. You might get stale data. How do we fix it? Sticky sessions? Read from leader? Wait for propagation? Trade-offs. Always.

---

## What Could Go Wrong? (Mini Disaster Story)

An e-commerce site runs on three servers. Inventory: 1 laptop left. User A (Server 1) adds to cart. User B (Server 2) adds to cart. Both see "1 in stock." Neither server has synced with the other. Both check out. Two orders. One laptop. Oversold. Customer B gets an email: "Sorry, we're out of stock." After they paid. Refunds. Complaints. Lost trust.

The system was inconsistent. Both servers thought they had the last item. Inventory requires consistency. Without it: chaos.

---

## Surprising Truth / Fun Fact

The CAP theorem—which we'll cover soon—says you can't have Consistency, Availability, AND Partition tolerance all at once. Eric Brewer proposed it in 2000. For decades, engineers have debated its exact meaning. But the core insight stands: in a distributed system, when things go wrong, you make hard choices. Consistency is often the thing we sacrifice for speed and availability. Not always. But often.

---

## Quick Recap (5 bullets)

- **Consistency** = all copies of data show the SAME value at the SAME time.
- Distributed systems have multiple servers with copies—keeping them in sync is hard.
- Without consistency: users see stale data, double-spends, overselling, confusion.
- Different use cases need different levels: banks want strong; social media often uses eventual.
- Replication lag causes "read your own write" failures—you write, then read stale from another server.

---

## One-Liner to Remember

**Consistency: When you have three notice boards, they all must tell the same story. Or students show up on a holiday.**

---

## Next Video

Next: **Strong consistency vs eventual consistency.** The post office stamp vs the mailbox. One gives instant certainty. The other gives hope. Which do you need? See you there.
