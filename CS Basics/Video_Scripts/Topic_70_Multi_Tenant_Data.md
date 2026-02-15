# Multi-Tenant Data: How to Isolate?

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

An apartment building. 10 families. Shared building. Shared elevator. Shared water supply. But each family has their OWN apartment. Own lock. Own stuff. Family A cannot walk into Family B's apartment. Privacy. Security. They share infrastructure. They do NOT share data. That's multi-tenancy. One system. Many customers. Each sees only their own. Salesforce. Shopify. Slack. All multi-tenant. But HOW do you actually isolate the data? One bug. One forgotten WHERE clause. Tenant A sees Tenant B's data. Lawsuit. Fines. Company over. Let me show you the options.

---

## The Story

Multi-tenant means one system serves many customers — tenants. Company A uses your SaaS. Company B uses it. Company C. Same codebase. Same servers. Same database. But Company A must NEVER see Company B's data. Isolation. Critical.

**Strategy 1: Separate database per tenant.** Each tenant gets their own database. Company A → database_a. Company B → database_b. Strongest isolation. Like each family gets a separate house. Backup per tenant. Restore per tenant. Compliance easy. But 1,000 tenants? 1,000 databases. Expensive. Connection pools. Maintenance. Scaling complexity. Best for: small number of large tenants. Enterprise. High-touch.

**Strategy 2: Separate schema per tenant.** Same database server. Different schemas. database → schema_company_a, schema_company_b. Same building. Different floors. Locked doors. Medium isolation. One database. Many schemas. Cheaper than separate DBs. But still: 1,000 tenants? 1,000 schemas? Possible. Messy. Migrations run 1,000 times. Best for: medium tenant count. Moderate isolation needs.

**Strategy 3: Shared table with tenant_id column.** One table. All tenants. Rows have tenant_id. Company A: tenant_id = 1. Company B: tenant_id = 2. Cheapest. Simplest. One table. Filter: WHERE tenant_id = X. But ONE bug. Developer forgets the WHERE clause. SELECT * FROM users. Returns EVERYONE. Tenant A sees Tenant B's users. Data leak. Nightmare. HIPAA. GDPR. Fines. Reputation destroyed. Weakest isolation. Requires discipline. Defense in depth. Row-level security. Audits. Best for: high tenant count. Cost-sensitive. With strong guardrails.

---

## Another Way to See It

Shared office space. Strategy 1: Each company gets its own floor. Locked. Separate. Strategy 2: Same floor. Separate rooms. Labels on doors. Strategy 3: Open plan. Desks mixed. Labels on each desk. Cheapest. One person at wrong desk? Sees wrong papers. Risky. Same trade-offs.

---

## Connecting to Software

**Strategy 1 — Separate DB:** tenant_id in connection string. Or separate server. Strongest isolation. Per-tenant backup. Per-tenant restore. Expensive. N tenants = N databases.

**Strategy 2 — Separate schema:** PostgreSQL: CREATE SCHEMA tenant_a. Tables in schema. Connection selects schema. Medium cost. N tenants = N schemas. Migrations × N.

**Strategy 3 — Shared table, tenant_id:** One table. tenant_id column. EVERY query: WHERE tenant_id = ?. Mandatory. Enforce with middleware. Row-level security. Triggers. Code review. One mistake = leak.

**Compliance:** HIPAA. Financial. Healthcare. Strategy 1 often required. Or strategy 2 with encryption. Strategy 3: risky. Possible with RLS, audit logs, and paranoia.

---

## Let's Walk Through the Diagram

