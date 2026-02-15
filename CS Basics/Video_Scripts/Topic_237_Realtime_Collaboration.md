# Real-Time Collaboration: CRDTs and Ordering

## Video Length: ~4-5 minutes | Level: Staff

---

## The Hook (20-30 seconds)

Google Docs. Two people typing in the same document simultaneously. Person A types "Hello" at position 5. Person B deletes position 3. Both changes happen at the "same time" on different devices. How do you merge them without conflicts? Without one overwriting the other? This is one of the hardest problems in distributed systems. And we've solved it. Two main approaches. Let's see.

---

## The Story

Concurrent edits. No central coordinator. Each client has its own view. They must converge to the SAME final document. If A inserts "X" at position 5 and B deletes position 3, what's the result? Depends on order. If A's insert happens first, B's delete might remove something different. If B's delete happens first, positions shift. A's "position 5" is now wrong. The challenge: no global clock. No single source of truth at write time. Each client operates independently. Merge must be deterministic. Everyone must end up with the same document. No conflicts. No data loss. This is the collaborative editing problem.

Two main solutions: Operational Transformation (OT) and CRDTs. OT: transform operations against each other. Complex. Google Docs uses it. CRDTs: Conflict-Free Replicated Data Types. Data structures that automatically merge. Mathematically guaranteed to converge. Figma uses it. Both work. Different trade-offs. Staff engineers choose based on product needs.

---

## Another Way to See It

Two chefs editing the same recipe. Chef A adds "cumin" at step 3. Chef B removes step 2. Do they conflict? If we track "steps" by number, yes. Step 3 moved. "Cumin" might land in the wrong place. If we use unique IDs for each step—step_abc, step_def—then "add after step_abc" and "remove step_def" don't conflict. We merge by identity, not position. CRDTs do this. Operations reference stable identities. Merge is automatic. OT: the chefs send edits. A central system transforms them. "Chef B's delete—apply it to Chef A's insert." Adjusted. Complex. But works. Both kitchens end up with the same recipe. Different paths.

---

## Connecting to Software

**Operational Transformation (OT).** Each edit is an operation. Insert(c, pos). Delete(pos). To merge: transform operations against each other. A inserts at 5. B deletes at 3. Transform B's delete against A's insert. "If A's insert happened first, B's delete position shifts." Rules get complex. Edge cases many. But: Google Docs. Proven. Works. Central server often required to serialize transforms. Conflict resolution is algorithmic. Not automatic. Requires careful design.

**CRDTs.** Conflict-Free Replicated Data Types. Data structures with merge rules. Example: G-Counter. Each node has its own counter. To get total: sum all. No conflicts. For text: RGA (Replicated Growable Array) or LSEQ. Each character has a unique ID. Insert "X" after ID abc. Delete character with ID xyz. Merging: apply all inserts and deletes. Same IDs. Same order (via causal ordering). Everyone converges. No central server needed. Peer-to-peer possible. Figma uses CRDTs for their design tool. Real-time. No conflicts. Math guarantees it.

**Example: G-Counter CRDT.** Three nodes. Node A increments: A=1, B=0, C=0. Node B increments: A=1, B=1, C=0. Merge: take max per node. A=1, B=1, C=0. Total=2. Correct. No coordination. Merge is commutative. Associative. Idempotent. Math works. For text, it's more complex. But the principle holds. Structure your data so merge is deterministic. CRDTs are that structure.

---

## Let's Walk Through the Diagram

```REAL-TIME COLLABORATION - MERGE
┌─────────────────────────────────────────────────────────────────┐
│                                                                  │
|   USER A                    USER B                    MERGE      |
│                                                                  │
|   Insert "X" at 5    |    Delete char at 3    |                  |
|        |             |         |               |                  |
|        v             |         v               |   OT: Transform |
|   [Local doc]        |    [Local doc]          |   ops against   |
|        |             |         |               |   each other    |
|        +-------------+---------+               |                  |
|        |             |         |               |   CRDT: Merge   |
|        v             v         v               |   by structure  |
|            [SERVER or P2P]                     |   (commutative) |
|                    |                            |                  |
|                    v                            |                  |
|            [Same document]                      |                  |
│                                                                  │
|   Key: No conflicts. Deterministic. Everyone converges.          |
│                                                                  │
└─────────────────────────────────────────────────────────────────┘```

