# Chapter 47. Configuration, Feature Flags & Secrets Management

---

# Introduction

Configuration systems are the invisible control plane of every production system. I've spent years building and operating configuration infrastructure at Google, and I'll be direct: the hardest part isn't storing key-value pairs—any junior engineer can build that. The hard part is propagating configuration changes to 100,000 servers in seconds without causing a cascading outage, providing instant feature flag evaluation without adding latency to every request, managing secrets that must never appear in logs or crash dumps, and doing it all with an audit trail that can survive a compliance investigation.

This chapter covers the design of a unified configuration, feature flags, and secrets management system at Staff Engineer depth: with deep understanding of the propagation latency that determines blast radius, awareness of the evaluation-path trade-offs that define flag architecture, and judgment about when dynamic configuration is a liability rather than an asset.

**The Staff Engineer's First Law of Configuration**: Configuration changes are the leading cause of production outages. More incidents are caused by config pushes than by code deploys. Treat your configuration system with MORE rigor than your deployment pipeline, not less.

---

## Quick Visual: Configuration, Feature Flags & Secrets System at a Glance

```
┌─────────────────────────────────────────────────────────────────────────────┐
│    CONFIGURATION, FEATURE FLAGS & SECRETS: THE STAFF ENGINEER VIEW          │
│                                                                             │
│   WRONG Framing: "Store and retrieve configuration values"                  │
│   RIGHT Framing: "Safely propagate state changes to a global fleet in      │
│                   seconds, with rollback, audit, targeting, and            │
│                   cryptographic secret protection—without ever being        │
│                   on the critical path of user requests"                    │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Before designing, understand:                                      │   │
│   │                                                                     │   │
│   │  1. What is the propagation latency requirement? (seconds? minutes?)│   │
│   │  2. Is flag evaluation on the hot path of every user request?       │   │
│   │  3. Who needs to change config: engineers only, or PMs and ops too? │   │
│   │  4. What is the blast radius of a bad config change?                │   │
│   │  5. How do secrets rotate without downtime?                         │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   THE UNCOMFORTABLE TRUTH:                                                  │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Instant propagation + zero downtime + full audit + fine-grained   │   │
│   │  targeting + secret encryption + no added latency to user requests  │   │
│   │  is ACHIEVABLE—but only if you accept that the configuration       │   │
│   │  system must be MORE reliable than any system it configures.       │   │
│   │  If the config system goes down, every dependent service is frozen │   │
│   │  at its last-known-good state. That's acceptable. What's NOT       │   │
│   │  acceptable is the config system pushing bad state to all servers  │   │
│   │  simultaneously.                                                    │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## L5 vs L6 Configuration / Feature Flags / Secrets Decisions

| Scenario | L5 Approach | L6 Approach |
|----------|-------------|-------------|
| **Config propagation** | "Push changes via API, services poll every 30 seconds" | "Local sidecar caches config, receives streaming updates via long-poll or gRPC stream. Propagation P99 < 5 seconds. But propagation speed is the ENEMY of safety—always pair fast propagation with gradual rollout." |
| **Feature flags** | "Boolean flag checked in an if statement" | "Flags are typed (bool, int, string, JSON), targeted (by user segment, percentage, region), versioned, and evaluated locally with no network call. Flag lifecycle includes creation, rollout, full-on, and cleanup. Stale flags are tech debt." |
| **Secrets** | "Store in environment variables or encrypted config file" | "Secrets are never stored in application memory longer than needed. Fetched from a secrets manager, cached briefly in a sidecar with memory-pinned buffers (no swap), rotated automatically, and audited on every access. The application never sees the raw secret if possible—use short-lived tokens or wrapped keys." |
| **Blast radius** | "Test in staging, then deploy to production" | "Canary to 1% of traffic for 15 minutes. Watch error rates. Expand to 10%, 50%, 100%. Any config change that skips canary is a P0 incident waiting to happen." |
| **Rollback** | "Revert the config and redeploy" | "Instant rollback: Every config change stores the previous version. Rollback is a one-click operation that propagates in < 5 seconds. The system maintains last-known-good state locally so even if the config server is unreachable, services continue with safe defaults." |

**Key Difference**: L6 engineers recognize that configuration is the most dangerous mutation surface in production. Code deploys are tested in CI, reviewed in PRs, and deployed gradually. Config changes often skip all of that—a single API call can change behavior across 100,000 servers in seconds. The system must enforce safety rails that prevent humans from destroying production with a typo.

---

# Part 1: Foundations — What a Configuration, Feature Flags & Secrets System Is and Why It Exists

## What Is a Configuration, Feature Flags & Secrets System?

A configuration, feature flags, and secrets management system provides a centralized, auditable, and safe mechanism to control the runtime behavior of distributed services without deploying new code.

It answers three fundamental questions:
1. **What parameters should this service use right now?** (Configuration)
2. **Should this feature be enabled for this specific user/request?** (Feature flags)
3. **What credentials does this service need to authenticate to its dependencies?** (Secrets)

### The Three Domains

```
┌─────────────────────────────────────────────────────────────────────────────┐
│              THE THREE DOMAINS OF RUNTIME STATE                             │
│                                                                             │
│   ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐          │
│   │  CONFIGURATION   │  │  FEATURE FLAGS   │  │     SECRETS      │          │
│   │                  │  │                  │  │                  │          │
│   │ What:            │  │ What:            │  │ What:            │          │
│   │ Key-value pairs  │  │ Conditional      │  │ Credentials,     │          │
│   │ that control     │  │ toggles that     │  │ keys, tokens     │          │
│   │ service behavior │  │ enable/disable   │  │ for auth &       │          │
│   │                  │  │ features per     │  │ encryption       │          │
│   │                  │  │ context          │  │                  │          │
│   │ Examples:        │  │ Examples:        │  │ Examples:        │          │
│   │ • Timeout: 500ms │  │ • new_checkout:  │  │ • DB password    │          │
│   │ • Max retries: 3 │  │   true for 10%   │  │ • API key        │          │
│   │ • Rate limit:    │  │ • dark_mode:     │  │ • TLS cert       │          │
│   │   1000 req/s     │  │   true for beta  │  │ • Signing key    │          │
│   │ • Log level:     │  │ • kill_switch:   │  │                  │          │
│   │   WARN           │  │   false globally │  │                  │          │
│   │                  │  │                  │  │                  │          │
│   │ Changed by:      │  │ Changed by:      │  │ Changed by:      │          │
│   │ Engineers, SREs  │  │ PMs, engineers   │  │ Security team,   │          │
│   │                  │  │                  │  │ automated        │          │
│   │                  │  │                  │  │ rotation         │          │
│   │ Sensitivity:     │  │ Sensitivity:     │  │ Sensitivity:     │          │
│   │ Medium           │  │ Low-Medium       │  │ CRITICAL         │          │
│   │ (bad value =     │  │ (bad flag =      │  │ (leaked secret = │          │
│   │  outage)         │  │  broken feature) │  │  breach)         │          │
│   └──────────────────┘  └──────────────────┘  └──────────────────┘          │
│                                                                             │
│   WHY ONE SYSTEM?                                                           │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  All three share: versioning, audit, propagation, access control,  │   │
│   │  rollback, and the need to be available when everything else fails.│   │
│   │  Building three separate systems means three separate failure      │   │
│   │  modes, three audit trails, and three propagation mechanisms.      │   │
│   │                                                                     │   │
│   │  Staff insight: Unify the control plane. Differentiate the data    │   │
│   │  plane. Config and flags can share storage and propagation.        │   │
│   │  Secrets need separate encryption, access control, and audit.      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### The Simplest Mental Model

```
┌─────────────────────────────────────────────────────────────────────────────┐
│           CONFIGURATION: THE THERMOSTAT ANALOGY                             │
│                                                                             │
│   Think of a config system as the thermostat + light switches + safe        │
│   in a building:                                                            │
│                                                                             │
│   THERMOSTAT (configuration)                                                │
│   • Set temperature to 72°F → All rooms adjust                              │
│   • Change is immediate, affects all rooms                                  │
│   • Wrong setting (200°F) → Building damage                                 │
│   • Need: Central control, safety limits, rollback                          │
│                                                                             │
│   LIGHT SWITCHES (feature flags)                                            │
│   • Turn on lights in specific rooms → Not all rooms                        │
│   • Some rooms have dimmers (percentage rollout)                            │
│   • "Party mode" switch (A/B testing different configurations)              │
│   • Need: Per-room control, gradual activation                              │
│                                                                             │
│   SAFE (secrets)                                                            │
│   • Contains valuables (credentials, keys)                                  │
│   • Only authorized people can open it                                      │
│   • Combination changes periodically (rotation)                             │
│   • Access logged (audit trail)                                             │
│   • Contents never displayed on lobby screen (no logging secrets)           │
│                                                                             │
│   COMPLICATIONS AT SCALE:                                                   │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  What if you have 10,000 buildings? (10K services)                  │   │
│   │  → Central thermostat server must propagate to all buildings fast    │   │
│   │                                                                     │   │
│   │  What if someone sets the thermostat to 200°F?                      │   │
│   │  → Need validation: reject dangerous values before propagation      │   │
│   │                                                                     │   │
│   │  What if the thermostat server goes down?                           │   │
│   │  → Buildings must maintain last-known-good temperature              │   │
│   │                                                                     │   │
│   │  What if the safe combination leaks?                                │   │
│   │  → Must rotate immediately, everywhere, without downtime            │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Why a Configuration, Feature Flags & Secrets System Exists

### 1. Decoupling Deployment from Release

The single most important reason for feature flags:

```
Without feature flags:
  Code deploy = Feature release
  → If feature is broken, must roll back entire deploy
  → Rolling back may revert other critical fixes
  → Deploy freezes during holidays = No releases for weeks

With feature flags:
  Code deploy ≠ Feature release
  → Deploy code with feature behind flag (disabled)
  → Enable flag for 1% of users → Test in production
  → If broken: Disable flag in seconds (no deploy needed)
  → Other code changes unaffected
  → Can release on holidays: Just flip a flag, rollback is instant

Staff insight: Feature flags convert "deploy and pray" into 
"deploy inert code, activate gradually, observe, decide."
```

### 2. Dynamic Tuning Without Deploys

Configuration changes that would otherwise require a deploy:

```
Without dynamic config:
  "Latency is spiking. We need to increase the timeout from 500ms to 2000ms."
  → Engineer writes code change
  → PR review (30 minutes)
  → CI/CD pipeline (15 minutes)
  → Canary deploy (30 minutes)
  → Full rollout (20 minutes)
  TOTAL: ~95 minutes to change one number

With dynamic config:
  "Latency is spiking. Increasing timeout to 2000ms."
  → Engineer changes config value in UI
  → Config propagates to all servers
  TOTAL: < 30 seconds
```

### 3. Safe Credential Management

Why environment variables and config files are insufficient:

```
Environment variables:
  Problem 1: Visible in /proc/<pid>/environ on Linux (any process can read)
  Problem 2: Inherited by child processes (unintended exposure)
  Problem 3: No rotation without restart
  Problem 4: No access audit (who read it? when?)
  Problem 5: Often committed to version control "accidentally"

Config files (even encrypted):
  Problem 1: Decryption key must be stored somewhere (turtles all the way down)
  Problem 2: File permissions are coarse (all-or-nothing per user)
  Problem 3: Rotation requires file rewrite + service restart
  Problem 4: No audit trail on reads

Secrets manager:
  ✓ Accessed via authenticated API call (identity-based access)
  ✓ Audit log on every read and write
  ✓ Automatic rotation with zero-downtime handoff
  ✓ Never stored on disk in plaintext (in-memory only, briefly)
  ✓ Lease-based access (secrets expire, must be re-fetched)
  ✓ Dynamic secrets (generate unique DB credentials per service instance)
```

### 4. Operational Control During Incidents

Kill switches, rate limit adjustments, and degradation controls:

```
Incident response with config system:

T+0min:   Database overloaded, read latency at 5s
T+0.5min: On-call enables kill_switch_heavy_queries flag
          → All expensive queries disabled in < 5 seconds
T+1min:   Sets cache_ttl from 60s to 300s (reduce DB load)
T+2min:   Sets rate_limit from 10000 to 5000 req/s
T+3min:   Database load dropping, latency recovering
T+5min:   Root cause identified: missing index on new query pattern
T+20min:  Index created, tested
T+21min:  Reverts all config changes (one click per change)
T+22min:  Normal operation restored

Without config system: Each of those changes is a code deploy.
During a fire, you don't want to be running CI pipelines.
```

## What Happens If a Configuration System Does NOT Exist (or Fails)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│              CONFIGURATION SYSTEM FAILURE MODES                              │
│                                                                             │
│   FAILURE MODE 1: CONFIG POISONING                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Bad config value pushed to all servers simultaneously               │   │
│   │  → timeout_ms set to 0 → All requests immediately time out          │   │
│   │  → 100% of traffic fails → Global outage                            │   │
│   │                                                                     │   │
│   │  This is THE #1 cause of severe production outages at scale.        │   │
│   │  Google, Facebook, Microsoft have all had config-induced outages.   │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   FAILURE MODE 2: SECRET LEAK                                               │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Database password committed to Git repository                       │   │
│   │  → Scraped by automated bots within minutes                         │   │
│   │  → Database accessed, data exfiltrated                              │   │
│   │  → Regulatory notification required (GDPR, SOC2, etc.)             │   │
│   │                                                                     │   │
│   │  Cost: Millions in breach response, legal, and reputation damage.   │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   FAILURE MODE 3: FLAG DEBT EXPLOSION                                       │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  500 feature flags, half of them stale (never cleaned up)           │   │
│   │  → Nobody knows which flags are active or what they do              │   │
│   │  → Flag interactions cause unexpected behavior                      │   │
│   │  → "Turning on flag A breaks feature B because of flag C"           │   │
│   │                                                                     │   │
│   │  Staff insight: Feature flags are RENTAL, not PURCHASE.             │   │
│   │  Every flag has a cost. If it's not being actively rolled out,      │   │
│   │  remove it.                                                         │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   FAILURE MODE 4: CONFIG SERVER OUTAGE                                      │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Config server goes down → New instances can't start                │   │
│   │  → Existing instances can't receive updates                         │   │
│   │  → If services crash-loop, they can't get config to restart         │   │
│   │                                                                     │   │
│   │  Staff insight: The config system must NEVER be on the startup      │   │
│   │  critical path with zero fallback. Services must start with         │   │
│   │  compiled-in defaults or cached config from the last healthy run.   │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   FAILURE MODE 5: PROPAGATION INCONSISTENCY                                 │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Config change reaches 60% of servers but not the rest              │   │
│   │  → Split-brain: Some servers use new behavior, others old           │   │
│   │  → User experience is inconsistent depending on which server        │   │
│   │    handles the request                                              │   │
│   │  → Debugging is a nightmare: "It works sometimes"                   │   │
│   │                                                                     │   │
│   │  Staff insight: Propagation must be atomic per config version.      │   │
│   │  All servers either see version N or version N+1, never a mix       │   │
│   │  of individual key changes.                                         │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Part 2: Functional Requirements

## Core Use Cases

### 1. Configuration Management

```
USE CASE: Store and retrieve typed configuration values

Operations:
  CREATE config namespace "payment-service/production"
  SET key "timeout_ms" = 500 (type: integer, min: 100, max: 30000)
  SET key "retry_count" = 3 (type: integer, min: 0, max: 10)
  SET key "allowed_currencies" = ["USD", "EUR", "GBP"] (type: string_list)
  GET key "timeout_ms" → 500
  UPDATE key "timeout_ms" = 1000 (with reason: "latency spike mitigation")
  
Namespacing:
  Config is organized hierarchically:
  /org/team/service/environment/key
  Example: /payments/checkout/payment-service/production/timeout_ms

  Inheritance: If key not found in /production, check /default
  Override: /production overrides /default for the same key

Validation:
  Each key has a schema (type, range, regex, allowed values)
  Invalid values are REJECTED at write time, not at read time
  → Prevents config poisoning before it reaches any server
```

### 2. Feature Flag Management

```
USE CASE: Control feature availability with fine-grained targeting

Flag definition:
  name: "new_checkout_flow"
  type: boolean
  default: false
  description: "Enables redesigned checkout UI"
  owner: "team-checkout"
  created: 2024-01-15
  
Targeting rules (evaluated in order):
  Rule 1: IF user_id IN [internal_testers] → true   (dogfood)
  Rule 2: IF user.country == "NZ" → true             (geo launch)
  Rule 3: IF hash(user_id) % 100 < 10 → true         (10% rollout)
  Rule 4: DEFAULT → false

Evaluation:
  evaluate("new_checkout_flow", context={user_id: "abc123", country: "US"})
  → Checks rules in order
  → First matching rule determines value
  → No match → default value (false)

Lifecycle:
  CREATED → TARGETING (gradual rollout) → FULLY_ON → CLEANUP (remove flag)
  
  Flags that remain in FULLY_ON for > 30 days generate cleanup tickets.
  Flags that remain in TARGETING for > 90 days generate review alerts.
```

### 3. Secrets Management

```
USE CASE: Securely store, access, rotate, and audit credentials

Secret storage:
  PATH: /secrets/payment-service/production/db_password
  VALUE: <encrypted, never returned in API responses, only to authorized services>
  VERSION: 3 (previous versions retained for rotation)
  ROTATION_POLICY: Every 90 days
  LAST_ROTATED: 2024-06-15T00:00:00Z
  NEXT_ROTATION: 2024-09-13T00:00:00Z

Secret access:
  Service authenticates via mTLS / service identity
  Requests secret: GET /secrets/payment-service/production/db_password
  System verifies:
    1. Service identity (is this really payment-service?)
    2. Access policy (is payment-service allowed to read this secret?)
    3. Environment match (production service accessing production secret?)
  Returns: Decrypted secret value + lease (TTL: 1 hour)
  Logs: WHO accessed WHAT at WHEN (audit trail)

Secret rotation (zero-downtime):
  Phase 1: Generate new secret (version N+1)
  Phase 2: Configure dependency to accept BOTH old (N) and new (N+1)
  Phase 3: Propagate new secret to all consuming services
  Phase 4: Verify all services using new secret (version N+1)
  Phase 5: Revoke old secret (version N)
  
Dynamic secrets (advanced):
  Instead of shared password, generate unique credentials per service instance
  → Each instance gets unique DB user: "payment-svc-pod-abc123"
  → Credentials auto-expire after lease TTL
  → Revocation is per-instance, not per-service
```

### 4. Gradual Rollout and Experimentation

```
USE CASE: Safely roll out changes to increasing percentages of traffic

Rollout stages:
  Stage 1: 0.1% (canary) — 15 minutes observation
  Stage 2: 1% — 30 minutes observation
  Stage 3: 5% — 1 hour observation
  Stage 4: 25% — 2 hours observation
  Stage 5: 50% — 4 hours observation
  Stage 6: 100% — Fully rolled out

Automatic rollback triggers:
  IF error_rate(treatment) > error_rate(control) * 1.5 → Auto-rollback
  IF latency_p99(treatment) > latency_p99(control) * 2.0 → Auto-rollback
  IF crash_rate(treatment) > 0 → Immediate rollback

A/B testing:
  Flag: "checkout_button_color"
  Variant A: "blue" (50% of users)
  Variant B: "green" (50% of users)
  Metric: conversion_rate
  
  Consistent assignment: Same user always sees same variant
  (hash(user_id + flag_name) determines bucket)
```

### 5. Change Audit and Compliance

```
USE CASE: Track every configuration change for compliance and debugging

Audit record:
  {
    timestamp: "2024-09-15T14:23:17Z",
    actor: "engineer@company.com",
    action: "UPDATE",
    namespace: "payment-service/production",
    key: "timeout_ms",
    old_value: 500,
    new_value: 1000,
    reason: "Latency spike mitigation per incident INC-4523",
    approval: "sre-lead@company.com",
    propagation_status: "COMPLETE",
    servers_updated: 2847,
    propagation_time_ms: 4230
  }

Query capabilities:
  "Show me all config changes in the last 24 hours" (incident investigation)
  "Show me all changes by user X" (access review)
  "Show me all changes to payment-service" (change history)
  "Show me who accessed secret Y" (security audit)
```

## Read Paths

```
READ PATH 1: Service reads config value (hot path, every request)
  Service → Local cache (sidecar/SDK) → Return value
  Latency: < 1 microsecond (in-process memory lookup)
  Never goes to network on the hot path

READ PATH 2: Config propagation (background, streaming)
  Config server → (change event) → Sidecar/SDK → Update local cache
  Latency: P99 < 5 seconds from write to all servers updated
  Uses long-poll, gRPC streaming, or server-sent events

READ PATH 3: Feature flag evaluation (hot path, per request)
  Service → SDK.evaluate(flag, context) → Local rules engine → Return value
  Latency: < 100 microseconds (in-process rule evaluation)
  No network call—all targeting rules cached locally

READ PATH 4: Secret fetch (startup + periodic refresh)
  Service → Sidecar → Secrets API → Decrypt → Return to sidecar
  Latency: < 50ms (network call, but infrequent)
  Cached in memory for lease duration (typically 1 hour)
  
