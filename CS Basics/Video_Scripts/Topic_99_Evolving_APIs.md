# How to Evolve APIs Without Breaking Clients

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

You run a popular restaurant. Menu printed on paper. Ten thousand copies distributed. Now you want to add a "spice level" column. Can you recall all 10,000 menus? No. But new menus have the extra column. Old menus still work—they just don't show spice level. That's backward-compatible change. Adding is safe. Removing or renaming is dangerous.

---

## The Story

A restaurant. Printed menus. Ten thousand copies. Handed to customers. On tables. At the door.

You want to improve. Add a "spice level" column. Mild. Medium. Hot. Great idea. But you can't recall every menu. They're out there. In the wild.

So you print new menus. With spice level. New customers get new menus. Old menus? Still valid. Chicken biryani is still item 12. Price unchanged. Old menus just don't have the new column. No problem. Everyone can still order. Adding is safe.

But what if you want to remove an item? Rename "Chicken Biryani" to "Hyderabadi Chicken Biryani"? Old menus say "Chicken Biryani." New menus say something else. Confusion. Or you change the price. Old menu says Rs 200. New says Rs 250. Customer orders from old menu. Argument. Removing and changing are dangerous.

APIs are the same. Add new fields. Safe. Remove fields. Dangerous. Change types. Dangerous.

---

## Another Way to See It

A form. You add a new optional field. "Phone number (optional)." Old users don't fill it. Form still submits. New users can fill it. Backward compatible. You remove a required field. Old code expects it. Breaks. Or you change "age" from number to "date_of_birth" string. Old code does math on age. Gets NaN. Crashes. Additive changes: safe. Destructive changes: dangerous.

---

## Connecting to Software

**Safe changes (backward-compatible):**
- Add new fields. Old clients ignore them. New clients use them.
- Add new endpoints. Old endpoints untouched.
- Add optional parameters. Old calls work without them.

**Dangerous changes (breaking):**
- Remove fields. Old clients break. Null reference. Parse error.
- Rename fields. Old clients look for old name. Get nothing.
- Change field types. Number → string. Old code crashes.
- Change URL paths. Old clients get 404.

**Strategy:** Always add. Never remove. If you must change: version the API. Add v2. Deprecate v1. Migrate. Sunset.

**Deprecation cycle:**
1. Announce: "Field X deprecated. Use Y instead."
2. Add new field Y. Keep X. Both work.
3. Give clients 6–12 months to migrate.
4. Monitor. Remind. Support.
5. Remove X in new version. Or when usage is zero.

**Feature flags:** New fields only returned if client opts in. Header: `Accept-Version: 2024-01` or `X-API-Version: 2`. Server checks the header. New version? Return new shape. Old version or missing? Return old shape. Gradual rollout. Clients migrate when ready. No big bang. No coordinated release. This pattern is used by Stripe and others. It gives you flexibility without breaking anyone.

---

## Let's Walk Through the Diagram

```
Safe vs Breaking Changes:

  SAFE (Additive):
  Old: { "name": "Alice", "age": 30 }
  New: { "name": "Alice", "age": 30, "email": "a@b.com" }
  Old clients: ignore "email". Still work. ✓

  BREAKING:
  Old: { "name": "Alice", "age": 30 }
  New: { "name": "Alice", "date_of_birth": "1994-01-01" }
  Old clients: expect "age". Get undefined. Break. ✗

  Migration path:
  Add "date_of_birth". Keep "age". Deprecate "age".
  Clients migrate. Remove "age" in v2.
```

---

## Real-World Examples

**1. Stripe**  
API versions. New fields added. Old ones deprecated with notice. They never remove without a version bump. Migrations are documented. Timelines given. Stability over perfection.

**2. Google APIs**  
Google's API design guide: "API stability is more important than API perfection. Never break a published API." They add. They deprecate. They version. They don't break.

**3. Twitter API**  
v1.1 to v2. New structure. New fields. Old endpoints still work for legacy apps. New apps use v2. Gradual migration. No big bang.

---

## Let's Think Together

Your API returns `age` as a number. You need to change it to `date_of_birth` string. How do you migrate without breaking existing clients?

Pause. Think.

Add `date_of_birth`. Keep `age`. Both in the response. Old clients keep using `age`. New clients use `date_of_birth`. Document: "age is deprecated. Use date_of_birth." Give 6 months. Monitor who uses `age`. Send emails. When usage is low, remove `age` in the next major version. Or keep both forever if usage never drops. Never remove `age` without a deprecation period and version bump.

---

## What Could Go Wrong? (Mini Disaster Story)

A company renamed a field. `user_id` to `userId`. "Small change. We'll do it in the next release." Millions of API calls. Hundreds of integrations. Release day. Integrations broke. "user_id is undefined." Cascading failures. Rollback. Emergency. Post-mortem: "We will never rename without versioning." They added `userId`. Kept `user_id` for a year. Deprecated. Migrated. Removed. Lesson: no "small" breaking change. All breaking changes are big.

---

## Surprising Truth / Fun Fact

Google's API design guide says: "API stability is more important than API perfection. Never break a published API." When you have billions of calls, millions of clients, one breaking change can take down thousands of businesses. Add. Deprecate. Version. Migrate. Never break. This discipline separates amateur APIs from professional ones. Amateurs change fields and hope nobody notices. Professionals add, deprecate, communicate, and migrate. The extra work pays off in trust. When your partners know you won't break them, they integrate deeper. Everyone wins. This is why companies like Stripe and Twilio have such strong developer loyalty. Their APIs are stable. You can build a business on them. When your API is a dependency for others, stability isn't optional. It's the foundation of trust. Evolve carefully. Add generously. Remove never—or only with long deprecation and clear communication. Document every change in a changelog. Notify partners. Give migration guides. The effort you put into safe evolution pays off in reduced support load and happy developers. Your API becomes a platform. Platforms don't break their users. They grow with them.

---

## Quick Recap (5 bullets)

- Safe: add new fields, new endpoints, optional params. Dangerous: remove, rename, change types.
- Strategy: always add, never remove. If you must change: version, deprecate, migrate, sunset.
- Deprecation: announce, add new field, give 6–12 months, monitor, remove when safe.
- Feature flags: return new fields only when client opts in (e.g., via header).
- API stability beats perfection. Never break a published API.

---

## One-Liner to Remember

*Evolving APIs safely means always adding, never removing—deprecate, migrate, then sunset.*

---

## Next Video

Next: Request IDs and tracing. How to find one request in 50 million. Topic 100: Request IDs and Tracing—Why They Matter.
