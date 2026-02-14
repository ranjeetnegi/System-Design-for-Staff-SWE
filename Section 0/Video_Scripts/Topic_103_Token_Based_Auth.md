# Token-Based Authentication: How It Works

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

Picture a different gym. No wristbands. No logbook. Instead, they hand you a laminated card. Your name is printed on it. Your membership type. Your photo. An expiry date. Every time you enter an area, the staff don't call the front desk. They don't check a book. They look at the card. The card tells them everything. It's **self-contained**. That's token-based authentication. The server gives you a token. The token carries all the info. The server never has to remember you. Let me show you how it works—and why it changes everything when you scale.

---

## The Story

The gym gives you a laminated card. "Name: Ravi. Membership: Gold. Expires: Dec 2025." You walk to the weights section. The guard looks at your card. He sees your name. He sees your membership level. He knows you're allowed. He doesn't need to call anyone. He doesn't need to check a logbook. The card is enough. That's a **token**. It carries the data. It's **stateless**—the server doesn't store anything. Any guard at any door can verify you. No central lookup. No shared memory. The token is the proof.

In software, the server creates a token when you log in. The token contains your user ID, maybe your role, an expiry time. The server signs it with a secret key—so it can't be forged. It sends the token to the client. From that moment, the client sends the token with every request—usually in an Authorization header. The server receives the token. It verifies the signature. If it's valid, it trusts the content. It knows who you are. No database lookup. No session store. Stateless. The server never had to remember you. You carried the proof.

---

## Another Way to See It

Think of a concert wristband. At the gate, they stamp it. The stamp proves you paid. Inside, every area checks the stamp. They don't call the ticket office. The stamp is the token. Self-contained. Verified on sight. Or think of a boarding pass. Your name, flight, seat. Airport staff scan it. They don't look you up in a central database every time. The pass carries the info. Token-based auth works the same way. The client holds the proof. The server verifies and trusts.

---

## Connecting to Software

The flow. Step 1: You send username and password. Step 2: The server verifies them. Step 3: The server creates a token. The token holds: user ID, role, expiry, maybe more. Step 4: The server signs the token with a secret key. Only the server knows the secret. Anyone can read the token. But only the server can create a valid signature. Step 5: The server sends the token to the client. Step 6: The client stores it—localStorage, memory, cookie. Step 7: Every API request, the client sends the token in the Authorization header. "Authorization: Bearer eyJhbGciOiJIUzI1NiIs..." Step 8: The server receives the request. It reads the token. It verifies the signature. If valid, it extracts the user ID and permissions. It processes the request. No database lookup for "who is this?" The token says it. Done.

Sessions vs tokens: Sessions = server stores state. The server has a session store. Tokens = client carries state. The server has nothing. Trade-off: tokens scale easily—any server can verify. No shared session store. But revocation is harder. If a token is stolen, how do you invalidate it? The server doesn't track it. We'll come back to that.

---

## Let's Walk Through the Diagram

```
    TOKEN-BASED AUTH (Stateless)

    ┌──────────┐    1. Login (user + pass)    ┌──────────┐
    │  CLIENT  │ ──────────────────────────► │  SERVER  │
    └──────────┘                              └────┬─────┘
         │                                        │
         │                                        │ 2. Verify
         │                                        │ 3. Create TOKEN
         │                                        │    (signed, contains user info)
         │                                        │ 4. NO storage - stateless!
         │    5. Return token                     │
         │ ◄─────────────────────────────────────┘
         │
         │  [Client stores token]
         │
         │    6. Request + Authorization: Bearer <token>
         │ ───────────────────────────────────────────►
         │                                        │
         │                                        │ 7. Verify signature
         │                                        │ 8. Extract user from token
         │                                        │    (no DB lookup!)
         │    9. Response                          │
         │ ◄──────────────────────────────────────┘

    Session: Server REMEMBERS.  Token: Client CARRIES.
```

No session store. No logbook. The token is the laminated card. Every server can verify it. Scales horizontally. Easy.

---

## Real-World Examples (2-3)

**Example 1: Mobile apps.** Apps often use tokens (JWT). User logs in once. App gets a token. App stores it. Every API call sends the token. The backend doesn't maintain sessions. Stateless. Perfect for mobile—no cookies, no shared session store across devices.

**Example 2: Microservices.** Service A calls Service B. Service B needs to know "who is the end user?" Option 1: Service A looks up the session. Option 2: Service A forwards the token. Service B verifies the token. Gets the user. No shared session store. Service B is stateless. Tokens win.

**Example 3: Single-page apps (SPAs).** React, Vue, Angular. They call APIs. No traditional server-rendered pages. Cookies work, but tokens are common. Store token in memory or localStorage. Send in header. Backend is stateless. Simple.

---

## Let's Think Together

A hacker steals your token. They have it. They can send requests with your token. The server will trust it—the signature is valid. How do you revoke it?

This is the hard part. With sessions, you delete the session from the store. Done. With tokens, the server doesn't track them. Options: (1) Short expiry. Token expires in 15 minutes. Damage window is small. (2) Refresh tokens. Access token is short-lived. Refresh token is long-lived but stored securely. When access token expires, use refresh token to get a new one. Revoke the refresh token = user must log in again. (3) Token blocklist. Store revoked token IDs in Redis. Server checks every request. "Is this token revoked?" Adds state—but only for revoked tokens. (4) Short expiry + refresh is the most common. Balance of security and simplicity.

---

## What Could Go Wrong? (Mini Disaster Story)

A company builds an API. They use long-lived tokens. Expiry: 30 days. "Users won't have to log in often. Great UX." An employee leaves. They revoke his access in the admin panel. But his token is still valid. It was already issued. It won't expire for 25 more days. He downloads customer data. He sells it. The company discovers it too late. The fix? Short-lived access tokens. Or a token blocklist. Or both. "Convenience" cost them a data breach. Tokens are powerful. But without revocation strategy, they're dangerous.

---

## Surprising Truth / Fun Fact

OAuth 2.0 access tokens are often opaque—random strings. The client doesn't read them. The resource server doesn't either. It sends the token to the authorization server: "Is this valid?" The auth server looks it up. JWT, by contrast, is self-contained. The server doesn't call anyone. It just verifies the signature. Two different token styles. Opaque = easy to revoke (auth server controls the list). JWT = stateless, no lookup, but revocation is harder. Choose based on your needs.

---

## Quick Recap (5 bullets)

- **Token-based auth** = client carries a signed token. Server verifies signature. No session store.
- **Stateless**: Server doesn't store sessions. Any server can verify. Scales easily.
- **Flow**: Login → server creates token (signed) → client sends token in header → server verifies → trusts content.
- **Trade-off**: Easy to scale, but hard to revoke. Use short expiry + refresh tokens or blocklist.
- **Best for**: Mobile apps, SPAs, microservices, APIs—where statelessness matters.

---

## One-Liner to Remember

**Session = server remembers you. Token = you carry the proof. Stateless wins for scale. Revocation is the catch.**

---

## Next Video

What's inside that token? How does the server sign it? Next: **What is JWT?**—the structure, the payload, and why you should never put your password in it. Stay tuned.
