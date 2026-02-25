# ACID: Consistency Explained

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

A cricket scoreboard. India batting. 287 runs on the board. Sachin hits a four. Then another. Twelve runs. The board should show 299. But a bug glitches it. The number flashes: 350. Three-fifty. The crowd groans. That's wrong. The math doesn't add up. 287 plus 12 is 299, not 350. The scoreboard is lying. That's inconsistency. And in a database? That kind of wrong can cost millions.

---

## The Story

Think about that scoreboard. Before Sachin's shot: 287. Valid. Correct. After his 12 runs: it should be 299. Still valid. The rules of cricket say runs add up. The rules of math say 287 + 12 = 299. But what if the system shows 350? Or 100? Or negative 50? The data is now INCONSISTENT. It breaks the rules.

**Consistency in databases means: after every transaction, all the rules are still true.** Your rules might be: balance cannot be negative. Email must be unique. Age must be between 0 and 150. Foreign keys must point to existing rows. Before the transaction: rules valid. After the transaction: rules STILL valid. The transaction takes the database from one valid state to another valid state. Never to an invalid one. Think of it as a contract: the database promises to never leave you in a state where the rules are broken. It's the foundation of trust in your data.

If your rule says "bank balance cannot be negative," then no transaction should EVER leave a balance at -500. The database will reject it. Roll it back. Refuse to commit. Consistency is the guardian of your rules.

---

## Another Way to See It

Sudoku. Every move must keep the puzzle valid. No duplicate numbers in a row. No duplicates in a column. No duplicates in a 3x3 box. A "consistent" move follows all the rules. You place a 5. Is that 5 already in the row? Then it's invalid. Inconsistent. The puzzle rejects it. Database consistency is the same. Every transaction is a "move." Valid move? Commit. Invalid move? Reject. The puzzle — your data — always stays solvable.

---

## Connecting to Software

Consistency isn't about "all copies agree." That's a different meaning — used in distributed systems. In ACID, consistency means **rule validity**. Your constraints. Your invariants. Examples: balance >= 0. Email UNIQUE. Product ID must exist in the products table. Age BETWEEN 0 AND 150.

The database checks these rules when you COMMIT. If the transaction would violate any rule, the COMMIT fails. Rollback. Try again with valid data. Before transaction: valid state. After transaction: valid state. The journey between them is a series of valid steps. During the transaction, the database might temporarily hold inconsistent intermediate state — that's why we have isolation — but the moment you commit, every constraint is checked. Pass? Commit. Fail? Reject. No compromises.

---

## Let's Walk Through the Diagram

```
RULE: Balance cannot be negative
RULE: Inventory cannot be negative

Transaction 1 (VALID):                 Transaction 2 (INVALID):
Before: Balance = 500                  Before: Balance = 50
        Buy item: -100 ✓                       Buy item: -500 ✗
After:  Balance = 400 ✓                After:  Balance = -450
        COMMIT ✓                               REJECTED. ROLLBACK.
        Rules still valid.                     Rule broken. Not allowed.
```

The database is the referee. It enforces the rules. Invalid state? Transaction fails. No exceptions.

---

## Real-World Examples (2-3)

**1. Bank balance:** Rule: balance >= 0. Transaction tries to withdraw more than available? Rejected. Consistency saves you from negative money.

**2. E-commerce inventory:** Rule: quantity_available >= 0. Two users buy the last ticket. Without consistency checks, you sell two tickets. Overselling. With consistency: the second transaction fails. "Sorry, sold out." One ticket, one sale. Rule upheld.

**3. User registration:** Rule: email UNIQUE. Two users try to register with the same email. First succeeds. Second fails. No duplicate accounts. Consistency enforced.

**4. Referral system:** Rule: user_id in referrals must exist in users table. A transaction tries to create a referral for user 999 — but user 999 doesn't exist. Foreign key constraint. Rejected. Consistency prevents orphan data. The database refuses to break the rule.

---

## Let's Think Together

Two users buy the last concert ticket at the same time. How does consistency prevent selling two tickets when only one exists?

*Pause. Think about it.*

The rule: tickets_sold cannot exceed tickets_available. When user A buys, the transaction checks: tickets_available = 1. Decrement. tickets_sold++. COMMIT. When user B tries — at the same moment — the database uses locks or isolation. User B's transaction sees tickets_available = 0. Their purchase would make it -1. Invalid. Rule broken. User B's transaction fails. "Sorry, sold out." One ticket, one buyer. Consistency won. The constraint is enforced at commit time. The database validates every rule. No exceptions. No "we'll fix it later." Consistency is the guard at the gate.

---

## What Could Go Wrong? (Mini Disaster Story)

No consistency checks. A ticket-selling startup. Flash sale. One million people. Last 100 tickets. The system allows multiple purchases. No constraint. No "quantity available" check. Result: 500 people "buy" tickets. Oversold by 400. The venue holds 100. Angry customers. "I paid! Where's my seat?!" Refunds. Lawsuits. Reputation destroyed. The fix? Add consistency. Enforce the rule: never sell more than you have. One constraint. Disaster prevented.

---

## Surprising Truth / Fun Fact

Here's the confusing part. In distributed systems, "consistency" means something completely different. It means: all nodes see the same data. When you read from any replica, you get the same value. Same word. Two meanings. ACID consistency = rules never broken. Distributed consistency = everyone agrees. Programmers get confused constantly. "Which consistency are you talking about?" Always clarify. Same word. Different worlds.

---

## Quick Recap (5 bullets)

- **Consistency** (ACID) = data always follows the rules. Constraints and invariants stay valid
- Before and after every transaction, the database is in a valid state
- Rules: balance >= 0, email unique, foreign keys exist, age in range, etc.
- Invalid transactions are REJECTED. COMMIT fails. Rollback.
- Different from "distributed consistency" — that's about copies agreeing, not rules

---

## One-Liner to Remember

> ACID consistency: the scoreboard always adds up. The rules are never broken. Valid state to valid state.

---

## Next Video

Consistency protects your rules. But what about when two transactions run at the same time? Can they see each other's half-finished work? Can they step on each other's toes? That's isolation. And what happens when the power goes out after you commit? Does your data survive? That's durability. Two properties. One video. The kitchen gets crowded. That's next.