Narrate it: A and B edit. Operations flow to merge point. OT: transform. Adjust positions. Apply. CRDT: merge by structure. Same IDs. Same result. Both paths yield one document. No overwrites. No data loss. The diagram simplifies. Implementation is hard. But the concept is clear. Concurrency without coordination. That's the dream. Both OT and CRDTs achieve it. Differently.

---

## Real-World Examples (2-3)

**Google Docs.** OT. Central server. They've published papers. Real-time. Billions of edits. The gold standard for collaborative docs. Complex. But it works. They've refined it for years.

**Figma.** CRDTs. Design tool. Multiple designers. Same file. Real-time. No central bottleneck for merge. Peer sync possible. They've blogged about it. CRDTs fit their model. Your product may differ. Choose the tool for the job.

**Notion.** Collaborative. Likely OT or similar. They don't publish details. But the pattern is the same. Real-time collaboration is a product expectation now. Users demand it. Build it. Learn the approaches.

---

## Let's Think Together

**"Two users simultaneously: User A inserts 'X' at position 5. User B deletes character at position 3. Final document?"**

With OT: depends on transform rules. Typically: apply both. If delete happens first, positions shift. A's insert at "5" might now be at 4. Transform adjusts. Result: document with X in the right logical place, delete applied. With CRDT: characters have IDs. A inserts X with id_x after char_5. B deletes char_3. Merge: X is in. char_3 is out. Order determined by causal metadata (lamport clocks, vector clocks). Result: same. The exact characters depend on the original document. But the principle: both operations apply. No conflict. Merge produces one result. Deterministic. Everyone agrees. That's the goal. Achievable. With care.

---

## What Could Go Wrong? (Mini Disaster Story)

A startup builds collaborative editing. No OT. No CRDT. Just "last write wins." User A types "Hello." User B types "World" in the same place. Last write wins. A's "Hello" gone. User A: "Where did my text go?!" Chaos. They rebuild with OT. Complex. Bugs. They eventually get it right. The lesson: don't wing it. Collaborative editing has established solutions. Use them. OT or CRDT. Don't invent. Adopt. Adapt. Implement. "Last write wins" is not collaboration. It's conflict. Users will hate it.

---

## Surprising Truth / Fun Fact

CRDTs were first formalized in 2011. The theory existed before. But the paper "Conflict-free Replicated Data Types" brought it together. Now they're in Riak, Redis (with modules), and many collaboration tools. The math is elegant. Merge functions that are commutative, associative, idempotent. Three properties. Guarantee convergence. No coordination. Distributed systems often need coordination. CRDTs show: sometimes you don't. Structure beats coordination. A profound idea. It changed how we build collaborative systems.

---

## Quick Recap (5 bullets)

- **Problem:** Concurrent edits. No central coordinator. Must converge to same document.
- **OT:** Transform operations. Central server often needed. Google Docs. Complex but proven.
- **CRDTs:** Structure data for automatic merge. No conflicts. Figma. Math guarantees convergence.
- **G-Counter example:** Each node has counter. Merge = sum. No coordination. Principle scales.
- **Choose by product:** OT for docs with central server. CRDTs for P2P or when you want structure.

---

## One-Liner to Remember

**Real-time collaboration needs merge without conflict—OT transforms operations, CRDTs structure data. Both work. Pick one. Don't use "last write wins."**

---

## Next Video

Next: messaging platform. WhatsApp. Delivery guarantees. Gray ticks. Blue ticks. How does it work?