```
MULTI-TENANT ISOLATION STRATEGIES

Strategy 1: Separate DB         Strategy 2: Separate Schema
┌─────────────┐ ┌─────────────┐   ┌─────────────────────────────┐
│ DB_Tenant_A│ │ DB_Tenant_B │   │ One DB                      │
│ users      │ │ users       │   │ schema_a.users schema_b.users│
│ orders     │ │ orders      │   │ schema_a.orders schema_b.orders│
└─────────────┘ └─────────────┘   └─────────────────────────────┘
Strong. Expensive.                 Medium. Cheaper.

Strategy 3: Shared Table
┌─────────────────────────────────────┐
│ users: id | tenant_id | name | ...  │
│ 1   | 1    | Alice  |  (Tenant A)   │
│ 2   | 1    | Bob    |  (Tenant A)   │
│ 3   | 2    | Carol  |  (Tenant B)   │
└─────────────────────────────────────┘
Cheapest. WHERE tenant_id = ? or DISASTER.
```

Three strategies. Isolation vs cost. Choose based on tenant count and compliance.

---

## Real-World Examples (2-3)

**1. Salesforce:** 150,000+ companies. Shared multi-tenant architecture. org_id (tenant_id) in every table. One bug. One leak. Would be catastrophic. They use shared tables. org_id everywhere. Row-level security. Decades of hardening. One of the most complex multi-tenant systems ever built.

**2. Shopify:** Millions of stores. Shared infrastructure. shop_id. Each store isolated. Scalable. Cost-effective. Strategy 3. With extreme discipline.

**3. Healthcare SaaS (typical):** HIPAA. Patient data. Often strategy 1. Each hospital or clinic gets own database. Or strategy 2. Compliance demands it. Can't risk leak. Cost is acceptable.

---

## Let's Think Together

Healthcare SaaS. Patient data. HIPAA compliance. Which strategy?

*Pause. Think about it.*

**Strategy 1.** Separate database per tenant (or per organization). Strongest isolation. Easiest to audit. "Show me database for Hospital X." Done. Backup. Restore. Encrypt. Compliance clear. Cost high. But healthcare pays for compliance. Or Strategy 2 — separate schema. If same database acceptable with encryption. Strategy 3? Risky. One developer forgets tenant_id. Patient A sees Patient B's records. HIPAA violation. Massive fines. Reputation destroyed. Don't risk it. Healthcare = strategy 1 or 2. Not 3.

---

## What Could Go Wrong? (Mini Disaster Story)

Shared table. tenant_id column. Developer writes: SELECT * FROM patients WHERE name LIKE 'John%'. Forgot tenant_id. Returns ALL Johns across ALL tenants. Hospital A sees Hospital B's patients. PHI leak. HIPAA violation. Reported. Audit. Fines. Millions. Company reputation destroyed. One WHERE clause. One mistake. Defense: middleware that injects tenant_id. Row-level security. Code review. Automated tests. "Does this query have tenant filter?" Linters. Paranoia. Strategy 3 requires it. Never relax.

---

## Surprising Truth / Fun Fact

Salesforce serves 150,000+ companies from a shared multi-tenant architecture. org_id in everything. They've scaled it. Secured it. One of the most complex multi-tenant systems ever. They've had incidents. They've learned. The pattern works. With extreme discipline. Shared tables. Shared infrastructure. Isolation by org_id. It's possible. Hard. But possible. And at their scale, separate DBs would be impossible. Multi-tenancy enables the business. Isolation enables trust.

---

## Quick Recap (5 bullets)

- **Multi-tenant:** One system, many customers. Each sees only their data. Isolation critical.
- **Strategy 1:** Separate DB per tenant. Strongest. Most expensive. Best for compliance.
- **Strategy 2:** Separate schema per tenant. Medium. Cheaper. Migrations × N.
- **Strategy 3:** Shared table, tenant_id. Cheapest. Riskiest. One bug = leak.
- Salesforce: 150K+ orgs, shared tables, org_id. Possible with discipline. Never forget the WHERE.

---

## One-Liner to Remember

> Same building. Separate apartments. Same database. Separate by tenant_id. One forgotten filter? Disaster.

---

## Next Video

We've covered sharding, partitioning, hot keys, skew, denormalization, and multi-tenancy. The foundations of scaling data. What's next? Maybe message queues. Or caching layers. Or the CAP theorem. The journey continues. See you there.
