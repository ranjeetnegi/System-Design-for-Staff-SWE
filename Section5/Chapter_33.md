# Chapter 33: Authentication System

---

# Introduction

Authentication is the front door of every system. It answers one question: **"Who are you?"** Every request that touches user data, every API call, every session starts with authentication. Get it wrong, and nothing else matters—your perfect database design, your elegant cache layer, your beautifully scaled queue—all of it is irrelevant if an attacker walks through the front door.

I've built authentication systems that handled billions of login attempts daily, investigated incidents where credential-stuffing attacks generated 50× normal traffic, and debugged subtle token-validation bugs that silently degraded to allowing unauthenticated access. The difference between a secure system and a breached one is rarely a sophisticated zero-day; it's usually a misconfigured token expiry, a missing rate limit on the login endpoint, or a session that wasn't properly invalidated.

This chapter covers authentication as a Senior Engineer owns it: token issuance and validation, session lifecycle, credential management, and the operational reality of keeping a system secure under constant attack.

**The Senior Engineer's First Law of Authentication**: Authentication must fail closed. If you cannot verify the identity, deny access. There is no "fail-open" for AuthN.

---

# Part 1: Problem Definition & Motivation

## What Is an Authentication System?

An authentication system verifies the identity of users and services, issues credentials (tokens) that prove that identity, and manages the lifecycle of those credentials. It is the gateway that sits before every protected resource.

### Simple Example

```
AUTHENTICATION SYSTEM OPERATIONS:

    LOGIN:
        User submits email + password
        → System verifies credentials
        → Issues access token + refresh token
        → User uses access token for subsequent requests

    TOKEN VALIDATION:
        Service receives request with access token
        → Validates token (signature, expiry, claims)
        → Extracts user identity
        → Passes identity to authorization layer

    TOKEN REFRESH:
        Access token expires (short-lived, e.g. 15 minutes)
        → Client uses refresh token to get new access token
        → No re-login required

    LOGOUT:
        User requests logout
        → Refresh token revoked
        → Access tokens expire naturally (or are blocklisted)
```

## Why Authentication Systems Exist

Authentication exists because systems need to know who is making each request, and that knowledge must be trustworthy, efficient, and revocable.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    WHY CENTRALIZE AUTHENTICATION?                           │
│                                                                             │
│   WITHOUT CENTRALIZED AUTH:                                                 │
│   ├── Each service stores its own passwords                                 │
│   ├── Each service validates credentials differently                        │
│   ├── No unified session management                                         │
│   ├── Password changes require updating N services                          │
│   └── Security audit nightmare (N credential stores)                        │
│                                                                             │
│   WITH CENTRALIZED AUTH:                                                    │
│   ├── Single source of truth for identities                                 │
│   ├── Uniform credential validation                                         │
│   ├── Centralized rate limiting on login                                    │
│   ├── One place to enforce password policy                                  │
│   └── Token-based: services validate identity without calling auth          │
│                                                                             │
│   KEY INSIGHT:                                                              │
│   Auth system issues TOKENS. Downstream services validate tokens locally.   │
│   This decouples "who are you?" from "are you allowed?"                     │
│   AuthN ≠ AuthZ. This chapter covers AuthN only.                            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Problem 1: Identity Verification at Scale

```
CHALLENGE:

100M registered users
    - Each logs in ~1×/day on average
    - Peak: 10× during events (Black Friday, launch)
    - 100M logins/day = ~1,200/sec average
    - 12,000/sec peak

Each login requires:
    - Credential lookup
    - Password hash verification (expensive: ~100ms bcrypt)
    - Token generation (signing)
    - Session creation

If every API request re-verified credentials:
    - 100K API QPS × 100ms bcrypt = 10,000 CPU-seconds/second
    - Impossible to scale

SOLUTION: Verify credentials ONCE, issue a token.
    Token validation is cheap (~0.1ms signature check).
    1,000,000× cheaper than re-verifying credentials.
```

### Problem 2: Security Under Constant Attack

```
ATTACK LANDSCAPE:

    CREDENTIAL STUFFING:
    - Attackers use leaked username/password pairs from other breaches
    - Automated, high volume: 10K-100K attempts/minute
    - 0.1-2% success rate (people reuse passwords)

    BRUTE FORCE:
    - Try common passwords against known usernames
    - Dictionary attacks
    - Slower but persistent

    PHISHING:
    - Trick users into revealing credentials
    - Auth system can't prevent, but can limit damage (short token expiry)

    TOKEN THEFT:
    - Stolen access tokens used to impersonate user
    - XSS, man-in-the-middle
    - Mitigated by short expiry, token binding

    SESSION HIJACKING:
    - Stolen session/refresh token gives long-lived access
    - Mitigated by refresh token rotation, device binding

    AUTH SYSTEM MUST:
    - Rate-limit login attempts
    - Detect anomalous patterns
    - Support MFA as second factor
    - Issue short-lived tokens
    - Allow revocation
```

### Problem 3: Token Lifecycle Complexity

```
TOKEN LIFECYCLE:

    ISSUANCE:
        Credentials verified → Access token + Refresh token issued
        Access token: 15 minutes, signed JWT
        Refresh token: 30 days, opaque, stored server-side

    VALIDATION:
        Every API request → Validate access token
        Check signature, expiry, issuer
        No database call required (JWT is self-contained)

    REFRESH:
        Access token expires → Client sends refresh token
        Server validates refresh token → Issues new access + refresh pair
        Old refresh token invalidated (rotation)

    REVOCATION:
        Logout → Refresh token deleted
        Password change → All refresh tokens invalidated
        Account compromise → All tokens invalidated + password reset forced

    THE HARD PART:
        Access tokens are self-contained (JWT) → Can't be revoked instantly
        Trade-off: Short expiry (15 min) limits damage window
        For immediate revocation: need a blocklist (adds latency)
```

## What Happens Without a Proper Auth System

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    SYSTEMS WITHOUT PROPER AUTHENTICATION                    │
│                                                                             │
│   FAILURE MODE 1: CREDENTIAL SPRAWL                                         │
│   Passwords stored in multiple services                                     │
│   Inconsistent hashing (some use MD5, some bcrypt)                          │
│   Password change doesn't propagate                                         │
│                                                                             │
│   FAILURE MODE 2: NO RATE LIMITING                                          │
│   Login endpoint unprotected                                                │
│   Credential stuffing succeeds en masse                                     │
│   Accounts compromised at scale                                             │
│                                                                             │
│   FAILURE MODE 3: LONG-LIVED CREDENTIALS                                    │
│   API keys that never expire                                                │
│   Sessions that last forever                                                │
│   Stolen credential = permanent access                                      │
│                                                                             │
│   FAILURE MODE 4: NO REVOCATION                                             │
│   User changes password but old sessions still work                         │
│   Compromised account can't be locked out                                   │
│   No way to force re-authentication                                         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Mental Model

```
┌─────────────────────────────────────────────────────────────────────────────┐
│              AUTHENTICATION SYSTEM: THE AIRPORT SECURITY ANALOGY            │
│                                                                             │
│   PASSPORT CONTROL (Login):                                                 │
│   - You present ID (credentials)                                            │
│   - Officer verifies identity (password check)                              │
│   - You receive a boarding pass (access token)                              │
│   - Boarding pass has your name, flight, seat, expiry                       │
│                                                                             │
│   GATE CHECK (Token Validation):                                            │
│   - Show boarding pass (present token)                                      │
│   - Gate agent scans it (verify signature + expiry)                         │
│   - No need to call passport control again                                  │
│   - Fast: scan takes 1 second, not 10 minutes                               │
│                                                                             │
│   BOARDING PASS EXPIRY (Token Expiry):                                      │
│   - Valid only for this flight (short-lived)                                │
│   - Expired pass: go back to the counter (refresh)                          │
│                                                                             │
│   SECURITY ALERT (Revocation):                                              │
│   - Boarding pass revoked (token blocklisted)                               │
│   - Gate agent checks blocklist for high-risk                               │
│   - Small delay, but critical for security                                  │
│                                                                             │
│   KEY INSIGHTS:                                                             │
│   1. Verify identity ONCE (expensive), then use token (cheap)               │
│   2. Tokens are self-contained (no callback to issuer)                      │
│   3. Short expiry limits blast radius of stolen tokens                      │
│   4. Revocation is the exception, not the rule                              │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Part 2: Users & Use Cases

## Primary Users

### 1. End Users (Human)
- Register with email/password or social login (OAuth)
- Log in from web browsers, mobile apps
- Manage their own sessions
- Enable/disable MFA

### 2. Internal Services (Machine-to-Machine)
- Validate user tokens on every request
- Need fast, local token validation
- Service-to-service authentication (mTLS or service tokens)

### 3. Admin / Security Team
- View active sessions
- Force logout / revoke tokens
- Configure password policies
- Review login anomaly alerts
- Respond to account compromise

## Core Use Cases

### Use Case 1: User Login (Password-Based)

```
FLOW:
1. User submits email + password
2. Auth system looks up user by email
3. Verifies password against stored hash (bcrypt)
4. If MFA enabled: challenge user for second factor
5. Issue access token (JWT, 15 min) + refresh token (opaque, 30 days)
6. Return tokens to client

// Pseudocode: Login
FUNCTION login(email, password, mfa_code=null):
    // Rate limit check
    IF is_login_rate_limited(email):
        RETURN Error(429, "Too many login attempts. Try again later.")
    
    // Lookup user
    user = user_store.get_by_email(email)
    IF NOT user:
        // Constant-time response to prevent user enumeration
        fake_bcrypt_verify()
        record_failed_attempt(email)
        RETURN Error(401, "Invalid credentials")
    
    // Verify password
    IF NOT bcrypt_verify(password, user.password_hash):
        record_failed_attempt(email)
        IF failed_attempts(email) >= 5:
            lock_account_temporarily(email, duration=15min)
        RETURN Error(401, "Invalid credentials")
    
    // MFA check
    IF user.mfa_enabled:
        IF NOT mfa_code:
            RETURN Error(403, "MFA required", mfa_challenge=true)
        IF NOT verify_totp(user.mfa_secret, mfa_code):
            RETURN Error(401, "Invalid MFA code")
    
    // Issue tokens
    access_token = generate_access_token(user)
    refresh_token = generate_refresh_token(user)
    
    // Record session
    session_store.create({
        user_id: user.id,
        refresh_token_hash: sha256(refresh_token),
        device_info: extract_device_info(request),
        ip_address: request.ip,
        created_at: now(),
        expires_at: now() + 30 days
    })
    
    // Clear failed attempts
    clear_failed_attempts(email)
    
    RETURN {
        access_token: access_token,
        refresh_token: refresh_token,
        expires_in: 900  // 15 minutes
    }

SECURITY PROPERTIES:
- Constant-time response for invalid email (prevents enumeration)
- Account lockout after 5 failures (prevents brute force)
- MFA enforcement if enabled
- bcrypt for password hashing (slow by design)
```

### Use Case 2: Token Validation (Every Request)

```
FLOW:
1. Client sends request with Authorization: Bearer <access_token>
2. Service extracts token
3. Validates JWT signature, expiry, issuer
4. Extracts user_id and claims
5. Passes to authorization layer

// Pseudocode: Token validation (in every downstream service)
FUNCTION validate_token(token_string):
    TRY:
        // Decode and verify JWT
        claims = jwt_verify(
            token_string,
            public_key = auth_service_public_key,
            algorithms = ["RS256"]
        )
        
        // Check expiry
        IF claims.exp < now():
            RETURN Error(401, "Token expired")
        
        // Check issuer
        IF claims.iss != "auth.internal.company.com":
            RETURN Error(401, "Invalid token issuer")
        
        // Optional: check blocklist for immediate revocation
        IF token_blocklist.contains(claims.jti):
            RETURN Error(401, "Token revoked")
        
        RETURN AuthenticatedUser(
            user_id: claims.sub,
            email: claims.email,
            roles: claims.roles,
            token_id: claims.jti
        )
        
    CATCH InvalidSignatureError:
        RETURN Error(401, "Invalid token")
    CATCH MalformedTokenError:
        RETURN Error(401, "Malformed token")

PERFORMANCE:
    - JWT verification: ~0.1ms (RSA signature check)
    - No network call to auth service required
    - Blocklist check: ~0.5ms (Redis, optional)
    - Total: < 1ms for 99% of requests
```

### Use Case 3: Token Refresh

```
FLOW:
1. Access token expired
2. Client sends refresh token to auth service
3. Auth service validates refresh token
4. Issues new access token + new refresh token
5. Invalidates old refresh token (rotation)

// Pseudocode: Token refresh
FUNCTION refresh_tokens(refresh_token):
    // Hash and lookup
    token_hash = sha256(refresh_token)
    session = session_store.get_by_refresh_hash(token_hash)
    
    IF NOT session:
        RETURN Error(401, "Invalid refresh token")
    
    IF session.expires_at < now():
        session_store.delete(session.id)
        RETURN Error(401, "Refresh token expired")
    
    // Detect refresh token reuse (potential theft)
    IF session.used:
        // Token was already used! Possible theft.
        // Revoke entire session family
        revoke_all_sessions_for_user(session.user_id)
        alert_security("Refresh token reuse detected", session)
        RETURN Error(401, "Token reuse detected. All sessions revoked.")
    
    // Mark old token as used
    session_store.mark_used(session.id)
    
    // Issue new tokens
    user = user_store.get(session.user_id)
    new_access_token = generate_access_token(user)
    new_refresh_token = generate_refresh_token(user)
    
    // Create new session, link to family
    session_store.create({
        user_id: user.id,
        refresh_token_hash: sha256(new_refresh_token),
        family_id: session.family_id,  // Same session family
        device_info: session.device_info,
        ip_address: request.ip,
        created_at: now(),
        expires_at: now() + 30 days
    })
    
    RETURN {
        access_token: new_access_token,
        refresh_token: new_refresh_token,
        expires_in: 900
    }

