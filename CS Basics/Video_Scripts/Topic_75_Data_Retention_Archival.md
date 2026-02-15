# Data Retention and Archival

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

Your house. This year's documents on your desk. Last year's in a drawer. Five years ago? A box in the attic. You don't throw them away. Tax authorities might ask. But they don't need to be on your desk.

That's data retention and archival. Where data lives. How long you keep it. And why it saves you money.

---

## The Story

Sarah runs a small business. She has papers everywhere. This month's invoices—on her desk. Easy to grab. Last year's—in a filing cabinet. She goes there once in a while. Receipts from 2018? Boxed in the attic. She almost never touches them. But the IRS can ask for 7 years. So she keeps them. Just not on her desk.

Same idea in software. **Hot storage**—your desk. Fast. Expensive. Frequently accessed. **Warm storage**—the drawer. Cheaper. Sometimes accessed. **Cold storage**—the attic. Cheapest. Rarely touched. **Archive**—almost never. Maybe tape. Maybe Glacier Deep Archive.

You don't delete everything. You **move** it. Cheaper storage. Slower to access. But it's there when you need it. That's archival. How long you keep it before deleting? That's retention.

---

## Another Way to See It

Like a library. New bestsellers—on the main floor. Easy access. Popular. Old editions—in the stacks. You can get them, but you walk. Rare archives—in climate-controlled storage. Request only. Might take a day. The book isn't gone. It's just in a different tier. Cost to store drops. Speed to access drops. Both by design.

The emotional beat: at first you think "we'll just keep everything on fast storage." Then the bill arrives. Tiering is not optional at scale. It's survival.

---

## Connecting to Software

**Hot tier:** SSD, in-memory, database. Milliseconds. For data you touch every day. Production databases. Active cache.

**Warm tier:** Cheaper disks. Maybe object storage standard class. For logs from last month. Recent backups. Accessed weekly.

**Cold tier:** S3 Glacier, Azure Archive. Retrieved in hours. For data you keep for compliance but rarely need. Old backups. Audit logs.

**Archive / Deep:** Glacier Deep Archive, tape. Retrieval in 12–48 hours. Pennies per GB. For "we might need it in 10 years" data.

**Retention policy:** "Keep application logs 90 days. Keep financial records 7 years. Delete user data 30 days after account deletion." Legal and business drive these numbers.

**Implementation:** Scheduled job moves data older than X days to a colder tier. Or use S3 lifecycle rules—automatically transition objects after 30 days to Glacier. Set expiration for true deletion after Y years.

The relief moment: you're not losing data. You're organizing it. Hot when it's hot. Cold when it's not. Your compliance team is happy. Your finance team is happy. Your storage bill drops by 70%. Everyone wins.

---

## Let's Walk Through the Diagram

```
    TIME →
┌─────────────────────────────────────────────────────────────┐
│  Today    │  Last 30 days  │  Last year  │  5+ years ago   │
├───────────┼────────────────┼─────────────┼─────────────────┤
│  HOT      │  WARM          │  COLD       │  ARCHIVE        │
│  SSD/DB   │  Cheaper disk  │  S3 Glacier │  Deep Glacier  │
│  $0.10/GB │  $0.02/GB      │  $0.004/GB  │  $0.001/GB     │
│  ms       │  seconds       │  hours      │  hours-days     │
└─────────────────────────────────────────────────────────────┘
```

As data ages, move it down. Cost drops. Latency rises. You decide the boundaries. Most companies: hot for 7–30 days, warm for 90 days, cold for 1–7 years. Then expire or deep archive. The exact numbers depend on your industry and compliance needs.

---

## Real-World Examples (2-3)

**Example 1 — AWS S3 lifecycle:** Create a rule. Objects older than 90 days → move to Glacier. Older than 365 days → Glacier Deep Archive. Or delete after 7 years. Automated. No custom code. You set it once. It runs forever.

**Example 2 — Log aggregation:** Splunk, Elasticsearch. Recent logs in hot storage. After 30 days, move to cold. After 1 year, delete or archive. Logs are huge. Tiering saves massive costs.

**Example 3 — Healthcare:** HIPAA requires medical records 6 years. Hospital keeps active records hot. After patient discharge, move to warm. After 6 years, archive. Retention is law.

The surprise: many engineers treat "keep forever" as the default. It's not. Every byte costs money. Every byte has compliance implications. Design retention into your system from the start. Document it. Automate it.

---

## Let's Think Together

Your app generates 10GB of logs per day. Storage costs? In 1 year that's 3.6TB. Keep all on SSD? Archive? Delete?

Pause and think.

10GB/day = 300GB/month = 3.6TB/year. SSD at $0.10/GB = $360/year just for 1 year. At 3 years, 10+ TB. Options: (1) Keep 30 days hot, archive rest—cheap. (2) Delete after 90 days if you don't need old logs. (3) Compress + cold storage for compliance.

Most teams keep 30–90 days hot, archive older. S3 Glacier would be maybe $15–30/year for the archived portion. Huge savings. The aha: retention policy isn't optional. It's a design decision. Make it early.

---

## What Could Go Wrong? (Mini Disaster Story)

A startup had no retention policy. Logs forever. Backups forever. User data forever. Year one: 2TB. Year three: 20TB. Year five: 200TB. Storage bill: $5,000/month. The CFO asked why. Nobody had thought to archive or delete. They rushed to build lifecycle rules. Migrated petabytes. Took months. Engineers worked weekends. The storage team was in crisis mode. A policy from day one would have saved millions. Write it down. Document retention by data type. Automate. Review quarterly.

---

## Surprising Truth / Fun Fact

The US IRS requires tax records for 7 years. HIPAA requires medical records for 6 years. Laws drive retention. Your storage strategy isn't just engineering—it's legal.

---

## Quick Recap (5 bullets)

- **Hot/warm/cold/archive:** Tiers by access frequency. Hot = fast, expensive. Cold = slow, cheap.
- **Retention:** How long you keep data before deleting. Often legally defined.
- **Archive vs delete:** Archive = move to cheaper storage. Delete = gone.
- **Cost:** S3 Standard ≈ $0.023/GB. Glacier ≈ $0.004/GB. 6x cheaper.
- **Implementation:** Lifecycle rules, scheduled jobs. Automate the transitions.

---

## One-Liner to Remember

Desk for now. Drawer for last year. Attic for old. Delete when the law says you can. Archive when it's cold. Hot when it's hot. Tier your storage. Automate the transitions. Your future self will thank you.

---

## Next Video

You need to add a column to a table with 500 million rows. In production. Without downtime. Schema migration—next.
