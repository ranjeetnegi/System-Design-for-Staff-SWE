# Authentication System: Flows and Tokens

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

A secure building. Front desk. You arrive. Show your government ID (credentials). Receptionist verifies (auth server). Gives you a visitor badge (token). Every floor you visit: guard checks your badge (token validation). Badge expires at 5 PM (token expiry). If you lose the badge? Come back to the front desk (re-authenticate). Designing an auth system is designing this entire flow at scale. Let's build it together.

---

## The Story

Authentication answers: "Who are you?" Authorization answers: "What can you do?" Auth flows: login, token issuance, token validation, token refresh, logout. Each step has design choices. Session or token? Short-lived or long? Where do we store? Who validates?

The flow: user provides credentials (password, OAuth). Auth server verifies against user database. If valid, issues token. Token is the proof. User presents token to every service. Service validates. No need to go back to auth server (for stateless tokens). Or service checks session store (for stateful). Trade-offs everywhere. Design for scale. Design for security. Design for user experience.

---

## Another Way to See It

Think of a subway. You buy a ticket (authenticate once). Ticket has a time limit (token expiry). You show it at each turnstile (token validation). No need to buy again each stop. The ticket is your token. The turnstile doesn't call the ticket office. It trusts the ticket (if it's hard to forge). That's the idea: authenticate once. Token proves identity. Services trust the token. Fast. Scalable. But: what if someone steals your ticket? Token security matters.

---

## Connecting to Software

**Components.** Auth server: receives credentials, validates, issues tokens. User database: stores credentials (hashed passwords), user info. Token store: if using sessions, stores session_id → user_id. Services validate by lookup. Token validation: each service receives request with token. Validates: signature (JWT) or lookup (opaque). Grants or denies access.

**Token flow.** Login: POST /login { email, password }. Auth server: hash password, compare to DB. Match? Generate access token + refresh token. Return both. Access token: short-lived. 15 minutes. Used for API calls. Refresh token: long-lived. 7 days. Used to get new access token without re-login. Client stores both. Access in memory. Refresh in httpOnly cookie or secure storage. On 401: use refresh token. POST /refresh { refresh_token }. Get new access token. Seamless. User doesn't re-enter password.

**JWT vs opaque.** JWT: self-contained. Payload has user_id, roles, expiry. Signed. Services validate by verifying signature. No lookup. Stateless. But: can't revoke before expiry. Once issued, valid until expiration. Opaque: random string. Maps to session in database. Services validate by lookup. Revocable. Logout = delete session. But: lookup on every request. More load. Trade-off: JWT for scale, opaque for revocability. Hybrid: short-lived JWT + refresh token. Compromise.

**Validation flow.** Request arrives with Authorization: Bearer <token>. Service extracts token. If JWT: verify signature, check expiry, read user_id. Allow or deny. If opaque: lookup token in session store. Exists and valid? Allow. Fast. Cached lookups for hot tokens.

---

## Let's Walk Through the Diagram

```
AUTH SYSTEM - TOKEN FLOW
┌─────────────────────────────────────────────────────────────────┐
│                                                                  │
│   LOGIN:                                                         │
│   User ──► Credentials ──► Auth Server ──► Validate vs DB       │
│                                    │                             │
│                                    │ Valid?                      │
│                                    ▼                             │
│   User ◄── Access Token (15 min) + Refresh Token (7 days)      │
│                                                                  │
│   API REQUEST:                                                   │
│   User ──► Request + Bearer <access_token> ──► Service           │
│                                    │                             │
│                                    │ Validate token              │
│                                    │ (JWT: verify sig + expiry   │
│                                    │  Opaque: lookup session)    │
│                                    ▼                             │
│   Allow or 401                                                    │
│                                                                  │
│   REFRESH:                                                       │
│   Access token expired ──► POST /refresh + refresh_token         │
│                                    │                             │
│                                    ▼                             │
│   New access token. No password. Seamless.                       │
│                                                                  │
│   JWT = stateless, can't revoke. Opaque = revocable, needs store │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

Narrate it: Login once. Get tokens. Access token for requests. Short-lived. Refresh token for getting new access. Long-lived. Services validate. JWT: no lookup. Opaque: lookup. Logout? Delete session (opaque) or wait for expiry (JWT). Design choice. Scale vs control.

---

## Real-World Examples (2-3)

**Auth0, Okta.** Identity platforms. Handle login, token issuance, validation. OAuth, OIDC. You integrate. They manage credentials. Focus on your app. Common for enterprises.

**Google, GitHub OAuth.** Login with existing account. No password to manage. Auth server is Google/GitHub. Issues token to your app. Your app validates. Delegated auth. Huge adoption.

**Session-based (traditional).** Login. Server creates session. Stores session_id in cookie. Every request: cookie, lookup session. Valid? Continue. Logout? Delete session. Simple. Server-side state. Scales with session store (Redis).

---

## Let's Think Together

**"How do you revoke a JWT before it expires? (Hint: it's hard without a blacklist.)"**

JWT is stateless. No server-side record. Can't "delete" it. Solutions. One: blacklist. Store revoked token IDs in Redis. On validate: check blacklist. If present, reject. Adds lookup. Defeats statelessness. But works. Two: short expiry. 5 minutes. Revocation? Wait 5 minutes. Acceptable for some. Three: token version. Store user's token_version in DB. JWT includes version. Revoke = increment version. Validate: compare JWT version to DB. Adds lookup. Four: use opaque for sensitive apps. JWT for read-heavy, low-sensitivity. Opaque for banking, healthcare. Revocation is a requirement. Choose accordingly. Most real systems: short-lived JWT + refresh token. Revoke refresh token on logout. Access token expires soon anyway. Compromise.

---

## What Could Go Wrong? (Mini Disaster Story)

A company uses long-lived JWTs. 24 hours. No refresh. Developer leaves. Token still valid. They can't revoke. Ex-employee has access. Breach. Fix: short expiry. Refresh tokens. Revocable refresh token store. Logout = invalidate refresh. Access token expires in 15 min. Damage limited. Lesson: design for revocation. Assume you'll need it. Tokens will leak. Keys will rotate. Plan for it.

---

## Surprising Truth / Fun Fact

OAuth 2.0 was designed for authorization (delegate access) not authentication (prove identity). OpenID Connect (OIDC) added the auth layer on top. "Login with Google" uses OIDC. OAuth grants access. OIDC proves identity. Often confused. Both matter for auth design.

---

## Quick Recap (5 bullets)

- **Flow:** Login → validate → issue access + refresh tokens. Request → validate token → allow/deny.
- **Access token:** Short-lived (15 min). Refresh token: long-lived (7 days). Refresh gets new access.
- **JWT:** Stateless. No lookup. Can't revoke easily. Opaque: lookup. Revocable.
- **Components:** Auth server, user DB, token/session store, validation at each service.
- **Revocation:** Short expiry + revocable refresh. Or blacklist. Or opaque. Design for it.

---

## One-Liner to Remember

**Auth: prove once, token proves thereafter. Short access, long refresh. Design for revocation.**

---

## Next Video

Next: search systems. Inverted index. Index path. Query path. 50 million books in milliseconds.