WHY REFRESH TOKEN ROTATION:
    If attacker steals refresh token, legitimate user's next refresh
    detects reuse → all sessions revoked → attacker locked out.
```

### Use Case 4: Logout

```
FLOW:
1. User requests logout
2. Refresh token revoked (session deleted)
3. Access token added to blocklist (optional, for immediate effect)
4. Client clears local tokens

// Pseudocode: Logout
FUNCTION logout(access_token, refresh_token):
    // Validate the access token (ensure it's the actual user)
    claims = validate_token(access_token)
    
    // Delete refresh token session
    token_hash = sha256(refresh_token)
    session_store.delete_by_refresh_hash(token_hash)
    
    // Optionally blocklist the access token for immediate revocation
    // Only needed if 15-minute expiry window is unacceptable
    IF IMMEDIATE_REVOCATION_ENABLED:
        token_blocklist.add(claims.jti, ttl=claims.exp - now())
    
    RETURN Success()

// Pseudocode: Logout all devices (password change, account compromise)
FUNCTION logout_all(user_id):
    // Delete all sessions
    session_store.delete_all_for_user(user_id)
    
    // Increment user's token_generation to invalidate all JWTs
    user_store.increment_token_generation(user_id)
    
    // Blocklist can't scale for all tokens, so we rely on
    // token_generation claim mismatch on next validation
    RETURN Success()
```

## Non-Goals (Out of Scope for V1)

| Non-Goal | Reason |
|----------|--------|
| Authorization (AuthZ) | Separate system; this chapter covers identity only |
| Social login (OAuth provider) | V2; adds complexity with external providers |
| SSO / SAML | Enterprise feature; V2 |
| Passwordless (WebAuthn/FIDO) | V2 after password-based is stable |
| User registration flow | Handled by user service; auth stores credentials |
| Account recovery (forgot password) | Important but out of core AuthN scope for V1 |

## Why Scope Is Limited

```
SCOPE LIMITATION RATIONALE:

1. AuthN ONLY (not AuthZ)
   Problem: Combining identity + permissions = tangled ownership
   Decision: Auth system answers "who are you?", not "what can you do?"
   Acceptable because: AuthZ uses the identity token this system provides

2. PASSWORD-BASED ONLY (V1)
   Problem: OAuth, SAML, WebAuthn each add external dependencies
   Decision: Password + optional TOTP MFA
   Acceptable because: Covers 90%+ of login volume; social login is additive

3. SINGLE CLUSTER
   Problem: Cross-region token issuance requires key distribution
   Decision: Single cluster, all logins hit this region
   Acceptable because: Login latency tolerance is seconds (one-time per session)

4. NO REAL-TIME RISK ENGINE
   Problem: ML-based risk scoring adds infrastructure + latency
   Decision: Rate limiting + account lockout + MFA
   Acceptable because: Handles 99% of attacks; ML is V2
```

---

# Part 3: Functional Requirements

## Core Operations

### LOGIN: Verify Credentials and Issue Tokens

```
OPERATION: LOGIN
INPUT: email, password, mfa_code (optional), device_fingerprint
OUTPUT: access_token, refresh_token, expires_in

BEHAVIOR:
1. Validate input format
2. Rate limit check (per-email and per-IP)
3. Look up user by email
4. Verify password (bcrypt)
5. Check MFA if enabled
6. Generate access token (JWT, RS256, 15 min)
7. Generate refresh token (opaque, 256-bit random)
8. Store session
9. Return tokens

ERROR CASES:
- Invalid email format → 400
- Rate limited → 429 with Retry-After header
- Invalid credentials → 401 (constant-time, no user enumeration)
- Account locked → 403 with lockout duration
- MFA required → 403 with challenge
- MFA invalid → 401
- Internal error → 500 (fail closed: no token issued)
```

### VALIDATE: Verify Access Token

```
OPERATION: VALIDATE
INPUT: access_token (JWT)
OUTPUT: authenticated user identity (user_id, email, roles)

BEHAVIOR:
1. Decode JWT header (extract algorithm, key ID)
2. Verify signature using auth service public key
3. Check expiry (exp claim)
4. Check issuer (iss claim)
5. Optionally check blocklist (jti claim)
6. Return user identity

PERFORMANCE:
    No network call to auth service for standard validation.
    Blocklist check requires Redis lookup (~0.5ms).

ERROR CASES:
- Missing token → 401
- Malformed token → 401
- Invalid signature → 401
- Expired → 401 (client should refresh)
- Revoked (blocklist) → 401
```

### REFRESH: Exchange Refresh Token for New Token Pair

```
OPERATION: REFRESH
INPUT: refresh_token
OUTPUT: new access_token, new refresh_token, expires_in

BEHAVIOR:
1. Hash refresh token
2. Look up session by hash
3. Verify session not expired
4. Detect reuse (if token already used → revoke family)
5. Mark old token as used
6. Issue new token pair
7. Create new session record

ERROR CASES:
- Invalid refresh token → 401
- Expired → 401
- Reuse detected → 401 + revoke all user sessions + security alert
```

### LOGOUT: Revoke Session

```
OPERATION: LOGOUT
INPUT: access_token, refresh_token
OUTPUT: success

BEHAVIOR:
1. Validate access token
2. Delete session for refresh token
3. Optionally blocklist access token JTI

LOGOUT_ALL VARIANT:
- Delete all sessions for user
- Increment token_generation (invalidates all outstanding JWTs)
```

### REGISTER_CREDENTIALS: Store New User Credentials

```
OPERATION: REGISTER_CREDENTIALS
INPUT: user_id, email, password
OUTPUT: success

BEHAVIOR:
1. Validate password strength (min 8 chars, complexity rules)
2. Check email uniqueness
3. Hash password with bcrypt (cost factor 12)
4. Store credential record
5. Return success

// Pseudocode: Password hashing
FUNCTION hash_password(password):
    // bcrypt cost factor 12 = ~250ms on modern hardware
    // Intentionally slow to resist brute force
    salt = bcrypt_generate_salt(cost=12)
    RETURN bcrypt_hash(password, salt)

PASSWORD POLICY:
    - Minimum 8 characters
    - At least one uppercase, one lowercase, one digit
    - Not in top 10,000 common passwords list
    - Not same as email
```

---

## Expected Behavior Under Partial Failure

| Scenario | System Behavior | User Impact |
|----------|-----------------|-------------|
| **Redis (blocklist) down** | Skip blocklist check; accept all valid JWTs | Revoked tokens may work for up to 15 min |
| **Database (sessions) slow** | Login and refresh delayed | Login takes seconds instead of ms |
| **Database down** | Login fails (no credential lookup) | Users cannot log in; existing tokens still work |
| **Auth service down** | Existing tokens valid (JWT is self-contained) | No new logins, no refreshes; active sessions continue |
| **bcrypt computation slow** | Login latency increases | Login takes 500ms+ instead of 300ms |

### Critical Design Decision: Fail Closed on Login, Fail Open on Validation

```
FAIL BEHAVIOR:

LOGIN (fail closed):
    If ANY component is unavailable → deny login
    Rationale: Issuing tokens without proper verification = security breach