READ PATH 5: Audit log query (admin/compliance, not hot path)
  Admin UI → Audit API → Audit store (indexed by time, actor, namespace)
  Latency: < 500ms for recent queries, seconds for historical
```

## Write Paths

```
WRITE PATH 1: Config value update
  Actor → API → Validate schema → Check permissions → Write to store
  → Version increment → Trigger propagation → Return success
  
  MUST: Validate before write (reject invalid values)
  MUST: Record audit log
  MUST: Support atomic multi-key updates (all-or-nothing)

WRITE PATH 2: Feature flag update
  Actor → API → Validate targeting rules → Write to store
  → Trigger propagation → Return success
  
  MUST: Validate targeting rule syntax
  MUST: Check for circular dependencies between flags
  MUST: Support draft/review/publish workflow

WRITE PATH 3: Secret write/rotation
  Actor → API → Encrypt with KMS → Write encrypted blob → Version increment
  → Trigger propagation to authorized consumers → Return success
  
  MUST: Encrypt at rest with service-specific key (envelope encryption)
  MUST: Never log the plaintext secret value
  MUST: Audit the write operation
```

## Control / Admin Paths

```
CONTROL PATH 1: Namespace/permission management
  Create namespaces, assign team ownership, configure access policies
  Grant/revoke read/write permissions per namespace, per service, per environment

CONTROL PATH 2: Schema management
  Define config key schemas (type, range, validation rules)
  Update schemas (with backward compatibility checks)

CONTROL PATH 3: Rollback
  Instant rollback of any config/flag change to previous version
  Rollback propagates with the same mechanism as forward changes
  
CONTROL PATH 4: Emergency kill switch
  Predefined flags that disable expensive features instantly
  No approval workflow—authorized on-call can flip immediately
  Kill switches propagate with HIGHEST priority

CONTROL PATH 5: Secret rotation trigger
  Manual or automated trigger to rotate a specific secret
  Initiates the multi-phase rotation workflow
  
CONTROL PATH 6: Config freeze
  Lock a namespace to prevent ALL changes (during critical periods)
  Only a designated admin can lift the freeze
```

## Edge Cases

```
EDGE CASE 1: Service starts with no network access to config server
  → Must start with compiled-in defaults or cached config from last run
  → Config file baked into container image as fallback

EDGE CASE 2: Config change partially propagated when network partitions
  → Some servers on version N, others on N+1
  → Must be tolerable: Config changes should be backward-compatible
  → Propagation retries until all servers acknowledge

EDGE CASE 3: Two actors change the same key simultaneously
  → Last-writer-wins with version conflict detection
  → Optimistic concurrency: "Update key X from version 5 to 6"
  → If version is 6 already, reject with conflict error

EDGE CASE 4: Feature flag targeting rule references non-existent attribute
  → Default to flag's default value (conservative behavior)
  → Log warning for debugging
  → Never crash the flag evaluation path

EDGE CASE 5: Secret rotation fails midway
  → Old secret still valid (dual-active period)
  → Retry rotation
  → Alert if rotation stuck for > 24 hours

EDGE CASE 6: Config value exceeds size limit
  → Individual values: Max 1 MB (reject larger)
  → Total config per namespace: Max 10 MB
  → Very large configs signal a design problem (config, not data)
```

## Intentionally Out of Scope

```
OUT OF SCOPE 1: Infrastructure-as-code (Terraform, Kubernetes manifests)
  → Different lifecycle: tied to deploy, not runtime
  → Different tooling: declarative, plan-apply model
  → We handle runtime config that changes BETWEEN deploys

OUT OF SCOPE 2: A/B testing statistical analysis
  → We provide flag targeting and consistent bucketing
  → Statistical significance calculation is a separate analysis system
  → We expose flag assignment events for the analysis system to consume

OUT OF SCOPE 3: Full PKI / Certificate Authority
  → We store and rotate TLS certificates as secrets
  → We do NOT run a full CA or manage certificate issuance chains
  → That's a separate infrastructure system

OUT OF SCOPE 4: Application-level state management
  → Config is for BEHAVIOR control, not DATA storage
  → "Rate limit = 1000 req/s" is config
  → "User X's preferences" is application data, not config
```

---

# Part 3: Non-Functional Requirements

## Latency Expectations

```
OPERATION                       P50         P99         Notes
─────────────────────────────────────────────────────────────────
Config read (local cache)       < 1µs       < 10µs      In-process memory
Flag evaluation (local)         < 50µs      < 200µs     In-process rules
Config propagation              < 2s        < 5s        Server to all clients
Secret fetch (cold)             < 20ms      < 100ms     Network + decrypt
Secret fetch (cached)           < 1µs       < 10µs      In-process memory
Config write (API)              < 50ms      < 200ms     Write + validate
Audit log query (recent)        < 100ms     < 500ms     Indexed query
Audit log query (historical)    < 1s        < 5s        Range scan

CRITICAL INSIGHT:
  Config/flag reads are on the HOT PATH of every user request.
  They MUST be local (in-process) operations.
  
  A 1ms network call per flag evaluation × 5 flags per request × 
  100,000 requests/second = 500,000 network calls/second to the config server.
  This kills the config server AND adds 5ms to every request.
  
  The ONLY acceptable design: Local evaluation with background sync.
```

## Availability Expectations

```
CONFIG READ: 99.999% (five nines)
  → Achieved through local caching + stale-if-unavailable
  → If config server is down, services use last-known-good config
  → Reads NEVER fail (return cached value or compiled-in default)

CONFIG WRITE: 99.95% (three and a half nines)
  → Config writes can tolerate brief unavailability
  → If config server is down for 5 minutes, changes queue and apply later
  → This is acceptable: Config changes are infrequent (not per-request)

SECRET READ: 99.99% (four nines)
  → Secrets cached locally with lease TTL
  → If secrets server is down, cached secrets remain valid until lease expires
  → Lease renewal retries automatically

SECRET WRITE/ROTATION: 99.9% (three nines)
  → Secret writes are very infrequent (rotation every 90 days)
  → Can tolerate brief unavailability without impact

PROPAGATION: 99.9% within SLA (< 5 seconds)
  → 0.1% of config changes may take up to 30 seconds
  → This is acceptable if the system can detect and alert on slow propagation

Staff insight: Config READS are the most critical path because they affect
every user request. Config WRITES are far less critical because they're
infrequent. Design accordingly: Over-invest in read availability.
```

## Consistency Needs

```
CONFIG/FLAG VALUES: Eventual consistency (bounded staleness)
  → All servers will eventually see the same config version
  → Propagation guarantee: Within 5 seconds, 99.9% of servers updated
  → Within 30 seconds: 100% of servers updated
  
  Acceptable: Server A sees config version 42 while Server B still sees 41
  → Brief inconsistency during propagation window
  → Applications must tolerate this (config changes are backward-compatible)

CONFIG WRITES: Strong consistency (single writer per namespace)
  → Config store returns success only after durable write
  → Version numbers are strictly monotonic
  → Two concurrent writers to the same key: One succeeds, one gets conflict

SECRET VALUES: Strong consistency for writes, eventual for reads
  → After rotation, new secret version must be durably stored
  → Propagation to consumers is eventually consistent
  → Dual-secret acceptance period handles the consistency gap

AUDIT LOG: At-least-once delivery, eventual consistency
  → Every change MUST be logged (no gaps)
  → Duplicates in audit log are acceptable (idempotent writes)
  → Log may be slightly behind real-time (seconds, not minutes)
```

## Durability

```
CONFIG VALUES: MUST survive any single failure (replicated storage)
  → Stored in replicated datastore (3+ replicas)
  → Full version history retained (never overwrite, always append)
  → Backup to cold storage every 24 hours

SECRET VALUES: MUST survive any single failure + encryption at rest
  → Encrypted before storage (envelope encryption with KMS)
  → Replicated across 3+ nodes in different failure domains
  → Hardware Security Module (HSM) for master key in highest-security tier

AUDIT LOG: MUST be immutable and durable
  → Append-only storage (no deletion or modification)
  → Replicated across availability zones
  → Retained for regulatory period (typically 7 years)
  → Separate from config storage (different failure domain)

LOCAL CACHE: Ephemeral (can be rebuilt from server)
  → Persisted to local disk as optimization (faster restart)
  → If local cache corrupted: Fetch full config from server
  → If server unreachable AND local cache corrupted: Use compiled-in defaults
```

## Correctness vs User Experience Trade-offs

```
TRADE-OFF 1: Propagation speed vs safety
  Faster propagation: Changes reach servers in < 1 second
  Problem: Bad changes also reach ALL servers in < 1 second
  Resolution: Propagation speed is configurable per change
    → Normal changes: 5-second propagation
    → Gradual rollout: Hours (percentage-based)
    → Emergency rollback: < 1 second (highest priority)

TRADE-OFF 2: Flag evaluation accuracy vs latency
  Accurate: Fetch latest rules from server on every evaluation
  Fast: Evaluate against locally cached rules (may be slightly stale)
  Resolution: Local evaluation always. Accept up to 5-second staleness.
  → 5 seconds of stale flag state is ALWAYS better than 5ms added latency.

TRADE-OFF 3: Secret security vs availability
  Secure: Short lease TTL (5 minutes), frequent re-fetch
  Available: Long lease TTL (24 hours), survives long server outages
  Resolution: Lease TTL = 1 hour (compromise)
    → Re-fetch every 50 minutes (before expiry)
    → Survives 1-hour config server outage without impact
    → Rotated secrets take up to 1 hour to fully propagate

TRADE-OFF 4: Validation strictness vs operational flexibility
  Strict: Reject any change that doesn't match schema exactly
  Flexible: Allow schema-violating changes with override flag
  Resolution: Strict by default, with emergency override for on-call
    → Emergency override requires additional approval + creates alert
    → Never allow schema bypass without audit trail
```

## Security Implications

```
THREAT MODEL:
  1. Compromised service reads another service's secrets
     → Mitigation: Service identity verification + per-service access policies
  
  2. Insider modifies config to cause outage
     → Mitigation: Audit trail + approval workflow for production changes
     → Two-person rule for critical config namespaces
  
  3. Config server compromised, attacker pushes malicious config
     → Mitigation: Config signing (changes signed with deploy key)
     → Clients verify signature before applying config
  
  4. Secret exfiltrated from memory dump or core dump
     → Mitigation: Secrets in memory-locked pages (mlock, no swap)
     → Core dump exclusion for secret memory regions
     → Secrets redacted from logging/error reporting
  
  5. Replay attack: Old config version replayed to revert security fix
     → Mitigation: Monotonic version numbers
     → Clients reject config with version lower than current
```

---

# Part 4: Scale & Load Modeling

## Users and Sources

```
CONFIG PRODUCERS (write-side):
  Engineers: ~5,000 (make config changes)
  Automated systems: ~200 (CI/CD pipelines, rotation jobs)
  
  Config changes per day: ~500 (human) + ~2,000 (automated) = ~2,500
  Most changes happen during business hours (10 AM - 6 PM)
  
CONFIG CONSUMERS (read-side):
  Services: 10,000 distinct services
  Instances: 500,000 server instances (containers/pods/VMs)
  
  Each instance evaluates config: ~100 lookups per request
  Each instance evaluates feature flags: ~10 evaluations per request
  Combined: ~110 config reads per request per instance

FLAG EVALUATIONS:
  If each instance handles 1,000 requests/second:
  → 110 × 1,000 = 110,000 flag evaluations/second per instance
  → 110,000 × 500,000 instances = 55 BILLION evaluations/second globally
  
  This CANNOT be a network call. Must be in-process.
  
SECRETS:
  Distinct secrets: ~50,000 (across all services and environments)
  Secret reads: ~500,000/hour (one per instance per lease renewal)
  Secret writes: ~100/day (rotations + new secrets)
```

## QPS and Throughput

```
CONFIG SERVER API:
  Write QPS: ~3 writes/second (2,500/day ÷ ~800 active seconds)
    Peak: ~30 writes/second (deploy wave, mass rotation)
  
  Read QPS (propagation):
    Long-poll/streaming: 500,000 persistent connections
    Each connection: ~1 update per minute (heartbeat/keepalive)
    Config change: 500,000 push notifications within 5 seconds
    → Burst: 100,000 notifications/second during config propagation

SECRETS API:
  Read QPS: ~140/second (500,000/hour steady state)
    Peak: ~1,000/second (mass restart event)
  Write QPS: ~0.001/second (negligible)
  
AUDIT LOG:
  Write QPS: ~10/second (config changes + secret accesses + flag changes)
  Read QPS: ~1/second (admin queries, compliance tools)

TOTAL CONFIG SERVER LOAD:
  Steady state: 500,000 persistent connections + 140 secret reads/second
  Burst: 100,000 push notifications/second during propagation
  
  Staff insight: The load is dominated by CONNECTION count, not QPS.
  500,000 persistent connections is the sizing constraint, not queries.
```

## Read/Write Ratio

```
CONFIG VALUES:
  Write: ~2,500/day ≈ 0.03/second
  Read: 55 billion/second (in-process, not server)
  Effective server read: ~500,000/second (propagation pushes)
  
  Read:Write ratio (server): ~17,000,000:1
  Read:Write ratio (total):  ~2,000,000,000,000:1
  
  This is one of the most extreme read-heavy systems in existence.
  The read path MUST be fully local. Any server involvement in reads
  is architecturally wrong.

SECRETS:
  Read:Write ratio: ~140:0.001 ≈ 140,000:1
  Also extremely read-heavy, but reads hit the server (not local-only)

AUDIT LOG:
  Write:Read ratio: 10:1
  Write-heavy! Audit is an append-only write workload with rare reads.
```

## Growth Assumptions

```
SERVICES: +20% per year (microservices proliferation)
  Year 0: 10,000 services, 500,000 instances
  Year 1: 12,000 services, 600,000 instances
  Year 3: 17,000 services, 860,000 instances

CONFIG KEYS: +30% per year (more granular config)
  Year 0: 500,000 distinct config keys
  Year 1: 650,000 keys
  Year 3: 1,100,000 keys

FEATURE FLAGS: +50% per year (more teams adopt flags)
  Year 0: 5,000 active flags
  Year 1: 7,500 flags
  Year 3: 16,800 flags (flag debt becomes a problem at Year 2)

SECRETS: +25% per year
  Year 0: 50,000 secrets
  Year 3: 97,000 secrets

DANGEROUS ASSUMPTION:
  "Config changes are rare so the write path doesn't matter."
  → During a large incident, multiple engineers change config simultaneously.
  → During automated rotation, hundreds of secrets rotate in batch.
  → The write path must handle 100× burst without degradation.
```

## Burst Behavior

```
BURST 1: Mass restart event
  All 500,000 instances restart simultaneously (Kubernetes upgrade,
  infrastructure event, cascading crash).
  
  Each instance on startup:
  → Fetches full config (500K × 1 config fetch = 500K requests in ~30 seconds)
  → Fetches secrets (500K × 3 secrets average = 1.5M requests in ~30 seconds)
  → Establishes streaming connection (500K new connections in ~30 seconds)
  
  Total burst: ~67,000 config requests/second + ~50,000 secret requests/second
  + ~17,000 new connections/second

BURST 2: Config propagation
  Config change affects 500,000 instances.
  Push within 5 seconds → 100,000 notifications/second

BURST 3: Incident response config changes
  During a major incident, 10 config changes in 2 minutes.
  Each triggers propagation to 500,000 instances.
  → 10 × 100,000 = 1,000,000 notifications/second (if overlapping)

BURST 4: Secret rotation batch
  200 secrets rotated in a scheduled window (monthly rotation job).
  Each secret consumed by ~100 instances → 20,000 secret fetches in ~5 minutes
  → ~67 secret fetches/second (manageable)
```

## What Breaks First at Scale

```
BREAK POINT 1: Connection count
  500,000 persistent connections is the primary scaling challenge.
  Each connection consumes memory on the config server.
  At ~10 KB per connection: 500K × 10 KB = 5 GB memory just for connections
  → Need connection aggregation or hierarchical propagation

BREAK POINT 2: Config propagation fan-out
  Pushing to 500,000 clients within 5 seconds is a fan-out problem.
  Single server can push ~10,000 notifications/second (TCP overhead).
  Need 50 seconds for one server → 10 servers minimum for 5-second SLA.

BREAK POINT 3: Flag evaluation complexity
  5,000 flags × 10 targeting rules each = 50,000 rules to sync.
  If rules change frequently, sync bandwidth grows.
  Each instance holds ~10 MB of flag rules in memory.
  500,000 instances × 10 MB = 5 TB total memory consumed by flag rules.

BREAK POINT 4: Secret decryption load
  During mass restart: 50,000 decrypt requests/second to KMS.
  KMS has rate limits (typically 10,000 requests/second per key).
  → Need secret caching at the sidecar layer to absorb bursts.

BREAK POINT 5: Audit log volume
  If every config read is logged (not just writes):
  55 billion reads/second × even 1-byte log = 55 GB/second
  → Never log reads on the hot path. Only log writes and secret accesses.
```

---

# Part 5: High-Level Architecture

## Core Components

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                   CONFIG SYSTEM: ARCHITECTURE OVERVIEW                       │
│                                                                             │
│   ┌─────────────┐     ┌──────────────────────────────┐                      │
│   │   Admin UI   │────▶│        Config API Server      │                      │
│   │  (Web/CLI)   │     │  (Write path, validation,     │                      │
│   └─────────────┘     │   versioning, permissions)     │                      │
│                        └──────────┬───────────────────┘                      │
│                                   │                                          │
│                          ┌────────▼────────┐                                 │
│                          │   Config Store   │                                 │
│                          │  (Versioned K/V  │                                 │
│                          │   + Flag Rules   │                                 │
│                          │   + Encrypted    │                                 │
│                          │     Secrets)     │                                 │
│                          └────────┬────────┘                                 │
│                                   │                                          │
│                          ┌────────▼────────┐                                 │
│                          │  Change Stream   │                                 │
│                          │   (Pub/Sub or    │                                 │
│                          │   Change Log)    │                                 │
│                          └────────┬────────┘                                 │
│                                   │                                          │
│                     ┌─────────────┼─────────────┐                            │
│                     ▼             ▼             ▼                             │
│              ┌────────────┐┌────────────┐┌────────────┐                      │
│              │  Propagation││  Propagation││  Propagation│                      │
│              │  Server 1   ││  Server 2   ││  Server N   │                      │
│              └──────┬─────┘└──────┬─────┘└──────┬─────┘                      │
│                     │             │             │                             │
│            ┌────────┼─────────────┼─────────────┼────────┐                   │
│            ▼        ▼             ▼             ▼        ▼                    │
│      ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐                    │
│      │ Sidecar  │ │ Sidecar  │ │ Sidecar  │ │ Sidecar  │                    │
│      │ /SDK     │ │ /SDK     │ │ /SDK     │ │ /SDK     │                    │
│      │ Instance1│ │ Instance2│ │ Instance3│ │ InstanceN│                    │
│      └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘                    │
│           │             │             │             │                         │
│      ┌────▼─────┐ ┌────▼─────┐ ┌────▼─────┐ ┌────▼─────┐                    │
│      │ Service  │ │ Service  │ │ Service  │ │ Service  │                    │
│      │ Instance │ │ Instance │ │ Instance │ │ Instance │                    │
│      └──────────┘ └──────────┘ └──────────┘ └──────────┘                    │
│                                                                             │
│   SEPARATE SECURITY BOUNDARY:                                               │
│   ┌─────────────┐      ┌──────────────────┐                                 │
│   │   KMS /HSM   │◄────│  Secrets Engine   │                                 │
│   │  (Key Mgmt)  │     │ (Encrypt/Decrypt, │                                 │
│   └─────────────┘      │  Rotation Logic)  │                                 │
│                         └──────────────────┘                                 │
│                                                                             │
│   WRITE-OPTIMIZED:                                                          │
│   ┌──────────────────┐                                                      │
│   │    Audit Log      │  (Append-only, all changes + secret accesses)       │
│   │    Store          │                                                      │
│   └──────────────────┘                                                      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Component Responsibilities

```
CONFIG API SERVER:
  - Handles all write operations (create, update, delete config/flags/secrets)
  - Validates schema, permissions, and business rules
  - Manages versioning (monotonic version per namespace)
  - Coordinates secret encryption/decryption with Secrets Engine
  - Writes to Config Store and emits change events
  - Serves admin UI API (list namespaces, view history, etc.)

CONFIG STORE:
  - Persistent, versioned storage for all config/flag/secret data
  - Supports key-value operations with version tracking
  - Maintains full version history (append-only)
  - Provides change stream (ordered log of all mutations)
  - Must be strongly consistent for writes, replicated for durability

CHANGE STREAM:
  - Ordered log of all config mutations
  - Propagation servers subscribe to this stream
  - Provides at-least-once delivery guarantee
  - Supports replay from any position (for new propagation servers)

PROPAGATION SERVER:
  - Receives change events from the change stream
  - Maintains persistent connections to client sidecars/SDKs
  - Fans out config updates to connected clients
  - Handles connection management (heartbeat, reconnection)
  - Stateless except for connection state (can be horizontally scaled)

