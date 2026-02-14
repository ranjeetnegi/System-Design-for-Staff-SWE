# What Is JWT? (Structure and Use)

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

That laminated gym card—remember it? It has three parts. Part one: a header. The card type. The security stamp method. Part two: your actual info. Name. Membership level. Expiry. Part three: a tamper-proof seal. If anyone changes part two, the seal breaks. The staff can verify: "This card hasn't been modified." That's JWT. Three parts. Base64-encoded. Signed. Not encrypted. And once you understand that last part, you'll never make the mistake that breaks systems. Let me walk you through it.

---

## The Story

A JWT—JSON Web Token—has three sections, separated by dots. Header.Payload.Signature. All base64-encoded. The **header** says how the token is signed. Usually: type = JWT, algorithm = HS256 or RS256. The **payload** is the data. User ID (sub), expiry (exp), issued-at time (iat), roles, custom claims. Whatever the app needs. The **signature** is the seal. The server takes header + payload, adds a secret key, runs a hash algorithm. The result is the signature. Anyone can read the payload. Base64 is not encryption. It's encoding. But nobody can change the payload without breaking the signature. The server verifies: "Did I create this? Signature matches. Trust it." If someone edits the payload—changes user ID from 123 to 456—the signature won't match. Reject. That's how JWT prevents tampering.

---

## Another Way to See It

Think of a sealed envelope. The letter inside is readable if you open it. But the wax seal on the outside proves nobody tampered with it. JWT payload = the letter. Signature = the seal. Or a medicine bottle. The label has the info. The cap has a tamper band. Break the band, you know someone opened it. JWT: change the payload, the signature fails. Same idea. Proof of integrity. Not secrecy.

---

## Connecting to Software

Decode a JWT. Go to jwt.io. Paste a token. You'll see the header and payload—human readable. Anyone can decode them. JWT is NOT encrypted. Don't store passwords. Don't store credit card numbers. Don't store anything that must stay secret. Store: user ID, expiry, roles. Things that prove identity and permission. Things that are okay if someone reads them. The signature proves they weren't changed. That's it.

Common claims: **sub** (subject—usually user ID), **exp** (expiry—Unix timestamp), **iat** (issued at), **aud** (audience—who the token is for), **role** (user role). Use standard claims when possible. Custom claims are fine—but keep them small. Large payloads = larger tokens = more bandwidth.

---

## Let's Walk Through the Diagram

```
    JWT STRUCTURE

    eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjMiLCJleHAiOjE2MDk4NTY3ODB9.SflKxwRJS

    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
    │   HEADER   │ .  │   PAYLOAD   │ .  │  SIGNATURE  │
    │ (base64)   │    │  (base64)   │    │  (base64)   │
    └─────────────┘    └─────────────┘    └─────────────┘
           │                   │                   │
           │                   │                   │
    {"alg":"HS256",     {"sub":"123",         Server signs
     "typ":"JWT"}        "exp":1609856780}    header+payload
                           │                   with secret
                           │
                    READABLE BY ANYONE
                    NOT encrypted!
                    Signature proves
                    it wasn't changed
```

Decode the middle part. You see the payload. No secret needed. The signature is what you verify. Never trust a JWT without verifying the signature.

---

## Real-World Examples (2-3)

**Example 1: Login flows.** User logs in. Server creates JWT with sub=user_id, exp=15min. Sends to client. Client stores it. Every API call: Authorization: Bearer <jwt>. Server verifies signature, reads sub, knows the user. Simple.

**Example 2: Service-to-service.** Service A calls Service B. It has a JWT with its own service ID. Service B verifies. Knows the caller. Or Service A gets a JWT from an auth server and forwards it. The JWT carries the end-user context. Service B doesn't need to call the auth server. Stateless.

**Example 3: "Login with Google."** Google issues a JWT (or ID token). Your app receives it. Your app verifies the signature using Google's public key. It reads the payload—email, name, etc. No need to call Google on every request. The JWT is the proof.

---

## Let's Think Together

Should you store sensitive data like a password in a JWT? Why or why not?

No. Never. JWT payload is base64-encoded. Not encrypted. Anyone with the token can decode it and read the password. Even if you don't share the token, it might leak—in logs, in browser storage, in a man-in-the-middle if sent over HTTP. Passwords must be hashed and never travel in tokens. Store only what's needed for authentication and authorization: user ID, roles, expiry. If you need to pass a secret, use encryption—not JWT's default signing. JWT gives integrity. Not confidentiality.

---

## What Could Go Wrong? (Mini Disaster Story)

A developer builds an API. Uses JWT. Forgets to set expiry. The token never expires. A user's token is stolen in a phishing attack. The attacker uses it. Forever. The user changes their password. Doesn't matter—the JWT doesn't contain the password. The token is still valid. The company has no way to revoke it. No expiry. No blocklist. The attacker has permanent access. The fix? Always set short exp. Use refresh tokens for longevity. And have a revocation plan—blocklist or short-lived tokens—before you need it. "JWT doesn't expire" is a gift to attackers.

---

## Surprising Truth / Fun Fact

The "none" algorithm attack. Early JWT libraries allowed alg: "none"—meaning no signature. An attacker could change the payload, set alg to "none", and some servers would accept it. "No signature to verify? Sure, I'll trust it." Critical vulnerability. Fix: always validate that the algorithm is one you expect. Never trust alg from the token blindly. Use a library that enforces this. Old bugs, but they still exist in misconfigured systems. Also worth noting: OAuth 2.0 access tokens are often opaque—random strings the client doesn't read. JWT is the opposite: self-contained, readable. The server verifies the signature without calling anyone. Two different token styles. Opaque = easy to revoke. JWT = stateless. Choose based on your needs.

---

## Quick Recap (5 bullets)

- **JWT** = Header.Payload.Signature, base64-encoded, signed (not encrypted).
- **Payload is readable** by anyone. Don't store passwords or secrets. Store user ID, roles, expiry.
- **Signature** proves the token wasn't tampered with. Always verify before trusting.
- **Common claims**: sub (user ID), exp (expiry), iat (issued at), role. Use standard claims when possible—they're well understood and libraries expect them.
- **Always set short expiry.** Use refresh tokens for long-lived access. Never use alg: "none". A token that never expires is a permanent key in the hands of anyone who steals it.

---

## One-Liner to Remember

**JWT is signed, not encrypted. Anyone can read it. The signature proves it wasn't changed. Never put secrets inside.**

---

## Next Video

You want to let another app access your data—without giving them your password. How? **OAuth 2.0**. The valet gets the car key, not the house key. Coming up next.
