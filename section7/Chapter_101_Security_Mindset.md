# Chapter 80: Security Mindset

> TODO: Full chapter to be written.

---

## Planned Coverage

**Core thesis:** Security is not a feature you add at the end. It is a way of thinking about every design decision. The question is not "is this secure?" but "what is the worst thing an adversary could do with this?"

**Topics to cover:**

### Part 1: Thinking Like an Attacker
- The adversarial mindset: assume every input is malicious
- Attack surface: what does the system expose and to whom?
- Threat modeling: STRIDE (Spoofing, Tampering, Repudiation, Info Disclosure, Denial of Service, Elevation of Privilege)
- The "what if the caller is lying?" question applied to every API

### Part 2: OWASP Top 10 for Backend Engineers
- SQL injection and how ORMs can still be vulnerable
- Authentication failures: weak tokens, session fixation, credential stuffing
- Injection (not just SQL): command injection, LDAP injection, template injection
- Insecure direct object references (IDOR): the most common API bug
- Security misconfiguration: default credentials, open S3 buckets, verbose errors
- Cryptographic failures: MD5 passwords, HTTP instead of HTTPS, weak random

### Part 3: Auth Patterns (Authentication + Authorization)
- Authentication: who are you? (API keys, OAuth2, JWT, session tokens)
- Authorization: what can you do? (RBAC, ABAC, policy engines)
- The confused deputy problem: when a service has more permissions than the caller
- JWT pitfalls: algorithm confusion, no expiry, no revocation
- The principle of least privilege: why services should only have what they need

### Part 4: Secure Defaults
- Deny by default: fail closed, not open
- Defense in depth: multiple layers, no single point of failure
- Secure coding patterns: parameterized queries, prepared statements, output encoding
- Secret management: no secrets in code, no secrets in logs, rotation strategy

### Part 5: Security in System Design
- How to think about security during a system design interview
- Data classification: PII, financial data, credentials — different handling for each
- Encryption at rest vs in transit vs in use
- Audit logging: what to log for security events and why
- Rate limiting and abuse prevention as security controls

### Real Incidents
- Equifax 2017: unpatched library, 147M records exposed
- Capital One 2019: SSRF attack via misconfigured WAF + overprivileged IAM role
- Uber 2016: credentials in GitHub repo, 57M records exposed

### Exercises
- Threat model a payment API using STRIDE
- Find the security bugs in a fictional API design (5 bugs hidden in the spec)
- Design the auth system for a multi-tenant SaaS product

---

*Status: TODO — placeholder only*