SIDECAR / SDK:
  - Runs as sidecar container or in-process library
  - Maintains local cache of all config values and flag rules
  - Evaluates feature flags locally (no network call)
  - Fetches and caches secrets (with lease management)
  - Persists cache to local disk (fast restart)
  - Falls back to compiled-in defaults if all else fails

SECRETS ENGINE:
  - Encrypts secrets using envelope encryption before storage
  - Decrypts secrets for authorized consumers
  - Manages encryption keys via KMS/HSM
  - Implements rotation workflows
  - Generates dynamic secrets (per-instance credentials)

AUDIT LOG STORE:
  - Append-only storage for all mutation events and secret accesses
  - Indexed by time, actor, namespace, and key
  - Retained for compliance period (years)
  - Separate failure domain from config store
```

## Stateless vs Stateful Decisions

```
STATELESS:
  Config API Server — Any server can handle any request
  Propagation Server — Client can reconnect to any propagation server
    (Config version tracked by client, not server)
  Secrets Engine — Stateless encryption/decryption service
  
STATEFUL:
  Config Store — The source of truth (replicated database)
  Sidecar/SDK cache — Local state (reconstructible from server)
  Audit Log Store — Append-only durable log
  KMS/HSM — Key material (hardware-bound)
  
SEMI-STATEFUL:
  Propagation Server — Holds connection state (which clients are connected)
    But no critical state: If it restarts, clients reconnect and re-sync
  
Staff decision: Maximize statelessness in the write and propagation path.
The ONLY irreplaceable state is in the Config Store and KMS.
Everything else can be rebuilt or re-fetched.
```

## Data Flow: Write Path

```
WRITE FLOW (Config Update):

1. Engineer opens Admin UI → Selects namespace → Edits config key
2. UI sends: PUT /api/v1/config/payment-service/production/timeout_ms
   Body: { value: 1000, previous_version: 41, reason: "latency mitigation" }
3. Config API Server:
   a. Authenticate actor (OAuth/SSO token)
   b. Authorize: Does actor have write permission for this namespace?
   c. Validate: Is 1000 a valid integer within schema range [100, 30000]?
   d. Version check: Is the current version 41? (optimistic concurrency)
   e. If approval required: Queue for approval workflow
   f. Write to Config Store: version 42, value 1000
   g. Emit change event to Change Stream
   h. Write to Audit Log: who, what, when, why
   i. Return success to UI (with new version number)
4. Propagation:
   a. Change Stream receives event: {namespace, key, version: 42}
   b. Propagation Servers subscribed to the stream receive the event
   c. Each Propagation Server pushes update to connected sidecars
   d. Sidecars update local cache, persist to disk
5. Monitoring:
   - Track propagation completeness (how many servers updated)
   - Alert if propagation takes > 5 seconds
```

## Data Flow: Read Path

```
READ FLOW (Config Value Access):

1. Application code: config.get("timeout_ms")
2. SDK intercepts:
   a. Lookup in in-process HashMap → Found? Return immediately (< 1µs)
   b. Not found? Check default values → Return default
   c. Never goes to network on this path
   
READ FLOW (Feature Flag Evaluation):

1. Application code: flags.evaluate("new_checkout", context)
2. SDK intercepts:
   a. Load flag rules from in-process cache
   b. Evaluate targeting rules against context:
      - Check user_id against allow-list → No match
      - Check country against geo-target → No match
      - Compute hash(user_id + flag_name) % 100 → 7 (< 10% threshold)
      - Result: true (user is in 10% rollout)
   c. Return result (< 100µs, no network)

READ FLOW (Secret Access):

1. Application code: secrets.get("db_password")
2. Sidecar intercepts:
   a. Check local cache → Secret found with valid lease? Return decrypted value
   b. Lease expired or not cached?
      → Call Secrets API with service identity
      → Secrets Engine verifies identity + permission
      → Decrypts secret using KMS
      → Returns plaintext + new lease (TTL: 1 hour)
   c. Sidecar caches in memory-locked buffer
   d. Returns to application

BACKGROUND SYNC:

1. Sidecar maintains persistent connection to Propagation Server
2. Propagation Server pushes: "namespace X updated to version 42"
3. Sidecar fetches delta: "What changed between version 41 and 42?"
4. Sidecar applies changes to local cache
5. Application's next config.get() returns new value automatically
```

---

# Part 6: Deep Component Design

## Component 1: Config API Server

### Internal Design

```
struct ConfigAPIServer:
  auth_provider: AuthProvider           // OAuth/SSO verification
  authz_engine: AuthorizationEngine     // RBAC/ABAC policy evaluation
  schema_registry: SchemaRegistry       // Config key schemas
  store_client: ConfigStoreClient       // Connection to Config Store
  audit_client: AuditLogClient          // Connection to Audit Log
  secrets_engine: SecretsEngineClient   // For secret operations
  rate_limiter: RateLimiter             // Per-actor rate limiting

FUNCTION handle_config_update(request):
  // Step 1: Authentication
  actor = auth_provider.verify(request.token)
  IF actor == NULL: RETURN 401 Unauthorized
  
  // Step 2: Authorization
  permission = authz_engine.check(actor, request.namespace, "write")
  IF NOT permission.allowed: RETURN 403 Forbidden
  
  // Step 3: Rate limiting
  IF NOT rate_limiter.allow(actor, "config_write"):
    RETURN 429 Too Many Requests
  
  // Step 4: Schema validation
  schema = schema_registry.get(request.namespace, request.key)
  IF schema != NULL:
    validation = schema.validate(request.value)
    IF NOT validation.ok: RETURN 400 Bad Request (validation.errors)
  
  // Step 5: Optimistic concurrency
  current = store_client.get(request.namespace, request.key)
  IF current.version != request.previous_version:
    RETURN 409 Conflict ("Version mismatch: expected {request.previous_version}, got {current.version}")
  
  // Step 6: Write
  new_version = store_client.put(
    namespace = request.namespace,
    key = request.key,
    value = request.value,
    version = current.version + 1,
    metadata = {actor: actor.id, reason: request.reason, timestamp: now()}
  )
  
  // Step 7: Audit
  audit_client.log({
    action: "CONFIG_UPDATE",
    actor: actor.id,
    namespace: request.namespace,
    key: request.key,
    old_value: current.value,
    new_value: request.value,
    old_version: current.version,
    new_version: new_version,
    reason: request.reason
  })
  
  RETURN 200 OK {version: new_version}
```

### Schema Validation System

```
SCHEMA DEFINITION:
  key: "timeout_ms"
  type: integer
  constraints:
    min: 100
    max: 30000
    step: 50  (must be multiple of 50)
  danger_zone:
    min: 100    (values 100-200 flagged as "dangerously low")
    max: 10000  (values > 10000 flagged as "unusually high")
  requires_approval: true (if value in danger_zone)

FUNCTION validate(schema, value):
  // Type check
  IF typeof(value) != schema.type: RETURN error("Type mismatch")
  
  // Range check
  IF value < schema.min OR value > schema.max:
    RETURN error("Out of range [{schema.min}, {schema.max}]")
  
  // Step check
  IF schema.step AND value % schema.step != 0:
    RETURN error("Must be multiple of {schema.step}")
  
  // Danger zone check (warning, not rejection)
  IF schema.danger_zone:
    IF value < schema.danger_zone.min OR value > schema.danger_zone.max:
      RETURN warning("Value in danger zone, requires approval")
  
  RETURN ok()

WHY THIS MATTERS:
  Without schema validation, a typo (500 → 50000) propagates to all servers.
  Schema validation catches this at write time, not at crash time.
  
  Staff example: A major outage was caused by setting a timeout to 0ms
  (instead of removing the override). Schema validation with min=100
  would have prevented it.
```

### Failure Behavior

```
CONFIG API SERVER CRASH:
  Impact: Config writes temporarily unavailable
  Impact on reads: NONE (reads are from local cache)
  Recovery: Load balancer routes to healthy instances
  Data safety: Config Store has the durable state
  
  Staff insight: API server failures are tolerable because config writes
  are infrequent. The system degrades from "can make changes" to
  "running on last-known-good config." This is acceptable.

CONFIG API SERVER OVERLOADED:
  Impact: Write latency increases, some writes time out
  Mitigation: Rate limiting per actor, request queuing
  Backpressure: Return 503 with retry-after header
  
  During incident response, multiple engineers making config changes
  simultaneously can overwhelm the API. Rate limiting per actor prevents
  one person from monopolizing the API.
```

## Component 2: Config Store

### Internal Design

```
STORAGE MODEL:
  Primary key: (namespace, key, version)
  
  Table: config_values
    namespace   TEXT     — e.g., "payment-service/production"
    key         TEXT     — e.g., "timeout_ms"
    version     BIGINT   — Monotonically increasing per (namespace, key)
    value       BLOB     — Serialized value (JSON, protobuf, or raw)
    value_type  TEXT     — "integer", "string", "boolean", "json", "string_list"
    metadata    JSON     — {actor, reason, timestamp, approval}
    created_at  TIMESTAMP
    
  Index: (namespace, key) → latest version (covering index)
  Index: (namespace, version) → all keys changed in this version

  Table: config_namespaces
    namespace   TEXT PRIMARY KEY
    owner_team  TEXT
    schema_id   TEXT     — Reference to schema definitions
    frozen      BOOLEAN  — If true, reject all writes
    created_at  TIMESTAMP

  Table: secret_values  (SEPARATE, encrypted)
    path        TEXT     — e.g., "/secrets/payment-service/production/db_password"
    version     BIGINT
    encrypted_value BLOB — Encrypted with envelope encryption
    key_id      TEXT     — Which KMS key was used for encryption
    metadata    JSON
    rotation_policy JSON
    created_at  TIMESTAMP

  Change Log (append-only):
    sequence_id BIGINT AUTO_INCREMENT
    namespace   TEXT
    key         TEXT
    version     BIGINT
    change_type TEXT     — "CREATE", "UPDATE", "DELETE"
    timestamp   TIMESTAMP
    
  This change log is the source of truth for propagation.
  Propagation servers read from here to push updates.

TECHNOLOGY CHOICE:
  Option A: etcd / ZooKeeper
    + Built for config (watch support, strong consistency)
    - Scalability ceiling (~100K keys, ~1GB data)
    - Not suitable for 500K config keys + 50K secrets
    
  Option B: PostgreSQL / MySQL with change stream
    + Mature, understood, no scalability ceiling for this workload
    + Supports complex queries for admin UI
    - Must build change stream (CDC or trigger-based)
    
  Option C: Custom append-only log + key-value store
    + Optimal for this specific workload
    - Operational burden of maintaining custom storage
    
  Staff decision: PostgreSQL with logical replication for the change stream.
  The write QPS is tiny (~30/second peak). PostgreSQL handles this trivially.
  Logical replication provides a built-in change stream.
  For very large scale (>1M keys), consider sharding by namespace prefix.
```

### Versioning

```
VERSIONING STRATEGY:
  Each (namespace, key) pair has an independent version number.
  Each namespace has a global version (max of all key versions).
  
  Key version: Incremented on every change to that specific key.
  Namespace version: The maximum key version across all keys in the namespace.
  
  Client tracks: "I have namespace X at version 42."
  On sync: "Give me all changes to namespace X since version 42."
  Response: List of (key, value, version) tuples where version > 42.

WHY NOT A SINGLE GLOBAL VERSION?
  Global version means every config change anywhere increments the version.
  10,000 namespaces × 50 changes/day = 500,000 version increments/day.
  Clients would see constant "updates" even for unrelated namespaces.
  
  Per-namespace versioning: Client only fetches changes for its own namespaces.
  A payment-service doesn't care about search-service config changes.
```

### Failure Behavior

```
CONFIG STORE UNAVAILABLE:
  Write impact: ALL config writes fail → Changes queue in API server (limited buffer)
  Read impact on services: NONE (local cache continues serving)
  Read impact on propagation: Propagation stalls (no new changes to push)
  
  This is acceptable: Services continue with last-known-good config.
  Config writes queue for up to 5 minutes, then fail.
  
  Recovery: When store returns, queued writes applied in order.
  Propagation catches up automatically (reads from change log).

CONFIG STORE DATA CORRUPTION:
  Detection: Checksums on every value, verified on read.
  Mitigation: Read from replica if primary corrupted.
  Last resort: Restore from backup (24-hour RPO).
  
  Staff insight: Config store corruption is catastrophic but extremely rare.
  Replicated storage (3+ replicas) makes this a multi-failure scenario.
```

## Component 3: Propagation Server

### Internal Design

```
struct PropagationServer:
  change_stream: ChangeStreamConsumer
  connections: HashMap<ClientID, Connection>
  namespace_subscriptions: HashMap<Namespace, Set<ClientID>>
  
  // Each propagation server handles ~50,000 client connections
  // 10 propagation servers handle 500,000 total connections

FUNCTION run():
  // Thread 1: Consume change stream
  FOR event IN change_stream.subscribe():
    subscribers = namespace_subscriptions.get(event.namespace)
    FOR client_id IN subscribers:
      connection = connections.get(client_id)
      IF connection.is_alive():
        connection.send(event)  // Non-blocking, buffered
      ELSE:
        mark_for_cleanup(client_id)
  
  // Thread 2: Handle new client connections
  FOR new_conn IN accept_connections():
    client_id = new_conn.authenticate()
    namespaces = new_conn.subscribe_namespaces()
    connections[client_id] = new_conn
    FOR ns IN namespaces:
      namespace_subscriptions[ns].add(client_id)
    
    // Send current state to new client
    FOR ns IN namespaces:
      current = config_store.get_latest(ns)
      new_conn.send(current)
  
  // Thread 3: Heartbeat and cleanup
  EVERY 30 seconds:
    FOR client_id, conn IN connections:
      IF conn.last_seen > 60 seconds ago:
        conn.close()
        remove_client(client_id)
      ELSE:
        conn.send_heartbeat()
```

### Propagation Protocols

```
OPTION A: Long-polling (HTTP)
  Client: GET /config/subscribe?namespace=payment-service&version=42
  Server: Holds connection open until change occurs or timeout (30s)
  On change: Returns delta and client immediately re-polls
  
  Pros: Works through all proxies and firewalls
  Cons: 30-second worst-case latency, high connection churn

OPTION B: Server-Sent Events (SSE)
  Client: GET /config/stream?namespace=payment-service
  Server: Sends events as they occur over persistent HTTP connection
  
  Pros: Low latency, standard HTTP, simple
  Cons: Unidirectional (server → client only)

OPTION C: gRPC Streaming (bi-directional)
  Client: Opens gRPC stream, sends subscription request
  Server: Pushes config changes on the stream
  Client: Sends acknowledgment for each change
  
  Pros: Low latency, bi-directional, compact binary format
  Cons: gRPC infrastructure required, HTTP/2 proxy support

Staff decision: gRPC streaming for internal services (low latency, 
efficient). SSE as fallback for environments where gRPC isn't available.
Long-polling as last resort for edge cases.
```

### Connection Scaling

```
PROBLEM: 500,000 persistent connections

SOLUTION: Hierarchical propagation (for very large scale)

  Without hierarchy (direct):
    Config Server → 500,000 sidecars
    Single server can handle ~50,000 connections
    Need 10 propagation servers
  
  With hierarchy (two-tier):
    Config Server → 100 aggregator nodes
    Each aggregator → 5,000 sidecars
    Total connections per layer: 100 + 500,000 = 500,100
    But each node handles ≤ 5,000 connections (much simpler)
  
  Trade-off: Hierarchy adds ~1 second propagation latency (extra hop)
  But reduces operational complexity significantly.

  At 500K instances, direct fan-out with 10 servers is manageable.
  At 5M instances, hierarchical propagation becomes necessary.
  
  Staff decision: Start with direct fan-out (10 propagation servers).
  Design the sidecar to support connecting to aggregator nodes.
  Switch when instance count exceeds 1M.
```

### Failure Behavior

```
PROPAGATION SERVER CRASH:
  Impact: ~50,000 clients lose their connection
  Recovery: Clients detect disconnect within 30 seconds (heartbeat timeout)
  → Clients reconnect to any available propagation server
  → Client sends its current config version
  → Propagation server sends delta since that version
  → Total recovery time: < 60 seconds
  → During recovery: Clients use stale (but safe) cached config
  
  No data loss: Config Store is the source of truth.
  Propagation servers are stateless (connection state is reconstructed).

ALL PROPAGATION SERVERS DOWN:
  Impact: No config changes propagated to any client
  Impact on services: NONE (local cache continues serving)
  Duration tolerance: Hours (config changes are infrequent)
  Recovery: When propagation servers restart, clients reconnect and catch up
  
  Staff insight: Propagation server downtime means "config frozen at current state."
  This is always preferable to "config unavailable" which would be catastrophic.
```

## Component 4: Sidecar / SDK

### Internal Design

```
struct ConfigSidecar:
  config_cache: HashMap<(Namespace, Key), ConfigValue>
  flag_rules: HashMap<FlagName, FlagDefinition>
  secret_cache: HashMap<SecretPath, CachedSecret>
  disk_cache: DiskCache      // Persistent cache for fast restart
  
  // Connection state
  propagation_conn: GrpcStream
  current_versions: HashMap<Namespace, Version>
  
  // Fallback chain
  compiled_defaults: HashMap<Key, Value>
  
struct CachedSecret:
  value: SecureBuffer  // Memory-locked, non-swappable
  lease_expiry: Timestamp
  
struct ConfigValue:
  value: Any
  version: Version
  last_updated: Timestamp

FUNCTION get_config(namespace, key):
  // Lookup chain (fastest to slowest):
  
  // 1. In-process cache (< 1µs)
  cached = config_cache.get((namespace, key))
  IF cached != NULL: RETURN cached.value
  
  // 2. Compiled-in default
  default = compiled_defaults.get(key)
  IF default != NULL:
    LOG.warn("Using compiled default for {namespace}/{key}")
    RETURN default
  
  // 3. No value available
  LOG.error("No config value for {namespace}/{key}, no default")
  RETURN NULL  // Caller must handle this

FUNCTION evaluate_flag(flag_name, context):
  flag = flag_rules.get(flag_name)
  IF flag == NULL:
    // Unknown flag → conservative default
    RETURN flag_defaults.get(flag_name, false)
  
  FOR rule IN flag.targeting_rules:
    IF rule.matches(context):
      RETURN rule.value
  
  RETURN flag.default_value

FUNCTION get_secret(path):
  cached = secret_cache.get(path)
  IF cached != NULL AND cached.lease_expiry > now() + 5_MINUTES:
    RETURN cached.value  // Valid lease, return cached
  
  // Lease expired or about to expire → re-fetch
  TRY:
    result = secrets_api.fetch(path, service_identity)
    secret_cache.put(path, CachedSecret{
      value: SecureBuffer.wrap(result.value),
      lease_expiry: now() + result.lease_ttl
    })
    RETURN result.value
  CATCH network_error:
    IF cached != NULL AND cached.lease_expiry > now():
      // Lease still valid, use cached value
      LOG.warn("Secrets API unreachable, using cached secret")
      RETURN cached.value
    ELSE:
      LOG.error("Secret unavailable and lease expired")
      RAISE SecretUnavailableError
```

### Local Cache Management

```
CACHE LIFECYCLE:

1. STARTUP (cold start):
   a. Read disk cache (persisted from last run)
   b. Establish connection to propagation server
   c. Send current versions for each namespace
   d. Receive delta updates (changes since last known version)
   e. Apply deltas to in-memory cache
   f. Service is now ready to serve (with up-to-date config)
   
   Fast restart: Disk cache + delta = milliseconds to ready
   Cold start (no disk cache): Full config fetch = < 1 second

2. STEADY STATE:
   a. Receive streaming updates from propagation server
   b. Apply updates to in-memory cache
   c. Periodically persist cache to disk (every 60 seconds or on change)
   
3. DISCONNECTED:
   a. Connection to propagation server lost
   b. Continue serving from in-memory cache (stale but safe)
   c. Attempt reconnection with exponential backoff (1s, 2s, 4s, ... 60s max)
   d. On reconnect: Send current versions, receive delta, apply
   
4. FALLBACK CASCADE:
   In-memory cache → Disk cache → Compiled defaults → Hard-coded failsafe
   
   NEVER: Return "config unavailable" to the application.
   ALWAYS: Return SOME value, even if it's a conservative default.

WHY IN-PROCESS (not sidecar process):
  Sidecar process requires IPC (Unix socket or localhost HTTP) → ~100µs
  In-process SDK is a memory lookup → < 1µs
  
  100µs × 110 lookups per request = 11ms added latency per request
  1µs × 110 lookups = 0.11ms
  
  For config reads: In-process SDK is 100× better.
  For secret management: Sidecar is acceptable (infrequent access).
  
  Staff decision: SDK for config and flags (in-process).
  Sidecar for secrets (separate process for security isolation).
```

### Why Simpler Alternatives Fail

```
ALTERNATIVE 1: Fetch config from server on every read
  100,000 QPS × 110 config reads = 11,000,000 requests/second to config server
  → Config server dies under load
  → Every request adds 5-20ms network latency
  → If config server is slow, ALL services are slow
  REJECTED: Config reads MUST be local

