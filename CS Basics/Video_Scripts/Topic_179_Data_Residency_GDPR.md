# Data Residency and GDPR Compliance

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

You live in Germany. Your medical records sit at a German hospital. One day you learn the hospital shipped copies of your records—your diagnoses, your history—to a random server in another country. No consent. No notice. You'd be horrified. That's exactly why laws like GDPR exist. European user data must be handled with specific rules. Some laws go further: data must STAY in specific countries. Data residency is where your data physically lives. Compliance is following the rules about how you store, process, and delete it.

---

## The Story

Data residency asks: where does your data physically sit? Which data center? Which country? Which jurisdiction? It matters. A European user's personal data stored in the US might be subject to US laws—FISA warrants, subpoenas—that conflict with EU privacy expectations. Germany might require healthcare data to never leave German soil. Russia might demand that citizen data stay in Russia. Data residency is the rule: keep data in a designated geographic location.

Compliance is broader. It's not just where data lives—it's how you handle it. GDPR says: you need a legal basis to process data. Users have the right to access their data, correct it, delete it ("right to be forgotten"), and export it. You must document what you collect and why. You must report breaches within 72 hours. Consent must be clear and withdrawable. Compliance means building processes, policies, and systems to meet these rules.

Another analogy: think of data like gold in a vault. Residency says "the gold must stay in this vault in Zurich." Compliance says "you must log every access, have guards, insure it, and allow audits." Both matter. One is location. One is behavior.

---

## Another Way to See It

Imagine a passport. Data residency is like a stamp: "This person may only travel within the Schengen zone." The passport (data) has geographic restrictions. Compliance is like customs rules: how you declare items, what you're allowed to carry, what forms you fill. You need both. The stamp restricts movement. The rules govern how you handle what you carry.

---

## Connecting to Software

In software, data residency affects architecture. If EU data must stay in EU, you need region-specific storage. AWS has eu-west-1, eu-central-1. You configure your databases and object storage to use EU regions for EU users. Replication? Be careful. Replicating EU data to US for backup might violate residency. You may need region-locked replication.

Compliance affects design too. Delete requests? You need to find and purge data across all systems—primary DB, backups, caches, logs, analytics. That's hard. You need data maps: where does each type of data live? Retention policies: how long do you keep it? Access controls: who can see what? Audit logs: who accessed what, when?

**Right to portability:** GDPR says users can export their data in a machine-readable format. Your system must support "give me everything you have on me." That might mean querying multiple databases, formatting into JSON or CSV, and delivering. Design for this from the start. It's not trivial to bolt on later.

---

## Let's Walk Through the Diagram

```
    GLOBAL APP WITHOUT RESIDENCY              GLOBAL APP WITH RESIDENCY

    Users (EU) ──► Load Balancer              Users (EU) ──► LB ──► EU Region Only
         │                    │                      │         (DB, Cache, Storage)
         │                    │                      │
         └──► US Data Center  │                      └──► EU Data Center
              (DB, etc.)      │                           ✓ Compliant
              ⚠ Data crosses borders
```

Left: EU user data might end up in US. Risk. Right: EU traffic routed to EU-only infrastructure. Data stays put.

---

## Real-World Examples (2-3)

**Example 1: Slack.** Slack stores EU customer data in EU data centers. When you sign up from Europe, your workspace data stays in EU regions. They publish a data residency guide and compliance documentation. Enterprises demand this before signing.

**Example 2: Healthcare apps.** A health app storing patient data in Germany must use German or EU-hosted infrastructure. HIPAA (US) and national health laws add more rules. Data residency isn't optional—it's legally required.

**Example 3: Google Cloud and GDPR.** Google offers GDPR-compliant configurations: data processing agreements, deletion tools, audit logs. Customers choose EU regions for EU data. Google handles requests for access, deletion, and portability through defined processes.

---

## Let's Think Together

**If your app has users in EU and US, do you need two separate databases?**

Often yes—or at least region-specific shards. EU user data in EU regions. US user data can go to US. You route by user region. Some companies use a single global DB but with strict replication rules (e.g., no replication of EU data outside EU). The key: know where each user's data lives and ensure it complies with their jurisdiction.

**What if you use a SaaS that stores data in the US, but your users are in EU?**

You need a Data Processing Agreement (DPA). The vendor commits to handling data per GDPR—sub-processors, security, deletion. Standard Contractual Clauses (SCCs) help for international transfers. Some vendors offer EU-hosted options. Check before you sign.

---

## What Could Go Wrong? (Mini Disaster Story)

A startup builds a fitness app. Users in France, Germany, UK. They use a US-based analytics provider. Analytics receives user IDs, workout data, location. No DPA. No EU hosting. A user requests deletion under GDPR. The startup deletes from their DB. But analytics still has the data. They can't delete it easily—no API, no process. Regulator finds out. Fine: 4% of global revenue. The startup nearly shuts down. Lesson: map your data flows. Every third-party that touches personal data must be compliant and deletable.

---

## Surprising Truth / Fun Fact

GDPR fines can go up to €20 million or 4% of global annual revenue—whichever is higher. In 2023, Meta was fined €1.2 billion for transferring EU data to the US without adequate safeguards. Data residency isn't just a checkbox. It's a business-critical architecture decision.

---

## Quick Recap (5 bullets)

- **Data residency** = where your data physically lives (which country, which data center).
- **Compliance** = following rules about storage, processing, access, and deletion (e.g., GDPR).
- EU data often must stay in EU regions; some sectors (health, finance) have stricter rules.
- Architecture must support region-specific storage and region-locked replication.
- Map all data flows; every third party handling personal data needs DPAs and deletion support.

---

## One-Liner to Remember

Data residency is *where* your data lives; compliance is *how* you handle it. Both matter—and both shape your system design.

---

## Next Video

Next up: **Failover and Failback**—when the pilot passes out and the co-pilot takes over. How systems switch to backup and switch back. Smooth. Automatic. Or not.
