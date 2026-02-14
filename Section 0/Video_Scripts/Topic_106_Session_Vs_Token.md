# When to Use Session vs Token

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

Two restaurants. Same street. Restaurant A: the waiter remembers your order. You're a regular. He nods. "The usual." No slip. No ticket. He just knows. Beautiful—until he gets sick. The replacement waiter has no idea what you ordered. Restaurant B: you get a written slip. Your order is on it. Any waiter can read it. New waiter? No problem. But if someone steals your slip, they can pretend to be you. Two strategies. Two trade-offs. Sessions and tokens work exactly like this. Let me show you when to pick each one.

---

## The Story

**Session-based auth**: The server remembers you. You log in. The server creates a session. Stores it. Gives you a session ID. From then on, the server looks you up. Like the waiter who remembers. Pros: Easy to revoke. Delete the session. Done. User is logged out everywhere. Simple. Secure—only an ID travels. The real data stays on the server. Cons: The server must store state. With multiple servers, you need a shared store (Redis) or sticky sessions. Scaling has a cost.

**Token-based auth**: The client carries the proof. You log in. The server gives you a token. The token has your info. Signed. From then on, you send the token. The server verifies. Doesn't store anything. Like the written slip. Any server can read it. Pros: Stateless. Scales easily. No shared store. Works across domains. Mobile, SPAs, microservices—tokens fit. Cons: Hard to revoke. The token is valid until it expires. If stolen, you're in trouble. Larger payload—more data in each request.

---

## Another Way to See It

Think of a gym again. Session = wristband + logbook. The gym controls the logbook. Rip the wristband? They can still revoke you in the book. Token = laminated card. No logbook. The card is the proof. Lose the card? Anyone who finds it can use it until it expires. You can't "delete" the card remotely. Two models. Session = server control. Token = client carries. Or think of a hotel. Session = the front desk has your reservation. You just say your name. They look it up. Token = you carry a voucher. Any front desk can read it. No lookup. Trade-offs. Always.

---

## Connecting to Software

**Traditional web apps** → Sessions. Server-rendered pages. Cookies. User stays in one domain. Revocation matters (banks, admin panels). Session fits. **Mobile apps** → Tokens. No cookies. Stateless APIs. Multiple devices. Tokens scale. **SPAs** (React, Vue) → Tokens common. They call APIs. No server-side session in the traditional sense. Tokens in headers. **Microservices** → Tokens. Service A calls B. B needs user context. Forward the token. No shared session store across services. **APIs** → Tokens. Third-party developers. No cookies. Token in Authorization header. Standard.

**Bank website** → Often sessions. Why? Revocation. User reports stolen phone. Bank flips a switch. All sessions killed. User must log in again. With tokens, you need short expiry + refresh tokens + refresh token revocation. Sessions make "log out everywhere" trivial. **Rules of thumb**: Need easy revocation? Sessions. Need stateless scale? Tokens. Mixed architecture? Both exist. Use the right tool.

---

## Let's Walk Through the Diagram

```
    SESSION vs TOKEN - THE TRADE-OFF

    ┌─────────────────────────────┐    ┌─────────────────────────────┐
    │       SESSION               │    │        TOKEN                │
    │  (Server Remembers)         │    │   (Client Carries)          │
    │                             │    │                             │
    │  Client ──session_id──►    │    │  Client ──full token──►     │
    │  Server                     │    │  Server                     │
    │  Server looks up session    │    │  Server verifies signature  │
    │  in Redis/DB                │    │  No lookup                  │
    │                             │    │                             │
    │  ✓ Easy revoke              │    │  ✓ Stateless                │
    │  ✓ Small cookie             │    │  ✓ Scales horizontally     │
    │  ✗ Needs shared store       │    │  ✓ Cross-domain             │
    │  ✗ Sticky or Redis          │    │  ✗ Hard to revoke           │
    │                             │    │  ✗ Larger payload           │
    └─────────────────────────────┘    └─────────────────────────────┘

    Pick based on: revocation need vs scale need
```

---

## Real-World Examples (2-3)

**Example 1: Amazon.** Traditional e-commerce. Session-based. You log in. Session cookie. Add to cart. Checkout. All session. Easy to "log out everywhere" from account settings. Fits the model.

**Example 2: Stripe API.** Third-party developers integrate. They get API keys. Tokens. Every request: Authorization: Bearer sk_live_xxx. Stateless. No sessions. Stripe doesn't know or care about "sessions." Tokens all the way.

**Example 3: Netflix.** Mobile app. You log in. Get a token. Watch on phone, tablet, TV. Each device might have its own token. Or one account, multiple tokens. No central session store for "all devices." Tokens scale. Sessions would need a massive Redis. Tokens win for this architecture.

---

## Let's Think Together

Microservices architecture. 20 services. User authenticates once at the API gateway. Each service—orders, inventory, notifications—needs to know who the user is. Sessions or tokens?

Tokens. Here's why. With sessions, the gateway would have the session. When the gateway calls Service A, Service A would need to either (a) call the gateway or a shared session store to resolve the user, or (b) receive the session ID and have access to the same store. Every service needs session store access. Complexity. With tokens, the gateway authenticates the user. Gets a token. Forwards that token to Service A. Service A verifies the token. Extracts user ID. No shared store. Service A is stateless. Same for Service B, C, D. Tokens propagate. Each service verifies independently. Stateless. Scalable. Tokens win for microservices.

---

## What Could Go Wrong? (Mini Disaster Story)

A company builds a hybrid app. Web = sessions. Mobile = tokens. Sounds fine. But they use the same backend. Session store for web. Token verification for mobile. Someone discovers: if you take a valid web session ID and put it in the Authorization header as "Bearer <session_id>", the mobile code path runs. It doesn't validate it as a JWT. It just passes through. Bug. Now the "token" is actually a session ID. It works. But session IDs aren't meant to be Bearer tokens. They're guessable. Shorter. Different security model. Chaos. The fix: separate endpoints or strict validation. Sessions and tokens are different. Don't mix the pipelines without care.

---

## Surprising Truth / Fun Fact

You can use both. Some systems use sessions for the web app—easy logout, secure—and issue short-lived JWTs for API calls from the same session. The web app has a session. When it needs to call an API, it gets a JWT from a session-backed endpoint. The JWT lasts 5 minutes. The session stays. Best of both? Sometimes. Complexity goes up. But hybrid approaches exist. It's not always either-or.

---

## Quick Recap (5 bullets)

- **Sessions**: Server stores state. Easy to revoke. Needs shared store (Redis) or sticky sessions for scale.
- **Tokens**: Client carries state. Stateless. Hard to revoke. Best for mobile, SPAs, microservices, APIs.
- **Traditional web apps, banks** → sessions (revocation matters).
- **Mobile, microservices, third-party APIs** → tokens (scale, stateless).
- **Microservices**: tokens—each service verifies independently. No shared session store.

---

## One-Liner to Remember

**Session = server remembers, easy revoke. Token = client carries, easy scale. Choose by what you need more.**

---

## Next Video

Services talking to services. How does Service B know Service A is who it claims to be? Next: **mTLS—mutual TLS**. When both sides show their ID. Coming up.