ALTERNATIVE 2: Bake config into container image
  → Config changes require new image build + deploy
  → 45-minute cycle for a one-line change
  → No dynamic control during incidents
  REJECTED: Defeats the entire purpose of dynamic config

ALTERNATIVE 3: Poll config server every N seconds
  500,000 instances × 1 poll/30 seconds = 16,667 requests/second
  → Manageable QPS, but 30-second propagation latency
  → Not acceptable for kill switches (need < 5 seconds)
  → High overhead: Most polls return "no change"
  REJECTED: Streaming is strictly superior to polling

ALTERNATIVE 4: Use a distributed cache (Redis) for config
  → Adds Redis as a dependency on the hot path
  → Redis down → Config unavailable → Outage
  → ~1ms per lookup (vs ~1µs for in-process)
  REJECTED: External cache on the hot path is wrong
```

## Component 5: Secrets Engine

### Internal Design

```
struct SecretsEngine:
  kms_client: KMSClient
  key_cache: HashMap<KeyID, CachedKey>  // Data encryption keys
  access_policies: PolicyStore
  audit_logger: AuditLogger

ENVELOPE ENCRYPTION:
  Master Key (in KMS/HSM): Never leaves hardware
  Data Encryption Key (DEK): Generated per-secret, encrypted by master key
  
  Storage:
    {
      path: "/secrets/payment-service/production/db_password",
      encrypted_dek: <DEK encrypted by master key>,
      encrypted_value: <secret value encrypted by DEK>,
      key_id: "master-key-2024-v3"
    }
  
  To read a secret:
    1. Fetch encrypted_dek and encrypted_value from store
    2. Send encrypted_dek to KMS → Get plaintext DEK
    3. Use DEK to decrypt encrypted_value → Plaintext secret
    4. Return plaintext to authorized caller
    5. Zero the DEK from memory
    
  WHY ENVELOPE ENCRYPTION:
    If you encrypted every secret directly with KMS:
    → 500,000 decrypt calls/hour to KMS (expensive, slow, rate-limited)
    
    With envelope encryption:
    → DEK cached in memory (10,000 DEKs × 256 bits = 320 KB)
    → KMS called only on cache miss or DEK rotation
    → 99%+ of decrypt operations are local (< 1µs)
    → KMS sees ~100 calls/hour instead of 500,000

FUNCTION decrypt_secret(path, service_identity):
  // Step 1: Verify access
  IF NOT access_policies.allows(service_identity, path, "read"):
    audit_logger.log_denied(service_identity, path)
    RETURN 403 Forbidden
  
  // Step 2: Fetch encrypted secret
  encrypted = config_store.get_secret(path)
  
  // Step 3: Get DEK (cached or from KMS)
  dek = key_cache.get(encrypted.key_id)
  IF dek == NULL:
    dek = kms_client.decrypt(encrypted.encrypted_dek)
    key_cache.put(encrypted.key_id, dek, ttl=1_HOUR)
  
  // Step 4: Decrypt
  plaintext = aes_decrypt(encrypted.encrypted_value, dek)
  
  // Step 5: Audit
  audit_logger.log_access(service_identity, path, encrypted.version)
  
  // Step 6: Return with lease
  RETURN {value: plaintext, lease_ttl: 1_HOUR, version: encrypted.version}
```

### Secret Rotation Workflow

```
ROTATION STATE MACHINE:

  ┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐
  │  IDLE    │────▶│ GENERATE │────▶│DUAL-LIVE │────▶│ REVOKE   │
  │          │     │          │     │          │     │ OLD      │
  └──────────┘     └──────────┘     └──────────┘     └──────────┘
       │                                                    │
       └────────────────────────────────────────────────────┘

PHASE 1 — GENERATE:
  Generate new secret value (random password, new key pair, etc.)
  Store as version N+1 (old = version N)
  Both versions are valid

PHASE 2 — DUAL-LIVE:
  Configure the dependency (e.g., database) to accept BOTH secrets
  For database passwords: Create new credentials (version N+1)
  Old credentials (version N) still work
  
  Notify consuming services: "New secret version available"
  Wait for all services to fetch version N+1
  
  Verification: Check that all services are using version N+1
  (Metric: secret_version_in_use{path="...", version="N+1"})
  
  Duration: 1-24 hours depending on service restart cadence

PHASE 3 — REVOKE OLD:
  Confirm all services are using version N+1
  Revoke version N (delete old DB credentials, invalidate old key)
  Log completion in audit trail

FAILURE DURING ROTATION:
  If phase 2 fails: Version N is still valid, no impact
  If phase 3 fails: Both versions still work, retry later
  → Rotation is ALWAYS safe to abort. Worst case: Old secret lives longer.
```

## Component 6: Feature Flag Evaluation Engine

### Internal Design

```
struct FlagEvaluationEngine:
  flags: HashMap<FlagName, FlagDefinition>
  
struct FlagDefinition:
  name: string
  type: FlagType  // BOOLEAN, STRING, INTEGER, JSON
  default_value: Any
  targeting_rules: List<TargetingRule>
  kill_switch: boolean  // If true, default_value always returned
  enabled: boolean      // If false, default_value always returned
  
struct TargetingRule:
  conditions: List<Condition>  // ALL must match (AND)
  value: Any                   // Value to return if all conditions match
  rollout_percentage: Optional<float>  // 0-100, for gradual rollout
  
struct Condition:
  attribute: string   // e.g., "user.country"
  operator: string    // "equals", "in", "startsWith", "regex", "semver_gte"
  values: List<Any>   // e.g., ["US", "CA"]

FUNCTION evaluate(flag_name, context):
  flag = flags.get(flag_name)
  IF flag == NULL: RETURN default_for_unknown_flags  // false for boolean
  
  // Kill switch overrides everything
  IF flag.kill_switch: RETURN flag.default_value
  IF NOT flag.enabled: RETURN flag.default_value
  
  FOR rule IN flag.targeting_rules:
    IF matches_all_conditions(rule.conditions, context):
      IF rule.rollout_percentage != NULL:
        // Consistent hashing for percentage rollout
        bucket = hash(context.user_id + flag_name) % 10000
        IF bucket < rule.rollout_percentage * 100:
          RETURN rule.value
        // Else: Fall through to next rule
      ELSE:
        RETURN rule.value
  
  RETURN flag.default_value

FUNCTION matches_all_conditions(conditions, context):
  FOR condition IN conditions:
    attribute_value = context.get(condition.attribute)
    IF attribute_value == NULL: RETURN false  // Missing attribute → no match
    
    MATCH condition.operator:
      "equals":     IF attribute_value != condition.values[0]: RETURN false
      "in":         IF attribute_value NOT IN condition.values: RETURN false
      "startsWith": IF NOT attribute_value.starts_with(condition.values[0]): RETURN false
      "regex":      IF NOT regex_match(condition.values[0], attribute_value): RETURN false
      "gte":        IF attribute_value < condition.values[0]: RETURN false
  
  RETURN true
```

### Consistent Hashing for Flag Assignment

```
WHY CONSISTENT HASHING:
  A user must ALWAYS see the same flag value for a given flag.
  Otherwise:
  → Request 1: User sees new checkout (flag=true)
  → Request 2: User sees old checkout (flag=false)
  → Confusing, breaks user state, corrupts A/B test data

FUNCTION compute_bucket(user_id, flag_name):
  // Combine user_id + flag_name to get independent buckets per flag
  input = user_id + ":" + flag_name
  hash_value = murmur3_hash(input)  // Fast, well-distributed
  bucket = hash_value % 10000       // 0.01% granularity
  RETURN bucket

