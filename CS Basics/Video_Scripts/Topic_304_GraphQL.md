# GraphQL: When It Fits

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

A restaurant. REST is like a set menu. "Chicken dinner" comes with rice, salad, and dessert. You wanted just the chicken. Tough. You get everything. GraphQL is like a build-your-own bowl. "Give me the chicken. Extra sauce. No salad. No dessert." You get exactly what you asked for. Nothing more. Nothing less. The client decides. That's GraphQL.

## The Story

With REST, you hit endpoints. `GET /users/123` gives you the whole user object. Maybe 50 fields—bio, last_login, settings, preferences, the works. You needed 3: name, avatar, email. That's **over-fetching**. You're paying for bandwidth and parsing you don't need. Then you need the user's orders. Another call: `GET /users/123/orders`. And the product details for each order. More calls. That's **under-fetching**—multiple round-trips to build one screen. Mobile on slow 3G? Painful. Waterfall requests. Spinners everywhere.

GraphQL flips it. One endpoint. One request. You send a **query** that specifies exactly what you want:

```graphql
{
  user(id: 123) {
    name
    email
    orders(limit: 5) {
      id
      total
    }
  }
}
```

The server returns exactly that. No extra fields. No extra requests. The client is in control.

## Another Way to See It

REST is like a vending machine. Press A1, you get the whole bag—chips, pretzels, whatever's in that slot. You can't say "just the chips." GraphQL is like a salad bar. You pick what you want. Cherry tomatoes? Yes. Olives? No. One trip. Custom result. The client is the chef. The server has the ingredients. The query is the recipe.

## Connecting to Software

GraphQL has a schema. Types, fields, resolvers. The client queries against that schema. The schema is the contract—both client and server agree on it. Change the schema? It's a breaking change (or you use deprecation). The server resolves each field. Resolver for `user` might hit the users table. Resolver for `orders` might hit the orders table. They can run in parallel. They can be batched. The flexibility is in your hands. But with flexibility comes responsibility: you have to optimize. Lazy loading, DataLoader, N+1 prevention—all on you. The server resolves each field—maybe from a database, maybe from another API. The beauty: the frontend can change its mind without the backend changing. "Add the user's last login" — just add it to the query. No new endpoint. No backend deploy. Frontend iteration gets faster.

But there's a catch. Complex queries can cause **N+1** problems. You ask for 100 users, each with 10 orders. Without careful batching, that's 1 + 100 database queries. Resolver for user 1: fetch orders. Resolver for user 2: fetch orders. A hundred round-trips. Ouch. You need DataLoader or similar to batch and cache. GraphQL gives you flexibility; it doesn't automatically optimize your data fetching. You have to think about it.

## Let's Walk Through the Diagram

```
REST (multiple calls):
  GET /products/456     → product + 20 extra fields
  GET /reviews?product=456 → 100 reviews, you need 3
  GET /sellers/789      → full seller object

GraphQL (one call):
  query {
    product(id:456) { name, price }
    reviews(limit:3) { text, rating }
    seller { name }
  }
  → One response, exactly what you asked for
```

## Real-World Examples (2-3)

- **Facebook (Meta)**: GraphQL was invented there. Huge, complex UIs. News feed, profile, messenger—each needs different data shapes. One GraphQL API serves them all.
- **GitHub API**: REST for simple things. GraphQL for complex queries. "Give me my repos, their open issues, and the last 3 commits" — one GraphQL query.
- **Shopify**: GraphQL for storefronts. Merchants customize what data they need—product, variants, images, maybe reviews. One API, many storefronts. Each storefront fetches exactly its fields. No over-fetching. Fast page loads.
- **Multi-client apps**: Same backend, different clients. Web needs 20 fields. Mobile needs 5. REST would either over-fetch on mobile or require separate endpoints. GraphQL: each client sends its own query. One schema. Many shapes. Frontend teams can iterate without backend changes—just change the query. That's the power.

## Let's Think Together

**E-commerce: product page needs product name, price, 3 reviews, and seller name. With REST? With GraphQL?**

REST: `GET /products/123` (over-fetch product). `GET /products/123/reviews?limit=3` (second call). `GET /sellers/456` (third call, if product has seller ID). Three round-trips. GraphQL: one query. Product { name, price }, reviews(limit:3) { text, rating }, seller { name }. One round-trip. One response. GraphQL wins when you're stitching data from multiple places for one view.

## What Could Go Wrong? (Mini Disaster Story)

You expose GraphQL as a public API. No limits. No complexity scoring. A malicious—or just careless—client sends a query: give me all users, each with all their orders, each order with all line items, each item with full product details, and each product with all its variants and images. One query. Nested 7 levels deep. Your database runs hundreds of joins. CPU spikes. Memory spikes. Other requests time out. Your database melts. GraphQL is flexible. That flexibility is dangerous if you don't add depth limits (max 5 levels?), query cost analysis (assign weights to fields, reject expensive queries), and rate limiting. REST's fixed endpoints protect you. GraphQL's flexibility requires gates. Add them. Or pay the price.

## Surprising Truth / Fun Fact

GraphQL was open-sourced by Facebook in 2015. Before that, the mobile app was slow. Too many REST round-trips. Too much over-fetching on 3G. GraphQL was built to fix that. "One request, exactly the data we need." It worked. Mobile load times dropped. Now it's everywhere—GitHub, Shopify, Airbnb. But it's not always the answer. Simple CRUD? REST is simpler. Caching? REST's URL-based caching is straightforward. GraphQL's single endpoint and POST bodies make caching trickier. Choose based on your data shape and client needs, not hype.

---

## Quick Recap (5 bullets)

- REST: over-fetching (get 50 fields, need 3) and under-fetching (multiple calls for one view)
- GraphQL: single endpoint, client-specified queries, exact response shape
- Good for: complex UIs, varied data needs (mobile vs web), rapid frontend iteration—change the query, not the backend
- Bad for: simple CRUD, public APIs (REST is more standard), caching (harder with POST bodies)
- Watch out: N+1 queries, malicious deep queries—add limits and complexity scoring; flexibility requires discipline

## One-Liner to Remember

*REST gives you what the server decided. GraphQL gives you what you asked for.*

Use GraphQL when your clients have varied, complex data needs and you're okay managing query complexity. Use REST when simple CRUD and wide compatibility matter more. Both are valid. Pick based on your data shape and who consumes your API.

---

## Next Video

Up next: Webhooks vs Polling—the doorbell versus checking the door every five minutes. See you there.
