# API Versioning: Why and How (v1, v2)

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

You build a building. Tenants move in. Now you want to redesign the lobby. But tenants use the lobby every day. You can't just demolish it. Solution: build the new lobby next door. Old tenants keep using the old lobby. New tenants use the new one. Gradually migrate. That's API versioning. Your API is a contract. Thousands of apps depend on v1. You can't just change it. You release v2 alongside v1.

---

## The Story

You own an office building. Tenants moved in years ago. The lobby works. But it's outdated. You want to modernize.

You can't just demolish it. Hundreds of people use it daily. They'd have nowhere to go. Chaos. Lawsuits.

So you build a new lobby. Next to the old one. Old tenants keep using the old lobby. New tenants use the new one. Over time, you migrate. Eventually, you can close the old lobby. But only when everyone has moved.

APIs are the same. v1 is the old lobby. Thousands of mobile apps use it. Web apps. Third-party integrations. You can't change v1. You'd break them all. So you release v2. New lobby. New apps use v2. Old apps stay on v1. Both run. You migrate when ready.

---

## Another Way to See It

A dictionary. Edition 1. Millions of copies sold. Now you want to add new words. Change definitions. You can't recall every copy. So you publish Edition 2. New buyers get Edition 2. Old buyers keep Edition 1. Both are valid. Different editions. Same publisher. API versioning is publishing a new edition without invalidating the old one.

---

## Connecting to Software

**Why version?** Your API changes. New fields. Removed fields. Renamed fields. Different structure. Old clients expect the old format. New format breaks them. Crashes. Wrong data. Angry users. Versioning lets old and new coexist.

**Versioning strategies:**

**1. URL path** — `/v1/users`, `/v2/users`  
Most common. Visible. Easy to debug. "We're calling v2." Clear.

**2. Header** — `Accept: application/vnd.myapi.v2+json`  
URL stays the same. Version in header. Cleaner URLs. But harder to test. Can't just paste URL in browser.

**3. Query param** — `/users?version=2`  
Simple. But easy to forget. Inconsistent. Less preferred.

**Best practice:** URL path. `/v1/`, `/v2/`. Everyone understands it. You can see the version in the URL. Easy to test in a browser. Easy to share. Easy to debug. "We're on v1" is clear. Header-based versioning is cleaner aesthetically, but URL path wins for visibility and simplicity. Most major APIs use it. When in doubt, follow the crowd.

**Deprecation:** Don't kill v1 overnight. Mobile apps take weeks to update through app stores. Enterprise clients might have integration cycles of months. Give them time. Six months minimum. A year for critical APIs. Monitor v1 usage. When it drops to near zero, send a final warning. Then sunset. And document everything. Changelog. Migration guide. Support channel. Make migration easy, and most clients will move. Force it, and you create enemies. Announce. "v1 deprecated. Migrate by June 2025." Monitor usage. Send reminders. Sunset when usage is near zero.

---

## Let's Walk Through the Diagram

```
API Versioning: URL Path Strategy

  OLD (v1)                    NEW (v2)
  ┌─────────────────┐        ┌─────────────────┐
  │ GET /v1/users   │        │ GET /v2/users   │
  │ Response:       │        │ Response:       │
  │ { "name": "..." }│       │ { "first_name", │
  └────────┬────────┘        │   "last_name" } │
           │                 └────────┬────────┘
           │                          │
  Mobile app (old)              Mobile app (new)
  Web (legacy)                  Web (new)
  Third-party A                 Third-party B

  Both run. Same server. Different code paths.
```

---

## Real-World Examples

**1. Stripe**  
Years of API versions. Each request can specify a version. Version transformers convert between formats. Old integrations keep working. New ones use new features. Stripe is the gold standard for API versioning.

**2. Twitter (X) API**  
v1.1 and v2 coexist. v2 has better structure. New developers use v2. Legacy apps still on v1.1. Migration is gradual.

**3. AWS APIs**  
Many services use version in the URL or in the request. `iam.amazonaws.com` vs. newer APIs. Versioning is built in from day one.

---

## Let's Think Together

v1 returns `user.name` as a string. v2 splits it into `user.first_name` and `user.last_name`. How do you migrate without breaking mobile apps still on v1?

Pause. Think.

Keep v1. In v1 handler, read `first_name` and `last_name` from DB. Concatenate. Return as `name`. v1 clients see no change. Add v2. In v2 handler, return `first_name` and `last_name` separately. New clients use v2. Old clients stay on v1. Migration: update mobile apps to use v2. When all migrated, deprecate v1. Never break v1. Add v2. Migrate. Then sunset.

---

## What Could Go Wrong? (Mini Disaster Story)

A company changed their API. No versioning. "We'll just update the response." Millions of mobile app installs. App stores take days to approve updates. Users don't update immediately. Old app version hit the API. New response format. App crashed. Parsing failed. "Cannot read property of undefined." Support flooded. Revert. Apologize. Then: add versioning. Never again.

---

## Surprising Truth / Fun Fact

Stripe maintains years of API versions simultaneously. They use a system where each request is run through version transformers. Your account can be on 2019-01-01, another on 2024-01-01. Same API. Different shapes. Transformers convert. That's how you support the world's payment infrastructure without breaking anyone.

---

## Quick Recap (5 bullets)

- API changes break clients. Versioning lets old and new coexist.
- URL path versioning (/v1/, /v2/) is most common and visible.
- Deprecation: announce, give timeline, monitor usage, sunset when safe.
- v1 and v2 can share backend logic; transform response per version.
- Never break a published API. Add. Version. Migrate. Sunset. Some companies support old API versions for years. Stripe does. AWS does. When you have paying customers, breaking their integrations is not an option. Versioning is the price of stability. Embrace it from day one. Even if you think your API is small. One day it won't be. Plan ahead. Version from v1 from the start. Even if you have one client. Put /v1/ in the URL. When you need to break things, you add /v2/. No migration of URLs. No surprise. Versioning is easier when it's baked in from day one. Retrofitting it later is painful. Start with /v1/. Thank yourself later.

---

## One-Liner to Remember

*API versioning is building the new lobby next to the old one—everyone keeps working while you migrate.*

---

## Next Video

Next: Idempotency. Why clicking "Pay Now" twice shouldn't charge you twice. Topic 98: API Design—Idempotency for Write APIs.