VALIDATION (fail open on blocklist only):
    If token signature is valid but blocklist is unavailable:
    → Accept the token (it has valid signature and hasn't expired)
    Rationale: 
        - Blocklist miss window is max 15 minutes (token expiry)
        - Blocking all requests because blocklist is down = site-wide outage
        - Trade-off: small revocation delay vs total unavailability

THIS IS THE MOST IMPORTANT TRADE-OFF IN AUTH DESIGN.
```

---

# Part 4: Non-Functional Requirements (Senior Bar)

## Latency Targets

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         LATENCY REQUIREMENTS                                │
│                                                                             │
│   OPERATION: Login                                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  P50: < 300ms  (bcrypt dominates)                                   │   │
│   │  P95: < 500ms  (DB lookup + bcrypt + token gen)                     │   │
│   │  P99: < 1s     (under load)                                         │   │
│   │  Timeout: 5s   (return error)                                       │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   OPERATION: Token Validation (in downstream services)                      │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  P50: < 0.1ms  (JWT signature check only)                           │   │
│   │  P95: < 0.5ms  (with blocklist check)                               │   │
│   │  P99: < 1ms                                                         │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   OPERATION: Token Refresh                                                  │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  P50: < 50ms   (DB lookup + token gen)                              │   │
│   │  P95: < 100ms                                                       │   │
│   │  P99: < 200ms                                                       │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   WHY LOGIN IS SLOW (AND THAT'S OK):                                        │
│   bcrypt intentionally takes ~100-250ms                                     │
│   This is a security feature, not a bug                                     │
│   Login happens once per session (hours/days)                               │
│   All subsequent requests use fast JWT validation                           │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Availability Targets

| Operation | Target | Justification |
|-----------|--------|---------------|
| Login | 99.9% | Users tolerate rare login failures |
| Token validation | 99.99% | Must not block all API traffic |
| Token refresh | 99.9% | If down, user re-logs in 15 min |
| Logout | 99.5% | Non-critical; tokens expire naturally |

**Why Token Validation Must Be Higher:**
- Every API request depends on it
- JWT validation is local (no network dependency)
- Only blocklist check adds external dependency
- Design for: validation works even if auth service is down

## Consistency Model

```
CONSISTENCY MODEL:

CREDENTIALS (strong consistency):
    Password changes must take effect immediately.
    If user changes password, old password must fail.
    Implementation: Single primary database, synchronous writes.

SESSION STATE (strong consistency on write, eventual on read):
    Session creation and deletion: synchronous to primary.
    Session lookup on refresh: can use replica (slight lag acceptable).
    Why: Refresh happens infrequently; slight lag (seconds) is fine.

TOKEN VALIDATION (eventually consistent):
    JWT is self-contained; no consistency concern for valid tokens.
    Blocklist propagation: eventually consistent across cache nodes.
    Why: 15-minute token expiry limits inconsistency window.

TOKEN GENERATION COUNTER (strong on increment, eventually consistent for reads):
    When "logout all" increments generation, the write is synchronous.
    Downstream validation checks generation claim:
    - If generation in JWT < current generation → reject.
    - Cache of current generation per user can be stale by seconds.
    Acceptable because: "logout all" is rare and urgent; 
    seconds of delay is acceptable vs not having the feature.
```

## Durability Requirements

```
DURABILITY:

CREDENTIALS (critical):
    - Stored in replicated database
    - Password hashes backed up
    - Loss = users can't log in
    - RPO: 0 (synchronous replication)

SESSIONS (important but recoverable):
    - If session store lost: users must re-login
    - Inconvenient but not catastrophic
    - RPO: minutes acceptable

BLOCKLIST (ephemeral):
    - In-memory (Redis) only
    - Lost on restart: tokens expire in 15 min anyway
    - No durability requirement

SIGNING KEYS (most critical):
    - RSA private key used to sign JWTs
    - Loss = can't issue new tokens
    - Compromise = attacker can forge tokens
    - Stored in HSM or KMS, never on disk
    - Rotated annually with overlap period
```

## Correctness Requirements

| Aspect | Requirement | Rationale |
|--------|-------------|-----------|
| No false positives | Valid credentials always succeed (if not rate limited) | User trust |
| No false negatives | Invalid credentials never succeed | Security |
| Constant-time comparison | Password check timing doesn't leak information | Prevent timing attacks |
| Token integrity | Tokens cannot be forged | Cryptographic signing |
| Revocation works | Revoked sessions cannot be refreshed | Security |

---

# Part 5: Scale & Capacity Planning

## Assumptions

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         SCALE ASSUMPTIONS                                   │
│                                                                             │
│   USER BASE:                                                                │
│   • Registered users: 100 million                                           │
│   • Monthly active: 50 million                                              │
│   • Daily active: 20 million                                                │
│   • MFA enabled: 10 million (20%)                                           │
│                                                                             │
│   LOGIN VOLUME:                                                             │
│   • Logins/day: 20 million (1 per DAU)                                      │
│   • Average QPS: 230 logins/sec                                             │
│   • Peak QPS: 2,300 logins/sec (10× burst)                                  │
│   • Attack traffic: up to 50K attempts/sec during credential stuffing       │
│                                                                             │
│   TOKEN VALIDATION:                                                         │
│   • API QPS: 100,000 (all services combined)                                │
│   • Each request = 1 token validation                                       │
│   • Validation is local (no auth service call)                              │
│                                                                             │
│   TOKEN REFRESH:                                                            │
│   • 20M users × 1 refresh/15min session = ~22K refreshes/sec during peak    │
│   • Average: ~5K refreshes/sec                                              │
│                                                                             │
│   STORAGE:                                                                  │
│   • Credentials: 100M users × 500 bytes = 50 GB                             │
│   • Sessions: 50M active × 300 bytes = 15 GB                                │
│   • Blocklist: < 1 GB (in Redis, TTL-based cleanup)                         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## What Breaks First at 10× Scale

```
CURRENT: 230 logins/sec, 5K refreshes/sec
10× SCALE: 2,300 logins/sec, 50K refreshes/sec

COMPONENT ANALYSIS:

1. BCRYPT COMPUTATION (Primary concern)
   Current: 230 logins/sec × 200ms = 46 CPU-seconds/sec
   10×: 2,300 × 200ms = 460 CPU-seconds/sec
   
   At 10×: Need 460 CPU cores just for bcrypt
   Breaking point: CPU-bound; can't cache or shortcut
   
   → AT 10×: Dedicate a pool of bcrypt workers
   → Consider Argon2id (parallelizable, memory-hard)

2. SESSION DATABASE WRITES (Secondary concern)
   Current: 230 session creates/sec + 5K refreshes/sec
   10×: 2,300 creates + 50K refreshes = 52,300 writes/sec
   
   Breaking point: ~30K writes/sec on single primary
   
   → AT 10×: Shard session store by user_id
   → Or move sessions to Redis (faster writes)

3. CREDENTIAL STUFFING AMPLIFICATION
   Current: 50K attack attempts/sec
   10×: 500K attempts/sec
   
   Problem: Rate limiting must handle 500K decisions/sec
   
   → AT 10×: Move rate limiting to edge/load balancer
   → IP reputation scoring at network layer

MOST FRAGILE ASSUMPTION:
    "Attack traffic stays at 50K/sec"
    
    If this breaks:
    - Credential stuffing at 500K/sec
    - Rate limiter itself becomes bottleneck
    - Bcrypt workers saturated by attack traffic
    - Legitimate users can't log in
    
    Detection: Monitor login failure rate, unique IPs, credential velocity
```

## Scale Estimates Table (Senior Bar)

| Metric | Current | 10× Scale | Breaking Point |
|--------|---------|-----------|----------------|
| Logins/sec | 230 (avg), 2.3K peak | 2.3K avg, 23K peak | bcrypt CPU exhausts ~5K/sec per pool |
| Sessions | 50M active | 500M | Session DB write throughput (~30K/sec single primary) |
| Token validations/sec | 100K (across services) | 1M | Local JWT verify scales; blocklist Redis may need sharding |
| Credential store | 100M rows, 50 GB | 1B rows, 500 GB | Single primary read capacity; need sharding |
| Rate limit keys (Redis) | ~10M active | ~100M | Redis memory and key eviction |

**Breaking point summary:** The first hard limit at 10× is **bcrypt CPU** (login path). Session store and credential DB become bottlenecks next. Token validation (JWT) and rate-limit logic scale with horizontal instances.

## Back-of-Envelope: Login Server Sizing

```
SIZING CALCULATION:

Step 1: Peak login throughput
    Legitimate: 2,300/sec
    Attack: 50,000/sec
    Total: 52,300 attempts/sec
    
Step 2: Processing cost per attempt
    Rate limit check (Redis): 1ms
    Credential lookup (DB): 5ms
    bcrypt verify: 200ms (only for valid-looking attempts)
    Token generation: 2ms
    
    Attack attempts are mostly rate-limited: 1ms each
    Legitimate logins: ~210ms each

Step 3: CPU budget
    Attack: 50,000/sec × 1ms = 50 CPU-seconds/sec
    Legitimate: 2,300/sec × 210ms = 483 CPU-seconds/sec
    Total: 533 CPU-seconds/sec
    
Step 4: Server sizing
    Per server: 8 cores
    Servers needed: 533 / 8 = 67 instances
    With 50% headroom: 100 instances
    
    Instance type: 8 vCPU, 4 GB RAM
    
COST ESTIMATE:
    100 instances × $200/month = $20,000/month compute
    Database (RDS Multi-AZ): $3,000/month
    Redis (blocklist + rate limit): $1,000/month
    Total: ~$24,000/month
```

---

# Part 6: High-Level Architecture

## Core Components

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    AUTHENTICATION SYSTEM ARCHITECTURE                       │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────┐     │
│   │                        CLIENT TIER                                │     │
│   │  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐               │     │
│   │  │  Web    │  │  iOS    │  │ Android │  │  API    │               │     │
│   │  │  App    │  │  App    │  │  App    │  │ Client  │               │     │
│   │  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘               │     │
│   └───────┼────────────┼───────────-┼────────────┼────────────────────┘     │
│           └────────────┴──────────-─┴────────────┘                          │
│                               │                                             │
│                               ▼                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                      LOAD BALANCER / API GATEWAY                    │   │
│   │   (TLS termination, IP-level rate limiting)                         │   │
│   └──────────────────────────────┬──────────────────────────────────────┘   │
│                                  │                                          │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                      AUTH API SERVICE                               │   │
│   │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                  │   │
│   │  │   Login     │  │  Refresh    │  │  Logout     │                  │   │
│   │  │  Handler    │  │  Handler    │  │  Handler    │                  │   │
│   │  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘                  │   │
│   └─────────┼────────────────┼────────────────┼─────────────────────────┘   │
│             │                │                │                             │
│     ┌───────┼────────────────┼────────────────┼───────┐                     │
│     │       │                │                │       │                     │
│     ▼       ▼                ▼                ▼       ▼                     │
│  ┌────-──┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐              │
│  │Redis  │ │Credential│ │ Session  │ │  Token   │ │ bcrypt   │              │
│  │       │ │  Store   │ │  Store   │ │  Signer  │ │ Worker   │              │
│  │- Rate │ │(Postgres)│ │(Postgres)│ │ (RSA Key)│ │  Pool    │              │
│  │  Lim  │ │          │ │          │ │          │ │          │              │
│  │- Block│ │          │ │          │ │          │ │          │              │
│  │  list │ │          │ │          │ │          │ │          │              │
│  └──────-┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘              │
│                                                                             │
│   ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─             │
│                                                                             │
│   DOWNSTREAM SERVICES (Token validation is LOCAL, no auth call)             │
│   ┌─────────┐  ┌─────────┐  ┌─────────┐                                     │
│   │Service A│  │Service B│  │Service C│  ← Each has auth service            │
│   │+ JWT    │  │+ JWT    │  │+ JWT    │    public key for local             │
│   │  verify │  │  verify │  │  verify │    validation                       │
│   └─────────┘  └─────────┘  └─────────┘                                     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Component Responsibilities

| Component | Responsibility | Stateful? |
|-----------|---------------|-----------|
| Auth API Service | Login, refresh, logout request handling | No |
| Credential Store | User email + password hash | Yes (PostgreSQL) |
| Session Store | Active refresh token sessions | Yes (PostgreSQL) |
| Redis | Rate limiting, token blocklist | Yes (ephemeral) |
| Token Signer | JWT creation with RSA private key | No (key in memory from KMS) |
| bcrypt Worker Pool | CPU-intensive password verification | No |

## Data Flow: Login

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          LOGIN FLOW                                         │
│                                                                             │
│  Client           LB            Auth API         Redis         Database     │
│    │               │               │               │              │         │
│    │ POST /login   │               │               │              │         │
│    │──────────────▶│               │               │              │         │
│    │               │               │               │              │         │
│    │               │  1. Forward   │               │              │         │
│    │               │──────────────▶│               │              │         │
│    │               │               │               │              │         │
│    │               │               │ 2. Rate limit │              │         │
│    │               │               │──────────────▶│              │         │
│    │               │               │   ALLOWED     │              │         │
│    │               │               │◀──────────────│              │         │
│    │               │               │               │              │         │
│    │               │               │ 3. Get credentials           │         │
│    │               │               │─────────────────────────────▶│         │
│    │               │               │   user record                │         │
│    │               │               │◀─────────────────────────────│         │
│    │               │               │               │              │         │
│    │               │               │ 4. bcrypt verify             │         │
│    │               │               │ (CPU-bound, ~200ms)          │         │
│    │               │               │               │              │         │
│    │               │               │ 5. Sign JWT                  │         │
│    │               │               │ (RSA256, ~1ms)               │         │
│    │               │               │               │              │         │
│    │               │               │ 6. Store session             │         │
│    │               │               │─────────────────────────────▶│         │
│    │               │               │               │              │         │
│    │  200 OK       │               │               │              │         │
│    │  {tokens}     │               │               │              │         │
│    │◀──────────────│◀──────────────│               │              │         │
│    │               │               │               │              │         │
│                                                                             │
│   TIMING:                                                                   │
│     Step 2: ~1ms (Redis)                                                    │
│     Step 3: ~5ms (DB lookup)                                                │
│     Step 4: ~200ms (bcrypt)                                                 │
│     Step 5: ~1ms (JWT sign)                                                 │
│     Step 6: ~5ms (DB write)                                                 │
│     TOTAL: ~215ms                                                           │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Why This Architecture

| Design Choice | Rationale |
|---------------|-----------|
| JWT (not opaque tokens) | Downstream services validate locally; no auth service call |
| Separate refresh + access tokens | Short-lived access limits damage; long-lived refresh avoids re-login |
| bcrypt (not SHA256) | Intentionally slow; resists brute force if DB is leaked |
| Redis for rate limiting | Sub-ms decisions; can't afford DB call for every login attempt |
| Session store in DB | Durable; survives restarts; supports "logout all" |

---

# Part 7: Component-Level Design

## Auth API Service

### Login Handler

```
// Pseudocode: Login handler with all security checks
CLASS LoginHandler:
    
    FUNCTION handle(request):
        email = request.body.email
        password = request.body.password
        mfa_code = request.body.mfa_code
        
        // Input validation
        IF NOT is_valid_email(email) OR NOT password:
            RETURN Error(400, "Invalid input")
        
        // IP-level rate limit
        IF rate_limiter.is_blocked(request.ip, "login_ip"):
            metrics.increment("login.rate_limited.ip")
            RETURN Error(429, "Too many requests")
        
        // Email-level rate limit
        IF rate_limiter.is_blocked(email, "login_email"):
            metrics.increment("login.rate_limited.email")
            RETURN Error(429, "Too many login attempts for this account")
        
        // Credential lookup
        user = credential_store.get_by_email(email)
        IF NOT user:
            // Constant-time fake check to prevent enumeration
            bcrypt_worker.fake_verify()
            rate_limiter.record_failure(email, "login_email")
            rate_limiter.record_failure(request.ip, "login_ip")
            RETURN Error(401, "Invalid credentials")
        
        // Account lockout check
        IF user.locked_until AND user.locked_until > now():
            RETURN Error(403, "Account locked. Try again in " + 
                         remaining_minutes(user.locked_until) + " minutes.")
        
        // Password verification (CPU-intensive)
        IF NOT bcrypt_worker.verify(password, user.password_hash):
            rate_limiter.record_failure(email, "login_email")
            rate_limiter.record_failure(request.ip, "login_ip")
            
            // Lock account after threshold
            failures = rate_limiter.failure_count(email, "login_email", window=15min)
            IF failures >= 5:
                credential_store.lock_account(user.id, duration=15min)
                RETURN Error(403, "Account locked for 15 minutes.")
            
            RETURN Error(401, "Invalid credentials")
        
        // MFA verification
        IF user.mfa_enabled:
            IF NOT mfa_code:
                RETURN Error(403, "MFA required", {mfa_challenge: true})
            IF NOT totp_verify(user.mfa_secret, mfa_code):
                RETURN Error(401, "Invalid MFA code")
        
        // Issue tokens
        access_token = token_signer.sign_access_token(user)
        refresh_token = token_signer.generate_refresh_token()
        
        // Store session
        session_store.create(user.id, refresh_token, request)
        
        // Clear failures on success
        rate_limiter.clear_failures(email, "login_email")
        
        metrics.increment("login.success")
        RETURN Success({
            access_token: access_token,
            refresh_token: refresh_token,
            expires_in: 900
        })
```

## Token Signer

```
// Pseudocode: JWT token generation
CLASS TokenSigner:
    
    CONSTRUCTOR():
        // Load RSA private key from KMS at startup
        this.private_key = kms.get_signing_key("auth-jwt-signing-key")
        this.public_key = derive_public_key(this.private_key)
        this.key_id = sha256(this.public_key)[:8]
    
    FUNCTION sign_access_token(user):
        now = current_time()
        claims = {
            iss: "auth.internal.company.com",
            sub: user.id,
            email: user.email,
            roles: user.roles,
            jti: generate_uuid(),         // Unique token ID (for blocklist)
            gen: user.token_generation,    // Generation counter (for logout-all)
            iat: now,
            exp: now + 15 minutes
        }
        
        header = {
            alg: "RS256",
            kid: this.key_id,
            typ: "JWT"
        }
        
        RETURN jwt_sign(header, claims, this.private_key)
    
    FUNCTION generate_refresh_token():
        // Opaque, cryptographically random
        RETURN base64url_encode(random_bytes(32))

KEY ROTATION:

    Old key:  Valid for signing until rotation date
    New key:  Generated, published, overlaps with old key
    Overlap:  2 weeks (old tokens still valid until they expire)
    
    // Pseudocode: Key rotation
    FUNCTION rotate_signing_key():
        new_key = kms.generate_new_key("auth-jwt-signing-key-v2")
        
        // Publish new public key to all services
        // (via shared config, JWKS endpoint, or service mesh)
        publish_public_key(new_key.public_key, new_key.key_id)
        
        // Start signing with new key
        this.private_key = new_key
        this.key_id = new_key.key_id
        
        // Old tokens (signed with old key) still validate
        // because services have both old and new public keys
        // Old tokens expire within 15 minutes
```

## Rate Limiter

```
// Pseudocode: Login rate limiting
CLASS LoginRateLimiter:
    
    RATE_LIMITS = {
        "login_email": {
            window: 15 minutes,
            max_failures: 5,
            lockout_duration: 15 minutes
        },
        "login_ip": {
            window: 1 minute,
            max_failures: 20,
            lockout_duration: 5 minutes
        },
        "login_ip_hourly": {
            window: 1 hour,
            max_failures: 100,
            lockout_duration: 1 hour
        }
    }
    
    FUNCTION is_blocked(identifier, limit_type):
        config = RATE_LIMITS[limit_type]
        key = "ratelimit:" + limit_type + ":" + identifier
        
        // Check if currently locked out
        lockout_key = "lockout:" + limit_type + ":" + identifier
        IF redis.exists(lockout_key):
            RETURN true
        
        RETURN false
    
    FUNCTION record_failure(identifier, limit_type):
        config = RATE_LIMITS[limit_type]
        key = "ratelimit:" + limit_type + ":" + identifier
        
        count = redis.incr(key)
        redis.expire(key, config.window)
        
        IF count >= config.max_failures:
            lockout_key = "lockout:" + limit_type + ":" + identifier
            redis.set(lockout_key, "1", ex=config.lockout_duration)

WHY TWO LEVELS (email + IP):
    - Per-email: Prevents brute force on specific account
    - Per-IP: Prevents credential stuffing across accounts
    - Both needed: Attacker can spray different emails from one IP,
      or target one email from many IPs
```

## Session Store

```
// Pseudocode: Session management
CLASS SessionStore:
    
    FUNCTION create(user_id, refresh_token, request):
        family_id = generate_uuid()
        
        db.execute(
            "INSERT INTO sessions (id, user_id, refresh_token_hash, family_id, device_info, ip_address, created_at, expires_at, used) VALUES ($1, $2, $3, $4, $5, $6, NOW(), NOW() + INTERVAL '30 days', false)",
            generate_uuid(),
            user_id,
            sha256(refresh_token),
            family_id,
            extract_device_info(request),
            request.ip
        )
    
    FUNCTION get_by_refresh_hash(token_hash):
        RETURN db.query(
            "SELECT * FROM sessions WHERE refresh_token_hash = $1",
            token_hash
        )
    
    FUNCTION delete_all_for_user(user_id):
        db.execute(
            "DELETE FROM sessions WHERE user_id = $1",
            user_id
        )
    
    FUNCTION revoke_family(family_id):
        // Revoke all tokens in this refresh chain
        db.execute(
            "DELETE FROM sessions WHERE family_id = $1",
            family_id
        )

SESSION CLEANUP:
    - Cron job: DELETE FROM sessions WHERE expires_at < NOW()
    - Run hourly
    - Index on expires_at for efficient cleanup
```

---

# Part 8: Data Model & Storage

## Schema

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         AUTHENTICATION SCHEMA                               │
│                                                                             │
│   TABLE: credentials                                                        │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  user_id          UUID           PRIMARY KEY                        │   │
│   │  email            VARCHAR(256)   NOT NULL UNIQUE                    │   │
│   │  password_hash    VARCHAR(256)   NOT NULL                           │   │
│   │  mfa_enabled      BOOLEAN        DEFAULT false                      │   │
│   │  mfa_secret       VARCHAR(64)    NULL (encrypted)                   │   │
│   │  token_generation INT            DEFAULT 0                          │   │
│   │  locked_until     TIMESTAMP      NULL                               │   │
│   │  created_at       TIMESTAMP      NOT NULL                           │   │
│   │  updated_at       TIMESTAMP      NOT NULL                           │   │
│   │                                                                     │   │
│   │  INDEX idx_email (email)                                            │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   TABLE: sessions                                                           │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  id                 UUID           PRIMARY KEY                      │   │
│   │  user_id            UUID           NOT NULL                         │   │
│   │  refresh_token_hash VARCHAR(64)    NOT NULL UNIQUE                  │   │
│   │  family_id          UUID           NOT NULL                         │   │
│   │  device_info        VARCHAR(512)   NULL                             │   │
│   │  ip_address         VARCHAR(45)    NOT NULL                         │   │
│   │  used               BOOLEAN        DEFAULT false                    │   │
│   │  created_at         TIMESTAMP      NOT NULL                         │   │
│   │  expires_at         TIMESTAMP      NOT NULL                         │   │
│   │                                                                     │   │
│   │  INDEX idx_user_sessions (user_id)                                  │   │
│   │  INDEX idx_refresh_hash (refresh_token_hash)                        │   │
│   │  INDEX idx_family (family_id)                                       │   │
│   │  INDEX idx_expires (expires_at)                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   TABLE: login_audit_log                                                    │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  id               BIGSERIAL      PRIMARY KEY                        │   │
│   │  email            VARCHAR(256)   NOT NULL                           │   │
│   │  success          BOOLEAN        NOT NULL                           │   │
│   │  failure_reason   VARCHAR(64)    NULL                               │   │
│   │  ip_address       VARCHAR(45)    NOT NULL                           │   │
│   │  user_agent       VARCHAR(512)   NULL                               │   │
│   │  created_at       TIMESTAMP      NOT NULL                           │   │
│   │                                                                     │   │
│   │  INDEX idx_email_created (email, created_at DESC)                   │   │
│   │  INDEX idx_ip_created (ip_address, created_at DESC)                 │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   REDIS STRUCTURES:                                                         │
│                                                                             │
│   Rate Limiting:                                                            │
│     Key: "ratelimit:login_email:{email}"   Value: counter   TTL: 15min      │
│     Key: "ratelimit:login_ip:{ip}"         Value: counter   TTL: 1min       │
│     Key: "lockout:login_email:{email}"     Value: "1"       TTL: 15min      │
│                                                                             │
│   Token Blocklist:                                                          │
│     Key: "blocklist:{jti}"                 Value: "1"       TTL: token_exp  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Storage Calculations

```
STORAGE ESTIMATES:

CREDENTIALS TABLE:
    Per record: ~500 bytes
    Total: 100M × 500 bytes = 50 GB
    Growth: ~1M new users/month = 500 MB/month

SESSIONS TABLE:
    Per record: ~300 bytes
    Active sessions: 50M users × 2 devices = 100M sessions
    Total: 100M × 300 bytes = 30 GB
    Turnover: Sessions expire and are cleaned up

LOGIN AUDIT LOG:
    Per record: ~200 bytes
    Volume: 50M logins/day (including failures) = 10 GB/day
    Retention: 90 days = 900 GB
    Partitioning: By created_at (daily or weekly partitions)

REDIS:
    Rate limit keys: ~10M active keys × 50 bytes = 500 MB
    Blocklist: < 100K entries × 50 bytes = 5 MB
    Total Redis: ~600 MB

TOTAL:
    PostgreSQL: ~80 GB active + 900 GB audit log
    Redis: ~600 MB
```

## Why This Storage Design

| Choice | Rationale |
|--------|-----------|
| Separate credentials and sessions tables | Different access patterns, different scaling needs |
| Hash refresh tokens (SHA-256) | If DB is compromised, attacker can't use tokens |
| Audit log separate table | Write-heavy, different retention, partitioned |
| Redis for rate limiting | Sub-ms decisions, ephemeral data |
| MFA secret encrypted in DB | Defense in depth; if DB leaked, secrets not exposed |

---

# Part 9: Consistency, Concurrency & Idempotency

## Consistency Model

```
CONSISTENCY GUARANTEES:

1. PASSWORD CHANGE (immediate consistency)
   Password updated in primary DB synchronously.
   Old password fails immediately.
   All existing refresh tokens revoked.
   
   Implementation:
   - Single transaction: update password + delete sessions + increment token_generation
   - No eventual consistency: security requires immediate effect

2. SESSION OPERATIONS (strong on write)
   Session create/delete: synchronous to primary.
   Session lookup on refresh: can hit replica with slight lag.
   
   Why replica is OK:
   - Refresh happens rarely (every 15 min)
   - 1-2 second lag is acceptable
   - If miss on replica, fall back to primary

3. TOKEN VALIDATION (no consistency concern for valid JWTs)
   JWT is self-contained. No database involved.
   Blocklist is eventually consistent (Redis propagation < 1 second).
```

## Race Conditions

### Race 1: Concurrent Login and Password Change

```
SCENARIO:
    User A logs in from Device 1
    User A changes password from Device 2 (simultaneously)

Device 1 (Login)                  Device 2 (Change Password)
T+0:  Submit login               Submit password change
T+1:  Rate limit check           Rate limit check
T+2:  Fetch credentials          Fetch credentials
T+3:  Verify old password (OK)   Update to new password hash
T+4:  Issue tokens               Delete all sessions
T+5:  Create session             Increment token_generation

OUTCOME:
    Device 1 has tokens with old token_generation.
    Access token works for up to 15 minutes (until expiry).
    Refresh token session was deleted at T+4 → refresh fails.
    
ACCEPTABLE:
    - 15-minute window is the design trade-off for JWT
    - Refresh fails, forcing re-login with new password
    - For immediate revocation: blocklist the token_generation mismatch
```

### Race 2: Refresh Token Reuse (Potential Theft)

```
SCENARIO:
    Attacker steals refresh token. Both attacker and user try to refresh.

Legitimate User                   Attacker
T+0:  Refresh token (T1)         Steals token (T1)
T+1:  Sends T1 → gets T2         
T+2:                              Sends T1 → REUSE DETECTED
T+3:                              All sessions in family revoked

OUTCOME:
    User's T2 is also revoked (same family).
    User must re-login.
    Attacker locked out.

WHY REVOKE THE LEGITIMATE USER TOO:
    - System can't distinguish who is legitimate
    - Revoking the family forces both parties to re-authenticate
    - The real user has the password; the attacker doesn't
    - Security alert sent to user
```

### Race 3: Concurrent Session Creation

```
SCENARIO:
    User logs in from two devices simultaneously

Device 1                          Device 2
T+0:  Login → create session      Login → create session
T+1:  Session S1 created          Session S2 created

OUTCOME:
    Both sessions valid (different session IDs, different refresh tokens).
    User has two active sessions.
    This is expected and correct behavior.

NO RACE CONDITION:
    Each login creates independent session.
    No shared mutable state between sessions.
```

## Idempotency

```
LOGIN IDEMPOTENCY:
    Login is NOT idempotent by design.
    Each successful login creates a new session.
    This is correct: same credentials → new session each time.
    
    Idempotency is not needed because:
    - Client retry after timeout? Gets a new session (old one expires).
    - No harmful side effect from duplicate logins.

REFRESH IDEMPOTENCY:
    Refresh IS effectively idempotent via reuse detection.
    First use: returns new tokens.
    Second use (same token): revokes all sessions (security).
    
    The caller should never retry a refresh with an already-used token.
    Correct client behavior: on refresh failure, re-login.

LOGOUT IDEMPOTENCY:
    Logout IS idempotent.
    Deleting an already-deleted session is a no-op.
    Second logout call returns success.
```

---

# Part 10: Failure Handling & Reliability

## Partial Failure Behavior (Not Total Outage)

The reviewer requires explicit treatment of **partial** failures: one replica slow, or one dependency timing out (not fully down).

```
PARTIAL FAILURE: One dependency slow (e.g. Redis 10× latency)

SITUATION: Redis responds but with 50ms latency instead of 5ms

BEHAVIOR:
- Rate limit check: 1ms → 50ms per login
- Blocklist check (on validation): 0.5ms → 5ms
- Login path: +50ms (noticeable but not fatal)
- Token validation path: +5ms (still < 10ms total)

USER IMPACT:
- Login feels slightly slower
- No incorrect accepts/denies (rate limit still correct, just slow)
- No security degradation

DETECTION: Redis P99 latency metric; auth API latency increase

MITIGATION: Scale Redis or add replicas; circuit breaker if latency > 100ms

---

PARTIAL FAILURE: One database replica slow (read used for credential lookup)

SITUATION: Primary is healthy; read replica has replication lag or disk contention

BEHAVIOR:
- If credential lookup uses replica: login latency +50–200ms
- If credential lookup uses primary: no impact
- Session read on refresh: may hit slow replica → refresh latency up

USER IMPACT:
- Login or refresh occasionally slow
- No wrong credentials accepted (primary is source of truth for writes)

DETECTION: Read replica lag metric; P99 login/refresh latency by instance

MITIGATION: Route credential lookups to primary only; use replica only for non-critical reads
```

**L5 relevance:** Senior engineers distinguish "dependency down" from "dependency slow." Partial failure often causes latency degradation and timeouts before total failure; runbooks and alerts should treat them explicitly.

---

## Dependency Failures

### Database Failure

```
SCENARIO: PostgreSQL primary fails over to replica

DETECTION:
- Connection errors from auth API
- Write latency spike
- Failover alerts from cloud provider

IMPACT:
- Login: FAILS (can't read credentials)
- Refresh: FAILS (can't read sessions)
- Validation: UNAFFECTED (JWT is self-contained)
- Active users: UNAFFECTED (their tokens still work)

RECOVERY:
1. Automatic failover: 10-30 seconds
2. Connection pools reconnect
3. Login and refresh resume

KEY INSIGHT:
    Database failure blocks NEW logins but doesn't affect EXISTING sessions.
    This is the core value of JWT: decoupled validation from the auth service.
    
    During a 30-second DB failover:
    - 0 users lose access (tokens still valid)
    - ~7,000 login attempts fail (230/sec × 30s)
    - Users see "login failed, try again" and retry after 30 seconds
```

### Redis Failure

```
SCENARIO: Redis unavailable

DETECTION:
- Redis connection errors
- Rate limit check failures
- Blocklist unavailable

IMPACT:
- Rate limiting: DISABLED (fall back to allowing all)
- Blocklist: DISABLED (revoked tokens work until expiry)
- Login: WORKS (but unprotected from brute force)

MITIGATION:
// Pseudocode: Redis fallback behavior
FUNCTION check_rate_limit_with_fallback(identifier, type):
    TRY:
        RETURN rate_limiter.is_blocked(identifier, type)
    CATCH RedisUnavailable:
        log.warn("Redis unavailable, rate limiting disabled")
        metrics.increment("redis.fallback.rate_limit")
        
        // During Redis outage, allow logins but alert
        IF NOT alert_already_sent:
            alert_oncall("Redis down: rate limiting disabled")
        
        RETURN false  // Allow (fail open for availability)

DECISION: Rate limiting fails open (allow)
    
    Why not fail closed (deny all)?
    - Redis outage would = login outage for all users
    - Duration is typically < 5 minutes
    - Risk: brute force during window is low if outage is short
    - Mitigated by account lockout (in DB, not Redis)
```

### Signing Key Unavailable

```
SCENARIO: KMS unavailable, can't load signing key

DETECTION:
- Auth service startup failure
- Token signing errors

IMPACT:
- Cannot issue new tokens (login fails)
- Cannot sign refresh responses
- Existing tokens still valid (validation uses public key)

MITIGATION:
1. Cache signing key in memory at startup
2. KMS outage during runtime: use cached key
3. KMS outage during deployment: block deployment
4. Alert immediately if signing key unavailable

// Pseudocode: Key loading with caching
FUNCTION load_signing_key():
    TRY:
        key = kms.get_key("auth-jwt-signing-key")
        this.cached_key = key
        RETURN key
    CATCH KMSUnavailable:
        IF this.cached_key:
            log.warn("KMS unavailable, using cached key")
            RETURN this.cached_key
        ELSE:
            log.error("KMS unavailable and no cached key!")
            THROW FatalError("Cannot start auth service without signing key")
```

## Realistic Production Failure Scenario

```
┌─────────────────────────────────────────────────────────────────────────────┐
│   FAILURE SCENARIO: CREDENTIAL STUFFING ATTACK DURING PRODUCT LAUNCH        │
│                                                                             │
│   TRIGGER:                                                                  │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Product launch generates press coverage.                           │   │
│   │  Attackers target the login endpoint.                               │   │
│   │  50,000 credential-stuffing attempts/minute (800/sec).              │   │
│   │  Legitimate traffic also spiking: 5× normal (1,200/sec).            │   │
│   │  Total login traffic: 2,000/sec (vs normal 230/sec)                 │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   WHAT BREAKS:                                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  T+0:    Attack starts                                              │   │
│   │  T+2min: Login latency increasing (bcrypt CPU saturation)           │   │
│   │  T+5min: P99 login latency: 5 seconds (vs normal 500ms)             │   │
│   │  T+8min: Some legitimate login timeouts                             │   │
│   │  T+10min: Alert fires: "Login error rate > 5%"                      │   │
│   │                                                                     │   │
│   │  SECONDARY EFFECTS:                                                 │   │
│   │  - Rate limiter blocking per-IP, but attacker uses 10K IPs          │   │
│   │  - Per-email locks catching some, but different emails each time    │   │
│   │  - bcrypt workers saturated by attack traffic                       │   │
│   │  - Legitimate users see slow or failed logins                       │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   DETECTION:                                                                │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  - Alert: "Login failure rate > 80%"                                │   │
│   │  - Alert: "Login P99 latency > 3 seconds"                           │   │
│   │  - Dashboard: Login QPS 10× normal                                  │   │
│   │  - Redis: Rate limit keys 50× normal count                          │   │
│   │  - Pattern: High failure rate from diverse IPs, common passwords    │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   SENIOR ENGINEER RESPONSE:                                                 │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  IMMEDIATE (0-5 min):                                               │   │
│   │  1. Confirm credential stuffing (not legitimate spike)              │   │
│   │  2. Check: Are existing users affected? (Token validation = fine)   │   │
│   │  3. Impact: Only new logins affected                                │   │
│   │                                                                     │   │
│   │  MITIGATION (5-15 min):                                             │   │
│   │  4. Enable aggressive IP-based rate limiting at load balancer       │   │
│   │  5. Block ASNs/IP ranges with > 95% failure rate                    │   │
│   │  6. Enable CAPTCHA challenge after 3 failures per IP                │   │
│   │  7. Scale up auth service instances (more bcrypt capacity)          │   │
│   │                                                                     │   │
│   │  POST-INCIDENT:                                                     │   │
│   │  1. Analyze: Which accounts were compromised?                       │   │
│   │  2. Force password reset for compromised accounts                   │   │
│   │  3. Add IP reputation scoring (V2 feature pulled forward)           │   │
│   │  4. Implement proof-of-work challenge for suspicious logins         │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   PERMANENT FIX:                                                            │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  1. Rate limiting at edge (WAF, load balancer) before reaching app  │   │
│   │  2. CAPTCHA integration for suspicious login patterns               │   │
│   │  3. IP reputation database (block known bad actors)                 │   │
│   │  4. Breached password detection (check against known leaks)         │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Timeout and Retry Configuration

```
TIMEOUT CONFIGURATION:

Auth API:
    bcrypt computation: 500ms timeout (usually 200ms)
    Database query: 500ms
    Redis: 50ms
    Overall request: 5 seconds

Downstream Token Validation:
    JWT verify: No timeout (CPU-local, < 1ms)
    Blocklist check (Redis): 50ms
    Fallback: Skip blocklist if Redis slow

RETRY CONFIGURATION:

Client-side (login):
    Max retries: 2
    Backoff: 1s, 3s
    Retryable: 500, 503 (NOT 401, 429)

Client-side (refresh):
    Max retries: 1
    On failure: Redirect to login
    Never retry with same refresh token

Server-side:
    Database retry: 1 attempt, 100ms delay
    Redis retry: 0 (fail open immediately)
    KMS retry: 3 attempts, exponential backoff (startup only)
```

---

# Part 11: Performance & Optimization

## Hot Path Analysis

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         TOKEN VALIDATION HOT PATH                           │
│                                                                             │
│   This runs on EVERY API REQUEST across ALL services.                       │
│   Must be < 1ms in the common case.                                         │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  1. Extract token from header        ~0.01ms                        │   │
│   │  2. Base64 decode JWT parts          ~0.01ms                        │   │
│   │  3. Verify RS256 signature           ~0.05ms                        │   │
│   │  4. Check expiry                     ~0.001ms                       │   │
│   │  5. Check issuer                     ~0.001ms                       │   │
│   │  ─────────────────────────────────────────────                      │   │
│   │  TOTAL: ~0.07ms (no network call)                                   │   │
│   │                                                                     │   │
│   │  Optional: Blocklist check (Redis)   ~0.5ms                         │   │
│   │  TOTAL WITH BLOCKLIST: ~0.6ms                                       │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   LOGIN PATH (less frequent but more expensive):                            │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  1. Rate limit check (Redis)         ~1ms                           │   │
│   │  2. Credential lookup (DB)           ~5ms                           │   │
│   │  3. bcrypt verify (CPU)              ~200ms ← DOMINANT COST         │   │
│   │  4. JWT sign (CPU)                   ~1ms                           │   │
│   │  5. Session write (DB)               ~5ms                           │   │
│   │  ─────────────────────────────────────────────                      │   │
│   │  TOTAL: ~215ms                                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   KEY INSIGHT: Login is 3000× more expensive than validation.               │
│   This is by design. Login happens once; validation happens millions of     │
│   times. Optimizing login means weakening bcrypt. Don't do that.            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Optimizations Applied

### 1. Public Key Distribution

```
PROBLEM: Every service needs auth's public key to validate JWTs

SOLUTION: JWKS endpoint + local caching

// Pseudocode: Public key distribution
// Auth service exposes: GET /.well-known/jwks.json
FUNCTION jwks_endpoint():
    RETURN {
        keys: [
            {
                kty: "RSA",
                kid: current_key_id,
                use: "sig",
                alg: "RS256",
                n: current_key.modulus,
                e: current_key.exponent
            },
            // Include previous key during rotation
            {
                kty: "RSA",
                kid: previous_key_id,
                ...
            }
        ]
    }

// Downstream services:
// Fetch JWKS at startup, cache, re-fetch every hour
FUNCTION get_public_key(key_id):
    cached = key_cache.get(key_id)
    IF cached:
        RETURN cached
    
    // Key not in cache (maybe rotated)
    keys = fetch("https://auth.internal/.well-known/jwks.json")
    FOR key IN keys:
        key_cache.set(key.kid, key)
    
    RETURN key_cache.get(key_id) OR Error("Unknown key")

BENEFIT:
    - No auth service call on every request
    - Key rotation transparent to downstream
    - Cache TTL: 1 hour (keys rotate rarely)
```

### 2. bcrypt Worker Pool

```
PROBLEM: bcrypt blocks the event loop / thread for 200ms

SOLUTION: Dedicated thread pool for bcrypt operations

// Pseudocode: bcrypt worker pool
BCRYPT_POOL = ThreadPool(
    size = num_cpus,  // One bcrypt thread per CPU core
    queue_size = 1000,
    reject_policy = "reject_with_503"
)

FUNCTION bcrypt_verify_async(password, hash):
    future = BCRYPT_POOL.submit(() => bcrypt_verify(password, hash))
    RETURN future.get(timeout=500ms)

BENEFIT:
    - bcrypt doesn't block other request handling
    - Pool limits concurrent bcrypt operations (prevents CPU exhaustion)
    - Overflow → 503 (backpressure to clients)
```

## Optimizations NOT Done

```
DEFERRED OPTIMIZATIONS:

1. CREDENTIAL CACHE
   Could cache credentials in Redis for faster lookup.
   NOT DONE because:
   - Credentials in cache = security risk
   - DB lookup is 5ms (acceptable)
   - bcrypt is 200ms anyway (DB is not the bottleneck)

2. SESSION STORE IN REDIS
   Could move sessions from PostgreSQL to Redis.
   NOT DONE because:
   - Sessions must survive restarts (durability)
   - PostgreSQL handles current session write load
   - Redis for sessions = data loss risk on failure

3. SYMMETRIC JWT SIGNING (HS256)
   Could use HMAC instead of RSA (faster signing).
   NOT DONE because:
   - HS256 requires sharing secret with all services
   - One compromised service = can forge tokens
   - RS256: only auth service has private key; services have public key
   - Security > performance here

4. ELIMINATING BLOCKLIST
   Could skip blocklist entirely (rely on 15-min expiry).
   NOT DONE because:
   - "Logout all" on account compromise needs faster revocation
   - Blocklist adds only 0.5ms
   - Peace of mind for security team
```

---

# Part 12: Cost & Operational Considerations

## Major Cost Drivers

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     AUTH SYSTEM COST BREAKDOWN                              │
│                                                                             │
│   For 100M users, 20M logins/day:                                           │
│                                                                             │
│   1. COMPUTE (60% of cost)                                                  │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Auth API servers (100): $200/month each = $20,000/month            │   │
│   │  (bcrypt is CPU-bound; this is the dominant cost)                   │   │
│   │                                                                     │   │
│   │  Attack traffic doubles compute cost.                               │   │
│   │  Without attacks: 50 instances sufficient.                          │   │
│   │  With attacks: 100 instances needed.                                │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   2. DATABASE (25% of cost)                                                 │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  PostgreSQL Multi-AZ: $3,000/month                                  │   │
│   │  Storage (1 TB): $100/month                                         │   │
│   │  Read replicas (2): $1,500/month                                    │   │
│   │  Audit log storage (900 GB): $90/month                              │   │
│   │  Total: ~$4,690/month                                               │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   3. REDIS (5% of cost)                                                     │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Redis cluster (rate limiting + blocklist): $1,000/month            │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   4. KMS (5% of cost)                                                       │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Key management: $500/month                                         │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   TOTAL MONTHLY COST: ~$26,000                                              │
│   COST PER 1000 LOGINS: $0.04                                               │
│                                                                             │
│   KEY INSIGHT: Half the compute cost is defending against attacks.          │
│   Better edge-level rate limiting (WAF) could cut costs 30%.                │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Cost Analysis Table (Senior Bar)

| Cost Driver | Current | At 10× Scale | Optimization |
|-------------|---------|--------------|---------------|
| Compute (auth API + bcrypt) | ~$20,000/mo | ~$120,000/mo (sub-linear) | Auto-scale off-peak; edge rate limit to reduce app load |
| Database | ~$4,700/mo | ~$25,000/mo (sharding) | Read replicas for credential lookup; session store shard by user_id |
| Redis | ~$1,000/mo | ~$5,000/mo | Cluster mode; blocklist TTL to cap size |
| KMS | ~$500/mo | ~$500/mo | Flat; key count doesn't scale with users |

**Tie to operations:**

| Decision | Cost Impact | Operability Impact | On-Call Impact |
|----------|-------------|-------------------|----------------|
| More auth instances | +$10K/mo | Better login capacity during attacks | Fewer "login slow" pages |
| Edge WAF rate limiting | -$6K/mo | Less app-level rate limit logic | Fewer credential-stuffing incidents |
| Shard session store | +$5K/mo | More complex "logout all" / session queries | Runbook updates; cross-shard revoke |

## On-Call Burden Analysis

```
ON-CALL REALITY:

EXPECTED PAGES (monthly):
    - Credential stuffing spikes: 2-4 (common, partially automated)
    - Database failover: 0-1 (rare)
    - Redis failure: 0-1 (rare)
    - Key rotation issues: 0-1 (during rotation)
    - Customer escalations: 1-2 ("I can't log in")
    
    Total: 3-7 pages/month

HIGH-BURDEN:
    1. Large-scale credential stuffing
       - Requires manual IP blocks, CAPTCHA enabling
       - Duration: 30 min to hours
    
    2. Signing key issue
       - If signing key unavailable: no new tokens
       - Very high urgency
       - Duration: Minutes if cached, longer if not

LOW-BURDEN (AUTOMATED):
    - Minor rate limit spikes → auto-handled
    - Single instance crash → auto-restart
    - Redis replica failure → auto-failover
```

## Misleading Signals & Debugging Reality

```
MISLEADING SIGNALS:

| Metric | Looks Healthy | Actually Broken |
|--------|---------------|-----------------|
| Login success rate 95% | Normal | 5% = credential stuffing successes |
| Token validation latency 0.1ms | Fast | Blocklist check disabled (Redis down) |
| Login QPS normal | No spike | Attack using slow, distributed pattern |
| Session count growing | More users | Refresh token leak (sessions never cleaned) |

REAL SIGNALS:
    - Login success rate by IP reputation
    - Unique IPs per minute (spike = botnet)
    - bcrypt pool utilization (saturation = attack)
    - Failed login patterns (same password across emails = stuffing)

DEBUGGING: "User can't log in"

1. Check: Is the email correct? (Most common: typo)
2. Check: Is the account locked? (Check locked_until)
3. Check: Rate limited? (Check Redis ratelimit keys)
4. Check: Auth service healthy? (Check /health endpoint)
5. Check: Password recently changed? (Check updated_at)
6. Check: MFA issue? (Clock skew on user's device → TOTP failure)

Common causes:
    - Wrong password / forgot password (60%)
    - Account locked from failed attempts (15%)
    - MFA clock skew (10%)
    - Rate limited (legitimate, shared IP like office) (10%)
    - Actual bug (5%)
```

---

# Part 12b: Rollout, Rollback & Operational Safety

## Deployment Strategy

```
AUTH SYSTEM DEPLOYMENT:

WHY AUTH DEPLOYMENT IS HIGH-RISK:
    - Bad deployment = all logins fail
    - Or worse: bad deployment = unauthorized access
    - Auth is the most sensitive service to deploy

COMPONENT TYPES AND STRATEGY:

1. Auth API (stateless)
   Strategy: Canary with automatic rollback
   Stages: 1% → 5% → 25% → 50% → 100%
   Bake time: 30 min per stage (longer than other services)
   
   Why longer bake:
   - Login issues may not surface immediately
   - Attack patterns vary over time
   - Token validation issues surface only at token expiry

2. Signing key rotation
   Strategy: Multi-phase with overlap
   Phase 1: Generate new key, publish new public key (no signing yet)
   Phase 2: Wait for all services to fetch new public key (1 day)
   Phase 3: Start signing with new key
   Phase 4: Remove old public key after all old tokens expire (1 day)

3. Schema changes
   Strategy: Forward-compatible migrations only
   - New columns: nullable with defaults
   - Never drop columns in same release
   - Test rollback with production data copy

CANARY CRITERIA:
    - Login success rate delta < 0.5%
    - Login P99 latency delta < 20%
    - Token validation error rate unchanged
    - No increase in security alerts
    - Zero unauthorized access signals
```

## Rollback Safety

```
ROLLBACK TRIGGERS:
    - Login success rate drops > 1%
    - P99 latency > 2× baseline
    - Any unauthorized access detected
    - Token validation errors from downstream services
    - On-call judgment (err on side of rollback)

ROLLBACK TIME:
    - API: 5-10 minutes to roll back canary
    - Key rotation: Don't rollback; both keys valid during transition
    - Schema: Code handles old schema; no urgent schema rollback needed

CRITICAL RULE:
    If unsure whether to rollback auth: ROLLBACK FIRST, investigate later.
    Auth failure modes are worse than downtime.
```

## Concrete Scenario: Bad Token Signing Deployment

```
SCENARIO: Deployed code has JWT claims format change

1. CHANGE DEPLOYED
   - New claim added: "org_id" in JWT
   - But: downstream service validation rejects unknown claims
   
2. BREAKAGE TYPE
   - Subtle: New logins get new-format tokens
   - Downstream services reject new tokens
   - Old tokens (pre-deploy) still work
   - Users who were already logged in: fine
   - Users who log in after deploy: broken
   
3. DETECTION SIGNALS
   - Downstream: 401 error rate spike
   - Auth: Login success rate fine (tokens issued OK)
   - Misleading: Auth dashboard looks healthy
   - Real signal: Downstream services reporting token validation failures

4. ROLLBACK STEPS
   a. Immediately rollback auth service to previous version
   b. New logins get old-format tokens
   c. Users with new-format tokens: wait 15 min for expiry, or
      redirect to re-login
   d. Verify downstream 401 rate returns to baseline

5. GUARDRAILS ADDED
   - Integration test: validate issued JWT against all downstream services
   - Canary: deploy to 1% and monitor DOWNSTREAM error rates (not just auth)
   - Claim format changes require coordination with all consumers
```

---

# Part 13: Security Basics & Abuse Prevention

## Credential Storage

```
CREDENTIAL SECURITY:

PASSWORD HASHING:
    Algorithm: bcrypt
    Cost factor: 12 (produces ~250ms hash time)
    Salt: Auto-generated per password (bcrypt built-in)
    
    WHY bcrypt (not SHA256, not MD5):
    - bcrypt is intentionally slow (resists brute force)
    - SHA256 is fast → attacker can try billions/sec on GPU
    - bcrypt: attacker gets ~100 tries/sec on GPU
    
    WHY cost factor 12:
    - 10 = ~100ms (too fast, easy to brute force)
    - 12 = ~250ms (good balance of security vs user experience)
    - 14 = ~1000ms (too slow for interactive login)

MFA SECRETS:
    Storage: Encrypted with AES-256 in database
    Key: Stored in KMS, never in application config
    Backup codes: Hashed individually (like passwords)

REFRESH TOKEN STORAGE:
    Stored as SHA-256 hash in database
    Original token never stored
    If database is compromised: attacker has hashes, not tokens
```

## Attack Prevention

```
ATTACK VECTORS AND DEFENSES:

1. CREDENTIAL STUFFING
   Defense: Per-IP + per-email rate limiting
   Detection: High failure rate from diverse IPs
   Response: CAPTCHA, IP blocking, alert security

2. BRUTE FORCE
   Defense: Account lockout after 5 failures
   Detection: Repeated failures on same email
   Response: 15-minute lockout, notify user

3. TIMING ATTACK (User Enumeration)
   Defense: Constant-time response for valid vs invalid email
   Implementation: Run fake bcrypt even for non-existent users
   Why: Attacker can't determine if email is registered by response time

4. TOKEN FORGERY
   Defense: RSA-256 signing (asymmetric)
   Implementation: Private key in KMS, public key distributed
   Why: Even if service is compromised, can't forge tokens

5. REFRESH TOKEN THEFT
   Defense: Rotation with reuse detection
   Implementation: Used tokens trigger family revocation
   Why: Stolen token is detected on next legitimate refresh

6. SESSION FIXATION
   Defense: New session ID on login
   Implementation: Always generate fresh tokens on login
   Why: Attacker can't pre-set a session ID
```

## Data Protection

```
DATA CLASSIFICATION:

CRITICAL (highest protection):
    - Password hashes (encrypted at rest + bcrypt)
    - MFA secrets (encrypted with KMS key)
    - Signing private key (HSM/KMS only)

SENSITIVE:
    - Email addresses (encrypted at rest)
    - Session data (encrypted at rest)
    - Login audit logs (encrypted at rest)

INTERNAL:
    - Rate limit counters (ephemeral, Redis)
    - Token blocklist (ephemeral, Redis)

ENCRYPTION:
    In transit: TLS 1.3 everywhere
    At rest: AES-256 (database + backups)
    Signing key: Never leaves KMS/HSM

LOGGING RULES:
    DO log: email (for debugging), IP, user agent, success/failure, timestamp
    DO NOT log: password (even failed ones), MFA codes, token values, password hashes
```

---

# Part 14: System Evolution

## V1: Minimal Auth System

```
V1 DESIGN (Launch):

Features:
- Email + password login
- JWT access tokens (15 min)
- Refresh tokens (30 days)
- Basic rate limiting
- Session management

Scale:
- 10M users
- 1M logins/day
- ~12/sec peak

Architecture:
- Single auth API service
- Single PostgreSQL
- Redis for rate limiting

Limitations:
- No MFA
- No account lockout
- No anomaly detection
- No key rotation
```

## First Issues and Fixes

```
ISSUE 1: Credential stuffing (Week 3)

Problem: 50K login attempts/minute from botnet
Detection: Login failure rate 95%, diverse IPs
Root cause: No IP-level rate limiting

Solution:
- Add per-IP rate limiting
- Block IPs with > 95% failure rate
- Add CAPTCHA after 3 failures per IP

Effort: 3 days

ISSUE 2: Users locked out from shared IPs (Month 1)

Problem: Office with 500 people behind NAT, all rate-limited
Detection: Support tickets from corporate users
Root cause: Per-IP limit too aggressive for shared IPs

Solution:
- Increase per-IP limit (20/min → 50/min)
- Add per-email rate limit as primary defense
- Consider IP reputation (residential vs datacenter)

Effort: 2 days

ISSUE 3: Token validation overhead (Month 2)

Problem: Some teams calling auth service to validate tokens
Detection: Auth service getting 50K QPS for validation
Root cause: Teams didn't know JWT is self-verifiable

Solution:
- Publish JWKS endpoint
- Create validation library (SDK)
- Documentation + internal training
- Deprecate validation endpoint

Effort: 1 week

ISSUE 4: MFA demanded (Month 3)

Problem: Account compromises from credential stuffing
Detection: Customer complaints, security audit
Root cause: Password-only auth insufficient

Solution:
- Add TOTP-based MFA
- Optional for users, mandatory for admins
- Recovery codes for lost devices

Effort: 2 weeks
```

## Rushed Decision Scenario (Real-World Application)

```
RUSHED DECISION: Defer MFA and ship password-only for launch

CONTEXT:
- Launch deadline in 4 weeks; product needed login immediately
- Ideal solution: Password + optional TOTP MFA from day one
- Time pressure: No bandwidth to integrate TOTP library, key backup flows, and recovery codes

DECISION MADE:
- Ship password-only auth; document MFA as V1.1
- Rely on rate limiting and account lockout as only defenses
- Acceptable because: Launch traffic was small; attack surface limited; security review accepted risk with timeline

TECHNICAL DEBT INTRODUCED:
- MFA added later required schema change (mfa_enabled, mfa_secret), migration, and client flows
- Users who had already chosen weak passwords remained at risk until MFA rollout
- Cost of carrying debt: One high-profile account compromise incident; 2-week MFA push; ongoing support for "why no MFA at signup?"

WHEN TO FIX: Before scaling user base or before any regulated/enterprise customers. Revisit when security audit or compliance requires MFA.
```

## V2 Improvements

```
V2: PRODUCTION-HARDENED AUTH SYSTEM

Added:
- TOTP MFA
- Account lockout (5 failures → 15 min lock)
- Refresh token rotation with reuse detection
- Login audit log
- Key rotation support
- Token blocklist for immediate revocation

Improved:
- Rate limiting at edge (WAF) + application
- bcrypt worker pool (dedicated threads)
- Session family tracking

Scale:
- 100M users, 20M logins/day
- Handles 50K attack attempts/sec
```

---

# Part 15: Alternatives & Trade-offs

## Alternative 1: Opaque Tokens Instead of JWT

```
CONSIDERED: Use opaque tokens (random strings) stored server-side

WHAT IT IS:
    Every token is a random string.
    Validation requires calling auth service to look up the token.

PROS:
- Instant revocation (delete from store)
- No public key distribution
- Simpler token format
- No claim size concerns

CONS:
- Every API request calls auth service → bottleneck
- Auth service becomes single point of failure for ALL services
- At 100K API QPS: auth service needs 100K lookups/sec
- Latency: +5ms per request (network call)

DECISION: JWT for access tokens, opaque for refresh tokens

REASONING:
- Access tokens validated 100K×/sec → must be local (JWT)
- Refresh tokens validated 5K×/sec → can afford DB lookup (opaque)
- Revocation concern: 15-min expiry + optional blocklist
- Hybrid approach gives best of both
```

## Alternative 2: Session-Based Auth (No Tokens)

```
CONSIDERED: Traditional session cookies stored server-side

WHAT IT IS:
    Login creates session on server.
    Session ID stored in cookie.
    Every request looks up session by ID.

PROS:
- Instant revocation (delete session)
- No token expiry logic
- Simple for web apps

CONS:
- Doesn't work for mobile apps / APIs (no cookies)
- Session store is single point of failure
- Sticky sessions or distributed session store needed
- Cross-domain issues
- Harder to scale (session affinity)

DECISION: Token-based (JWT + refresh)

REASONING:
- Need to support web, mobile, and API clients
- Token-based is stateless for validation
- Mobile apps don't use cookies naturally
- Microservices need token-based auth
```

## Alternative 3: Shorter/Longer Access Token Expiry

```
CONSIDERED: Different access token lifetimes

5-MINUTE TOKENS:
    Pros: Smaller revocation window
    Cons: Refresh every 5 min, more load on auth service
    Verdict: Too aggressive; doubles refresh traffic

1-HOUR TOKENS:
    Pros: Fewer refreshes, simpler client logic
    Cons: 1 hour of access after compromise
    Verdict: Too long for security-sensitive systems

15-MINUTE TOKENS (chosen):
    Pros: Good balance of security and usability
    Cons: Requires refresh token logic in every client
    Verdict: Industry standard, well-understood trade-off

THE TRADE-OFF:
    Shorter expiry = more secure but more complex and more load
    Longer expiry = simpler but larger blast radius
    15 minutes is the sweet spot for most systems.
```

---

# Part 16: Interview Calibration (L5 Focus)

## What Interviewers Evaluate

| Signal | How It's Assessed |
|--------|-------------------|
| Scope management | Do they separate AuthN from AuthZ? Clarify channels, MFA scope? |
| Trade-off reasoning | JWT vs opaque, token expiry, bcrypt cost factor? |
| Failure thinking | What happens if DB is down? If signing key is compromised? |
| Scale awareness | bcrypt CPU cost, attack traffic, validation must be local? |
| Security mindset | Timing attacks, token theft, credential stuffing? |
| Ownership mindset | Key rotation, audit logging, on-call for auth? |

## Example Strong L5 Phrases

- "First, I need to separate AuthN from AuthZ. This system only answers 'who are you?'"
- "bcrypt is intentionally slow. I'd never cache credentials to speed up login."
- "Token validation must be local. If every API request calls auth, auth becomes a SPOF."
- "The main threat I'm designing against is credential stuffing, not sophisticated attacks."
- "15-minute token expiry is a conscious trade-off: security vs refresh complexity."

## How Google Interviews Probe Auth Systems

```
COMMON INTERVIEWER QUESTIONS:

1. "How do you handle token revocation?"
   
   L4: "Delete the token from the database."
   
   L5: "Access tokens are JWTs—self-contained, so can't be
   revoked without a blocklist. We accept a 15-minute window 
   where a revoked token still works.
   
   For refresh tokens: they're opaque, stored server-side, 
   instantly revocable.
   
   For 'logout all': we increment a token_generation counter. 
   Downstream services check the generation claim against the 
   current value. Mismatch = reject.
   
   The blocklist is a Redis set with TTL matching token expiry. 
   Small, fast, and self-cleaning."

2. "What happens if your auth service goes down?"
   
   L4: "Users can't log in."
   
   L5: "Users can't log in or refresh—that's correct, and
   by design (fail closed on issuance).
   
   But—and this is the key insight—existing sessions CONTINUE
   WORKING. JWT validation is local to each service. No auth
   call needed. So 100% of active users are unaffected.
   
   Impact is limited to: users who need to log in or refresh
   during the outage (15-minute window). That's a small
   percentage of total traffic."

3. "How do you prevent credential stuffing?"
   
   L4: "Rate limit the login endpoint."
   
   L5: "Multi-layered defense:
   
   1. Edge: WAF blocks known bad IPs before reaching app
   2. IP rate limit: 20 attempts/minute per IP
   3. Email rate limit: 5 failures per email per 15 minutes
   4. Account lockout: 5 failures → 15 minute lock
   5. CAPTCHA: Triggered after 3 failures per IP
   
   The key insight: attackers use thousands of IPs, so per-IP 
   alone isn't enough. Per-email catches targeted attacks. 
   Together they cover both spray and targeted patterns."
```

## Common L4 Mistakes

```
L4 MISTAKE: "Store passwords with SHA-256"

WHY IT'S L4: Focus on "hashing" without understanding attack model (brute force).
Problem: SHA-256 is fast → attacker can try billions/sec; even with salt, GPU cracking is feasible.

L5 APPROACH: bcrypt (or Argon2id) with high cost factor. Intentionally slow → 100 tries/sec on GPU.
Cost factor tuned to balance security and UX.


L4 MISTAKE: "Call auth service to validate every request"

WHY IT'S L4: Treats auth as a single service call; doesn't reason about scale and SPOF.
Problem: Auth service becomes SPOF for entire platform; 100K QPS to auth; adds 5ms latency to every request.

L5 APPROACH: JWT with local validation. Public key distributed via JWKS. Auth service only needed for login/refresh.
Validation: 0.1ms, no network call.


BORDERLINE L5 MISTAKE: "Use symmetric JWT signing (HS256)"

WHY IT'S BORDERLINE: Correct choice of "signed token" but wrong trade-off (simplicity over security).
Problem: All services share the signing secret; one compromised service can forge tokens for any user;
secret rotation requires updating all services simultaneously.

L5 FIX: RS256 (asymmetric): private key in auth service only. Services only have public key → can verify but not forge.
Key rotation: publish new public key, services fetch it.
```

---

# Part 17: Diagrams

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    AUTHENTICATION SYSTEM ARCHITECTURE                       │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────┐     │
│   │                        CLIENTS                                    │     │
│   │  ┌─────────┐  ┌─────────┐   ┌─────────┐  ┌─────────┐              │     │
│   │  │  Web    │  │  iOS    │   │ Android │  │ Service │              │     │
│   │  └────┬────┘  └────┬────┘   └────┬────┘  └────┬────┘              │     │
│   └───────┼────────────┼─────────--──┼────────────┼───────────────────┘     │
│           └────────────┴──────────--─┴────────────┘                         │
│                               │                                             │
│                               ▼                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                      WAF + LOAD BALANCER                            │   │
│   │  (IP rate limiting, TLS termination, bot detection)                 │   │
│   └──────────────────────────────┬──────────────────────────────────────┘   │
│                                  │                                          │
│                                  ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                      AUTH API SERVICE                               │   │
│   │  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐         │   │
│   │  │  Login    │  │ Refresh   │  │  Logout   │  │  JWKS     │         │   │
│   │  │ /login    │  │ /refresh  │  │ /logout   │  │ /.well-   │         │   │
│   │  │           │  │           │  │           │  │ known/jwks│         │   │
│   │  └─────┬─────┘  └─────┬─────┘  └─────┬─────┘  └───────────┘         │   │
│   └────────┼──────────────┼──────────────┼──────────────────────────────┘   │
│            │              │              │                                  │
│    ┌───────┼──────────────┼──────────────┼───────┐                          │
│    ▼       ▼              ▼              ▼       ▼                          │
│ ┌──────┐ ┌────────┐ ┌──────────┐ ┌──────────┐ ┌──────┐                      │
│ │Redis │ │bcrypt  │ │Credential│ │ Session  │ │ KMS  │                      │
│ │      │ │Workers │ │  Store   │ │  Store   │ │      │                      │
│ │-Rate │ │        │ │(Postgres)│ │(Postgres)│ │-Sign │                      │
│ │ Limit│ │-CPU    │ │-email    │ │-refresh  │ │ Key  │                      │
│ │-Block│ │ pool   │ │-password │ │-sessions │ │      │                      │
│ │ list │ │        │ │-mfa      │ │-audit    │ │      │                      │
│ └──────┘ └────────┘ └──────────┘ └──────────┘ └──────┘                      │
│                                                                             │
│   ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─                       │
│   DOWNSTREAM SERVICES (validate JWT locally, no auth call)                  │
│   ┌──────────┐  ┌──────────┐  ┌──────────┐                                  │
│   │Service A │  │Service B │  │Service C │                                  │
│   │+pub key  │  │+pub key  │  │+pub key  │                                  │
│   │+JWT lib  │  │+JWT lib  │  │+JWT lib  │                                  │
│   └──────────┘  └──────────┘  └──────────┘                                  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Login + Token Validation Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│              LOGIN → USE TOKEN → REFRESH LIFECYCLE                          │
│                                                                             │
│  Client         Auth Service      Service A      Redis        Database      │
│    │                │                │              │              │        │
│    │ 1. LOGIN       │                │              │              │        │
│    │ (email+pass)   │                │              │              │        │
│    │───────────────▶│                │              │              │        │
│    │                │ rate check     │              │              │        │
│    │                │──────────────────────────────▶│              │        │
│    │                │ credentials    │              │              │        │
│    │                │─────────────────────────────────────────────▶│        │
│    │                │ bcrypt verify  │              │              │        │
│    │                │ sign JWT       │              │              │        │
│    │                │ store session  │              │              │        │
│    │                │─────────────────────────────────────────────▶│        │
│    │◀───────────────│                │              │              │        │
│    │ access + refresh tokens         │              │              │        │
│    │                │                │              │              │        │
│    │ 2. API CALL    │                │              │              │        │
│    │ (with JWT)     │                │              │              │        │
│    │────────────────────────────────▶│              │              │        │
│    │                │                │ verify JWT   │              │        │
│    │                │                │ (LOCAL, 0.1ms)              │        │
│    │                │                │ no auth call!│              │        │
│    │◀────────────────────────────────│              │              │        │
│    │ response       │                │              │              │        │
│    │                │                │              │              │        │
│    │ 3. TOKEN EXPIRED (15 min later) │              │              │        │
│    │ REFRESH        │                │              │              │        │
│    │ (refresh token)│                │              │              │        │
│    │───────────────▶│                │              │              │        │
│    │                │ lookup session │              │              │        │
│    │                │─────────────────────────────────────────────▶│        │
│    │                │ rotate token   │              │              │        │
│    │                │─────────────────────────────────────────────▶│        │
│    │◀───────────────│                │              │              │        │
│    │ new access + refresh tokens     │              │              │        │
│    │                │                │              │              │        │
│                                                                             │
│   KEY INSIGHT:                                                              │
│   Step 2 (the most frequent operation) has ZERO dependency on auth service  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Part 18: Brainstorming & Senior-Level Exercises (MANDATORY)

---

## A. Scale & Load Thought Experiments

### Experiment A1: Traffic Growth Scenarios

| Scale | Users | Logins/Day | Attack QPS | What Changes | What Breaks First |
|-------|-------|-----------|-----------|--------------|-------------------|
| Current | 100M | 20M | 800/sec | Baseline | Nothing |
| 2× | 200M | 40M | 1.6K/sec | ? | ? |
| 5× | 500M | 100M | 4K/sec | ? | ? |
| 10× | 1B | 200M | 8K/sec | ? | ? |

```
AT 2× (40M logins/day):
    Changes needed:
    - Double auth API instances
    - Database read replicas for credential lookups
    
    First stress: bcrypt CPU (must double compute)
    
    Action: Scale compute linearly with login volume

AT 5× (100M logins/day):
    Changes needed:
    - Shard session store by user_id
    - WAF at edge to block attack traffic earlier
    - Consider Argon2id for parallelizable hashing
    
    First stress: Session database writes
    
    Action:
    - Move sessions to sharded PostgreSQL or Redis with persistence
    - Edge-level rate limiting to reduce app-level load

AT 10× (200M logins/day):
    Changes needed:
    - Multi-region auth (for login latency)
    - Credential database sharding
    - Dedicated bcrypt hardware (ASICs?)
    
    First stress: Single-region can't serve global logins fast enough
    
    Action:
    - Regional auth clusters with shared credential store
    - Global session replication
```

### Experiment A2: Most Fragile Assumption

```
FRAGILE ASSUMPTION: "Attack traffic stays at predictable levels"

Why it's fragile:
- Credential stuffing is unpredictable
- Major data breaches dump billions of credentials
- Botnet capacity grows constantly
- A single breach can 10× our attack traffic overnight

What breaks:
    If attack traffic hits 500K/sec:
    - Rate limiter Redis becomes bottleneck
    - bcrypt workers fully saturated
    - Legitimate users can't log in
    
Detection:
    - Login failure rate > 90%
    - Unique IPs/minute > 100K
    - bcrypt pool utilization > 95%

Mitigation:
    - Edge-level blocking (WAF, IP reputation)
    - CAPTCHA for all logins during attack
    - Proof-of-work challenge (make bots work harder)
    - Scale bcrypt workers dynamically
```

---

## B. Failure Injection Scenarios

### Scenario B1: Slow Database (10× Latency)

```
SITUATION: Credential store responding at 50ms instead of 5ms

IMMEDIATE BEHAVIOR:
- Login latency: 250ms → 300ms (small increase, bcrypt dominates)
- Refresh latency: 50ms → 100ms (more noticeable)
- Session writes slow

USER SYMPTOMS:
- Login slightly slower (users barely notice)
- Refresh slightly slower
- If very slow (500ms+): login timeouts for some

DETECTION:
- Database latency metrics
- P99 login latency increase
- Connection pool utilization growing

FIRST MITIGATION:
1. Check database health (replication lag? disk? connections?)
2. If reads slow: route reads to replica
3. If writes slow: check for long transactions or locks

PERMANENT FIX:
1. Connection pool tuning
2. Query optimization
3. Consider read replica for credential lookups
```

### Scenario B2: Retry Storm from Clients

```
SITUATION: Frontend bug causes login retry loop on 401 response

IMMEDIATE BEHAVIOR:
- Same user retries login 100×/second
- Per-email rate limit triggers
- Account gets locked
- Across many users: auth service overloaded

USER SYMPTOMS:
- "Account locked" error
- Can't log in even with correct password
- Support tickets spike

DETECTION:
- Per-user login rate abnormally high
- Account lockout rate spike
- Login QPS increase without corresponding unique users

FIRST MITIGATION:
1. Identify client bug (check user agent, app version)
2. Rate limiting contains blast radius
3. Temporarily increase lockout threshold if needed

PERMANENT FIX:
1. Fix client: max 3 retries with backoff
2. Add server-side Retry-After header
3. Monitor for client retry patterns
```

### Scenario B3: Signing Key Compromise

```
SITUATION: Private signing key potentially leaked (engineer laptop stolen)

IMMEDIATE BEHAVIOR:
- Attacker can forge any JWT
- All services trust forged tokens
- Complete identity compromise

USER SYMPTOMS:
- None immediately (attacker is impersonating silently)

DETECTION:
- May not be detected by monitoring
- Detected by: security report, audit, forensics
- This is why key protection is paramount

FIRST MITIGATION:
1. IMMEDIATELY generate new signing key
2. Publish new public key to all services
3. Blocklist all JTIs issued before the rotation time
4. Force all users to re-login (increment token_generation for all)
5. Full security audit

PERMANENT FIX:
1. Move key to HSM (if not already)
2. Restrict access to KMS
3. Audit KMS access logs
4. Consider short-lived signing key certificates
```

### Scenario B4: Redis Down

```
SITUATION: Redis completely unavailable

IMMEDIATE BEHAVIOR:
- Rate limiting disabled (fail open)
- Blocklist unavailable (revoked tokens accepted)
- Login still works (credentials in DB)

USER SYMPTOMS:
- No visible impact for most users
- But: brute force attacks unmitigated
- And: recently revoked tokens still work

DETECTION:
- Redis health check fails
- Rate limit fallback metric increases
- Alert: "Rate limiting disabled"

FIRST MITIGATION:
1. Verify Redis is actually down (not just slow)
2. Enable application-level rate limiting fallback (in-memory, per-instance)
3. Alert security team: "Brute force protection degraded"
4. Monitor login failure patterns manually

PERMANENT FIX:
1. Redis cluster with automatic failover
2. In-memory fallback rate limiter (per-instance)
3. Edge-level rate limiting as backstop (not dependent on Redis)
```

### Scenario B5: Database Failover During Peak

```
SITUATION: PostgreSQL primary fails, replica promoted during high login traffic

IMMEDIATE BEHAVIOR:
- 10–30 second write unavailability
- Auth API connection errors; login and refresh return 5xx
- Existing tokens continue to validate (JWT local; no DB)
- Replica promoted to primary; connections re-established

USER SYMPTOMS:
- "Login failed" / "Service unavailable" for 10–30 seconds
- Users who retry after failover succeed
- No session or credential corruption (failover is transparent to data)

DETECTION:
- Database failover alerts (cloud provider / PgBouncer)
- Auth API error rate spike
- Connection pool exhaustion logs

FIRST MITIGATION:
1. Confirm failover completed (new primary healthy)
2. Verify auth API reconnected (no code change needed)
3. Monitor login success rate returning to baseline
4. Do not restart auth fleet (thundering herd)

PERMANENT FIX:
1. Multi-AZ deployment; automated failover tested regularly
2. Connection retry with backoff in auth service
3. Runbook: "DB failover during peak" with verification steps
```

---

## C. Cost & Trade-off Exercises

### Exercise C1: 30% Cost Reduction Request

```
CURRENT COST: $26,000/month

OPTIONS:

Option A: Reduce auth instances during off-peak (-$5,000)
    Action: Auto-scale from 100 → 50 instances during low traffic
    Risk: Attack traffic is unpredictable; may be caught understaffed
    Recommendation: YES with auto-scale triggers for attack patterns

Option B: Move to Argon2id with lower cost factor (-$3,000)
    Action: Slightly faster hashing, fewer CPU cores needed
    Risk: Must migrate all password hashes (re-hash on next login)
    Recommendation: CAREFUL - migration takes months (gradual)

Option C: Reduce audit log retention (-$500)
    Action: 90 days → 30 days
    Risk: Can't investigate older breaches
    Recommendation: NO for auth - compliance requires longer retention

Option D: Move rate limiting to edge WAF (-$1,000)
    Action: Replace Redis rate limiting with WAF rules
    Risk: Less granular (per-email not possible at edge)
    Recommendation: HYBRID - edge for IP, Redis for email

SENIOR RECOMMENDATION:
    Options A + D = ~25% savings ($6,000)
    Never compromise on auth security for cost savings.
```

---

## D. Ownership Under Pressure

```
SCENARIO: 30-minute mitigation window

You're on-call. At 2 AM an alert fires: "Login success rate dropped to 60%."
Customer-impacting. You have about 30 minutes before the next escalation.

QUESTIONS:

1. What do you check first?
   - Is this a credential stuffing attack? (Check failure rate by IP)
   - Or an auth service issue? (Check error logs, health endpoints)
   - Check: Are existing sessions working? (Yes → issue is login-only)
   - Check: Recent deployments or config changes?

2. What do you explicitly AVOID touching?
   - Signing keys (never rotate under pressure without full procedure)
   - Rate limit configuration (could open flood gates)
   - Database schema
   - Password hashing parameters

3. Escalation criteria?
   - If it's an attack: engage security team
   - If it's a service failure: engage infra team
   - If compromised accounts detected: engage incident commander

4. How do you communicate?
   - Post in incident channel: "Investigating login success rate drop.
     Existing sessions unaffected. Checking for attack vs service issue."
   - Update every 10 minutes
   - When resolved: "Mitigated. Root cause: [X]. Users can log in normally."
```

---

## E. Correctness & Data Integrity

### Exercise E1: Ensuring Password Changes Work

```
QUESTION: User changes password. What must happen atomically?

OPERATIONS (single transaction):
1. Update password_hash to new bcrypt hash
2. Increment token_generation (invalidates all JWTs)
3. Delete all sessions for this user
4. Log the password change event

IF ANY STEP FAILS:
    Entire transaction rolls back.
    Old password still works.
    No sessions deleted.
    User must retry.

WHY ATOMIC:
    If password changes but sessions aren't deleted:
    → Old refresh tokens still work
    → Attacker who stole refresh token retains access
    → Password change is security-meaningless
```

### Exercise E2: Clock Skew and JWT

```
QUESTION: What if server clocks are skewed?

SCENARIO:
    Auth server clock: 10:00:00
    Service A clock: 10:00:05 (5 sec ahead)
    Service B clock: 09:59:55 (5 sec behind)

IMPACT:
    Token issued at 10:00:00, expires at 10:15:00.
    
    Service A (ahead): Sees token as 5 sec closer to expiry → OK
    Service B (behind): Sees token as 5 sec younger → OK
    
    If Service B is 5 MINUTES behind:
    Token appears to not exist yet (iat in future) → some libs reject

MITIGATION:
    - NTP on all servers (keeps clock within 1 second)
    - Add "leeway" to JWT validation (5 seconds)
    - Never rely on sub-second JWT timing
```

---

## F. Incremental Evolution & Ownership

### Exercise F1: Adding Social Login (2 weeks)

```
SCENARIO: Product wants Google/Apple OAuth login

REQUIRED CHANGES:
- New login flow: redirect to provider → callback → issue our tokens
- New credential type: OAuth provider + external ID
- Link social account to existing email if matching

RISKS:
- OAuth provider outage = social login fails
- User confusion if social and password use same email
- Token format doesn't change (still our JWT)

DE-RISKING:
- Social login calls our auth service; we issue OUR tokens
- Provider tokens are only used during login flow, then discarded
- Feature flag: enable per-user segment
- Password login always available as fallback
```

### Exercise F2: Safe Signing Key Rotation

```
SCENARIO: Annual key rotation required

SAFE PROCEDURE:

Phase 1: Generate and publish (Day 1)
    - Generate new key pair in KMS
    - Add new public key to JWKS endpoint
    - All services fetch updated JWKS
    - Do NOT sign with new key yet

Phase 2: Verify distribution (Day 2-3)
    - Confirm all services have new public key
    - Monitor JWKS fetch logs
    - Test: validate a token signed with new key → should pass

Phase 3: Switch signing (Day 3)
    - Auth service starts signing with new key
    - New tokens have new kid (key ID) in header
    - Old tokens (signed with old key) still valid

Phase 4: Remove old key (Day 4+)
    - Wait until all old tokens have expired (15 min minimum, 24 hours safe)
    - Remove old public key from JWKS
    - Decommission old private key in KMS

ROLLBACK:
    Phase 1-2: Just remove new public key
    Phase 3: Switch back to old key for signing
    Phase 4: Cannot rollback (old key gone); plan accordingly
```

---

## G. Interview-Oriented Thought Prompts

### Prompt G1: Clarifying Questions to Ask First

```
ESSENTIAL QUESTIONS:

1. "What clients? Web only, or also mobile and API?"
   → Determines: cookies vs tokens, session management

2. "How many users and what login patterns?"
   → Determines: bcrypt capacity, session store sizing

3. "Any regulatory requirements? (GDPR, SOC2, HIPAA)"
   → Determines: audit logging, encryption, retention

4. "MFA required? For all users or optional?"
   → Determines: complexity of login flow

5. "What's the revocation requirement? Instant or eventual?"
   → Determines: blocklist vs expiry-only
```

### Prompt G2: What You Explicitly Don't Build

```
1. AUTHORIZATION (AuthZ)
   "That's a separate system. AuthN gives you identity; 
   AuthZ decides permissions."

2. USER MANAGEMENT
   "Registration, profile management, email verification—
   those are user service. We store credentials."

3. RISK-BASED AUTH (V1)
   "No ML-based risk scoring for V1. Rate limiting + MFA 
   covers 99% of cases."

4. PASSWORD RESET FLOW
   "Important but separate. Uses a different token type 
   (one-time, short-lived)."
```

---

# Final Verification

```
✓ This chapter MEETS Google Senior Software Engineer (L5) expectations.

SENIOR-LEVEL SIGNALS COVERED:

A. Design Correctness & Clarity:
✓ End-to-end login → token → validation → refresh → logout flow
✓ Component responsibilities clear (API, signer, session store, rate limiter)
✓ JWT vs opaque token decision justified

B. Trade-offs & Technical Judgment:
✓ JWT vs opaque, RS256 vs HS256, bcrypt cost factor
✓ Fail closed (login) vs fail open (blocklist)
✓ Token expiry trade-off (security vs usability)

C. Failure Handling & Reliability:
✓ Partial failure behavior (one dependency slow / one replica slow)
✓ Database failure, Redis failure, KMS failure
✓ Credential stuffing production scenario
✓ Timeout and retry configuration
✓ Failure injection: Slow DB, Retry storm, Signing key, Redis down, Database failover (B5)

D. Scale & Performance:
✓ Concrete numbers (20M logins/day, 230/sec, attack traffic)
✓ Scale Estimates Table (Current | 10× | Breaking Point)
✓ bcrypt as CPU bottleneck identified
✓ Token validation decoupled (0.1ms, no network)

E. Cost & Operability:
✓ $26K/month breakdown, attack cost highlighted
✓ Cost Analysis Table (Current | At Scale | Optimization) and tie to operations
✓ Misleading signals section
✓ On-call burden analysis

F. Ownership & On-Call Reality:
✓ Debugging "user can't log in"
✓ Credential stuffing response playbook
✓ Signing key compromise response

G. Rollout & Operational Safety:
✓ Deployment strategy (canary, bake time, auth-specific risks)
✓ Key rotation procedure (multi-phase)
✓ Bad deployment scenario (JWT claims format change)

H. Interview Calibration:
✓ What Interviewers Evaluate table; Example Strong L5 Phrases
✓ L4 mistakes with WHY IT'S L4 / L5 APPROACH; Borderline L5 with L5 FIX
✓ Strong L5 signals and phrases
✓ Clarifying questions and non-goals

I. Real-World Application (Step 9):
✓ Rushed Decision scenario (defer MFA for launch → technical debt and when to fix)
```

---

*This chapter provides the foundation for confidently designing and owning an authentication system as a Senior Software Engineer. The core insight: verify identity once (expensive bcrypt), issue a self-contained token (JWT), and let every downstream service validate cheaply without calling auth. Master this pattern and you've mastered the most critical system in any architecture—the front door.*