PROPERTIES:
  1. Deterministic: Same input always gives same bucket
  2. Independent per flag: User in 10% for flag A doesn't imply 10% for flag B
  3. Uniform distribution: Buckets are evenly distributed
  4. Stable under rollout changes: Increasing rollout from 10% to 20%
     keeps the original 10% in the treatment (they don't get moved out)
     
CRITICAL: The hash salt includes the FLAG NAME.
  Without salt: 10% rollout of flag A and 10% rollout of flag B
  → Same 10% of users in both → Not independent
  With flag-name salt: Different 10% for each flag → Independent tests
```

---

# Part 7: Data Model & Storage Decisions

## What Data Is Stored

```
DATA CATEGORY 1: Configuration values
  ~500,000 key-value pairs across 10,000 namespaces
  Average value size: 200 bytes
  Total active config data: ~100 MB
  With version history (30 versions per key average): ~3 GB
  
DATA CATEGORY 2: Feature flag definitions
  ~5,000 flags with targeting rules
  Average flag definition: 2 KB (includes all rules)
  Total flag data: ~10 MB
  
DATA CATEGORY 3: Encrypted secrets
  ~50,000 secrets with 3 versions each
  Average encrypted secret: 1 KB
  Total secret data: ~150 MB (encrypted)
  
DATA CATEGORY 4: Audit log entries
  ~10 entries/second × 86,400 seconds/day = ~864,000 entries/day
  Average entry: 500 bytes
  Daily audit volume: ~430 MB
  Annual: ~157 GB
  7-year retention: ~1.1 TB

DATA CATEGORY 5: Change log (for propagation)
  Mirrors config writes: ~2,500 entries/day
  Average entry: 300 bytes
  Retained for 7 days (after propagation): ~5 MB
  
TOTAL STORAGE:
  Config + Flags + Secrets: ~3.3 GB (trivially small)
  Audit Log: ~1.1 TB over 7 years (modest, append-only)
  
  Staff insight: The data size is TINY. The challenge is not storage—
  it's propagation speed, connection count, and availability.
```

## How Data Is Keyed

```
CONFIGURATION:
  Primary key: (namespace, key)
  Namespace: hierarchical string → "org/team/service/environment"
  Key: flat string → "timeout_ms"
  
  Full path: "payments/checkout/payment-service/production/timeout_ms"
  
  Namespace inheritance:
    /payments/checkout/payment-service/default/timeout_ms = 500
    /payments/checkout/payment-service/production/timeout_ms = 1000
    
    Production overrides default. If production key doesn't exist,
    fall back to default namespace.

FEATURE FLAGS:
  Primary key: (flag_name)
  Global scope: Flags are not per-service (they're per-product)
  Targeting context is provided at evaluation time, not at definition time
  
  Flag key: "new_checkout_flow"
  Evaluation: evaluate("new_checkout_flow", {user_id: "abc", country: "US"})

SECRETS:
  Primary key: (path)
  Path: hierarchical → "/secrets/service/environment/secret_name"
  Versioned: Latest version is the default, can request specific version
  
  Example: "/secrets/payment-service/production/stripe_api_key"
```

## How Data Is Partitioned

```
PARTITIONING STRATEGY:
  Config store data is small (~3 GB). No partitioning needed for storage.
  But propagation must be partitioned to avoid broadcasting all changes.

PROPAGATION PARTITIONING BY NAMESPACE:
  Each sidecar subscribes to specific namespaces (its service's config).
  Propagation server tracks subscriptions.
  Config change in namespace X → Push only to subscribers of namespace X.
  
  Without partitioning: Every change pushed to all 500,000 instances.
  With partitioning: Change to "payment-service" pushed to ~500 instances.

AUDIT LOG PARTITIONING:
  Partitioned by time (daily partitions)
  Recent partitions: Fast SSD storage (< 30 days)
  Historical partitions: Cold storage (> 30 days)
  
  Why time-based: Most audit queries are "show me recent changes."
  Historical queries are rare (compliance audits).

SECRET STORAGE PARTITIONING:
  Partitioned by security classification:
  Tier 1: Standard secrets (DB passwords, API keys)
    → Standard encryption, standard access policies
  Tier 2: High-security secrets (signing keys, encryption master keys)
    → HSM-backed encryption, two-person access policy, enhanced audit
  Tier 3: Regulatory secrets (PCI DSS, HIPAA)
    → Separate physical storage, separate KMS, separate audit trail
```

## Retention Policies

```
CONFIGURATION VALUES:
  Active version: Retained indefinitely (as long as key exists)
  Historical versions: Retained for 90 days (for rollback and audit)
  After 90 days: Only metadata retained (who changed what when)
  Deleted keys: Tombstone retained for 30 days, then hard-deleted
  
FEATURE FLAGS:
  Active flags: Retained indefinitely
  Completed flags (fully rolled out): Cleanup ticket generated after 30 days
  Archived flags: Metadata retained for 1 year, rules deleted
  
SECRETS:
  Active version: Retained until rotated
  Previous version: Retained for rotation overlap period (24-72 hours)
  Older versions: Encrypted value deleted, metadata retained for audit
  
AUDIT LOG:
  Standard: 7-year retention (SOC2, ISO 27001 compliance)
  PCI-related: 10-year retention
  Immutable: Cannot be modified or deleted during retention period
  
CHANGE LOG:
  Retained for 7 days (enough for any propagation delay + replay)
  After 7 days: Archived to cold storage
```

## Schema Evolution

```
CONFIGURATION SCHEMA CHANGES:
  
  Adding a new config key:
    → Add schema definition (type, constraints)
    → Set default value
    → Services that don't know about the key ignore it (safe)
  
  Changing value type (e.g., integer → string):
    → DANGEROUS: Existing services expect integer, new value is string
    → Must coordinate: New schema version + code deploy + config update
    → Safer approach: Add new key with new type, deprecate old key
  
  Narrowing constraints (e.g., max 10000 → max 5000):
    → Validate: Is the current production value within new constraints?
    → If not: Change value first, then change constraint
  
  Removing a config key:
    → Check: Any service still reading this key? (usage metrics)
    → Deprecation period: 30 days with warning logs
    → Then: Delete key

FLAG SCHEMA CHANGES:
  Adding new operators (e.g., "semver_gte"):
    → SDK must be updated to support new operator
    → Old SDKs that don't recognize the operator skip the rule → default value
    → This is safe: New features degrade to "off" for old SDKs
  
  Adding new flag types (e.g., JSON):
    → Old SDKs return the raw string
    → Application code handles parsing
```

## Why Other Data Models Were Rejected

```
RELATIONAL DATABASE (with complex schema):
  Problem: Config is key-value by nature, not relational
  Where it works: As the BACKING store (PostgreSQL), but accessed as K/V
  
DOCUMENT STORE (MongoDB):
  Problem: No built-in change stream ordering guarantee
  Problem: Eventual consistency makes version tracking unreliable
  Where it works: For audit log storage (document-oriented, append-only)

DISTRIBUTED KEY-VALUE (DynamoDB, Cassandra):
  Problem: Overkill for ~3 GB of data
  Problem: Eventual consistency complicates version ordering
  Where it works: If config data exceeds 100 GB (unlikely for config)

FILE-BASED CONFIG (YAML/JSON in Git):
  Problem: Changes require git push → CI/CD → deploy (slow)
  Problem: No fine-grained access control
  Problem: No real-time propagation
  Where it works: For STATIC config that changes with deploys
  
  Staff example: Infrastructure config (instance types, region mapping)
  lives in Git. Runtime config (timeouts, flags, secrets) lives in
  the config system. Know the difference.
```

---

# Part 8: Consistency, Concurrency & Ordering

## Strong vs Eventual Consistency

```
CONFIG WRITES: Strong consistency
  A successful write means the value is durably stored.
  The next read to the API returns the new value.
  Version numbers are strictly monotonic per (namespace, key).
  
  WHY: If an engineer changes timeout_ms and the API says "success,"
  they need confidence that the change is durable. "Maybe it saved,
  maybe it didn't" is unacceptable for config changes.

CONFIG READS (from local cache): Eventual consistency
  After a write, the new value propagates to all instances.
  P99 propagation: < 5 seconds.
  During the propagation window, some instances see the old value.
  
  WHY EVENTUAL IS ACCEPTABLE:
  Config changes are backward-compatible by convention.
  Both old and new values produce correct behavior.
  The 5-second window is negligible for most use cases.
  
  WHERE IT'S NOT ACCEPTABLE:
  Kill switches must propagate as fast as possible.
  → Kill switch propagation uses HIGHEST priority channel.
  → Propagation servers send kill switch changes before regular changes.
  → Target: < 2 seconds for kill switches.

FLAG EVALUATION: Eventual consistency (with consistency-within-request)
  All flag evaluations within a single request MUST see the same flag version.
  → SDK snapshots flag rules at the start of request processing.
  → All evaluations during the request use the snapshot.
  → Next request may see a different version (after propagation).
  
  This prevents: Request starts with flag=false, halfway through flag=true
  causing inconsistent behavior within a single request.
```

## Race Conditions

```
RACE CONDITION 1: Two writers update the same key simultaneously
  
  Writer A: SET timeout_ms = 1000 (from version 5)
  Writer B: SET timeout_ms = 2000 (from version 5)
  
  WITHOUT PROTECTION:
    Writer A writes version 6 = 1000
    Writer B writes version 7 = 2000
    → Writer A's change is silently overwritten
    → Writer A thinks timeout is 1000, but it's actually 2000
  
  WITH OPTIMISTIC CONCURRENCY:
    Writer A: SET timeout_ms = 1000 WHERE version = 5 → Success (version 6)
    Writer B: SET timeout_ms = 2000 WHERE version = 5 → CONFLICT (version is now 6)
    Writer B: Must re-read, see version 6, decide whether to proceed
    
  Implementation: Every write includes the expected previous version.
  If the current version doesn't match, the write is rejected with 409 Conflict.

RACE CONDITION 2: Config change + code deploy overlap
  
  T+0s: Code deploy begins (new code expects config key "feature_x_enabled")
  T+10s: New code rolling out to 50% of servers
  T+15s: Config change: SET feature_x_enabled = true
  T+17s: 50% of servers have new code + new config = Working
         50% of servers have old code + new config = Unknown behavior
  
  MITIGATION:
    Config keys should be backward-compatible.
    New code should handle missing config gracefully (use defaults).
    Sequence: Deploy code first → Verify → Then enable config.
    Never deploy code and config simultaneously.

RACE CONDITION 3: Secret rotation during active use
  
  T+0s: Rotation starts, new secret version N+1 generated
  T+1s: Service instance A fetches new secret (version N+1)
  T+2s: Service instance B still using old secret (version N)
  T+3s: Old secret revoked → Instance B's connections fail
  
  MITIGATION:
    NEVER revoke old secret before ALL consumers use new version.
    Rotation has explicit verification step: "Are all instances on N+1?"
    Only then revoke N.
```

## Idempotency

```
CONFIG WRITES:
  Idempotent by design: Writing the same value twice with the same version
  produces the same result (rejected as conflict on second write).
  
  For API retries: Client includes idempotency key.
  Server tracks recent idempotency keys (1-hour window).
  Duplicate request → Return cached response (no re-write).

SECRET ACCESS:
  Idempotent: Reading a secret multiple times returns the same value.
  Lease renewal: Fetching the same secret refreshes the lease.
  No side effects on read.

FLAG EVALUATION:
  Purely idempotent: Same context always produces same result
  (for the same flag version). No state mutation on evaluation.
  
AUDIT LOG:
  At-least-once: Same event may be logged twice (on retry).
  Audit log consumers must handle duplicates (dedup by event_id).
```

## Ordering Guarantees

```
WITHIN A NAMESPACE:
  Config versions are strictly ordered: V1 < V2 < V3 < ...
  Changes within a namespace are applied in version order.
  
  Client receives: "Update to version 42" before "Update to version 43"
  → If client has version 40, it applies 41, 42, 43 in order.
  → Deltas are composable: Applying 41+42+43 = same as snapshot at 43.

ACROSS NAMESPACES:
  No ordering guarantee between namespaces.
  Namespace A version 42 may propagate before or after Namespace B version 17.
  This is acceptable because namespaces are independent.
  
  Exception: If two services need coordinated config changes,
  use a SINGLE namespace for the coordinated values.
  (Or use a config "transaction" feature with cross-namespace versioning.)

CHANGE LOG ORDERING:
  Change log has a global sequence number (monotonic).
  Propagation servers process the log in order.
  This ensures that if key X is updated to V1, then V2,
  the propagation server pushes V1 before V2.
  
  If a client misses V1 but receives V2, it requests a full snapshot.
  → This is rare (< 0.01% of propagation events).
```

## Clock Assumptions

```
CONFIG SYSTEM CLOCKS:
  Config server: Uses server clock for timestamps in audit log.
  No cross-server clock coordination needed (single writer per namespace).
  
  Propagation: Uses version numbers, NOT timestamps, for ordering.
  → Clock skew doesn't affect config ordering.
  → Version numbers are assigned by the config store (single source).

SECRET LEASE EXPIRY:
  Lease TTL is relative (e.g., "1 hour from now"), not absolute.
  Client clock skew could cause early or late renewal.
  → Conservative: Renew at 50% of TTL (30 minutes into 1-hour lease).
  → Even with 10-minute clock skew, renewal happens before expiry.
  
AUDIT TIMESTAMPS:
  Recorded by the config server (authoritative clock).
  Not by the client (clients can have skewed clocks).
  Audit queries use server timestamps for consistency.

FLAG EVALUATION:
  No clock dependency. Flag rules are evaluated against context attributes,
  not against time (unless a rule explicitly uses a time-based condition).
  
  Time-based rules (e.g., "enable after 2024-09-15"):
  → Use config server's clock to set the flag, not client clock.
  → Or: Avoid time-based rules entirely (use gradual rollout instead).
```

---

# Part 9: Failure Modes & Degradation

## Failure Mode 1: Config Store Unavailable

```
SCENARIO: Primary config store database is unreachable.

IMPACT:
  Config writes: FAIL (cannot store new values)
  Config reads (services): UNAFFECTED (local cache)
  Config propagation: STALLS (no new changes to push)
  Secret access: DEGRADED (cached secrets work, new secrets unavailable)
  New service starts: DEGRADED (use disk cache or compiled defaults)

BLAST RADIUS:
  No user-visible impact (services continue with cached config)
  Engineering impact: Cannot make config changes during outage
  Duration tolerance: Hours (config changes are rare)
  
USER-VISIBLE SYMPTOMS:
  None (if no config changes were in-flight)
  If config change was needed (e.g., increase rate limit during traffic spike):
  → Cannot apply the change → Indirect impact from not being able to tune

DEGRADATION:
  1. API returns 503 for write operations
  2. Propagation servers continue serving cached state
  3. Sidecars continue serving from in-process cache
  4. Alert: "Config store unreachable"
  5. If persists > 30 minutes: Escalate to infrastructure team

RECOVERY:
  Config store comes back → Queued writes applied → Propagation resumes
  → All clients sync to latest → Normal operation
```

## Failure Mode 2: Propagation Server Fleet Failure

```
SCENARIO: All propagation servers crash simultaneously.

IMPACT:
  Config writes: WORK (stored in config store)
  Config propagation: STOPS (no mechanism to push changes)
  Config reads: UNAFFECTED (local cache)
  
BLAST RADIUS:
  Config changes are "stored but not propagated"
  Services continue with stale config (last propagated version)
  If no config changes pending: Zero impact
  If config changes were pending (e.g., kill switch): Changes don't reach services

TIMELINE:
  T+0:    Propagation servers crash
  T+30s:  Sidecars detect connection loss (heartbeat timeout)
  T+31s:  Sidecars begin reconnection attempts (exponential backoff)
  T+1min: Alert fires: "Propagation fleet down"
  T+5min: On-call begins investigation
  T+10min: Propagation servers restarted
  T+11min: Sidecars reconnect, receive all queued changes
  T+12min: All services updated to latest config
  
  During T+0 to T+11min: Config frozen at last propagated version.
  This is safe as long as no critical config changes were needed.

DEGRADATION:
  The system degrades to "static config" mode—everything works,
  but no new config changes take effect until propagation recovers.
```

## Failure Mode 3: Bad Config Push (Config Poisoning)

```
SCENARIO: Engineer sets timeout_ms = 0 (bypassing schema validation due to
emergency override), propagated to all servers.

WHY THIS IS THE MOST DANGEROUS FAILURE:
  All other failures → System runs on stale-but-safe config
  Config poisoning → System runs on ACTIVELY HARMFUL config
  
  With timeout=0, every request immediately times out.
  100% failure rate. Global outage.

TIMELINE:
  T+0:    Config change pushed: timeout_ms = 0
  T+3s:   Propagated to 60% of servers
  T+5s:   Propagated to 100% of servers
  T+5s:   ALL requests failing → Error rate goes from 0.01% to 100%
  T+6s:   Alert fires (error rate spike)
  T+7s:   On-call opens dashboard → Sees global failure
  T+8s:   On-call clicks "Rollback" on config UI
  T+10s:  Rollback propagated → timeout_ms = 500 (previous value)
  T+12s:  Error rate dropping
  T+15s:  Normal operation restored
  
  TOTAL IMPACT: ~10 seconds of global outage

PREVENTION LAYERS:
  Layer 1: Schema validation (reject timeout_ms = 0)
  Layer 2: Canary rollout (apply to 1% first, wait, observe)
  Layer 3: Automatic rollback (if error rate spikes after config change)
  Layer 4: Config change review (two-person approval for production)
  Layer 5: Blast radius limit (never apply to all servers simultaneously)

STAFF INSIGHT:
  If Layer 1 (schema validation) works, you never get to the other layers.
  But layers 2-5 exist because schemas are imperfect:
  → timeout_ms = 100 passes validation but may still cause problems
  → Valid value + bug in the application = outage from valid config
  → Defense in depth is non-negotiable for config systems
```

## Failure Mode 4: Secret Leak

```
SCENARIO: Secret value appears in application logs.

TIMELINE:
  T+0:    Developer adds logging: log.info("Connecting with password: {}", password)
  T+5min: Code passes review (reviewer misses the log line)
  T+30min: Deployed to production
  T+31min: Secret appears in centralized log aggregation
  T+2hr:  Log shipped to analytics platform (third-party)
  T+24hr: Security scan detects password pattern in logs
  T+24.5hr: Incident declared
  
MITIGATION (prevention):
  1. Secret values stored in SecureString type that overrides toString()
     → toString() returns "***REDACTED***" instead of the value
  2. Log scrubbing: Regex-based scrubber in log pipeline removes patterns
     matching passwords, API keys, tokens
  3. Static analysis: CI pipeline scans for logging of secret variables
  4. Runtime detection: Log aggregation system alerts on secret-like patterns
  
MITIGATION (response):
  1. Immediately rotate the leaked secret
  2. Purge the secret from all log storage (if possible)
  3. Audit: Who accessed the logs during the exposure window?
  4. Incident report: How did the secret get logged?

STAFF INSIGHT:
  The application should NEVER hold the raw secret string.
  Ideal: Application gets a "wrapped" credential that can be used for auth
  but not extracted as a string. Example: A pre-configured database connection
  object, not a password string.
```

## Failure Mode 5: Flag Evaluation Inconsistency

```
SCENARIO: Flag rollout at 50% → Some users see inconsistent behavior
across requests due to inconsistent flag rules across servers.

ROOT CAUSE:
  Propagation delay: Server A has flag version 7 (50% rollout)
  Server B still has flag version 6 (25% rollout)
  User in the 26-50% bucket: Sees new feature on Server A, not on Server B
  → "It works sometimes" reports from users

DURATION: 5-second propagation window (brief, but noticeable for active users)

MITIGATION:
  1. STICKY SESSIONS: Route user to same server for session duration
     → Consistent experience within a session
     → But: Degrades load balancing, adds complexity
     
  2. VERSION PINNING: Client includes flag version in cookie
     → Server evaluates against the version the user first saw
     → Consistent across servers
     → But: Increases complexity, stale version risk
     
  3. ACCEPT IT: 5 seconds of inconsistency during flag changes
     → Most flag changes happen once (not continuously)
     → Impact: Very few users experience inconsistency
     → Cost of fixing is higher than cost of the problem
  
  Staff decision: Option 3 for most flags. Option 2 for critical flags
  (payment flow, checkout process) where inconsistency causes data issues.
```

## Failure Timeline Walkthrough

```
SCENARIO: Complete infrastructure failure affecting config system

T+0min:   Network partition separates config store from propagation servers
T+0.5min: Propagation servers detect: Cannot read change log
T+1min:   Propagation servers continue serving cached state
          Sidecars: Unaffected (connected, receiving heartbeats)
T+2min:   Config API rejects writes: "Store unreachable"
T+3min:   On-call engineer needs to change rate_limit during incident
          → Cannot make config changes → Frustration
T+5min:   Alert: "Config store unreachable for 5 minutes"
T+10min:  On-call decides to use emergency local override:
          SSH to critical servers, set local config file override
          → This bypasses the config system (emergency fallback)
T+15min:  Network partition resolved
T+16min:  Config store reachable again
T+17min:  Propagation servers catch up on change log
T+18min:  All sidecars receive pending updates
T+20min:  On-call removes local config overrides from critical servers
T+22min:  Normal operation fully restored

LESSONS:
1. Config store outage ≠ service outage (cached config kept services running)
2. Inability to CHANGE config during incident is the real pain point
3. Emergency local override mechanism is a critical escape hatch
4. Config system must recover gracefully (catch-up, not restart)
```

## On-Call Runbooks for the Config Platform

```
RUNBOOK 1: CONFIG PROPAGATION DELAYED
  Alert: config_propagation_lag_seconds > 10 for 5 minutes
  
  Diagnosis steps:
  1. Check propagation server health (are they running?)
  2. Check change log consumer lag (is the stream backed up?)
  3. Check network between propagation servers and clients
  4. Check for large config change (bulk update = slower propagation)
  
  Resolution:
  - If propagation servers down: Restart, clients auto-reconnect
  - If stream backed up: Scale propagation servers
  - If large change: Wait (propagation is working, just slow)

RUNBOOK 2: CONFIG STORE UNREACHABLE
  Alert: config_store_health != "healthy" for 2 minutes
  
  IMMEDIATE:
  1. Verify database health (replica status, disk, connections)
  2. Check if writes are failing or reads too
  3. If writes only: Possible leader election in progress → Wait 30s
  4. If reads and writes: Database down → Failover to replica
  
  Impact: Config changes impossible, but services unaffected
  
RUNBOOK 3: CARDINALITY EXPLOSION IN FLAGS
  Alert: total_active_flags > 10000
  
  This isn't an emergency, but it's tech debt accumulating:
  1. Run flag usage report: Which flags haven't been evaluated in 30 days?
  2. Identify flags in FULLY_ON state for > 30 days → Should be code-cleaned
  3. Send cleanup assignments to flag owners
  4. If owners unresponsive after 2 weeks → Auto-archive the flag
```

---

# Part 10: Performance Optimization & Hot Paths

## Critical Paths

```
CRITICAL PATH 1: Flag evaluation (per-request, in-process)
  Budget: < 100µs (must not impact request latency)
  
  Optimization: Rules compiled into decision tree on sync
    Instead of: FOR each rule, FOR each condition, evaluate
    Compiled to: Binary decision tree, average depth 3 → 3 comparisons
    
  Before compilation: 50 rules × 3 conditions = 150 condition evaluations
  After compilation: 3-5 condition evaluations (decision tree)
  
  Speedup: 30-50×

CRITICAL PATH 2: Config value lookup (per-request, in-process)
  Budget: < 1µs
  
  Optimization: HashMap with pre-computed hash
    Config keys are known at sync time → Pre-hash all keys
    Lookup: Single hash table access → O(1)
    
  Additional: Hot config values (accessed > 1000×/second per instance)
    → Promote to thread-local cache to avoid HashMap lock contention

CRITICAL PATH 3: Config propagation (background, but latency-sensitive)
  Budget: < 5 seconds from write to all clients
  
  Optimization: Delta-based sync
    Instead of: Sending entire config on every change
    Send only: Changed keys and their new values
    
  For 500,000 keys, a typical change touches 1 key:
  Full sync: 100 MB × 500,000 clients = 50 TB of network traffic
  Delta sync: 200 bytes × 500,000 clients = 100 MB of network traffic
  Saving: 500,000× less network traffic

NOT ON CRITICAL PATH (but still important):
  Config writes: 50-200ms is acceptable (human-initiated, rare)
  Secret rotation: Minutes is acceptable (background operation)
  Audit queries: Seconds is acceptable (admin-only)
```

## Caching Strategies

```
CACHE LAYER 1: In-process HashMap (flag rules + config values)
  Cache: ALL config values for subscribed namespaces
  Invalidation: On propagation event (push-based)
  Size: ~10 MB per instance (trivially fits in memory)
  Hit rate: 100% (all reads served from cache after initial sync)
  
CACHE LAYER 2: Disk cache (persistent across restarts)
  Cache: Serialized snapshot of in-process cache
  Written: Every 60 seconds or on significant change
  Used on: Service restart (avoids full fetch from server)
  Size: Same as in-process cache (~10 MB)
  
CACHE LAYER 3: DEK cache in Secrets Engine
  Cache: Decrypted data encryption keys
  Size: 10,000 keys × 256 bits = 320 KB
  TTL: 1 hour per key
  Hit rate: >99% (keys rarely change)
  Impact: Reduces KMS calls from 500,000/hour to ~100/hour

CACHE LAYER 4: Propagation server config cache
  Cache: Latest version of each namespace
  Used for: Serving full config to newly connected clients
  Invalidation: On change log event
  
ANTI-PATTERN: Caching at a shared layer (Redis) between service and config
  → Adds a network hop to every config read
  → Redis down → Config unavailable (new dependency)
  → Defeats the purpose of local evaluation
  NEVER cache config in an external shared cache for runtime reads.
```

## Precomputation vs Runtime Work

```
PRECOMPUTED:
  1. Flag targeting rule compilation
     At sync time: Rules compiled into decision tree
     At eval time: Traverse tree (fast)
     Cost: ~10ms per flag to compile (5,000 flags = 50 seconds)
     Benefit: 30-50× faster evaluation
  
  2. Config key hashing
     At sync time: Pre-hash all config keys
     At read time: Direct HashMap lookup (no hashing)
     Cost: ~1µs per key to hash (500,000 keys = 500ms)
     Benefit: Eliminates hashing from hot path
  
  3. Percentage rollout bucketing
     At sync time: Pre-compute bucket assignments for common contexts
     At eval time: Lookup pre-computed assignment
     Cost: Not practical for all users (too many)
     Benefit: Marginal (hash is already fast)
     Staff decision: NOT precomputed. Hash is fast enough (~10ns).

RUNTIME:
  1. Config value lookups (trivial HashMap access)
  2. Flag evaluation (compiled decision tree traversal)
  3. Secret decryption (on cache miss only)
  
Staff insight: Precompute everything that happens at sync time.
The sync happens ~once per minute (when config changes).
The evaluation happens ~110 times per request.
Any work moved from evaluation to sync is multiplied by millions.
```

## Backpressure

```
BACKPRESSURE 1: Too many config changes too fast
  Scenario: Automated system writes 1,000 config changes in 10 seconds
  Problem: Propagation pipeline overwhelmed, lag increases
  
  Backpressure mechanism:
  → Config API: Rate limit per actor (max 10 writes/second)
  → Batch writes: API supports atomic multi-key updates
    → 1,000 key changes = 1 batch write = 1 propagation event
  → Propagation server: If lag > 10 seconds, log warning
  → If lag > 30 seconds, alert on-call

BACKPRESSURE 2: Too many clients reconnecting simultaneously
  Scenario: Propagation server restart → 50,000 clients reconnect at once
  Problem: Each reconnection requires full delta sync
  
  Backpressure mechanism:
  → Client reconnection jitter: Random delay 0-10 seconds
  → Server connection queue: Accept max 1,000 new connections/second
  → Prioritize: Existing heartbeat traffic over new connections
  → Clients with valid disk cache can serve during reconnection delay

BACKPRESSURE 3: KMS rate limit exceeded
  Scenario: Mass restart → 50,000 secret decrypt requests in 30 seconds
  Problem: KMS rate limit (10,000 requests/second per key)
  
  Backpressure mechanism:
  → Sidecar: Stagger secret fetches (random delay 0-60 seconds on startup)
  → Secrets engine: Queue requests, batch KMS calls
  → If KMS unavailable: Use cached DEKs (if within cache TTL)
  → Compiled-in emergency DEK (last resort, security trade-off)
```

## Load Shedding

```
LOAD SHEDDING 1: Config API under heavy write load
  Priority 1: Kill switch changes (NEVER shed)
  Priority 2: Secret rotation (high priority)
  Priority 3: Config updates with approval (medium priority)
  Priority 4: Bulk/automated changes (first to shed)
  
  When load > 80%: Queue Priority 4 requests
  When load > 90%: Reject Priority 4, queue Priority 3
  When load > 95%: Reject Priority 3-4, only serve Priority 1-2

LOAD SHEDDING 2: Propagation server under connection load
  When connections > 90% capacity:
  → Stop accepting new connections (return 503)
  → Maintain existing connections (never drop active connections)
  → Alert: "Propagation server at capacity, scale up"

LOAD SHEDDING 3: Secret API under heavy load
  When decrypt QPS > KMS capacity:
  → Serve from DEK cache (no KMS call needed if DEK cached)
  → Queue new DEK fetches
  → If cache completely cold (mass restart): Stagger service startups
```

## Why Some Optimizations Are Intentionally NOT Done

```
OPTIMIZATION 1: Compress config values for network efficiency
  Why NOT: Config deltas are tiny (~200 bytes per change)
  Compression overhead > savings for small payloads
  
OPTIMIZATION 2: CDN for config distribution
  Why NOT: Config must be pushed (not pulled)
  CDNs are pull-based and introduce caching inconsistency
  CDN cache invalidation adds latency, defeating the propagation SLA
  
OPTIMIZATION 3: Peer-to-peer config distribution
  Why NOT: Adds complexity, no clear trust model
  Central propagation is simple and sufficient for 500K instances
  P2P would be necessary at >10M instances (hyperscale)
  
OPTIMIZATION 4: Read-through cache for secrets
  Why NOT: Every cache layer is a secret leakage risk
  Minimize the number of places secrets exist in memory
  Cache in the sidecar only, nowhere else
```

---

# Part 11: Cost & Efficiency

## Major Cost Drivers

```
COST DRIVER 1: Config Store (database)
  Data size: ~3 GB (trivially small)
  Replicated across 3 AZs: ~$50/month
  This is NOT a significant cost.

COST DRIVER 2: Propagation Server Fleet
  10 servers handling 50,000 connections each
  Memory-bound: ~5 GB RAM per server (connection buffers)
  Compute: Minimal (just forwarding events)
  Cost: ~$2,000/month
  
COST DRIVER 3: KMS / HSM
  50,000 secrets, ~100 KMS API calls/hour (with DEK caching)
  KMS cost: $1 per 10,000 API calls = ~$7/month
  HSM (if used): ~$1,500/month per HSM instance (minimum 2 for HA)
  → HSM is the largest single cost item (if required by compliance)

COST DRIVER 4: Audit Log Storage
  430 MB/day × 365 days × 7 years = ~1.1 TB total
  Hot storage (< 30 days): ~12 GB on SSD → $5/month
  Cold storage (> 30 days): ~1.1 TB on object storage → $25/month
  Total audit storage: ~$30/month

COST DRIVER 5: Engineering Time (the real cost)
  Platform team: 3-5 engineers maintaining the config platform
  At $300K fully loaded cost per engineer: $900K - $1.5M/year
  → The infrastructure cost is negligible compared to people cost
  → Staff insight: Build vs buy decision should focus on engineering time

TOTAL INFRASTRUCTURE COST: ~$5,000 - $7,000/month
  (Dominated by HSM if required, otherwise ~$2,500/month)
  
This is CHEAP for a system serving 500,000 instances.
Cost per instance: $0.005 - $0.014/month.
```

## How Cost Scales with Traffic

```
SCALING FACTOR: Number of service instances (not QPS)
  Config reads are local → No server cost per read
  Cost scales with: Connections (propagation), Secrets (KMS calls)
  
  500K instances → $5K/month
  1M instances → $8K/month (more propagation servers)
  5M instances → $25K/month (hierarchical propagation needed)
  
SCALING FACTOR: Number of secrets
  Each secret rotation requires KMS calls
  50K secrets → $7/month KMS
  500K secrets → $70/month KMS (still trivial)
  
SCALING FACTOR: Number of config changes
  Each change triggers propagation to all subscribers
  2,500 changes/day → Negligible (a few bytes per change)
  250,000 changes/day → Still negligible (config system is not data-heavy)
  
COST CLIFF: HSM requirements
  If compliance requires HSM (PCI DSS Level 1, FIPS 140-2):
  → $1,500/month per HSM × 2 (HA) × 3 (regions) = $9,000/month
  → Dominates ALL other costs combined
  → Staff decision: Use cloud KMS (software-based) unless compliance mandates HSM
```

## Trade-offs Between Cost and Reliability

```
TRADE-OFF 1: Replication factor for config store
  3 replicas: Standard, survives 1 failure → ~$50/month
  5 replicas: Survives 2 failures → ~$85/month
  Decision: 3 replicas. Config store failure is not service-impacting.
  
TRADE-OFF 2: Propagation server redundancy
  N+1: 11 servers (1 spare) → $2,200/month
  N+2: 12 servers (2 spare) → $2,400/month
  2N: 20 servers → $4,000/month
  Decision: N+2. Losing 2 servers still leaves capacity for all connections.
  
TRADE-OFF 3: Audit log durability
  Single region: $30/month → Risk: Region failure loses audit data
  Multi-region: $90/month → Survives region failure
  Decision: Multi-region for audit (compliance requirement, non-negotiable)
  
TRADE-OFF 4: Secret encryption strength
  AES-256 (software): Fast, standard, free
  HSM-backed: Slower, expensive ($9K/month), required by some compliance
  Decision: AES-256 by default, HSM for Tier 2+ secrets only
```

## What Over-Engineering Looks Like

```
OVER-ENGINEERING 1: Sub-second propagation
  "Config changes must propagate in < 100ms"
  Reality: 5 seconds is fine for 99.9% of use cases
  Cost of 100ms: Requires dedicated push infrastructure, websockets everywhere
  Savings: Accept 5-second SLA → 80% simpler architecture

OVER-ENGINEERING 2: Full CRDT-based config with conflict resolution
  "Support concurrent writes with automatic merge"
  Reality: Config writes are rare (~3/second). Optimistic concurrency is fine.
  CRDT adds massive complexity for zero practical benefit.

OVER-ENGINEERING 3: Zero-knowledge secret storage
  "The config system should not be able to decrypt secrets"
  Reality: The system needs to decrypt to serve secrets to consumers.
  Zero-knowledge works for password managers, not for service config.
  
OVER-ENGINEERING 4: Machine learning for config anomaly detection
  "Automatically detect bad config values using ML"
  Reality: Schema validation catches 99% of bad values.
  ML for the remaining 1% is expensive and produces false positives.
  → Better approach: Canary rollout with metrics-based rollback.
```

## Cost-Aware Redesign

```
IF BUDGET IS $500/MONTH (startup with 1,000 instances):
  → Use cloud-native solution (AWS AppConfig, GCP Remote Config)
  → No dedicated infrastructure
  → Feature flags via LaunchDarkly or similar SaaS
  → Secrets in AWS Secrets Manager or GCP Secret Manager
  → Total: ~$200-500/month (managed services)
  
  This is the RIGHT decision for a startup. Don't build a config platform.

IF BUDGET IS $5,000/MONTH (mid-scale, 100,000 instances):
  → Self-hosted config store (PostgreSQL)
  → Custom propagation (5 servers)
  → SDK for local evaluation
  → Cloud KMS for secrets
  → Total: ~$3,000/month
  
IF BUDGET IS $50,000/MONTH (hyperscale, 5,000,000 instances):
  → Sharded config store
  → Hierarchical propagation (aggregator tier)
  → Multi-region with independent propagation per region
  → Dedicated HSMs for compliance
  → Total: ~$25,000-40,000/month
```

---

# Part 12: Multi-Region & Global Considerations

## Data Locality

```
PRINCIPLE: Config is global by default, but secrets must be regional.

CONFIGURATION AND FLAGS:
  Same config applies everywhere (e.g., timeout_ms = 500)
  Exception: Region-specific overrides
    /payment-service/production/timeout_ms = 500          (global default)
    /payment-service/production/us-east-1/timeout_ms = 1000  (region override)
  
  Namespace resolution:
    Service in us-east-1: Check /us-east-1/ first, then /production/, then /default/
    This allows region-specific tuning without separate config systems.

SECRETS:
  Secrets SHOULD be regional (different DB credentials per region)
  Even for the same database: Different read replicas per region
  
  Secret path: /secrets/payment-service/us-east-1/db_password
  
  WHY REGIONAL SECRETS:
  1. Different regions may use different infrastructure
  2. Secret rotation in one region shouldn't require global coordination
  3. Blast radius of a leaked secret is limited to one region
  4. Compliance: Some secrets cannot leave a geographic boundary (GDPR)
```

## Replication Strategies

```
CONFIG STORE REPLICATION:
  Primary region: All writes go to primary
  Read replicas: One per region (async replication, < 1 second lag)
  
  Propagation servers in each region read from local replica.
  Clients in each region connect to local propagation server.
  
  On primary region failure:
  → Read replicas have recent data (< 1 second behind)
  → Promote a replica to primary (manual or automated failover)
  → Config writes resume in new primary
  → No service impact (local caches still valid)

SECRET REPLICATION:
  Tier 1 secrets: Replicated across regions (for availability)
  Tier 2 secrets: Region-specific (no replication, for security)
  
  Replication encrypted in transit (TLS) and at rest (region-specific KMS key)
  
  Staff insight: Replicating secrets across regions means more places
  where secrets exist. Minimize replication to what's needed for availability.
```

## Traffic Routing

```
CLIENT-TO-PROPAGATION-SERVER ROUTING:
  Each client connects to the NEAREST propagation server
  (Same region, same availability zone if possible)
  
  DNS-based routing: propagation.config.internal resolves to local servers
  Fallback: If local propagation servers are down, connect to next-nearest region
  
  Latency impact of cross-region fallback:
  → Propagation latency increases by cross-region RTT (~50-100ms)
  → Still within 5-second SLA
  → Acceptable during regional failure

CONFIG API ROUTING:
  All writes go to primary region (strong consistency)
  Admin UI reads can go to any replica (eventual consistency)
  
  If primary region unavailable:
  → Writes queue at edge (limited buffer)
  → Or: Promote replica and accept potential split-brain risk
  → Staff decision: Queue writes. Split-brain in config is worse than delayed writes.
```

## Failure Across Regions

```
SCENARIO: US-East-1 (primary) experiences complete outage.

IMPACT:
  Config writes: UNAVAILABLE (primary down)
  Config reads in US-East-1: From local cache (stale but safe)
  Config reads in other regions: From local replica (< 1 second behind)
  Propagation in US-East-1: Stopped (no propagation servers)
  Propagation in other regions: Continues from local replica
  
FAILOVER:
  Option A: Wait for US-East-1 to recover (minutes to hours)
    Pro: No risk of split-brain
    Con: Cannot make config changes during outage
    
  Option B: Promote US-West-2 to primary
    Pro: Config writes resume
    Con: If US-East-1 comes back, two primaries → Data conflict
    → Requires reconciliation protocol
    
  Staff decision: Option A for most outages (they recover in minutes).
  Option B only if outage exceeds 30 minutes AND config changes are critical.
```

## When Multi-Region Is NOT Worth It

```
MULTI-REGION CONFIG IS NOT WORTH IT WHEN:

1. All services run in a single region
   → Single-region config store with multi-AZ replication is sufficient
   → Multi-region adds complexity without benefit

2. Total instance count < 10,000
   → Single propagation server fleet handles everything
   → Cross-region latency for propagation is tolerable
   
3. Config changes are infrequent (< 100/day)
   → Even with 5-second cross-region propagation, impact is minimal
   
MULTI-REGION IS NECESSARY WHEN:
  → Services span 3+ regions with independent operational needs
  → Compliance requires data residency per region
  → Cross-region network latency exceeds propagation SLA
  → Total instances > 100,000 (connection scaling requires regional servers)
```

---

# Part 13: Security & Abuse Considerations

## Abuse Vectors

```
ABUSE VECTOR 1: Config store as general-purpose database
  Developer stores large JSON blobs (user lists, ML models) in config
  → Config store fills up, propagation slows, all services affected
  
  Mitigation:
  → Per-key size limit: 1 MB max
  → Per-namespace size limit: 10 MB max
  → Review: Flag configs > 100 KB for manual review
  → Education: "Config is for BEHAVIOR, not DATA"

ABUSE VECTOR 2: Feature flag as permanent code branch
  Developer creates flag "if feature_flag_x then path_A else path_B"
  Flag stays in TARGETING state for 2 years
  → Code becomes unmaintainable, flag interactions unpredictable
  
  Mitigation:
  → Flag expiry: Flags > 90 days in TARGETING generate alerts
  → Flag cleanup SLA: Owner must clean up within 30 days of full rollout
  → Auto-archive: Flags not evaluated in 30 days get archived
  → Code review: Block PRs that reference archived flags

ABUSE VECTOR 3: Secret sprawl
  Each team creates its own copy of shared credentials
  → Same DB password stored in 50 different paths
  → Rotation must happen 50 times instead of once
  → One copy gets forgotten and never rotated
  
  Mitigation:
  → Shared secrets: Reference pattern (/secrets/shared/db_password)
  → Teams reference the shared secret, not copy it
  → Secret duplication detection (alert when same value appears in multiple paths)

ABUSE VECTOR 4: Config change as attack vector
  Compromised CI/CD pipeline pushes malicious config
  → Disables security features, opens rate limits, redirects traffic
  
  Mitigation:
  → Config change signing (CI/CD pipeline has limited permissions)
  → Production changes require human approval
  → Config changes audited and alertable
  → Critical configs (security-related) require two-person approval
```

## Rate Abuse

```
RATE ABUSE 1: Automated script making thousands of config changes/minute
  → Overwhelms config store and propagation pipeline
  
  Mitigation:
  → Per-actor rate limit: 10 changes/second (generous for humans)
  → Per-namespace rate limit: 100 changes/minute
  → Batch API for bulk changes (1 propagation event for N changes)

RATE ABUSE 2: Tight loop re-fetching secrets
  Application bug: Fetch secret on every request instead of caching
  → 100,000 QPS to secrets API per instance
  
  Mitigation:
  → SDK enforces minimum cache TTL (5 minutes)
  → Secrets API rate limit per service identity (100 requests/minute)
  → Alert on excessive secret access patterns

RATE ABUSE 3: Flag evaluation with expensive context
  Developer passes entire user object (100+ fields) as flag context
  → Each evaluation marshals and processes all fields
  → 10× slower evaluation
  
  Mitigation:
  → SDK validates context size (max 20 attributes)
  → Documentation: "Only pass attributes used in targeting rules"
```

## Data Exposure

```
EXPOSURE RISK 1: Config values in error messages
  Service crashes, stack trace includes config values
  → Connection strings, internal URLs, thresholds exposed in error reports
  
  Mitigation:
  → Config SDK marks values as "sensitive" or "non-sensitive"
  → Error reporting libraries redact sensitive config values
  → Config values never included in client-facing error messages

EXPOSURE RISK 2: Secrets in memory dumps
  Service crashes, core dump written to disk
  → Core dump contains decrypted secrets in memory
  
  Mitigation:
  → Secrets in mlock'd memory (no swap)
  → Core dump exclusion for secret memory regions (madvise(MADV_DONTDUMP))
  → Encrypt core dumps at rest
  → Auto-delete core dumps after 24 hours

EXPOSURE RISK 3: Flag targeting rules reveal business logic
  Targeting rules contain: "country IN [US, CA, UK]" + "user_tier == premium"
  → Reveals launch plans, pricing strategy, geographic priorities
  
  Mitigation:
  → Access control on flag definitions (separate from flag evaluation)
  → Flag rules visible only to flag owner's team
  → Evaluation API returns only the result, not the rules
```

## Privilege Boundaries

```
BOUNDARY 1: Service identity
  Each service has a unique identity (mTLS certificate)
  Services can only read config for their own namespaces
  Services can only read secrets they're explicitly granted access to
  
BOUNDARY 2: Environment isolation
  Production secrets CANNOT be accessed from staging environments
  Staging config CANNOT affect production services
  Enforcement: Separate config stores or strict namespace isolation
  
BOUNDARY 3: Admin tiers
  Tier 1: Read-only (view config values, flag states)
  Tier 2: Config writer (change config values within owned namespaces)
  Tier 3: Flag manager (create/modify flags, targeting rules)
  Tier 4: Secret admin (manage secrets, trigger rotations)
  Tier 5: Platform admin (manage namespaces, permissions, schemas)
  
  Each tier includes the permissions of lower tiers.
  Tier 4+ requires additional authentication (MFA, hardware key).
  
BOUNDARY 4: Change approval
  Non-production: Self-service (no approval needed)
  Production, non-critical: Peer review (one approver)
  Production, critical (security, payments): Two-person approval
  Emergency: On-call bypass (logged, automatically reviewed within 24 hours)
```

## Why Perfect Security Is Impossible

```
1. The config system MUST be able to serve secrets:
   If it can decrypt secrets, it can be compromised to leak them.
   Full zero-trust would mean the config system can't do its job.

2. Engineers need to change config during incidents:
   Incident response requires fast, sometimes bypass-approval changes.
   Strict approval workflows slow down incident response.
   → Trade-off: Emergency bypass with post-incident review.

3. Config values reveal system behavior:
   Even without secrets, knowing "timeout = 500ms, retry = 3"
   reveals implementation details useful for targeted attacks.
   → Acceptable risk: Config is internal-only.

4. Flag rules can be reverse-engineered from behavior:
   Users who are systematically included/excluded from features
   can deduce the targeting logic.
   → Acceptable risk: Flag rules aren't typically secret.

PRACTICAL STANCE:
  Protect secrets with encryption, access control, and audit.
  Protect config with access control and validation.
  Assume everything else will eventually leak.
  Design for detection and response, not just prevention.
```

## Multi-Team Governance and Platform Ownership

```
ORGANIZATIONAL STRUCTURE:

PLATFORM TEAM (3-5 engineers):
  Owns: Config API, Config Store, Propagation, SDK, Secrets Engine
  Provides: Self-service onboarding, documentation, client libraries
  SLOs: Propagation latency, read availability, secret availability
  
SERVICE TEAMS (500+ teams):
  Own: Their config namespaces, flag definitions, secret access policies
  Responsible for: Config schema definitions, flag cleanup, secret rotation
  Self-service: Create namespaces, define flags, request secret access

GOVERNANCE MECHANISMS:

1. NAMESPACE OWNERSHIP:
   Every namespace has an owning team.
   Only the owning team can write to the namespace.
   Cross-team access requires explicit grant from the owner.

2. FLAG LIFECYCLE ENFORCEMENT:
   Flags in TARGETING > 90 days → Auto-alert to owner
   Flags in FULLY_ON > 30 days → Cleanup ticket created
   Flags not evaluated in 30 days → Auto-archived
   
   Quarterly report to team leads:
   "Your team has 47 flags. 12 are stale (not evaluated in 30 days).
    8 are fully on (should be cleaned up from code).
    Estimated code debt from stale flags: ~500 lines."

3. SECRET ROTATION COMPLIANCE:
   Secrets > 90 days old without rotation → Auto-alert to security team
   Secrets > 180 days old → Forced rotation triggered
   Per-team rotation compliance dashboard:
   "95% of your secrets are within rotation policy. 3 overdue."

4. COST ATTRIBUTION:
   Monthly report per team:
   "Your team has 200 config keys, 15 flags, 30 secrets.
    Config changes this month: 45
    Estimated platform cost: $12/month (negligible)"
   
   Since config platform cost is trivially low, cost attribution is
   primarily about AWARENESS, not chargeback.
```

---

# Part 14: Evolution Over Time

## V1: Naive Design

```
V1 ARCHITECTURE (startup, 100 services, 1,000 instances):

  YAML files in Git repository
  CI/CD pipeline bakes config into container image
  Secrets in environment variables (set during deploy)
  Feature flags: if/else in code with environment-specific branches
  
  Deployment: Change YAML → PR → Merge → Build → Deploy
  Latency to apply config change: 30-60 minutes
  
  WHY IT WORKS AT SMALL SCALE:
  → 1,000 instances, 100 services, 5 deploys/day
  → 30-minute deploy cycle is tolerable
  → Small team, everyone knows the config
  → Few secrets, manual rotation is manageable
  
  COST: $0 (no dedicated infrastructure)
```

## What Breaks First

```
BREAK 1: Config change latency (at ~500 instances)
  "We need to change a timeout NOW, not in 30 minutes"
  → First incident where deploy speed matters
  → Engineers start SSH-ing to servers to change config manually
  → Manual changes are untracked, unreproducible, dangerous

BREAK 2: Secret management (at ~1,000 instances)
  "Our database password is in 47 environment variables across 12 services"
  → Password rotation requires 12 coordinated deploys
  → Someone commits a .env file to Git (secret leak incident)
  → Compliance audit: "Where are your secrets? Who has access?"

BREAK 3: Feature flag spaghetti (at ~2,000 instances)
  "We have 200 feature flags in code, half are stale"
  → Flag interactions cause bugs nobody can reproduce
  → "It works in staging but not production" (flag configuration differs)
  → Flags scattered across multiple config files with no central view

BREAK 4: Config consistency (at ~5,000 instances)
  "Why does this service behave differently on different servers?"
  → Manual config edits on some servers but not others
  → Config drift: Production doesn't match what's in Git
  → Incident: "The config in Git says X but the servers have Y"
```

## V2: Intermediate Design

```
V2 ARCHITECTURE (mid-scale, 1,000 services, 50,000 instances):

  Central config API (REST)
  Key-value store (etcd or Consul)
  Services poll config server every 30 seconds
  Feature flags: Dedicated flag service with targeting rules
  Secrets: HashiCorp Vault or cloud secrets manager
  
  Latency to apply config change: 30 seconds (poll interval)
  
  IMPROVEMENTS OVER V1:
  → Dynamic config without deploy
  → Central visibility (who changed what)
  → Secret encryption at rest
  → Feature flag targeting (user segments, percentages)
  
  PROBLEMS:
  → Polling at 50,000 instances = 1,667 requests/second (manageable but wasteful)
  → 30-second propagation is too slow for kill switches
  → etcd/Consul scalability ceiling (~100K keys)
  → Flag evaluation requires network call (adds latency)
  → Config server is on the critical path (if it's slow, services are slow)
```

## V3: Long-Term Stable Architecture

```
V3 ARCHITECTURE (scale, 10,000 services, 500,000 instances):

  This chapter's architecture:
  
  Central config store (PostgreSQL, sharded if needed)
  Streaming propagation (gRPC streams, not polling)
  In-process SDK for config reads and flag evaluation (no network on hot path)
  Separate sidecar for secret management
  Envelope encryption with KMS
  Schema validation at write time
  Gradual rollout with automatic metrics-based rollback
  Full audit trail with compliance retention
  Multi-region with per-region propagation
  
  Latency to apply config change: < 5 seconds (streaming)
  Kill switch latency: < 2 seconds (priority propagation)
  Flag evaluation latency: < 100µs (in-process)
  
  IMPROVEMENTS OVER V2:
  → No polling overhead (streaming push)
  → No network call on hot path (in-process evaluation)
  → Scalable propagation (hierarchical if needed)
  → Secret isolation (sidecar, not in-process)
  → Schema validation prevents config poisoning
  → Gradual rollout prevents blast-radius explosions
  
  Staff insight: The jump from V2 to V3 is primarily about moving
  evaluation from server-side to client-side. This ONE change
  eliminates the config server from the critical path and enables
  the system to serve billions of evaluations per second.
```

## How Incidents Drive Redesign

```
INCIDENT 1: "Config change caused global outage (timeout set to 0)"
  → Added: Schema validation with range constraints
  → Added: Canary rollout (1% → 10% → 100%)
  → Added: Automatic rollback on error rate spike after config change
  
INCIDENT 2: "Secret found in application logs"
  → Added: SecureString type that redacts on toString()
  → Added: Log pipeline scrubbing for secret patterns
  → Added: Static analysis in CI to detect logging of secret variables
  
INCIDENT 3: "Config server overloaded during mass restart"
  → Added: Disk cache for fast restart (no config fetch needed)
  → Added: Connection rate limiting and jitter on reconnection
  → Added: Compiled-in defaults as last-resort fallback
  
INCIDENT 4: "Flag interaction caused checkout to break for 5% of users"
  → Added: Flag dependency tracking (which flags affect which flows)
  → Added: Integration tests for common flag combinations
  → Added: Flag cleanup enforcement (stale flags auto-archived)
  
INCIDENT 5: "Secret rotation took 6 hours because 3 services didn't pick up new version"
  → Added: Rotation verification step (check all consumers before revoking old)
  → Added: Per-service secret version metric for visibility
  → Added: Forced-refresh mechanism (push notification to sidecar)
```

## Canary Deployment for the Config Platform

```
PROBLEM: A bad deploy to the config platform can freeze all
configuration for the entire organization, or worse, corrupt config data.

BLAST RADIUS OF BAD PLATFORM DEPLOY:
  - Bug in config API: All config writes fail
  - Bug in propagation: Config changes stop reaching services
  - Bug in SDK: All flag evaluations may produce wrong results
  - Bug in secrets engine: Secret access may fail

CANARY STRATEGY:

1. SDK DEPLOY (highest risk, widest blast radius):
   SDKs are embedded in every service. A bad SDK version
   affects every service that adopts it.
   
   Strategy: SDK is a LIBRARY, not a service. It's adopted
   per-service, not deployed centrally.
   → Service teams adopt new SDK versions at their own pace
   → Platform team publishes SDK, doesn't force upgrades
   → Critical bug: Publish fix, notify teams, but don't force
   
   Exception: If SDK has a security vulnerability, force upgrade with deadline.

2. PROPAGATION SERVER DEPLOY:
   Deploy to 1 server (out of 10) → Monitor for 1 hour
   → Deploy to 3 servers → Monitor for 2 hours
   → Deploy to all → Monitor for 4 hours
   
   Compare canary vs non-canary:
   - Connection stability (disconnection rate)
   - Propagation latency (event delivery time)
   - Memory usage (per-connection overhead)

3. CONFIG API DEPLOY:
   Deploy to 1 instance (out of 3) behind load balancer
   → Route 33% of writes to canary
   → Compare: Error rate, latency, validation behavior
   → If no issues after 1 hour: Full deployment

4. SECRETS ENGINE DEPLOY:
   Deploy to 1 instance → Route test secret decryptions
   → Verify decrypted value matches expected (end-to-end test)
   → Deploy to all after 2 hours of clean operation

STAFF PRINCIPLE:
  "Config platform changes are the SECOND slowest to deploy
  (after the observability platform). Move deliberately."
```

---

# Part 15: Alternatives & Explicit Rejections

## Alternative 1: Git-Based Config with CI/CD Propagation

```
DESIGN:
  All config stored in Git repository as YAML/JSON files.
  Changes require PR → Review → Merge → CI/CD pipeline.
  Pipeline pushes config to services (Kubernetes ConfigMap, Ansible, etc.).

WHY IT SEEMS ATTRACTIVE:
  → Familiar workflow (Git + PRs)
  → Built-in audit trail (Git history)
  → Review process (PR approval)
  → Version control (Git tags/branches)
  → Infrastructure-as-code movement encourages this

WHY A STAFF ENGINEER REJECTS IT (for runtime config):
  1. PROPAGATION LATENCY: 5-30 minutes (CI/CD pipeline)
     → Kill switch takes 30 minutes instead of 5 seconds
     → Unacceptable for incident response
     
  2. NO DYNAMIC TARGETING: Feature flags need per-user evaluation
     → Git files are static; can't target "10% of users in US"
     → Would need a separate flag system anyway
     
  3. NO SECRET ENCRYPTION IN GIT: Secrets in Git require extra tooling
     (git-crypt, SOPS, sealed-secrets)
     → Complex, error-prone, and doesn't solve rotation
     
  4. BLAST RADIUS: CI/CD deploys to all servers simultaneously
     → No canary, no gradual rollout, no automatic rollback

WHERE IT DOES WORK:
  → Static infrastructure config (region mappings, instance types)
  → Config that changes with code (API schemas, database migrations)
  → Configuration that needs PR review by design (security policies)
  
  Staff guideline: Git for DEPLOY-TIME config, dynamic system for RUNTIME config.
```

## Alternative 2: Distributed Consensus (etcd/ZooKeeper) as the Full Solution

```
DESIGN:
  Use etcd or ZooKeeper as the centralized config store.
  Watch mechanism for real-time propagation.
  All services connect directly to etcd.

WHY IT SEEMS ATTRACTIVE:
  → Built-in watch support (real-time updates)
  → Strong consistency (linearizable reads)
  → Battle-tested (Kubernetes uses etcd)
  → Low operational complexity (single system)

WHY A STAFF ENGINEER REJECTS IT (as the full solution):
  1. SCALABILITY CEILING: etcd handles ~100K keys, ~1 GB data reliably
     → 500K config keys + version history exceeds this
     → Watch performance degrades with many watchers (500K watchers = trouble)
     
  2. CONNECTION LIMIT: ZooKeeper handles ~10K active sessions well
     → 500K instances each needing a session = 50× beyond limit
     → Would need a proxy layer (which IS the propagation server)
     
  3. NO FEATURE FLAG ENGINE: etcd stores key-values, not targeting rules
     → Must build flag evaluation, rollout, A/B testing on top
     → At that point, etcd is just the storage layer
     
  4. NO SECRET MANAGEMENT: No encryption, rotation, lease management
     → Must add these as separate layers
     
  5. NO SCHEMA VALIDATION: etcd accepts any value for any key
     → Must add validation layer (which IS the config API server)

WHERE IT DOES WORK:
  → As a COMPONENT of the config system (backing store for small deployments)
  → For coordination/election (leader election, distributed locks)
  → For Kubernetes-internal config (which is its design purpose)
  
  Staff guideline: etcd/ZooKeeper is a BUILDING BLOCK, not a complete solution.
```

## Alternative 3: Fully Managed SaaS (LaunchDarkly / Split / ConfigCat)

```
DESIGN:
  Use third-party SaaS for feature flags and config.
  SDK embedded in services evaluates flags locally (same as our design).
  Management UI hosted by vendor.
  Secrets managed separately (AWS Secrets Manager, etc.).

WHY IT SEEMS ATTRACTIVE:
  → Zero infrastructure to manage
  → Feature-rich UI (experimentation, targeting, analytics)
  → Battle-tested SDKs
  → Fast time-to-value (days, not months)

WHY A STAFF ENGINEER REJECTS IT (at hyperscale):
  1. COST AT SCALE: LaunchDarkly pricing is per-seat + per-MAU
     → At 10M MAU, 500 engineers: ~$500K/year
     → Our self-hosted system: ~$60K-80K/year infrastructure
     → But: Self-hosted requires 3-5 engineers ($900K-$1.5M/year)
     → NET: SaaS may be CHEAPER than self-hosted until very large scale
     
  2. VENDOR DEPENDENCY: Vendor outage = Flag evaluation stuck
     → Modern SaaS SDKs cache locally (same as our design)
     → Actual risk is low (vendors have high availability)
     
  3. DATA RESIDENCY: Config data stored on vendor's infrastructure
     → May violate compliance requirements (financial services, government)
     
  4. CUSTOMIZATION: Can't customize targeting rules, integration with
     internal systems, or specialized rollout strategies
     
  5. UNIFIED SYSTEM: SaaS handles flags but not config or secrets
     → Still need config and secrets management separately
     → Three systems instead of one

WHERE IT DOES WORK:
  → Companies with < 1,000 engineers (TCO favors SaaS)
  → Product teams that need experimentation features immediately
  → Organizations without platform engineering capability
  
  Staff guideline: Use SaaS until the cost exceeds the cost of building.
  For most companies, that inflection point is around 2,000 engineers.
  Build only when you need deep customization or have compliance constraints.
```

---

# Part 16: Interview Calibration (Staff Signal)

## How Interviewers Probe This System

```
PROBE 1: "Design a feature flag system"
  Testing: Do you think beyond boolean flags?
  Weak answer: "Store flags in a database, check on each request"
  Strong answer: Discusses targeting rules, local evaluation, propagation,
  rollout percentages, consistent bucketing, and flag lifecycle management.

PROBE 2: "How do you propagate config to 500K servers?"
  Testing: Do you understand the fan-out problem?
  Weak answer: "Each server polls the config API"
  Strong answer: Discusses streaming push, propagation servers, delta sync,
  connection scaling limits, and hierarchical propagation for very large scale.

PROBE 3: "What happens if a bad config is pushed?"
  Testing: Do you design for failure?
  Weak answer: "We test in staging first"
  Strong answer: Discusses schema validation, canary rollout, automatic
  rollback on metric deviation, blast radius control, and rollback speed.

PROBE 4: "How do you manage secrets at scale?"
  Testing: Do you understand the security implications?
  Weak answer: "Encrypt secrets and store them"
  Strong answer: Discusses envelope encryption, KMS/HSM, secret rotation
  workflow (dual-live period), lease-based access, audit trail, and why
  secrets should never appear in logs or memory dumps.

PROBE 5: "How does the config system interact with deployments?"
  Testing: Do you understand the deploy vs. release distinction?
  Weak answer: "Config changes are part of the deploy"
  Strong answer: Discusses decoupling deploy from release, deploying inert
  code behind flags, activating via config change, and why config changes
  are MORE dangerous than code deploys (less testing, instant propagation).

PROBE 6: "What if the config server goes down?"
  Testing: Do you design for the config system's own failure?
  Weak answer: "Services will use defaults"
  Strong answer: Discusses the fallback chain (in-memory cache → disk cache
  → compiled defaults), why config reads must NEVER fail, and why the config
  system must not be on the startup critical path.

PROBE 7: "How do you handle config changes across multiple services?"
  Testing: Cross-service coordination awareness
  Weak answer: "Change both at the same time"
  Strong answer: Discusses backward-compatible config changes, coordinated
  rollout (change consumer first, then producer), shared config namespaces
  for cross-service values, and the dangers of config coupling.
```

## Common L5 Mistakes

```
MISTAKE 1: Putting config reads on the network path
  L5: "Service calls config API on each request to get fresh values"
  Problem: Config API becomes the bottleneck for ALL services
  Every request adds 5-20ms of latency for a config lookup
  L6 fix: In-process evaluation with background streaming sync

MISTAKE 2: Ignoring config change safety
  L5: "Config changes go straight to production"
  Problem: A single bad value = global outage in seconds
  L6 fix: Schema validation + canary rollout + automatic rollback

MISTAKE 3: Treating flags as permanent code branches
  L5: "We'll just leave the flag in and use it forever"
  Problem: Flag debt accumulates, interactions become unpredictable
  L6 fix: Flag lifecycle management with expiry enforcement

MISTAKE 4: Storing secrets alongside config
  L5: "Secrets are just another config value"
  Problem: Different security, access control, and audit requirements
  L6 fix: Separate secrets engine with encryption, rotation, and lease management

MISTAKE 5: No config versioning
  L5: "We just overwrite the old value"
  Problem: Can't roll back, can't audit, can't detect conflicts
  L6 fix: Append-only versioned storage with rollback capability

MISTAKE 6: Polling as the propagation mechanism
  L5: "Services poll every 30 seconds"
  Problem: 30-second worst-case latency, wasteful network traffic
  L6 fix: Streaming push with < 5 second propagation guarantee

MISTAKE 7: No local fallback for config unavailability
  L5: "If config server is down, return an error"
  Problem: Config server outage → ALL services fail
  L6 fix: Multi-layer fallback chain (cache → disk → compiled defaults)
```

## Staff-Level Answers

```
"The most dangerous thing in production isn't a code deploy—it's a config
change. Code deploys go through CI, testing, canary. Config changes can
bypass all of that. My first design decision is: How do we make config
changes AS safe as code deploys?"

"Flag evaluation must be a local operation—in-process memory lookup,
no network call. At our scale, any network involvement in flag evaluation
would add 5ms × 110 evaluations = 550ms to every request."

"Secrets are not config. They share the same propagation mechanism,
but they have completely different security requirements: encryption at
rest, access control per-service, rotation without downtime, and audit
on every read."

"The config system's failure mode should be 'frozen at last known good,'
never 'unavailable.' Services must continue serving with cached config.
The ONLY time config unavailability should be visible is when a service
starts cold with no cache—and even then, compiled-in defaults must work."

"Config changes are the #1 cause of production outages at scale.
Not code bugs, not hardware failures—config changes. That's why I
start the design with safety rails: schema validation, canary rollout,
automatic rollback, and blast radius control."
```

## Example Phrases a Staff Engineer Uses

```
"Let me separate the control plane from the data plane. Config writes
go through the control plane (API → Store). Config reads are entirely
on the data plane (local cache, no network)."

"I'd classify config changes by blast radius: single service, single
region, global. Each category gets a different safety gate."

"The propagation problem is about fan-out, not throughput. We need to
push to 500K clients in 5 seconds. The data per push is tiny."

"For secrets, I'd use envelope encryption—DEKs cached locally,
master key in KMS. This reduces KMS calls from 500K/hour to 100/hour."

"Feature flags have a lifecycle: create, target, roll out, fully on,
clean up. If we don't enforce cleanup, we'll have 10,000 stale flags
in 2 years, and nobody will know what any of them do."

"The most important metric for this system isn't uptime—it's
config change safety. How many config changes caused an incident
versus how many were applied safely?"
```

### Additional Interview Probes and Staff Signals

```
PROBE 8: "How do you handle configuration for serverless functions?"
  Testing: Understanding of ephemeral compute
  L5 answer: "Fetch config on every cold start"
  L6 answer: "Bake a config snapshot into the function package at deploy time.
  Lambda-style functions live for minutes, not hours. Streaming push doesn't
  work for ephemeral compute. Use deploy-time config with a cache layer
  that warms from the nearest config replica on cold start."

PROBE 9: "How do you prevent config changes from cascading across services?"
  Testing: Cross-service dependency awareness
  L5 answer: "Each service has its own config"
  L6 answer: "Config changes should be backward-compatible. If service A
  changes a shared timeout, service B must tolerate both old and new values.
  I'd enforce this with shared config namespaces that require cross-team
  approval for changes, plus integration tests for common config combinations."

STAFF SIGNALS:
1. SAFETY-FIRST THINKING: Candidate leads with blast radius control
   before discussing features. "Before I talk about targeting rules,
   let me explain how we prevent a bad flag from breaking production."

2. DEPLOY/RELEASE SEPARATION: Candidate naturally distinguishes between
   deploying code and releasing features. This indicates production experience.

3. OPERATIONAL EMPATHY: Candidate designs for the on-call engineer:
   "If the config system is down at 3 AM, the on-call needs to be able
   to change config locally without the central system."
```

---

# Part 17: Diagrams

## Diagram 1: Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                CONFIG SYSTEM: COMPONENT INTERACTION                          │
│                                                                             │
│   TEACH: How data flows from admin change to service behavior change        │
│                                                                             │
│   ┌──────────┐                                                              │
│   │  Admin    │                                                              │
│   │  (Human)  │──── 1. SET timeout=1000 ────┐                               │
│   └──────────┘                               │                              │
│                                    ┌─────────▼──────────┐                   │
│                                    │   Config API Server  │                   │
│                                    │  2. Validate schema  │                   │
│                                    │  3. Check permission  │                   │
│                                    │  4. Version: 41→42   │                   │
│                                    └─────────┬──────────┘                   │
│                                              │                              │
│                                 5. Write     │     5b. Audit Log            │
│                                    ┌─────────▼──────────┐                   │
│                                    │    Config Store      │                   │
│                                    │  (PostgreSQL)        │                   │
│                                    │  6. Emit change log  │                   │
│                                    └─────────┬──────────┘                   │
│                                              │                              │
│                            7. Change event   │                              │
│                              ┌───────────────┼───────────────┐              │
│                              ▼               ▼               ▼              │
│                     ┌──────────────┐ ┌──────────────┐ ┌──────────────┐      │
│                     │  Propagation  │ │  Propagation  │ │  Propagation  │      │
│                     │  Server #1    │ │  Server #2    │ │  Server #3    │      │
│                     └──────┬───────┘ └──────┬───────┘ └──────┬───────┘      │
│                            │               │               │              │
│                   8. gRPC stream push      │               │              │
│                     ┌──────┼─────────┬─────┼────────┬──────┼─────┐        │
│                     ▼      ▼         ▼     ▼        ▼      ▼     ▼        │
│                  ┌─────┐┌─────┐  ┌─────┐┌─────┐  ┌─────┐┌─────┐          │
│                  │ SDK ││ SDK │  │ SDK ││ SDK │  │ SDK ││ SDK │          │
│                  │  A  ││  B  │  │  C  ││  D  │  │  E  ││  F  │          │
│                  └──┬──┘└──┬──┘  └──┬──┘└──┬──┘  └──┬──┘└──┬──┘          │
│                     │      │        │      │        │      │              │
│                  ┌──▼──┐┌──▼──┐  ┌──▼──┐┌──▼──┐  ┌──▼──┐┌──▼──┐          │
│                  │ Svc ││ Svc │  │ Svc ││ Svc │  │ Svc ││ Svc │          │
│                  │  A  ││  B  │  │  C  ││  D  │  │  E  ││  F  │          │
│                  └─────┘└─────┘  └─────┘└─────┘  └─────┘└─────┘          │
│                                                                             │
│              9. Service A: config.get("timeout") → 1000 (new value!)        │
│                                                                             │
│   Total time: ~3 seconds from step 1 to step 9                              │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Diagram 2: Data Flow — Secret Access Detail

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                SECRET ACCESS: ENVELOPE ENCRYPTION FLOW                       │
│                                                                             │
│   TEACH: How secrets are encrypted, stored, and decrypted without           │
│          exposing the master key or the plaintext secret at rest             │
│                                                                             │
│   WRITE (secret creation/rotation):                                         │
│                                                                             │
│   Admin ─── plaintext secret ───▶ Secrets Engine                            │
│                                     │                                        │
│                                     │ 1. Generate random DEK (256-bit)       │
│                                     │ 2. Encrypt secret with DEK             │
│                                     │    encrypted_value = AES(DEK, secret)  │
│                                     │ 3. Send DEK to KMS for wrapping        │
│                                     │                                        │
│                                     ▼                                        │
│                                   ┌─────┐                                    │
│                                   │ KMS │                                    │
│                                   └──┬──┘                                    │
│                                      │ 4. Encrypt DEK with master key        │
│                                      │    encrypted_dek = KMS(master, DEK)   │
│                                      ▼                                       │
│                                   Secrets Engine                             │
│                                     │                                        │
│                                     │ 5. Store both in Config Store:         │
│                                     │    {encrypted_dek, encrypted_value}    │
│                                     │                                        │
│                                     │ 6. DISCARD plaintext DEK from memory   │
│                                     │    DISCARD plaintext secret from memory│
│                                     ▼                                        │
│                                ┌───────────┐                                 │
│                                │Config Store│  (only encrypted data at rest) │
│                                └───────────┘                                 │
│                                                                             │
│   READ (service accesses secret):                                           │
│                                                                             │
│   Service ─── "I need db_password" ───▶ Sidecar                             │
│                                           │                                  │
│                                           │ 1. Check cache → Miss            │
│                                           │ 2. Authenticate with mTLS        │
│                                           ▼                                  │
│                                        Secrets Engine                        │
│                                           │                                  │
│                                           │ 3. Verify service identity       │
│                                           │ 4. Check access policy           │
│                                           │ 5. Fetch {encrypted_dek,         │
│                                           │          encrypted_value}        │
│                                           │ 6. Check DEK cache               │
│                                           │    → Hit? Skip step 7            │
│                                           │    → Miss? Step 7                │
│                                           ▼                                  │
│                                         ┌─────┐                              │
│                                         │ KMS │                              │
│                                         └──┬──┘                              │
│                                            │ 7. Decrypt DEK                  │
│                                            ▼                                 │
│                                        Secrets Engine                        │
│                                           │                                  │
│                                           │ 8. Decrypt secret with DEK       │
│                                           │ 9. Cache DEK (not secret)        │
│                                           │ 10. Return plaintext + lease     │
│                                           ▼                                  │
│                                        Sidecar                               │
│                                           │                                  │
│                                           │ 11. Cache in secure memory       │
│                                           │ 12. Return to service            │
│                                           ▼                                  │
│                                        Service (uses secret, forgets it)     │
│                                                                             │
│   SECURITY PROPERTIES:                                                       │
│   ✓ Master key never leaves KMS/HSM hardware                                │
│   ✓ Plaintext secret never written to persistent storage                    │
│   ✓ DEK cached to minimize KMS calls (performance)                          │
│   ✓ Secret cached in sidecar memory only (mlock'd, no swap)                │
│   ✓ Every access logged in audit trail                                      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Diagram 3: Failure Propagation — Bad Config Push

```
┌─────────────────────────────────────────────────────────────────────────────┐
│           FAILURE PROPAGATION: BAD CONFIG PUSH AND RECOVERY                  │
│                                                                             │
│   TEACH: How a bad config change propagates, is detected,                   │
│          and is automatically rolled back                                    │
│                                                                             │
│   ┌──────────────────────────────────────────────────────────────────────┐  │
│   │  T+0s: Engineer sets timeout_ms = 5 (typo, meant 5000)              │  │
│   │                                                                      │  │
│   │  LAYER 1 — SCHEMA VALIDATION (prevention):                           │  │
│   │  ┌────────────────────────────────────────────────────────────────┐  │  │
│   │  │  Schema: min=100, max=30000                                    │  │  │
│   │  │  Value 5 < 100 → REJECTED ❌                                   │  │  │
│   │  │  Response: "Value 5 is below minimum 100 for timeout_ms"       │  │  │
│   │  │  INCIDENT PREVENTED. No further propagation.                   │  │  │
│   │  └────────────────────────────────────────────────────────────────┘  │  │
│   └──────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│   ┌──────────────────────────────────────────────────────────────────────┐  │
│   │  T+0s: Engineer sets timeout_ms = 150 (valid but dangerously low)   │  │
│   │                                                                      │  │
│   │  LAYER 1 — SCHEMA: Value 150 ≥ 100 → PASSES ✓ (but danger zone)   │  │
│   │  → Warning: "Value in danger zone, canary rollout required"         │  │
│   │                                                                      │  │
│   │  LAYER 2 — CANARY ROLLOUT:                                           │  │
│   │  ┌────────────────────────────────────────────────────────────────┐  │  │
│   │  │  T+0s: Applied to 1% of instances (50 out of 5,000)           │  │  │
│   │  │  T+30s: Monitoring error rate on canary instances              │  │  │
│   │  │  T+45s: Error rate canary: 12% vs control: 0.1%               │  │  │
│   │  │  T+46s: ERROR RATE THRESHOLD EXCEEDED (12% > 0.1% × 1.5)     │  │  │
│   │  │                                                                │  │  │
│   │  │  LAYER 3 — AUTOMATIC ROLLBACK:                                 │  │  │
│   │  │  T+47s: Revert to previous value (timeout_ms = 500)           │  │  │
│   │  │  T+50s: Rollback propagated to canary instances                │  │  │
│   │  │  T+55s: Error rate returns to normal                           │  │  │
│   │  │                                                                │  │  │
│   │  │  BLAST RADIUS: 1% of instances for 46 seconds                  │  │  │
│   │  │  IMPACT: ~0.12% of total traffic experienced errors            │  │  │
│   │  │                                                                │  │  │
│   │  │  WITHOUT CANARY: 100% of instances for however long until      │  │  │
│   │  │  human detects and rolls back (~5-15 minutes)                  │  │  │
│   │  └────────────────────────────────────────────────────────────────┘  │  │
│   └──────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│   DEFENSE IN DEPTH:                                                         │
│   Layer 1: Schema validation → Catches obviously bad values                 │
│   Layer 2: Canary rollout → Catches subtly bad values                       │
│   Layer 3: Auto-rollback → Limits blast radius to canary                    │
│   Layer 4: Manual rollback → Human decision for complex cases               │
│   Layer 5: Local fallback → Service survives even total config failure      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Diagram 4: Evolution Over Time

```
┌─────────────────────────────────────────────────────────────────────────────┐
│              CONFIG SYSTEM: EVOLUTION FROM V1 TO V3                          │
│                                                                             │
│   TEACH: How the system evolves as scale and requirements grow              │
│                                                                             │
│   V1: STARTUP (100 services, 1K instances)                                  │
│   ┌─────────────────────────────────────────────────────┐                   │
│   │  YAML in Git → CI/CD → Container image              │                   │
│   │  Secrets in environment variables                    │                   │
│   │  Feature flags: if/else in code                      │                   │
│   │                                                     │                   │
│   │  ✓ Simple, no infrastructure                        │                   │
│   │  ✗ 30-minute change latency                         │                   │
│   │  ✗ No rollback, no targeting                        │                   │
│   │  ✗ Secrets in plaintext                             │                   │
│   └───────────────────────┬─────────────────────────────┘                   │
│                           │                                                  │
│                    INCIDENT: "Need to change timeout NOW,                    │
│                     not in 30 minutes during outage"                         │
│                           │                                                  │
│                           ▼                                                  │
│   V2: MID-SCALE (1K services, 50K instances)                                │
│   ┌─────────────────────────────────────────────────────┐                   │
│   │  Central config API + etcd/Consul                    │                   │
│   │  Services poll every 30 seconds                      │                   │
│   │  Feature flag service with targeting                 │                   │
│   │  Vault for secrets                                   │                   │
│   │                                                     │                   │
│   │  ✓ Dynamic config, 30-second propagation            │                   │
│   │  ✓ Secret encryption and rotation                   │                   │
│   │  ✗ Polling is wasteful and slow                     │                   │
│   │  ✗ Flag eval is a network call (adds latency)       │                   │
│   │  ✗ No schema validation (config poisoning risk)     │                   │
│   └───────────────────────┬─────────────────────────────┘                   │
│                           │                                                  │
│                    INCIDENT: "Config server overloaded,                      │
│                     flag eval adding 5ms to every request"                   │
│                           │                                                  │
│                           ▼                                                  │
│   V3: SCALE (10K services, 500K instances)                                  │
│   ┌─────────────────────────────────────────────────────┐                   │
│   │  Config store (PostgreSQL) + streaming propagation   │                   │
│   │  In-process SDK for local evaluation (no network)    │                   │
│   │  Envelope encryption with KMS for secrets            │                   │
│   │  Schema validation + canary rollout + auto-rollback  │                   │
│   │  Multi-region with per-region propagation            │                   │
│   │                                                     │                   │
│   │  ✓ < 5s propagation, < 1µs reads                   │                   │
│   │  ✓ Config server NOT on hot path                    │                   │
│   │  ✓ Defense-in-depth against bad config              │                   │
│   │  ✓ Scalable to millions of instances                │                   │
│   └─────────────────────────────────────────────────────┘                   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Part 18: Brainstorming, Exercises & Redesigns

## "What If X Changes?" Questions

```
Q1: What if config changes must be approved by TWO people before taking effect?
  Impact: Write path adds approval workflow
  Changes needed:
  - Config change creates a "pending" entry
  - Two distinct approvers must approve before propagation
  - If not approved within 24 hours, auto-rejected
  - Emergency bypass requires on-call escalation
  - Staff insight: Two-person approval for production is standard at Google.
    Build the approval workflow from day 1 for critical namespaces.

Q2: What if propagation latency must be < 500ms (instead of 5 seconds)?
  Impact: Cannot use standard gRPC streaming (too slow for some topologies)
  Changes needed:
  - Direct push via pre-established websocket connections
  - Propagation servers must be co-located with clients (same rack/AZ)
  - Hierarchical propagation with dedicated priority channel
  - Trade-off: Higher infrastructure cost, more complex routing
  - Staff assessment: Needed for kill switches, overkill for normal config.
    Implement dual-channel: Priority (<500ms) for kill switches, standard
    (<5s) for everything else.

Q3: What if feature flags need to support complex boolean logic?
  "Enable if (country=US AND tier=premium) OR (employee=true AND experiment=enrolled)"
  Impact: Targeting rule engine becomes much more complex
  Changes needed:
  - Full boolean expression evaluation (AND, OR, NOT)
  - Nested conditions
  - Decision tree compilation for performance
  - Rule validation (detect contradictions, dead rules)
  - Staff insight: Keep rules simple. Complex rules are unmaintainable.
    If a flag needs complex logic, it's probably multiple flags.

Q4: What if we need to support config rollback to any historical version (not just previous)?
  Impact: Need full version history with point-in-time snapshot capability
  Changes needed:
  - Retain all versions indefinitely (or configurable retention)
  - Rollback API: rollback(namespace, key, target_version)
  - Show diff between any two versions
  - Staff assessment: Store full history for 90 days, metadata-only after.
    Rolling back to 90+ day old config is almost certainly wrong.

Q5: What if 50% of your config changes are automated (not human-initiated)?
  Impact: Rate limiting, approval workflows, and blast radius controls
  must accommodate automated changes
  Changes needed:
  - Service accounts for automated systems with specific permissions
  - Automated changes exempt from human approval (but require pre-registration)
  - Rate limits: Higher for registered automation, lower for unregistered
  - All automated changes must reference a CI/CD pipeline ID (traceability)
```

## Redesign Under New Constraints

```
CONSTRAINT REDESIGN 1: Config system must work in air-gapped environment
  (no cloud services, no internet)
  
  Changes:
  - Self-hosted KMS (SoftHSM or dedicated hardware HSM)
  - Config store: PostgreSQL on-premises
  - Propagation: Internal network only
  - No cloud SDK dependencies
  - Manual secret rotation (no automated external rotation)
  
  Trade-offs:
  - Operational burden increases 3×
  - No managed HSM (must manage hardware)
  - When it makes sense: Military, government, financial trading floors

CONSTRAINT REDESIGN 2: Config system for edge/IoT devices
  (100,000 devices with intermittent connectivity)
  
  Changes:
  - Devices cache config for days (not hours)
  - Sync when online via HTTP polling (no persistent connections)
  - Config signed for offline verification
  - Very conservative default values (device must work fully offline)
  - Gradual rollout by device cohort (not percentage)
  
  Trade-offs:
  - Propagation latency: Hours to days
  - No kill switch capability (devices may be offline)
  - Secret rotation requires device-by-device verification

CONSTRAINT REDESIGN 3: Config system with $100/month budget
  (Startup with 50 services, 500 instances)
  
  - etcd for config store (free, small scale)
  - Single propagation server (handles 500 connections easily)
  - SDK with polling (30-second interval, acceptable at this scale)
  - AWS Secrets Manager for secrets ($0.40/secret/month = $20/month)
  - No HSM (not needed until compliance requires it)
  - Total: ~$100/month
  
  This is the RIGHT design for this scale. Don't build a platform.
```

## Failure Injection Exercises

```
EXERCISE 1: Config Store is unreachable for 2 hours
  Question: What happens to all services?
  Expected answer: Nothing visible—all services use cached config.
  Follow-up: What happens if a new service tries to start?
  Expected answer: Starts with compiled-in defaults or disk cache.
  Follow-up: What if an engineer needs to change config during this?
  Expected answer: Cannot—must use emergency local override (SSH or K8s env var).

EXERCISE 2: Propagation server pushes wrong version
  (Bug: Sends version 40 data labeled as version 42)
  Question: How do clients detect this?
  Expected answer: Content hash verification. Client computes hash of received
  data and compares to expected hash for the version. Mismatch → Reject, re-fetch.
  Follow-up: What if the client doesn't have hash verification?
  Expected answer: Clients may accept wrong data → Potential inconsistency.
  This is why content hashing is non-negotiable in the protocol.

EXERCISE 3: Secret rotation leaves one service on old version
  (Pod is stuck, never fetched new secret)
  Question: What happens when old secret is revoked?
  Expected answer: That service loses DB connectivity.
  Follow-up: How should the rotation workflow handle this?
  Expected answer: Verification step checks ALL consumers before revoking.
  If any consumer hasn't rotated, block revocation and alert.

EXERCISE 4: Cascading config change
  Service A changes its timeout, which causes service B to time out,
  which causes service C to return errors.
  Question: How do you diagnose this?
  Expected answer: Config change audit log correlated with error rate metrics.
  "What config changed in the last 10 minutes?" → "Service A timeout changed"
  → "Service B depends on A" → Root cause identified.
  Follow-up: How do you prevent this?
  Expected answer: Config change metadata includes dependency mapping.
  Dashboard shows: "Changing this value affects services B, C, D."
```

## Trade-Off Debates

```
DEBATE 1: Push vs pull for config propagation

  Push advocates:
  "Low latency (< 5 seconds). No wasted polling.
  Server controls the pace. Perfect for kill switches."
  
  Pull advocates:
  "Simpler. Clients control the pace. No persistent connections.
  Works through all proxies. No connection scaling problem."
  
  Resolution: Push for most scenarios (streaming + delta sync).
  Pull only for environments where push is impossible (edge devices, firewalls).

DEBATE 2: In-process SDK vs sidecar for config/flag evaluation

  SDK advocates:
  "Sub-microsecond reads. No IPC overhead. No sidecar to manage.
  No additional failure mode (sidecar crash doesn't affect service)."
  
  Sidecar advocates:
  "Language-independent. Single implementation for all services.
  Can be updated without service redeploy. Better secret isolation."
  
  Resolution: SDK for config/flags (performance critical, < 1µs matters).
  Sidecar for secrets (security isolation more important than speed).

DEBATE 3: Optimistic vs pessimistic concurrency for config writes

  Optimistic:
  "Config writes are rare. Conflicts are extremely unlikely.
  Don't add locking overhead for the 99.99% case."
  
  Pessimistic:
  "Config changes are critical. A lost update could cause an outage.
  The lock overhead is milliseconds—trivial for a write path."
  
  Resolution: Optimistic. Config writes are rare (~3/second), and conflicts
  are rarer still. Version-based conflict detection is sufficient.

DEBATE 4: Single config system vs separate systems for config/flags/secrets

  Single system:
  "Unified propagation, unified audit, unified access control.
  One system to maintain, one system to monitor."
  
  Separate systems:
  "Different requirements for each domain. Secrets need special encryption.
  Flags need targeting engine. Config is simple key-value."
  
  Resolution: Unified control plane (API, propagation, audit).
  Differentiated data plane (secret encryption is separate from config storage).
  Flag evaluation engine is in the SDK (not a separate service).

DEBATE 5: Config change safety: Human-enforced vs system-enforced

  Human-enforced:
  "Process and culture. PR reviews, runbooks, training.
  Engineers know their systems best."
  
  System-enforced:
  "Schemas, canary rollout, auto-rollback. Humans make mistakes.
  Systems don't forget the safety check."
  
  Resolution: System-enforced always. Human judgment on top.
  The system prevents obvious mistakes (schema validation).
  Humans make nuanced decisions (is this the right change?).
  Never rely solely on humans for safety—they're tired at 3 AM.
```

## Additional Brainstorming Questions

```
Q6: What if you need to support per-request config overrides for testing?
  "In this request, evaluate flag X as true (regardless of targeting)"
  Impact: Testing in production without changing config for everyone
  Changes needed:
  - Request context includes "overrides" map
  - SDK checks overrides before normal evaluation
  - Overrides ONLY accepted from internal testing headers
  - Override traffic EXCLUDED from A/B test analysis
  - Staff insight: Essential for testing. But NEVER allow overrides
    from external traffic. Validate the override source cryptographically.

Q7: What if config must be compliant with audit frameworks (SOC2, ISO 27001)?
  Impact: Strict audit requirements
  Changes needed:
  - Immutable audit log (no deletion, no modification)
  - Audit log includes: who, what, when, why, from where (IP, device)
  - Access reviews: Quarterly review of who has access to what
  - Separation of duties: Person who writes config ≠ person who approves
  - Evidence generation: Automated reports for compliance auditors
  - Staff insight: Build compliance into the system from day 1.
    Retroactively adding audit trails is 10× harder.

Q8: What if the config system must support 100 different programming languages?
  Impact: SDK maintenance burden
  Changes needed:
  - Sidecar model becomes more attractive (one sidecar, any language)
  - Or: gRPC-based protocol (gRPC has codegen for many languages)
  - Or: OpenFeature standard (emerging open standard for flag evaluation)
  - Staff insight: Standardize the PROTOCOL, not the SDK.
    Provide 3-5 SDKs for major languages, sidecar for the rest.

Q9: What if you need to A/B test config VALUES (not just flags)?
  "Test timeout=500ms vs timeout=750ms and measure latency impact"
  Impact: Config values become experiment variants
  Changes needed:
  - Config values can have variant definitions (like flags)
  - Consistent user bucketing for config values
  - Metrics correlation: "Which variant was this request in?"
  - Staff assessment: Valuable but complex. Limit to specific keys.
    Most config values don't need A/B testing.

Q10: What if the system must support real-time config VALIDATION against live traffic?
  "Before rolling out timeout=150ms, simulate what would have happened
  if the last hour of traffic had used that value"
  Impact: Config "shadow mode" or "dry run"
  Changes needed:
  - Shadow evaluation: Evaluate both old and new config, log both results
  - Replay capability: Re-process recent traffic with proposed config
  - Comparison dashboard: Side-by-side metrics for old vs. proposed
  - Staff assessment: Extremely valuable for critical paths (payment
    timeouts, rate limits). Overkill for non-critical config.
```

## Additional Full Design Exercises

```
FULL DESIGN EXERCISE 1: CONFIG-DRIVEN CIRCUIT BREAKER
────────────────────────────────────────────────────────
Requirement: Circuit breaker thresholds (error rate threshold, cooldown period,
half-open trial count) are managed via the config system.

Design considerations:
• Config change must take effect within 5 seconds (during active incident)
• Circuit breaker state is LOCAL to each instance (not shared)
• Config defines the RULES, not the STATE
• Multiple services share circuit breaker config templates
• Override per-service for specific dependencies

This exercise tests:
• Understanding the difference between config (rules) and state (open/closed)
• Propagation latency requirements for operational controls
• Template/inheritance in config namespaces

FULL DESIGN EXERCISE 2: MULTI-CLOUD CONFIG FEDERATION
────────────────────────────────────────────────────────
Requirement: Services run across AWS, GCP, and on-premises.
Each environment has its own secrets infrastructure (AWS KMS, GCP KMS, on-prem HSM).
Config and flags must be consistent across all environments.

Design considerations:
• Secrets are environment-specific (AWS credentials ≠ GCP credentials)
• Config values may differ per cloud (different instance types, endpoints)
• Propagation must work across cloud boundaries
• Single source of truth for flag definitions
• Cloud-specific SDK variants

This exercise tests:
• Multi-environment config architecture
• Cross-cloud secret management
• Consistent propagation across network boundaries

FULL DESIGN EXERCISE 3: CONFIG SYSTEM MIGRATION
────────────────────────────────────────────────────────
Requirement: Migrate 500 services from LaunchDarkly (flags) + Consul (config)
+ Vault (secrets) to the unified system described in this chapter.
Without downtime. Without losing config history.

Design considerations:
• Dual-read period: Services read from both old and new system
• Config value parity: Verify old and new systems return same values
• Flag evaluation parity: Same targeting rules produce same results
• Secret migration: Re-encrypt secrets under new KMS
• Cutover strategy: Per-service? Per-region? Big-bang?
• Rollback plan: If new system has issues, revert to old

This exercise tests:
• Migration planning (the hardest problem in platform engineering)
• Risk management under uncertainty
• Organizational coordination across 500 teams
```

## Additional Trade-Off Debates

```
DEBATE 6: Flag evaluation: Server-side vs client-side rendering

  Server-side: "Flag evaluated on the server, result sent to client.
  Client never knows the flag exists or its rules."
  
  Client-side: "Flag rules sent to client SDK, evaluated locally.
  Faster for client-side features, but rules exposed to client."
  
  Resolution: Server-side for security-sensitive flags (pricing, access control).
  Client-side for UI flags (dark mode, new design) where speed matters.
  Never send targeting rules to untrusted clients for sensitive flags.

DEBATE 7: Config change notifications: Best-effort vs guaranteed delivery

  Best-effort: "Push change, if client misses it, they'll get it on next sync.
  Simpler, no acknowledgment tracking."
  
  Guaranteed: "Track which clients received which version.
  Retry until all clients acknowledge. Know exact propagation status."
  
  Resolution: Best-effort for config/flags (client catches up on periodic sync).
  Guaranteed delivery for secret rotation (must know all clients rotated before
  revoking old secret). The guarantee is only needed where safety depends on it.

DEBATE 8: Config system availability: Active-active vs active-passive

  Active-active: "Both regions accept writes. Complex conflict resolution.
  Higher availability."
  
  Active-passive: "One primary for writes. Simple. Failover takes minutes."
  
  Resolution: Active-passive. Config writes are rare (~3/second).
  The complexity of active-active conflict resolution for config values
  is not justified by the marginal availability improvement.
  If the primary is down for 10 minutes, config changes wait 10 minutes.
  Services are completely unaffected (local cache).
```

---

# Summary

Configuration, feature flags, and secrets management form the runtime control plane of every production system. The core challenge isn't storing key-value pairs—it's safely propagating changes to hundreds of thousands of servers in seconds, evaluating flags without adding latency to user requests, and protecting secrets through their entire lifecycle.

**Key Staff-Level Insights:**

1. **Config changes are the #1 cause of production outages.** More incidents come from config pushes than code deploys. Schema validation, canary rollout, and automatic rollback are non-negotiable safety rails.

2. **Config reads must be local.** Any network involvement in config or flag evaluation on the request hot path is architecturally wrong. In-process evaluation with background streaming sync is the only viable pattern at scale.

3. **Secrets are not config.** They share propagation mechanisms but require separate encryption, access control, rotation workflows, and audit trails. Envelope encryption with KMS eliminates the key management bootstrap problem.

4. **The config system's failure mode is "frozen," never "unavailable."** Services continue with cached config when the config system is down. The multi-layer fallback chain (in-memory → disk → compiled defaults) ensures config reads never fail.

5. **Feature flags are rental, not purchase.** Every flag has a lifecycle: create, target, roll out, clean up. Stale flags are tech debt that compounds. Enforce cleanup with automated expiry and archival.

6. **Propagation speed is the enemy of safety.** The faster you can propagate config, the faster a bad config can destroy production. Always pair fast propagation with gradual rollout and blast radius control.

**The Staff Engineer Difference:**

An L5 might design a working key-value config store with an API. An L6 designs a config platform that validates changes before propagation, rolls them out gradually with automatic rollback, evaluates flags in sub-microsecond time without network calls, rotates secrets without downtime, and degrades to "frozen config" instead of "no config" when the control plane fails. The difference is understanding that the configuration system isn't just a database—it's the most powerful and most dangerous mutation surface in production.

---

### Topic Coverage in Exercises:

| Topic | Questions/Exercises |
|-------|---------------------|
| **Config Safety** | Q1, Q2, Exercise 1, Debate 5 |
| **Feature Flags** | Q3, Q6, Exercise 1, Debate 1, Debate 6 |
| **Secrets** | Q8, Exercise 3, Debate 7 |
| **Propagation** | Q2, Debate 1, Exercise 2 |
| **Scale** | Q5, Redesign 2, Debate 2 |
| **Cost** | Redesign 3, Debate 4 |
| **Compliance** | Q4, Q7, Exercise 3 |
| **Multi-Environment** | Redesign 1, Exercise 2 |
| **Full Trade-Off Debates** | Debates 1-8 |

### Remaining Considerations (Not Gaps):

1. **GitOps integration** is referenced but not deeply covered (separate deployment concern)
2. **Service mesh integration** (Istio/Envoy config) is a specialization of this system
3. **ML model config** (model versions, hyperparameters) uses this system but has unique lifecycle
4. **Database migration config** is deploy-time, not runtime (out of scope)

These are intentional scope boundaries, not gaps. Each could be a separate chapter.

### Pseudo-Code Convention:

All code examples in this chapter use language-agnostic pseudo-code:
- `FUNCTION` keyword for function definitions
- `IF/ELSE/FOR/WHILE` for control flow
- Descriptive variable names in snake_case
- No language-specific syntax (no `def`, `public void`, `func`, etc.)
- Comments explain intent, not syntax

### How to Use This Chapter in Interview:

1. Start with the "L5 vs L6 Decisions" table to frame your approach
2. Lead with config change safety as the primary design constraint—this signals Staff-level awareness
3. Immediately state that config/flag reads must be local (no network)—this separates L5 from L6
4. Discuss the deploy vs. release distinction when feature flags come up
5. For secrets: Explain envelope encryption and why it reduces KMS calls by 5000×
6. Use the failure timeline to demonstrate operational maturity
7. Reference the flag lifecycle to show you think about maintenance, not just features
8. Practice the brainstorming questions to anticipate follow-ups

---
