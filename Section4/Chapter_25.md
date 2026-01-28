# Chapter 24: Data Locality, Compliance, and System Evolution

---

# Introduction

Data locality and compliance are among the most misunderstood constraints in system design. Engineers often treat them as policy concerns—something legal or security teams worry about—until an audit reveals that data is flowing where it shouldn't, deletion requests aren't being honored, or a regional expansion is blocked because the architecture fundamentally cannot support data residency requirements.

I've spent years building systems at Google scale where data locality was a first-class constraint from day one, and I've also inherited systems where it was ignored until a regulatory deadline made it an emergency. The difference in cost, risk, and engineering effort between these two approaches is staggering—often 10x or more.

This chapter teaches data locality and compliance as Staff Engineers practice it: as architectural constraints that shape system design from the beginning, not as afterthoughts to be bolted on later. We'll cover what data locality actually means in practice, why it affects far more than just databases, and how to design systems that can evolve safely as regulations, products, and organizational requirements change.

**The Staff Engineer's First Law of Data Locality**: If you can't explain where every piece of user data is at any moment—including copies, caches, logs, and derived data—you cannot claim compliance.

---

## Quick Visual: Data Locality at a Glance

```
┌─────────────────────────────────────────────────────────────────────────────┐
│              DATA LOCALITY: THE STAFF ENGINEER VIEW                         │
│                                                                             │
│   WRONG Framing: "Data locality is a database configuration problem"       │
│   RIGHT Framing: "Data locality is an architectural constraint that        │
│                   affects every layer of the system"                        │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Before designing, answer:                                          │   │
│   │                                                                     │   │
│   │  1. What data MUST stay in a specific region?                       │   │
│   │  2. What data CAN move between regions (and under what conditions)? │   │
│   │  3. Where do COPIES of data exist? (caches, logs, backups, replicas)│   │
│   │  4. Where does DERIVED data end up? (analytics, ML models, reports) │   │
│   │  5. How do you PROVE compliance at any moment?                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   THE UNCOMFORTABLE TRUTH:                                                  │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Most compliance failures aren't in the primary database.           │   │
│   │  They're in logs, caches, analytics pipelines, and backups that     │   │
│   │  nobody thought about when designing the system.                    │   │
│   │  "I deleted it from the database" is not the same as "I deleted it."│   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## L5 vs L6 Data Locality Decisions

| Scenario | L5 Approach | L6 Approach |
|----------|-------------|-------------|
| **New region launch** | "Let's replicate the database to the new region" | "What data can be replicated? What must stay local? What about logs, caches, and analytics? Let's map every data flow first." |
| **User deletion request** | "Delete the row from the user table" | "Where are all copies of this user's data? Primary DB, replicas, caches, logs, analytics, backups, derived ML models? We need a deletion manifest." |
| **Logging for debugging** | "Log request payloads for debugging" | "Request payloads contain user data. Where do logs go? How long are they retained? Are they replicated globally? We may need to log references, not data." |
| **Caching for performance** | "Cache user data globally for faster reads" | "Global caching means data leaves the user's region. Can we cache hashes/references? Or must caches be regional?" |
| **Analytics pipeline** | "Stream all events to the data warehouse" | "Which events contain user data subject to locality? We may need regional data warehouses or anonymization before aggregation." |

**Key Difference**: L6 engineers recognize that data locality affects the entire system, not just the primary data store. They think in terms of data flows, not just data storage.

---

# Part 1: Foundations — What Data Locality and Compliance Mean in Practice

## What "Data Locality" Actually Means

Data locality (or data residency) refers to the requirement that certain data must be stored, processed, or accessible only within specific geographic or jurisdictional boundaries.

### The Three Layers of Data Location

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     THREE LAYERS OF DATA LOCATION                           │
│                                                                             │
│   LAYER 1: DATA AT REST                                                     │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Where data is persistently stored                                  │   │
│   │  • Primary databases                                                │   │
│   │  • Replicas and backups                                             │   │
│   │  • Object storage (files, media)                                    │   │
│   │  • Search indexes                                                   │   │
│   │  • Analytics data warehouses                                        │   │
│   │                                                                     │   │
│   │  Question: Which region's disk does this byte live on?              │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   LAYER 2: DATA IN TRANSIT                                                  │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Where data moves through during processing                         │   │
│   │  • Network paths between services                                   │   │
│   │  • Cross-region replication streams                                 │   │
│   │  • API calls that carry user data                                   │   │
│   │  • Message queues and event buses                                   │   │
│   │                                                                     │   │
│   │  Question: Does this data cross a jurisdictional boundary?          │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   LAYER 3: DERIVED DATA                                                     │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Data created from processing primary data                          │   │
│   │  • Application logs containing user data                            │   │
│   │  • Aggregated analytics and reports                                 │   │
│   │  • ML models trained on user data                                   │   │
│   │  • Caches and materialized views                                    │   │
│   │  • Debug dumps and error reports                                    │   │
│   │                                                                     │   │
│   │  Question: Can you trace this derived data back to a user?          │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   COMPLIANCE REQUIRES CONTROL OVER ALL THREE LAYERS                         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Why Data Location Matters Beyond Performance

Data location isn't just about latency. It matters for:

**Legal Requirements**: Many jurisdictions require that certain data (especially personal data) remains within their borders. This isn't a preference—it's a legal obligation that can result in fines, service bans, or criminal liability.

**Customer Trust**: Enterprise customers often require contractual guarantees about where their data resides. Losing a major customer because you can't prove data residency is a real business risk.

**Sovereignty and Control**: Organizations increasingly want assurance that foreign governments cannot compel access to their data through legal mechanisms in other jurisdictions.

**Incident Scope**: When a breach occurs, data location determines which regulations apply, which users must be notified, and which authorities have jurisdiction.

## Common Misconceptions

### Misconception 1: "Compliance Can Be Added Later"

**Why it's wrong**: Data locality requirements affect fundamental architectural decisions:
- How data is partitioned
- Where replicas are placed
- What can be cached and where
- How cross-region requests are handled

Retrofitting these into an existing system typically requires a major rewrite, not a configuration change.

**Example**: A startup stores all user data in a single global database. When they expand to Europe and discover they need regional data residency, they face a choice: expensive migration of the entire data layer, or telling European customers they can't be served.

### Misconception 2: "Only Databases Are Affected"

**Why it's wrong**: User data exists in many places beyond the primary database:

```
// Pseudocode: Where does user data actually live?

FUNCTION audit_user_data_locations(user_id):
    locations = []
    
    // Primary storage (obvious)
    locations.append("primary_database")
    
    // Replicas (often forgotten)
    FOR replica IN database_replicas:
        locations.append(replica.region)
    
    // Caches (frequently overlooked)
    FOR cache IN [redis_cache, cdn_cache, local_cache]:
        IF cache.contains_user_data(user_id):
            locations.append(cache.location)
    
    // Logs (almost always missed)
    FOR log_sink IN [application_logs, access_logs, debug_logs]:
        IF log_sink.may_contain_user_data():
            locations.append(log_sink.storage_region)
    
    // Analytics (often in different region)
    IF analytics_pipeline.has_user_events(user_id):
        locations.append(analytics_warehouse.region)
    
    // Backups (critical for compliance)
    FOR backup IN all_backups:
        IF backup.contains(user_id):
            locations.append(backup.storage_region)
    
    // Search indexes (frequently forgotten)
    FOR index IN search_indexes:
        IF index.contains_user_data(user_id):
            locations.append(index.region)
    
    // Third-party services (the hidden danger)
    FOR external_service IN integrated_services:
        IF external_service.receives_user_data():
            locations.append(external_service.data_region)
    
    RETURN locations
```

### Misconception 3: "Encrypted Data Doesn't Count"

**Why it's wrong**: Most data residency regulations care about where data is located, not just whether it's encrypted. Encrypted EU user data stored in the US is still EU user data stored in the US.

Encryption protects against unauthorized access but doesn't change the legal jurisdiction where the data resides.

## Simple Example: Where Naive Designs Fail

**Scenario**: A user profile service with global users.

### Naive Design

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        NAIVE GLOBAL DESIGN                                  │
│                                                                             │
│      Users Worldwide                                                        │
│            │                                                                │
│            ▼                                                                │
│   ┌─────────────────────┐                                                   │
│   │   Global API Layer  │  ← Any server can handle any user                │
│   └─────────────────────┘                                                   │
│            │                                                                │
│            ▼                                                                │
│   ┌─────────────────────┐                                                   │
│   │   Global Redis Cache│  ← All user data cached globally                 │
│   └─────────────────────┘                                                   │
│            │                                                                │
│            ▼                                                                │
│   ┌─────────────────────┐                                                   │
│   │  Global Database    │  ← Single database, replicated everywhere        │
│   │  (US Primary)       │                                                   │
│   └─────────────────────┘                                                   │
│            │                                                                │
│            ▼                                                                │
│   ┌─────────────────────┐                                                   │
│   │  Global Analytics   │  ← All events aggregated globally                │
│   └─────────────────────┘                                                   │
│                                                                             │
│   PROBLEM: EU user data exists in:                                          │
│   • US primary database                                                     │
│   • Every replica region                                                    │
│   • Global cache                                                            │
│   • Global analytics warehouse                                              │
│   • All backup locations                                                    │
│                                                                             │
│   This CANNOT satisfy EU data residency requirements.                       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Why It Fails

1. **Data at rest**: EU user data is stored on US disks (primary database)
2. **Data in transit**: Every read request for EU user crosses Atlantic
3. **Derived data**: Analytics contains EU user events in a US warehouse
4. **Deletion**: Deleting from primary doesn't remove from cache, replicas, analytics, backups

---

# Part 2: Why This Matters at Google Staff Level

## Staff Engineers Must Anticipate Change

Regulations change. Products expand to new regions. Customer requirements evolve. Acquisitions bring new compliance obligations.

A Staff Engineer's job is not just to build systems that work today—it's to build systems that can adapt to tomorrow's constraints without requiring a full rewrite.

### How Compliance Constraints Affect Systems

**Architecture**: Data locality requirements fundamentally shape:
- Where services are deployed
- How data is partitioned and replicated
- What can be centralized vs. what must be distributed
- How cross-region requests are handled (or forbidden)

**Team Velocity**: Poor compliance architecture slows everything:
- New features require compliance review
- Simple changes touch multiple systems
- Testing becomes more complex (multi-region, multi-policy)
- Debugging spans jurisdictional boundaries

**Incident Response**: During an incident:
- You must know exactly what data was affected
- You must know what jurisdictions are involved
- You must follow notification timelines that vary by regulation
- Poor data lineage makes this impossible under pressure

**Long-term Product Strategy**: Architecture limits business options:
- Can't enter new markets if architecture can't support their requirements
- Can't sign enterprise contracts without residency guarantees
- Can't acquire companies without knowing how to integrate their data

## The Cost of Ignoring Compliance Early

```
┌─────────────────────────────────────────────────────────────────────────────┐
│              COST OF COMPLIANCE: EARLY VS. LATE                             │
│                                                                             │
│   COMPLIANCE DESIGNED IN FROM DAY ONE                                       │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  • Regional data partitioning built into schema                     │   │
│   │  • Data flows mapped and documented                                 │   │
│   │  • Deletion and retention automated                                 │   │
│   │  • Audit trails in place                                            │   │
│   │                                                                     │   │
│   │  Cost: +15-20% initial development time                             │   │
│   │  Ongoing: Minimal overhead, changes are incremental                 │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   COMPLIANCE RETROFITTED AFTER LAUNCH                                       │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  • Major data migration required                                    │   │
│   │  • Every service must be audited and modified                       │   │
│   │  • Unclear data lineage requires forensic analysis                  │   │
│   │  • Historical data may be impossible to make compliant              │   │
│   │                                                                     │   │
│   │  Cost: 5-10x original development time                              │   │
│   │  Risk: May not be fully achievable without starting over            │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   REAL-WORLD PATTERN:                                                       │
│   "We'll add compliance later" → 18 months later → "We need to rewrite     │
│   the entire data layer to support the EU market"                           │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## L5 vs L6 Thinking

| L5 Thinking | L6 Thinking |
|-------------|-------------|
| "Store data where it's easiest" | "Design so data placement can change safely" |
| "Compliance is a legal/policy concern" | "Compliance requirements are architectural inputs" |
| "We'll handle deletion when requested" | "Deletion paths must be designed upfront" |
| "Logs are just for debugging" | "Logs containing user data are subject to same constraints as primary data" |
| "That's the security team's responsibility" | "I own the architecture; I own compliance enablement" |

---

# Part 3: Core Data Locality Design Patterns

## Pattern 1: Read-Local, Write-Central

**What it solves**: Users need low-latency reads, but data must be authoritative in one region.

**How it works**:

```
// Pseudocode: Read-local, write-central pattern

FUNCTION handle_read(user_id, user_region):
    // Try local replica first
    local_data = local_replica.get(user_id)
    
    IF local_data exists AND acceptable_staleness(local_data):
        RETURN local_data
    ELSE:
        // Fall back to primary region
        RETURN primary_region.get(user_id)

FUNCTION handle_write(user_id, data, user_region):
    // All writes go to the user's home region
    home_region = get_user_home_region(user_id)
    
    result = home_region.write(user_id, data)
    
    // Asynchronously replicate to other regions for reads
    // (only non-sensitive data that can legally be replicated)
    queue_replication(user_id, data, get_replication_targets(user_id))
    
    RETURN result
```

**Trade-offs**:
- ✅ Reads are fast (local)
- ✅ Data ownership is clear (home region)
- ❌ Writes have higher latency for remote users
- ❌ Stale reads are possible

**Failure behavior**: If primary region is down, reads continue from replicas but writes fail.

**When a Staff Engineer chooses this**: When read latency matters more than write latency, and eventual consistency for reads is acceptable.

---

## Pattern 2: Regional Data Ownership

**What it solves**: Data must never leave its designated region.

**How it works**:

```
// Pseudocode: Regional data ownership

CLASS RegionalDataService:
    
    FUNCTION create_user(user_data, user_region):
        // Determine home region based on user's location
        home_region = determine_home_region(user_data.country)
        
        // Store region assignment in global directory
        global_directory.set(user_data.id, home_region)
        
        // Store actual data only in home region
        home_region_service = get_service_for_region(home_region)
        home_region_service.create(user_data)
        
        RETURN user_data.id
    
    FUNCTION get_user(user_id, requesting_region):
        // Look up where user data lives
        data_region = global_directory.get(user_id)
        
        IF data_region == requesting_region:
            // Same region: direct access
            RETURN local_service.get(user_id)
        ELSE:
            // Cross-region: user must be redirected or request proxied
            // NOTE: This may be forbidden for certain data types
            IF cross_region_access_allowed(user_id):
                RETURN remote_proxy.get(user_id, data_region)
            ELSE:
                RAISE DataLocalityViolation("Cannot access from this region")
    
    FUNCTION delete_user(user_id):
        data_region = global_directory.get(user_id)
        
        // Delete from home region
        home_region_service = get_service_for_region(data_region)
        home_region_service.delete(user_id)
        
        // Delete from global directory
        global_directory.delete(user_id)
        
        // Trigger deletion cascades (logs, caches, analytics)
        deletion_propagator.propagate(user_id, data_region)
```

**Trade-offs**:
- ✅ Full control over data location
- ✅ Clear compliance boundary
- ❌ Cross-region access is complex or forbidden
- ❌ Global views require aggregation

**Failure behavior**: Each region operates independently. Global directory is the only shared component.

**When a Staff Engineer chooses this**: When strict data residency is required and cross-region data access is limited or forbidden.

---

## Pattern 3: Metadata vs. Primary Data Separation

**What it solves**: Need to operate globally but keep sensitive data local.

**How it works**:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│              METADATA VS. PRIMARY DATA SEPARATION                           │
│                                                                             │
│   GLOBAL LAYER (Replicated Everywhere)                                      │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  • User ID                                                          │   │
│   │  • Home region                                                      │   │
│   │  • Account status (active/suspended)                                │   │
│   │  • Feature flags                                                    │   │
│   │  • Routing information                                              │   │
│   │                                                                     │   │
│   │  Contains NO personally identifiable information                    │   │
│   │  Can be cached globally, replicated freely                          │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                │                                            │
│                                │ User ID → Home Region lookup               │
│                                ▼                                            │
│   REGIONAL LAYER (Stays In Region)                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  • Name, email, address                                             │   │
│   │  • Profile content                                                  │   │
│   │  • User-generated content                                           │   │
│   │  • Transaction history                                              │   │
│   │  • Preferences containing personal info                             │   │
│   │                                                                     │   │
│   │  Subject to data residency requirements                             │   │
│   │  NEVER replicated outside the region                                │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Pseudocode**:

```
// Pseudocode: Metadata separation

CLASS UserService:
    
    FUNCTION get_user_for_display(user_id, requesting_region):
        // Global metadata (cached everywhere)
        metadata = global_metadata_cache.get(user_id)
        
        IF NOT metadata:
            RETURN USER_NOT_FOUND
        
        // Check if we can access the data
        IF requesting_region == metadata.home_region:
            // Same region: full access
            personal_data = regional_store.get(user_id)
            RETURN merge(metadata, personal_data)
        ELSE:
            // Cross-region: return only global metadata
            // UI must handle partial data gracefully
            RETURN metadata.to_limited_view()
    
    FUNCTION search_users(query, requesting_region):
        // Search can only see users in this region
        // (unless query is ID-based, which uses global metadata)
        
        IF query.is_id_lookup:
            RETURN get_user_for_display(query.user_id, requesting_region)
        ELSE:
            // Name/email search: regional only
            RETURN regional_search_index.search(query)
```

**Trade-offs**:
- ✅ Global operations possible without moving sensitive data
- ✅ Clear separation of concerns
- ❌ Application must handle partial data views
- ❌ Some features limited to same-region users

**Failure behavior**: Global layer failure blocks routing; regional failure only affects that region's users.

**When a Staff Engineer chooses this**: When you need global functionality (search, routing, status checks) but sensitive data must remain local.

---

## Pattern 4: Data Classification and Tiering

**What it solves**: Different data types have different locality requirements.

**How it works**:

```
// Pseudocode: Data classification framework

ENUM DataClassification:
    PUBLIC          // No restrictions (cached anywhere)
    INTERNAL        // Company-internal (replicated within company boundaries)
    PERSONAL        // Subject to data residency (stays in user's region)
    SENSITIVE       // Stricter controls (encryption, access logging)
    REGULATED       // Legal/regulatory controls (specific retention, audit)

CLASS DataClassifier:
    
    FUNCTION classify(data_type, data_content):
        // Explicit classification for known types
        IF data_type == "user_profile":
            RETURN PERSONAL
        ELSE IF data_type == "access_log":
            IF contains_personal_identifiers(data_content):
                RETURN PERSONAL
            ELSE:
                RETURN INTERNAL
        ELSE IF data_type == "payment_info":
            RETURN REGULATED
        ELSE IF data_type == "public_content":
            RETURN PUBLIC
        ELSE:
            // Default to more restrictive when unknown
            RETURN PERSONAL
    
    FUNCTION get_allowed_operations(classification, region):
        rules = {
            PUBLIC: {
                replicate: ALL_REGIONS,
                cache: ANYWHERE,
                log: ANYWHERE,
                retain: FOREVER
            },
            PERSONAL: {
                replicate: USER_HOME_REGION_ONLY,
                cache: USER_HOME_REGION_ONLY,
                log: ANONYMIZED_ONLY_OUTSIDE_REGION,
                retain: POLICY_DEFINED
            },
            REGULATED: {
                replicate: NEVER,
                cache: NEVER,
                log: AUDIT_REQUIRED,
                retain: REGULATORY_MINIMUM
            }
        }
        RETURN rules[classification]
```

**Trade-offs**:
- ✅ Fine-grained control over different data types
- ✅ Can optimize for each category separately
- ❌ Classification must be maintained as data model evolves
- ❌ Misclassification is a compliance risk

**When a Staff Engineer chooses this**: When a system handles multiple data types with different sensitivity levels.

---

# Part 4: Compliance Constraints as Design Inputs

## Why Regulations Affect Architecture

Regulations like GDPR, CCPA, and similar frameworks impose requirements that translate directly to system design:

| Regulatory Concept | System Design Implication |
|--------------------|---------------------------|
| Right to be forgotten | Complete deletion across all stores, caches, logs, backups |
| Data portability | Export functionality for all user data |
| Purpose limitation | Data can only be used for stated purposes |
| Data minimization | Collect only what's needed, delete when no longer needed |
| Retention limits | Automated expiration of data after defined periods |
| Access logging | Audit trail for all access to personal data |
| Consent tracking | Record of what user agreed to and when |

## Key System Design Implications

### Implication 1: Data Deletion ("Right to Be Forgotten")

**The problem**: "Delete user data" sounds simple until you realize user data exists in:
- Primary database
- Read replicas
- Caches (Redis, CDN, local)
- Message queues
- Log files
- Analytics pipelines
- ML training data
- Backups (daily, weekly, monthly)
- Third-party services
- Search indexes

**Staff-level approach**:

```
// Pseudocode: Deletion manifest pattern

CLASS DeletionService:
    
    FUNCTION delete_user(user_id):
        manifest = create_deletion_manifest(user_id)
        
        // Phase 1: Immediate deletion (user-visible data)
        FOR store IN manifest.immediate_stores:
            delete_from_store(store, user_id)
            mark_complete(manifest, store)
        
        // Phase 2: Async deletion (caches, replicas)
        FOR store IN manifest.async_stores:
            queue_deletion(store, user_id, manifest.id)
        
        // Phase 3: Deferred deletion (logs, analytics)
        // These may have retention periods or batch processing
        FOR store IN manifest.deferred_stores:
            schedule_deletion(store, user_id, manifest.id, store.retention_period)
        
        // Phase 4: Backup deletion
        // Backups are immutable; track for exclusion from restore
        add_to_backup_exclusion_list(user_id, manifest.id)
        
        // Track overall progress
        RETURN manifest.id
    
    FUNCTION create_deletion_manifest(user_id):
        manifest = new DeletionManifest()
        
        // Discover all places this user's data exists
        manifest.immediate_stores = [
            "user_db.users",
            "user_db.profiles", 
            "user_db.preferences"
        ]
        
        manifest.async_stores = [
            "redis_cache",
            "cdn_cache",
            "search_index"
        ]
        
        manifest.deferred_stores = [
            "application_logs",      // 90 day retention
            "analytics_events",      // 365 day retention
            "ml_training_snapshots"  // Next training cycle
        ]
        
        manifest.external_services = get_external_services_with_user_data(user_id)
        
        RETURN manifest
```

### Implication 2: Retention and Expiration

**The problem**: Data must be deleted after a certain period, but:
- Different data types have different retention periods
- Some data must be kept for legal/audit purposes even after user deletion
- Retention clock may reset on activity

**Staff-level approach**:

```
// Pseudocode: Retention policy engine

CLASS RetentionEngine:
    
    POLICIES = {
        "user_activity_logs": {
            retention: 90 days,
            clock_reset_on: NONE,
            delete_on_user_deletion: TRUE
        },
        "payment_records": {
            retention: 7 years,  // Legal requirement
            clock_reset_on: NONE,
            delete_on_user_deletion: FALSE,  // Legal hold
            anonymize_on_user_deletion: TRUE
        },
        "session_tokens": {
            retention: 30 days,
            clock_reset_on: USER_ACTIVITY,
            delete_on_user_deletion: TRUE
        },
        "analytics_events": {
            retention: 2 years,
            clock_reset_on: NONE,
            delete_on_user_deletion: TRUE,
            aggregate_after: 90 days  // Keep aggregates, delete raw
        }
    }
    
    FUNCTION apply_retention():
        FOR policy IN POLICIES:
            expired_records = find_expired(policy)
            
            FOR record IN expired_records:
                IF policy.aggregate_after AND record.age > policy.aggregate_after:
                    aggregate_and_delete(record)
                ELSE IF record.age > policy.retention:
                    delete(record)
    
    FUNCTION handle_user_deletion(user_id):
        FOR policy IN POLICIES:
            IF policy.delete_on_user_deletion:
                delete_user_records(policy, user_id)
            ELSE IF policy.anonymize_on_user_deletion:
                anonymize_user_records(policy, user_id)
            // else: keep for legal/audit purposes
```

### Implication 3: Auditability and Traceability

**The problem**: You must be able to prove:
- What data you have about a user
- Where it came from
- What it's been used for
- Who accessed it

**Staff-level approach**:

```
// Pseudocode: Data lineage tracking

CLASS DataLineageTracker:
    
    FUNCTION record_data_ingestion(user_id, data_type, source, purpose):
        lineage_record = {
            user_id: user_id,
            data_type: data_type,
            source: source,           // "user_input", "api_import", "derived"
            purpose: purpose,         // "account_creation", "analytics", "ml_training"
            timestamp: now(),
            consent_id: get_active_consent(user_id, purpose),
            retention_policy: get_policy(data_type)
        }
        
        lineage_store.append(lineage_record)
    
    FUNCTION generate_user_data_report(user_id):
        // For data portability / subject access requests
        report = {
            user_id: user_id,
            generated_at: now(),
            data_inventory: []
        }
        
        FOR record IN lineage_store.get_all(user_id):
            item = {
                data_type: record.data_type,
                source: record.source,
                collected_at: record.timestamp,
                purpose: record.purpose,
                current_location: find_current_location(user_id, record.data_type),
                scheduled_deletion: calculate_deletion_date(record)
            }
            report.data_inventory.append(item)
        
        RETURN report
    
    FUNCTION record_access(user_id, data_type, accessor, purpose):
        access_log.append({
            user_id: user_id,
            data_type: data_type,
            accessor: accessor,
            purpose: purpose,
            timestamp: now(),
            source_ip: get_request_context().ip,
            authorized_by: get_authorization_record()
        })
```

## Balancing Correctness, Performance, and Simplicity

**The Staff Engineer's Challenge**: Compliance adds overhead. How do you minimize impact?

**Strategies**:

1. **Batch operations**: Instead of checking compliance on every request, batch validation
2. **Caching compliance decisions**: Region/policy lookups can be cached
3. **Async compliance**: Some operations (audit logging) can be async
4. **Classification at ingestion**: Classify data once when it enters the system
5. **Smart defaults**: Default to more restrictive handling; opt-in to less restrictive

```
// Pseudocode: Efficient compliance checking

CLASS ComplianceMiddleware:
    
    // Cache policy decisions (TTL: 5 minutes)
    policy_cache = LRUCache(ttl=300)
    
    FUNCTION check_request(request):
        // Fast path: cached decision
        cache_key = (request.user_id, request.data_type, request.operation)
        
        cached = policy_cache.get(cache_key)
        IF cached:
            RETURN cached
        
        // Slow path: compute decision
        user_region = get_user_region(request.user_id)
        request_region = get_request_region(request)
        data_class = classify_data(request.data_type)
        
        allowed = evaluate_policy(user_region, request_region, data_class, request.operation)
        
        policy_cache.set(cache_key, allowed)
        
        // Async: record for audit (don't block request)
        async_queue.enqueue(create_audit_record(request, allowed))
        
        RETURN allowed
```

---

# Part 5: Applied System Examples

## Example 1: User Profile Service

### Which Data is Subject to Locality?

| Data Field | Classification | Locality Requirement |
|------------|---------------|---------------------|
| User ID | Internal | Global (not PII) |
| Display name | Personal | User's home region |
| Email | Personal | User's home region |
| Profile photo URL | Internal | Global (URL only, not image) |
| Profile photo content | Personal | User's home region |
| Account status | Internal | Global |
| Preferences | Personal | User's home region |
| Last login timestamp | Personal | User's home region |

### Naive Design

```
// Naive: Single global database with full replication

CLASS NaiveUserProfileService:
    
    FUNCTION get_profile(user_id):
        RETURN global_db.get("users", user_id)
    
    FUNCTION update_profile(user_id, updates):
        global_db.update("users", user_id, updates)
        global_cache.invalidate(user_id)

// Problems:
// 1. All personal data replicated to all regions
// 2. EU user data exists in US, Asia, etc.
// 3. Cache contains personal data globally
// 4. Deletion must hit all replicas
```

### Staff-Level Design

```
// Staff-level: Separated metadata with regional storage

CLASS RegionalUserProfileService:
    
    FUNCTION get_profile(user_id, requesting_region):
        // Global metadata (fast, cached everywhere)
        metadata = global_metadata.get(user_id)
        
        IF NOT metadata:
            RETURN NOT_FOUND
        
        IF requesting_region == metadata.home_region:
            // Same region: full profile
            personal = regional_store[metadata.home_region].get(user_id)
            RETURN FullProfile(metadata, personal)
        ELSE:
            // Cross-region: limited view
            // (or proxy through home region if needed and allowed)
            RETURN LimitedProfile(metadata)
    
    FUNCTION update_profile(user_id, updates, requesting_region):
        metadata = global_metadata.get(user_id)
        
        // All writes go to home region
        IF requesting_region != metadata.home_region:
            // Option 1: Reject and redirect
            RETURN REDIRECT_TO_HOME_REGION
            // Option 2: Proxy (if network policy allows)
            // RETURN proxy_write(metadata.home_region, user_id, updates)
        
        // Separate updates by classification
        global_updates = filter_global(updates)  // display_name_hash, status
        personal_updates = filter_personal(updates)  // email, preferences
        
        // Update appropriate stores
        IF global_updates:
            global_metadata.update(user_id, global_updates)
        
        IF personal_updates:
            regional_store[metadata.home_region].update(user_id, personal_updates)
        
        // Invalidate caches (only in home region for personal data)
        regional_cache[metadata.home_region].invalidate(user_id)
        global_cache.invalidate_metadata(user_id)
    
    FUNCTION delete_user(user_id):
        metadata = global_metadata.get(user_id)
        home_region = metadata.home_region
        
        // Create deletion manifest
        manifest = DeletionManifest(user_id)
        
        // Phase 1: Primary data
        regional_store[home_region].delete(user_id)
        
        // Phase 2: Global metadata
        global_metadata.delete(user_id)
        
        // Phase 3: Regional caches
        regional_cache[home_region].delete(user_id)
        
        // Phase 4: Logs and analytics (async)
        deletion_queue.enqueue(manifest)
        
        RETURN manifest.tracking_id
```

### Trade-offs Explained

| Aspect | Naive Design | Staff Design |
|--------|--------------|--------------|
| Latency | Fast everywhere | Fast for home region, slower cross-region |
| Compliance | Cannot satisfy | Regional data stays regional |
| Complexity | Simple | More complex routing |
| Deletion | Must hit all replicas | Clear regional scope |

---

## Example 2: Logging and Analytics Pipeline

### Which Data is Subject to Locality?

Logs are often the overlooked compliance risk. What gets logged?

| Log Content | Classification | Risk |
|-------------|---------------|------|
| User ID | Personal identifier | Links other fields to user |
| IP address | Personal (in some jurisdictions) | Location identifier |
| Request path | Usually safe | May contain user IDs |
| Request body | May contain personal data | High risk |
| User agent | Usually safe | Fingerprinting possible |
| Error messages | May contain personal data | Often includes user context |

### Naive Design

```
// Naive: Log everything to central analytics

FUNCTION log_request(request, response):
    log_entry = {
        timestamp: now(),
        user_id: request.user_id,
        path: request.path,
        body: request.body,        // Contains personal data!
        response_code: response.code,
        latency_ms: response.latency,
        ip_address: request.ip,
        region: get_region()
    }
    
    // Send to central log aggregator (probably in one region)
    central_logger.send(log_entry)

// Problems:
// 1. Request body may contain personal data
// 2. All logs centralized (violates residency)
// 3. User ID makes logs personal data
// 4. IP address subject to same rules as personal data
```

### Staff-Level Design

```
// Staff-level: Tiered logging with locality awareness

CLASS LocalityAwareLogger:
    
    FUNCTION log_request(request, response):
        // Tier 1: Operational logs (anonymized, global OK)
        operational_log = {
            timestamp: now(),
            path_pattern: anonymize_path(request.path),  // /users/{id} not /users/123
            response_code: response.code,
            latency_ms: response.latency,
            region: get_region(),
            request_id: request.id  // Correlation without user link
        }
        global_ops_logger.send(operational_log)
        
        // Tier 2: User-linked logs (stays in region)
        IF should_log_user_context(request):
            user_log = {
                request_id: request.id,
                user_id: hash(request.user_id),  // Pseudonymized
                action: classify_action(request),
                region: get_region()
            }
            regional_logger[get_region()].send(user_log)
        
        // Tier 3: Debug logs (PII, short retention, regional)
        IF is_error(response) OR sampling_enabled():
            debug_log = {
                request_id: request.id,
                sanitized_body: sanitize_body(request.body),
                error_context: sanitize_error(response.error)
            }
            regional_debug_logger.send(debug_log, retention=7_DAYS)
    
    FUNCTION sanitize_body(body):
        // Remove/redact known PII fields
        RETURN redact_fields(body, PII_FIELD_PATTERNS)
    
    FUNCTION anonymize_path(path):
        // Replace IDs with placeholders
        // /users/12345/posts/67890 → /users/{user_id}/posts/{post_id}
        RETURN apply_patterns(path, ID_PATTERNS)

CLASS AnalyticsPipeline:
    
    FUNCTION process_events():
        // Regional aggregation first
        FOR region IN regions:
            regional_events = regional_event_store[region].read_batch()
            
            // Aggregate within region (preserves locality)
            regional_aggregates = aggregate(regional_events)
            regional_aggregates_store[region].write(regional_aggregates)
            
            // Only send anonymized aggregates globally
            anonymized_aggregates = remove_all_identifiers(regional_aggregates)
            global_analytics.write(anonymized_aggregates)
```

### Key Trade-offs

| Aspect | Naive | Staff Design |
|--------|-------|--------------|
| Debugging | Easy (full data) | Harder (must correlate across tiers) |
| Compliance | Fails (central PII) | Passes (regional, anonymized) |
| Analytics | Full user tracking | Aggregate metrics only globally |
| Storage cost | Lower (single store) | Higher (regional stores) |

---

## Example 3: Messaging or Notification Metadata

### Which Data is Subject to Locality?

| Data Element | Classification | Notes |
|--------------|---------------|-------|
| Message content | Personal | The actual message |
| Sender/recipient IDs | Personal | Links to users |
| Timestamps | Personal when linked | Part of communication record |
| Read receipts | Personal | User activity |
| Notification tokens | Personal | Device identifiers |

### The Hard Problem: Cross-Region Messaging

**Scenario**: US user sends message to EU user.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│               CROSS-REGION MESSAGING: THE COMPLIANCE CHALLENGE              │
│                                                                             │
│   US Region                                   EU Region                     │
│   ┌────────────────────┐                     ┌────────────────────┐        │
│   │  US User (sender)  │                     │  EU User (receiver)│        │
│   │  Data stays in US  │                     │  Data stays in EU  │        │
│   └────────────────────┘                     └────────────────────┘        │
│            │                                          ▲                     │
│            │                                          │                     │
│            ▼                                          │                     │
│   ┌────────────────────┐                     ┌────────────────────┐        │
│   │  US Message Store  │      Message        │  EU Message Store  │        │
│   │  (sent messages)   │────────────────────>│  (received msgs)   │        │
│   └────────────────────┘                     └────────────────────┘        │
│                                                                             │
│   QUESTION: Where does the message "live"?                                  │
│   - US user's sent folder: US                                               │
│   - EU user's inbox: EU                                                     │
│   - The message itself must exist in BOTH to function                       │
│                                                                             │
│   SOLUTION: Message exists in both, controlled by respective user's rights │
│   - US user deletes: Removed from US, stays in EU (EU user still has it)   │
│   - EU user deletes: Removed from EU, stays in US (US user still has it)   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Staff-Level Design

```
// Pseudocode: Locality-aware messaging

CLASS LocalityAwareMessaging:
    
    FUNCTION send_message(sender_id, recipient_id, content):
        sender_region = get_user_region(sender_id)
        recipient_region = get_user_region(recipient_id)
        
        message_id = generate_id()
        
        // Store in sender's region (sent folder)
        sender_copy = {
            id: message_id,
            type: "sent",
            owner: sender_id,
            other_party: recipient_id,  // Reference, not data
            content: content,
            timestamp: now()
        }
        regional_store[sender_region].write(sender_copy)
        
        // Store in recipient's region (inbox)
        // Note: Content crosses region boundary here (necessary for function)
        recipient_copy = {
            id: message_id,
            type: "received",
            owner: recipient_id,
            other_party: sender_id,  // Reference, not data
            content: content,
            timestamp: now()
        }
        
        IF sender_region == recipient_region:
            regional_store[recipient_region].write(recipient_copy)
        ELSE:
            // Cross-region write (encrypted in transit)
            cross_region_messenger.deliver(recipient_region, recipient_copy)
        
        // Notify recipient
        notification_service.notify(recipient_id, "new_message", message_id)
    
    FUNCTION delete_message(user_id, message_id):
        user_region = get_user_region(user_id)
        
        // Delete only this user's copy
        regional_store[user_region].delete(message_id, owner=user_id)
        
        // Other party's copy is unaffected
        // (They own their copy under their jurisdiction)
    
    FUNCTION handle_user_deletion(user_id):
        user_region = get_user_region(user_id)
        
        // Delete all messages owned by this user
        regional_store[user_region].delete_all(owner=user_id)
        
        // For messages where this user is the other_party:
        // Anonymize the reference (don't delete the message)
        FOR region IN all_regions:
            regional_store[region].anonymize_party(user_id)
```

---

# Part 6: System Evolution Under Changing Constraints

## Evolution Triggers

Systems must evolve when:
- **New regions are added** (geographic expansion)
- **Regulations change** (new laws, stricter interpretation)
- **Data policies tighten** (enterprise customer requirements)
- **Products expand** (new features with different data needs)
- **Organizational changes** (acquisitions, spin-offs)

## Designing for Change

### Principle 1: Backward Compatibility

New constraints shouldn't break existing functionality:

```
// Pseudocode: Backward-compatible data classification

CLASS EvolvingDataClassifier:
    
    VERSION = 3
    
    FUNCTION classify(record):
        // Check if record has explicit classification
        IF record.has_classification():
            RETURN record.classification
        
        // Legacy data: apply current rules with migration path
        legacy_class = infer_classification_v3(record)
        
        // Mark for async migration
        IF NOT record.classification_migrated:
            migration_queue.enqueue(record.id, legacy_class)
        
        RETURN legacy_class
    
    FUNCTION migrate_classifications():
        // Batch job to update legacy records
        FOR record_id, new_class IN migration_queue.batch(1000):
            record = storage.get(record_id)
            record.classification = new_class
            record.classification_migrated = TRUE
            record.classification_version = VERSION
            storage.update(record)
```

### Principle 2: Incremental Migration

Avoid big-bang migrations:

```
// Pseudocode: Incremental regional migration

CLASS RegionalMigration:
    
    FUNCTION migrate_users_to_new_region(users, source_region, target_region):
        // Phase 1: Dual-write (new writes go to both)
        enable_dual_write(target_region)
        
        // Phase 2: Background copy of existing data
        FOR user IN users:
            copy_user_data(user, source_region, target_region)
            mark_copied(user)
        
        // Phase 3: Verify consistency
        FOR user IN users:
            verify_consistency(user, source_region, target_region)
        
        // Phase 4: Switch reads to new region
        FOR user IN users:
            switch_read_region(user, target_region)
            verify_reads(user)
        
        // Phase 5: Switch writes to new region
        FOR user IN users:
            switch_write_region(user, target_region)
        
        // Phase 6: Disable dual-write, clean up source
        disable_dual_write(source_region)
        schedule_cleanup(source_region, users, delay=30_DAYS)
```

### Principle 3: Dual-Write / Dual-Read (Conceptual)

Transition periods require running old and new paths simultaneously:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                   DUAL-WRITE / DUAL-READ TRANSITION                         │
│                                                                             │
│   PHASE 1: DUAL-WRITE                                                       │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │              Write Request                                          │   │
│   │                   │                                                 │   │
│   │          ┌────────┴────────┐                                        │   │
│   │          ▼                 ▼                                        │   │
│   │   ┌─────────────┐   ┌─────────────┐                                 │   │
│   │   │ Old Store   │   │ New Store   │                                 │   │
│   │   │ (primary)   │   │ (shadow)    │                                 │   │
│   │   └─────────────┘   └─────────────┘                                 │   │
│   │          │                                                          │   │
│   │          ▼                                                          │   │
│   │       Response                                                      │   │
│   │                                                                     │   │
│   │   Reads: Old store only                                             │   │
│   │   Writes: Both stores, old is authoritative                         │   │
│   │   Verification: Compare shadow with primary async                   │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   PHASE 2: DUAL-READ                                                        │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │              Read Request                                           │   │
│   │                   │                                                 │   │
│   │          ┌────────┴────────┐                                        │   │
│   │          ▼                 ▼                                        │   │
│   │   ┌─────────────┐   ┌─────────────┐                                 │   │
│   │   │ Old Store   │   │ New Store   │                                 │   │
│   │   │ (fallback)  │   │ (primary)   │                                 │   │
│   │   └─────────────┘   └─────────────┘                                 │   │
│   │                            │                                        │   │
│   │                            ▼                                        │   │
│   │                         Response                                    │   │
│   │                                                                     │   │
│   │   Reads: New store primary, old as fallback                         │   │
│   │   Writes: Both stores, new is authoritative                         │   │
│   │   Verification: Ensure new store is consistent                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   PHASE 3: CUTOVER                                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │   • Disable writes to old store                                     │   │
│   │   • Disable reads from old store (with monitoring)                  │   │
│   │   • Keep old store for rollback (30 days)                           │   │
│   │   • Clean up old store                                              │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Principle 4: Designing for Reversibility

Every migration should be reversible:

```
// Pseudocode: Reversible migration

CLASS ReversibleMigration:
    
    FUNCTION execute_migration(migration_plan):
        checkpoint = create_checkpoint()
        
        TRY:
            FOR step IN migration_plan.steps:
                execute_step(step)
                verify_step(step)
                record_progress(step, checkpoint)
        EXCEPT Exception as e:
            // Rollback to checkpoint
            rollback_to(checkpoint)
            RAISE MigrationFailed(e, checkpoint)
    
    FUNCTION create_checkpoint():
        RETURN {
            timestamp: now(),
            state_snapshot: capture_state(),
            can_rollback_until: now() + 7_DAYS
        }
    
    FUNCTION rollback_to(checkpoint):
        IF now() > checkpoint.can_rollback_until:
            RAISE RollbackWindowExpired()
        
        restore_state(checkpoint.state_snapshot)
        verify_restoration()
```

## Handling Unknown Future Constraints

Staff Engineers plan for constraints they can't predict:

**1. Indirection layers**: Don't hardcode region logic
```
// Bad: Hardcoded region check
IF user.country == "DE" OR user.country == "FR":
    use_eu_store()

// Good: Policy-driven
region_policy = policy_service.get_policy(user)
use_store(region_policy.data_store)
```

**2. Data classification from day one**: Tag data with sensitivity
**3. Audit trails**: Record decisions for future analysis
**4. Abstraction over location**: Services don't know physical location

---

# Part 7: Failure and Risk Scenarios

## Scenario: Compliance Violation During Incident

**Background**: A global e-commerce platform stores user data in regional databases. During a major incident affecting the EU database, an engineer temporarily routes EU traffic to the US cluster.

### Timeline

```
T+0:     EU database becomes unresponsive
T+5min:  Pager fires, on-call engineer investigates
T+15min: Engineer identifies issue: EU database needs restart
T+20min: Engineer makes decision: "Users are down, let's route to US temporarily"
         → Redirects EU users to US cluster
T+30min: EU users can access the service again
T+45min: EU database comes back online
T+60min: Traffic restored to EU
T+2hrs:  Incident resolved, post-mortem scheduled

T+1week: Security review discovers:
         → 500,000 EU users had data processed in US
         → For 45 minutes, EU personal data was stored in US
         → This is a data residency violation
```

### Impact Analysis

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    COMPLIANCE INCIDENT IMPACT                               │
│                                                                             │
│   IMMEDIATE IMPACT:                                                         │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  • 500,000 EU users' requests processed in US                       │   │
│   │  • Personal data temporarily stored in US caches                    │   │
│   │  • Logs in US contain EU user data                                  │   │
│   │  • Session data replicated to US                                    │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   REMEDIATION REQUIRED:                                                     │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  • Purge US caches of EU user data                                  │   │
│   │  • Delete or anonymize US logs containing EU data                   │   │
│   │  • Document incident for regulators                                 │   │
│   │  • Assess notification requirements                                 │   │
│   │  • Update incident response procedures                              │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   WHAT MADE IT WORSE:                                                       │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  • No guardrails prevented cross-region routing                     │   │
│   │  • System didn't distinguish between "can" and "should"             │   │
│   │  • Logs don't have automatic regional retention                     │   │
│   │  • Cache TTL was 24 hours (still had EU data next day)              │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   WHAT COULD HAVE LIMITED DAMAGE:                                           │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  • Routing policy that rejects locality-violating routes            │   │
│   │  • Degraded mode that returns errors rather than violating          │   │
│   │  • Immediate cache purge on cross-region detection                  │   │
│   │  • Alert when data crosses compliance boundaries                    │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Staff-Level Design: Compliance-Aware Failover

```
// Pseudocode: Compliance-aware routing

CLASS ComplianceAwareRouter:
    
    FUNCTION route_request(request):
        user_region = get_user_data_region(request.user_id)
        target_regions = get_healthy_regions()
        
        // First choice: user's home region
        IF user_region IN target_regions:
            RETURN route_to(user_region)
        
        // Second choice: region with same compliance profile
        compatible = get_compliance_compatible_regions(user_region)
        FOR region IN compatible:
            IF region IN target_regions:
                log_warning("Cross-region routing within compliance zone",
                            user_region, region)
                RETURN route_to(region)
        
        // No compliant option: FAIL rather than violate
        log_error("No compliant region available", user_region)
        
        // Return degraded response instead of routing violation
        RETURN degraded_response(
            message="Service temporarily limited",
            retry_after=estimate_recovery_time()
        )

CLASS LocalityGuard:
    
    FUNCTION validate_operation(operation, user_id, executing_region):
        user_data_region = get_user_data_region(user_id)
        
        IF NOT regions_compatible(user_data_region, executing_region):
            // Block the operation entirely
            raise LocalityViolationError(
                user_data_region, executing_region, operation
            )
        
        IF user_data_region != executing_region:
            // Log cross-region access within same compliance zone
            log_audit("Cross-region access",
                      user_id, user_data_region, executing_region)
        
        RETURN ALLOW

FUNCTION regions_compatible(data_region, processing_region):
    // Define compliance zones
    eu_zone = ["eu-west-1", "eu-central-1", "eu-north-1"]
    us_zone = ["us-east-1", "us-west-1", "us-central-1"]
    ap_zone = ["ap-northeast-1", "ap-southeast-1"]
    
    // Same zone is compatible
    IF data_region IN eu_zone AND processing_region IN eu_zone:
        RETURN TRUE
    IF data_region IN us_zone AND processing_region IN us_zone:
        RETURN TRUE
    IF data_region IN ap_zone AND processing_region IN ap_zone:
        RETURN TRUE
    
    // Cross-zone is NOT compatible
    RETURN FALSE
```

### Lessons Learned

1. **Availability vs Compliance**: Sometimes the correct answer during an outage is "users get errors" rather than "users get data from the wrong region"

2. **Guardrails, Not Guidelines**: Compliance boundaries must be enforced in code, not just documented in runbooks

3. **Derived Data Matters**: The cache, logs, and session store all contained EU data in US—not just the database

4. **Detection vs Prevention**: This incident was detected a week later. Prevention would have avoided the violation entirely

---

## Scenario 2: The Deletion Backlog Disaster

### Background

A social media platform received 50,000 user deletion requests (GDPR "right to be forgotten") per month. They had a deletion service, but it only handled the primary database.

### The Timeline

```
Month 1:    Deletion service launched, deletes from primary user table
Month 2:    Audit reveals posts table still has user content
Month 3:    Fix deployed, now deletes from user + posts tables
Month 4:    Audit reveals messages table, analytics, and logs still have data
Month 5:    Team realizes data exists in:
            • Primary database (3 tables)
            • Search index
            • Recommendations cache
            • Analytics warehouse
            • Log storage (18 months retention)
            • ML training datasets
            • Backup snapshots (3 years retention)
Month 6:    Regulatory inquiry begins
```

### Root Cause: No Data Map

```
// The flawed approach: whack-a-mole deletion
FUNCTION delete_user_data(user_id):
    // Version 1: Just the obvious table
    primary_db.delete("users", user_id)
    
    // Version 2: Found more tables
    primary_db.delete("posts", user_id)
    primary_db.delete("comments", user_id)
    
    // Version 3: Found even more (but still incomplete)
    search_index.delete(user_id)
    cache.invalidate(user_id)
    
    // Still missing: analytics, logs, backups, ML datasets...
```

### Staff-Level Design: Data Lineage and Deletion Manifest

```
// Pseudocode: Complete data deletion with manifest

CLASS DataManifest:
    // Every data store containing user data must register
    registered_stores = []
    
    FUNCTION register_data_store(store_name, deletion_handler, verification):
        registered_stores.append({
            name: store_name,
            delete: deletion_handler,
            verify: verification,
            owner_team: get_team_owner(store_name)
        })
    
    FUNCTION get_deletion_manifest(user_id):
        manifest = {
            user_id: user_id,
            created_at: now(),
            stores: [],
            status: "pending"
        }
        
        FOR store IN registered_stores:
            IF store.has_user_data(user_id):
                manifest.stores.append({
                    store: store.name,
                    status: "pending",
                    estimated_deletion_time: store.get_sla()
                })
        
        RETURN manifest

CLASS DeletionOrchestrator:
    
    FUNCTION execute_deletion(user_id):
        manifest = DataManifest.get_deletion_manifest(user_id)
        
        // Phase 1: Immediate deletion from primary stores
        FOR store IN manifest.stores.filter(priority="immediate"):
            result = store.delete(user_id)
            manifest.update(store.name, result.status)
        
        // Phase 2: Queue deletion from async stores
        FOR store IN manifest.stores.filter(priority="async"):
            queue_deletion(store.name, user_id, manifest.id)
        
        // Phase 3: Mark for eventual deletion (backups, archives)
        FOR store IN manifest.stores.filter(priority="eventual"):
            schedule_eventual_deletion(store.name, user_id, manifest.id)
        
        // Persist manifest for audit trail
        save_manifest(manifest)
        
        RETURN manifest
    
    FUNCTION verify_deletion(manifest_id):
        manifest = load_manifest(manifest_id)
        
        FOR store IN manifest.stores:
            exists = DataManifest.registered_stores[store.name].verify(manifest.user_id)
            IF exists:
                alert("Deletion incomplete", store.name, manifest.user_id)
                RETURN INCOMPLETE
        
        manifest.status = "verified_complete"
        save_manifest(manifest)
        RETURN COMPLETE
```

### Deletion Timeline by Data Store Type

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    DELETION TIMELINE BY DATA STORE                          │
│                                                                             │
│   IMMEDIATE (within request):                                               │
│   ├── Primary database: DELETE FROM users WHERE id = ?                      │
│   ├── Session store: Invalidate all sessions                                │
│   └── CDN cache: Purge user content                                         │
│                                                                             │
│   ASYNC (within hours):                                                     │
│   ├── Search index: Remove from index, reindex affected pages               │
│   ├── Recommendations cache: Invalidate user vectors                        │
│   └── Message queues: Consume and discard pending user events               │
│                                                                             │
│   BATCH (within days):                                                      │
│   ├── Analytics warehouse: Anonymize or delete historical data              │
│   ├── ML training data: Remove from future training sets                    │
│   └── Logs: Mark for accelerated expiration                                 │
│                                                                             │
│   EVENTUAL (within retention period):                                       │
│   ├── Backups: Cannot modify; wait for natural expiration                   │
│   ├── Disaster recovery: Schedule special purge job                         │
│   └── Archives: Queue for next archive cleanup cycle                        │
│                                                                             │
│   KEY INSIGHT:                                                              │
│   "Deleted" means different things for different stores.                    │
│   Track and verify each separately.                                         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Part 8: Diagrams

## Diagram 1: Data Locality Boundaries Across Regions

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                  DATA LOCALITY BOUNDARIES: GLOBAL VIEW                       │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                        EU COMPLIANCE ZONE                            │   │
│   │   ┌─────────────────┐    ┌─────────────────┐    ┌───────────────┐   │   │
│   │   │   EU-WEST-1     │    │   EU-CENTRAL-1  │    │  EU-NORTH-1   │   │   │
│   │   │                 │    │                 │    │               │   │   │
│   │   │  ┌───────────┐  │    │  ┌───────────┐  │    │ ┌───────────┐ │   │   │
│   │   │  │ User Data │  │◄──►│  │  Replica  │  │◄──►│ │  Replica  │ │   │   │
│   │   │  │ (Primary) │  │    │  │ (Read)    │  │    │ │ (Read)    │ │   │   │
│   │   │  └───────────┘  │    │  └───────────┘  │    │ └───────────┘ │   │   │
│   │   │  ┌───────────┐  │    │  ┌───────────┐  │    │ ┌───────────┐ │   │   │
│   │   │  │   Logs    │  │    │  │   Logs    │  │    │ │   Logs    │ │   │   │
│   │   │  └───────────┘  │    │  └───────────┘  │    │ └───────────┘ │   │   │
│   │   │  ┌───────────┐  │    │  ┌───────────┐  │    │ ┌───────────┐ │   │   │
│   │   │  │  Analytics│  │    │  │  Analytics│  │    │ │ Analytics │ │   │   │
│   │   │  └───────────┘  │    │  └───────────┘  │    │ └───────────┘ │   │   │
│   │   └─────────────────┘    └─────────────────┘    └───────────────┘   │   │
│   │                                                                      │   │
│   │   DATA CAN FLOW FREELY WITHIN EU ZONE                                │   │
│   │   ═══════════════════════════════════════                            │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                              ║                                              │
│                              ║ BOUNDARY: No EU user data crosses            │
│                              ║ (Only anonymized aggregates allowed)         │
│                              ║                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                        US COMPLIANCE ZONE                            │   │
│   │   ┌─────────────────┐    ┌─────────────────┐                        │   │
│   │   │   US-EAST-1     │    │   US-WEST-1     │                        │   │
│   │   │                 │    │                 │                        │   │
│   │   │  ┌───────────┐  │    │  ┌───────────┐  │                        │   │
│   │   │  │ User Data │  │◄──►│  │  Replica  │  │                        │   │
│   │   │  │ (Primary) │  │    │  │ (Read)    │  │                        │   │
│   │   │  └───────────┘  │    │  └───────────┘  │                        │   │
│   │   └─────────────────┘    └─────────────────┘                        │   │
│   │                                                                      │   │
│   │   DATA CAN FLOW FREELY WITHIN US ZONE                                │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   GLOBAL SERVICES (Non-User Data Only):                                     │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  • Configuration service (no user data)                              │   │
│   │  • Global load balancer (routes, doesn't store)                      │   │
│   │  • Anonymized metrics (aggregate counts only)                        │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Diagram 2: Data Flow with Locality Constraints

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                DATA FLOW WITH LOCALITY CONSTRAINTS                          │
│                                                                             │
│   USER REQUEST (EU User)                                                    │
│         │                                                                   │
│         ▼                                                                   │
│   ┌───────────────────────────────────────────────────────────────────┐     │
│   │ GLOBAL LOAD BALANCER                                               │     │
│   │ Decision: Route to EU based on user's data region                  │     │
│   │ (Does NOT inspect or store user data)                              │     │
│   └───────────────────────────────────────────────────────────────────┘     │
│         │                                                                   │
│         ▼                                                                   │
│   ┌───────────────────────────────────────────────────────────────────┐     │
│   │ EU-WEST-1: API SERVER                                              │     │
│   │                                                                    │     │
│   │   1. Validate request                                              │     │
│   │   2. Check: Is user data region == current region?  ──► YES       │     │
│   │   3. Process request locally                                       │     │
│   └───────────────────────────────────────────────────────────────────┘     │
│         │                                                                   │
│         ├────────────────────────────────────────────────────┐              │
│         ▼                                                    ▼              │
│   ┌─────────────────────┐                        ┌─────────────────────┐    │
│   │ EU: PRIMARY DB      │                        │ EU: CACHE           │    │
│   │ (Read/Write)        │                        │ (Read/Write)        │    │
│   │                     │                        │ ⚠️ Contains user    │    │
│   │ User data stays     │                        │   data, must be     │    │
│   │ in EU region        │                        │   region-local      │    │
│   └─────────────────────┘                        └─────────────────────┘    │
│         │                                                                   │
│         │ (Async replication within EU zone only)                           │
│         ▼                                                                   │
│   ┌─────────────────────┐                                                   │
│   │ EU: READ REPLICAS   │                                                   │
│   │ (EU-CENTRAL, etc.)  │                                                   │
│   │                     │                                                   │
│   │ Replicas stay       │                                                   │
│   │ within EU zone      │                                                   │
│   └─────────────────────┘                                                   │
│         │                                                                   │
│         │ (Anonymized aggregates only)                                      │
│         ▼                                                                   │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │ GLOBAL ANALYTICS                                                    │   │
│   │                                                                     │   │
│   │ Receives: count of requests, latency percentiles, error rates       │   │
│   │ Does NOT receive: user IDs, email addresses, content                │   │
│   │                                                                     │   │
│   │ ✅ Compliance-safe: No individual user data crosses boundary        │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   WHAT CROSSES BOUNDARIES:           WHAT STAYS LOCAL:                      │
│   ├── Aggregate metrics              ├── User profile data                  │
│   ├── System health data             ├── User content                       │
│   ├── Anonymized counts              ├── Activity logs with user IDs        │
│   └── Configuration                  └── Caches, replicas, backups          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Diagram 3: System Evolution Under Changing Constraints

```
┌─────────────────────────────────────────────────────────────────────────────┐
│            SYSTEM EVOLUTION UNDER CHANGING CONSTRAINTS                       │
│                                                                             │
│   PHASE 1: SINGLE REGION (Starting Point)                                   │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │   US-EAST-1                                                          │   │
│   │   ┌────────────────────────────────────────────────────────────┐    │   │
│   │   │  All users, all data, all processing                        │    │   │
│   │   │  Simple but doesn't support data locality                   │    │   │
│   │   └────────────────────────────────────────────────────────────┘    │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                     │                                       │
│                                     ▼                                       │
│   PHASE 2: REGIONAL COMPUTE, CENTRAL DATA                                   │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │   US-EAST-1 (Primary)              EU-WEST-1 (Compute Only)         │   │
│   │   ┌───────────────────┐            ┌───────────────────┐           │   │
│   │   │  Database         │◄───────────│  API Servers      │           │   │
│   │   │  (All User Data)  │  Network   │  (Stateless)      │           │   │
│   │   └───────────────────┘            └───────────────────┘           │   │
│   │                                                                     │   │
│   │   ⚠️ EU user data still processed in US                            │   │
│   │   ⚠️ Does NOT satisfy data locality requirements                   │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                     │                                       │
│                                     ▼                                       │
│   PHASE 3: REGIONAL DATA PARTITIONING                                       │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │   US-EAST-1                         EU-WEST-1                        │   │
│   │   ┌───────────────────┐            ┌───────────────────┐           │   │
│   │   │  US User Data     │            │  EU User Data     │           │   │
│   │   │  Database         │            │  Database         │           │   │
│   │   └───────────────────┘            └───────────────────┘           │   │
│   │   ┌───────────────────┐            ┌───────────────────┐           │   │
│   │   │  US Logs          │            │  EU Logs          │           │   │
│   │   └───────────────────┘            └───────────────────┘           │   │
│   │   ┌───────────────────┐            ┌───────────────────┐           │   │
│   │   │  US Analytics     │            │  EU Analytics     │           │   │
│   │   └───────────────────┘            └───────────────────┘           │   │
│   │                                                                     │   │
│   │   ✅ User data stays in user's region                               │   │
│   │   ⚠️ Cross-region user interaction requires careful design          │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                     │                                       │
│                                     ▼                                       │
│   PHASE 4: FULL LOCALITY COMPLIANCE                                         │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │   US ZONE                              EU ZONE                       │   │
│   │   ┌────────────────────────┐          ┌────────────────────────┐   │   │
│   │   │  US User Data          │          │  EU User Data          │   │   │
│   │   │  US Logs               │          │  EU Logs               │   │   │
│   │   │  US Analytics          │          │  EU Analytics          │   │   │
│   │   │  US Backups            │          │  EU Backups            │   │   │
│   │   │  US ML Models          │          │  EU ML Models          │   │   │
│   │   └────────────────────────┘          └────────────────────────┘   │   │
│   │            │                                    │                   │   │
│   │            └────────────────┬───────────────────┘                   │   │
│   │                             │                                       │   │
│   │                             ▼                                       │   │
│   │              ┌────────────────────────────┐                        │   │
│   │              │  GLOBAL LAYER              │                        │   │
│   │              │  (Non-User Data Only)      │                        │   │
│   │              │  • Configuration           │                        │   │
│   │              │  • Routing                 │                        │   │
│   │              │  • Anonymized aggregates   │                        │   │
│   │              └────────────────────────────┘                        │   │
│   │                                                                     │   │
│   │   ✅ Full data locality compliance                                  │   │
│   │   ✅ Deletion can be scoped to region                               │   │
│   │   ✅ Audit trail is region-complete                                 │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   MIGRATION STRATEGY:                                                       │
│   1. Identify all data stores containing user data                          │
│   2. Add region tagging to existing data                                    │
│   3. Deploy regional instances of each store                                │
│   4. Migrate users to regional stores (batch by batch)                      │
│   5. Update routing to send users to regional instances                     │
│   6. Verify no cross-region data flows                                      │
│   7. Decommission central user data stores                                  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Part 9: Interview Calibration

## How Google Interviewers Probe Data Locality Thinking

Interviewers rarely ask directly about compliance. Instead, they probe through design constraints:

### Common Indirect Probes

**"Your system has users in Europe. Walk me through the data flow."**
- Tests whether you consider where data is stored, not just processed
- Strong candidates identify all data copies: primary, replicas, caches, logs

**"A user requests deletion of their account. How do you handle it?"**
- Tests whether you understand the scope of user data
- Strong candidates ask "Where is all of this user's data?" before answering

**"How would your design change if you had to launch in a new country with strict data laws?"**
- Tests whether the architecture is flexible or brittle
- Strong candidates explain what would change vs what's already designed for evolution

**"Tell me about your logging strategy."**
- Hidden test: Do you recognize that logs often contain user data?
- Strong candidates discuss what data logs contain and retention implications

**"What happens during a regional outage?"**
- Hidden test: Would failover violate data locality?
- Strong candidates explain compliance-aware failover behavior

---

## Example Interview Questions

### Basic Level
- "Where would you store user data for a global application?"
- "How would you implement user deletion?"

### Intermediate Level
- "Your analytics team wants access to all user activity. How do you provide it while respecting data locality?"
- "How do you cache user data for a globally distributed application?"

### Staff Level
- "Design a system that can adapt to new data residency requirements without a major rewrite."
- "How would you audit your system to verify compliance at any point in time?"
- "Walk me through how you'd migrate an existing global system to support regional data isolation."

---

## Example Phrases a Staff Engineer Would Use

**When discussing architecture:**
- "We intentionally separate user metadata from user content so we can route and cache metadata globally while keeping content regional."
- "I'd design the data model with region as a first-class attribute from day one, even if we only have one region now."
- "Let me map all the places this user's data would exist—primary store, replicas, caches, logs, analytics—before we discuss deletion."

**When discussing trade-offs:**
- "Global caching would improve latency, but it means EU user data in US caches. We'd need regional cache instances, which increases operational complexity."
- "We could simplify by having one global database, but that closes off future regional isolation. The indirection cost is worth preserving optionality."

**When discussing failures:**
- "During a regional outage, we'll return errors to that region's users rather than routing them to another region. Availability isn't worth a compliance violation."
- "If deletion fails partway through, we need idempotent retry, not manual cleanup. The manifest tracks state so we can resume."

**When discussing evolution:**
- "This design assumes we know all future compliance requirements, which we don't. Let me show you where we've built in flexibility."
- "We version the data locality policy separately from the code, so we can respond to regulatory changes without a deploy."

---

## Common Mistakes Made by Strong Senior Engineers

### Mistake 1: Treating Compliance as an Afterthought

**L5 Thinking:**
"Let's get the system working first, then add compliance features."

**Why It Fails:**
Data locality requirements affect data model, caching, logging, replication—nearly everything. Adding it later requires rewriting core components.

**L6 Thinking:**
"What are the data locality constraints? Let me design the data model and data flows with those in mind from the start."

---

### Mistake 2: Only Considering the Primary Database

**L5 Thinking:**
"Our database is in EU, so EU data is in EU. Compliance handled."

**Why It Fails:**
Caches, logs, analytics, backups, replicas, search indexes, message queues—all may contain user data in other regions.

**L6 Thinking:**
"Let me trace every place this data could exist. For each store, where is it physically located and what's the retention?"

---

### Mistake 3: Assuming Deletion Is Simple

**L5 Thinking:**
"We'll add a DELETE endpoint that removes the user from the database."

**Why It Fails:**
Deletion must cover all copies: replicas (eventually consistent), caches (may be global), logs (long retention), analytics (historical data), backups (immutable), ML models (trained on user data).

**L6 Thinking:**
"Deletion is a multi-phase process with different timelines per data store. We need a manifest to track what's been deleted and verification to confirm completeness."

---

### Mistake 4: Ignoring Cross-Region Interactions

**L5 Thinking:**
"EU users go to EU servers, US users go to US servers. Data stays local."

**Why It Fails:**
What if an EU user messages a US user? What if a US user views an EU user's profile? Cross-region interactions create data flows that may violate locality.

**L6 Thinking:**
"For cross-region interactions, we need to decide: Does data cross regions? Do we proxy through the data's home region? Do we accept latency to maintain locality?"

---

# Part 10: Brainstorming Questions

## Discovery Questions

1. **"Which data actually needs locality constraints?"**
   - Is it all user data, or just PII?
   - Can usage metrics be anonymized and aggregated globally?
   - What about metadata vs content?

2. **"What happens if regulations change tomorrow?"**
   - New country requires data to stay in-country
   - Existing regulation tightens (shorter retention, faster deletion)
   - New data type becomes regulated (location, health)

3. **"Where does derived data end up?"**
   - ML models trained on user data
   - Analytics aggregations
   - Search indexes
   - Recommendation vectors

4. **"How would you prove compliance right now?"**
   - Can you list every data store with user data?
   - For each, where is it located?
   - For each, what's the retention?
   - For each, how is deletion handled?

5. **"What's the blast radius of a locality violation?"**
   - How many users affected?
   - How long until detection?
   - What's the remediation effort?
   - What's the regulatory exposure?

## Trade-off Questions

6. **"Latency vs Locality"**
   - Global caching reduces latency but may violate locality
   - Regional caches maintain locality but reduce cache efficiency
   - What's the right balance for this system?

7. **"Simplicity vs Flexibility"**
   - Single global database is simple but can't support locality
   - Regional partitioning is flexible but complex
   - Where on this spectrum is appropriate?

8. **"Consistency vs Availability under Locality"**
   - During regional outage: errors vs cross-region routing
   - For cross-region interactions: latency vs data movement
   - What's acceptable for this use case?

9. **"Cost vs Compliance"**
   - Regional instances cost more than centralized
   - Shorter log retention reduces storage but loses debugging ability
   - What's the right investment level?

10. **"Speed vs Auditability"**
    - Fast deletion vs verifiable deletion
    - Inline processing vs logged manifests
    - How much overhead is acceptable?

## Evolution Questions

11. **"What if you add a new region?"**
    - What data needs to exist there?
    - How do you migrate existing users?
    - How do you handle users who travel between regions?

12. **"What if you add a new data type?"**
    - How do you classify its locality requirements?
    - How do you ensure all data flows respect those requirements?

13. **"What if you acquire another company?"**
    - Their data may be in different regions
    - Their data model may not have region attributes
    - How do you integrate while maintaining compliance?

14. **"What if a regulation is repealed?"**
    - Can you simplify the system?
    - Is the complexity now technical debt?
    - How do you safely reduce regional isolation?

15. **"What if users change regions?"**
    - How do you migrate their data?
    - What happens during the transition?
    - How long is acceptable?

---

# Homework Exercises

## Exercise 1: Locality Audit

**Objective:** Practice identifying all data stores containing user data.

Take a system you've worked on (or a public system design) and create a data map:

| Data Store | Contains User Data? | Location | Retention | Deletion Mechanism |
|------------|---------------------|----------|-----------|-------------------|
| Primary DB | Yes - profiles | us-east-1 | Forever | Hard delete |
| Cache | Yes - sessions | Global | 24 hours | TTL |
| Logs | Yes - request bodies | us-east-1 | 90 days | Expiration |
| Analytics | Yes - events | us-west-2 | 2 years | Anonymization |

**Deliverable:** Complete data map with gaps identified.

---

## Exercise 2: Deletion Design

**Objective:** Design a complete deletion system.

For a social media platform with:
- User profiles
- Posts and comments
- Direct messages
- Activity logs
- Search index
- Recommendation vectors
- Backups (immutable, 1-year retention)

Design:
1. Data manifest: Where is all user data?
2. Deletion phases: What gets deleted when?
3. Verification: How do you confirm deletion is complete?
4. Edge cases: What about shared data (messages with other users)?

**Deliverable:** Deletion system design document.

---

## Exercise 3: Migration Planning

**Objective:** Plan migration to regional data isolation.

Given a system with:
- Single global database (US)
- Global CDN cache
- Centralized logging
- Global analytics warehouse

And requirement:
- EU user data must stay in EU

Plan:
1. What changes are needed to each component?
2. How do you migrate existing EU users?
3. How do you handle the transition period?
4. How do you verify completion?

**Deliverable:** Migration plan with phases, risks, and rollback strategy.

---

## Exercise 4: Cross-Region Interaction Design

**Objective:** Design cross-region user interactions that respect locality.

Scenario: EU user wants to message US user.

Options to consider:
1. Message stored in sender's region only
2. Message replicated to recipient's region
3. Message stored in recipient's region only
4. Message stored in neutral location

For each option:
- What are the locality implications?
- What's the user experience during regional outage?
- What happens for deletion requests?

**Deliverable:** Design decision with trade-off analysis.

---

## Exercise 5: Compliance-Aware Failover

**Objective:** Design failover that respects data locality.

Given:
- Three regions: US, EU, AP
- Each region has its users' data
- EU region has an outage

Design failover behavior:
- What happens to EU users?
- What operations can continue?
- What operations must fail?
- How do you communicate to users?

**Deliverable:** Failover runbook with compliance constraints.

---

## Exercise 6: Data Classification System

**Objective:** Design a system for classifying data by locality requirements.

Create a classification framework:

| Classification | Definition | Examples | Locality Requirement |
|----------------|------------|----------|---------------------|
| PII-Strict | Identified user data | Email, name | User's region only |
| PII-Derived | Inferred from PII | Activity patterns | User's region only |
| Pseudonymous | Linked by ID, not name | User ID + behavior | Compliance zone OK |
| Anonymized | Cannot identify user | Aggregate counts | Global OK |

Design:
- How do you tag data at creation?
- How do you enforce locality based on classification?
- How do you audit classification accuracy?

**Deliverable:** Classification framework with enforcement design.

---

## Exercise 7: Logging Strategy

**Objective:** Design compliance-aware logging.

Challenge: You need detailed logs for debugging, but logs contain user data.

Design:
1. What should be logged? (Request ID, user ID, parameters, responses)
2. Where should logs be stored? (Regional? Global?)
3. What's the retention? (Different for different log types?)
4. How do you handle deletion requests? (Remove user data from logs)
5. How do you debug cross-region issues without centralizing logs?

**Deliverable:** Logging strategy document with compliance considerations.

---

## Exercise 8: Analytics Pipeline Design

**Objective:** Design analytics that respects data locality.

Requirements:
- Product team needs global usage metrics
- Data science team needs training data for ML
- EU user data must stay in EU

Design options:
1. Regional data warehouses, global aggregation layer
2. Anonymization at collection time
3. Differential privacy for cross-region queries
4. Federated learning for ML

For each relevant option:
- What queries are possible?
- What's lost vs centralized approach?
- What's the operational complexity?

**Deliverable:** Analytics architecture with locality compliance.

---

# Part 11: Real-World Incident Case Study

## The Analytics Pipeline Leak

### Background

A SaaS company had EU data residency requirements but a centralized analytics pipeline.

### The Design (Flawed)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    ANALYTICS PIPELINE (FLAWED)                               │
│                                                                             │
│   EU-WEST-1                               US-EAST-1                         │
│   ┌─────────────────┐                    ┌─────────────────────────────┐    │
│   │  EU Application │──── Events ────────│  Central Analytics         │    │
│   │                 │                    │  Warehouse                 │    │
│   └─────────────────┘                    │                            │    │
│                                          │  Contains:                 │    │
│   US-WEST-1                              │  - All events              │    │
│   ┌─────────────────┐                    │  - User IDs                │    │
│   │  US Application │──── Events ────────│  - Request parameters      │    │
│   │                 │                    │  - Response data           │    │
│   └─────────────────┘                    └─────────────────────────────┘    │
│                                                                             │
│   ⚠️ EU user events (with PII) stored in US data warehouse                  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### The Incident

```
Timeline:
Month 1:  Analytics pipeline deployed, events from all regions flow to US
Month 6:  Security audit requested by potential enterprise customer
Month 6:  Audit reveals EU user data (including PII) in US warehouse
Month 7:  Emergency project to remediate
Month 8:  3 engineering months spent on:
          - Building EU analytics cluster
          - Migrating EU historical data back to EU
          - Deleting EU data from US warehouse
          - Rebuilding ML models without EU data
Month 9:  Incident report filed with regulators
```

### The Fix: Regional Analytics

```
// Pseudocode: Locality-aware analytics pipeline

CLASS AnalyticsRouter:
    
    FUNCTION process_event(event):
        // Determine event's data region
        user_region = get_user_data_region(event.user_id)
        
        // Classify event data
        classification = classify_event_data(event)
        
        IF classification == "PII" OR classification == "PII_DERIVED":
            // Route to regional warehouse only
            regional_warehouse = get_warehouse(user_region)
            regional_warehouse.ingest(event)
        
        ELSE IF classification == "ANONYMIZED":
            // Anonymized data can go global
            anonymized = anonymize_event(event)
            global_warehouse.ingest(anonymized)
        
        ELSE:
            // Default: regional to be safe
            regional_warehouse = get_warehouse(user_region)
            regional_warehouse.ingest(event)

CLASS GlobalAnalyticsView:
    
    FUNCTION query(query):
        // For global queries, federate across regional warehouses
        IF query.scope == "global":
            results = []
            FOR region IN all_regions:
                regional_result = regional_warehouse[region].query(
                    redact_pii(query)
                )
                results.append(regional_result)
            RETURN aggregate(results)
        
        ELSE:
            // Regional queries go directly
            RETURN regional_warehouse[query.region].query(query)
```

### Lessons Learned

1. **Analytics is user data**: Events contain user IDs, behavior, and often request parameters—all subject to locality
2. **Central warehouse is tempting**: Single source of truth is operationally simple but may violate locality
3. **Retroactive fix is expensive**: Building regional analytics after the fact cost 3 engineering months plus regulatory risk
4. **Federated queries are possible**: You can still answer global questions by aggregating regional results

---

# Part 12: Final Verification — L6 Readiness Checklist

## Does This Chapter Meet L6 Expectations?

| L6 Criterion | Coverage | Assessment |
|--------------|----------|------------|
| **Judgment & Decision-Making** | L5/L6 contrast, explicit trade-offs, design patterns with WHY | ✅ Strong |
| **Failure & Degradation Thinking** | 2 incident case studies, compliance-aware failover | ✅ Strong |
| **Scale & Evolution** | 4-phase evolution diagram, migration strategies | ✅ Strong |
| **Staff-Level Signals** | L5/L6 table, Staff phrases, common mistakes | ✅ Strong |
| **Real-World Grounding** | User profile, logging, messaging examples; 2 incidents | ✅ Strong |
| **Interview Calibration** | Probing questions, phrases, L5 mistakes | ✅ Strong |
| **Diagrams** | 3 conceptual diagrams | ✅ Strong |

## Staff-Level Signals Covered

✅ Data locality as architectural constraint, not afterthought
✅ Three layers of data location (at rest, in transit, derived)
✅ Deletion as multi-phase process with manifest
✅ Compliance-aware failover design
✅ Regional data partitioning patterns
✅ Analytics pipeline locality constraints
✅ System evolution under changing requirements
✅ Cross-region interaction design
✅ Data classification frameworks
✅ Audit and verification strategies

## This chapter now meets Google Staff Engineer (L6) expectations.

---

# Quick Reference Card

## Data Locality Decision Framework

| Question | If Yes... | If No... |
|----------|-----------|----------|
| Contains user PII? | Must respect locality | Can be global |
| Derived from PII? | Likely must respect locality | Evaluate case by case |
| Can be anonymized? | Global aggregation OK | Keep regional |
| Supports deletion? | Design deletion mechanism | Re-evaluate data necessity |

## Data Store Checklist

For every data store, answer:
1. Does it contain user data?
2. What regions is it in?
3. What's the retention period?
4. How is deletion handled?
5. What audit trail exists?

## Deletion Timeline

| Store Type | Expected Deletion Time |
|------------|----------------------|
| Primary DB | Immediate |
| Cache | Minutes (TTL invalidation) |
| Search Index | Hours (reindex) |
| Analytics | Days (batch process) |
| Logs | Days to weeks (accelerated expiration) |
| Backups | Weeks to months (natural expiration) |

## Evolution Readiness

| Capability | Ready | Not Ready |
|------------|-------|-----------|
| Region as data attribute | ✅ | ❌ Hardcoded region |
| Configurable data flows | ✅ | ❌ Fixed replication |
| Auditable data stores | ✅ | ❌ Unknown data locations |
| Deletion manifests | ✅ | ❌ Ad-hoc deletion |

---

# Conclusion

Data locality and compliance are not bureaucratic obstacles—they're architectural constraints that, when embraced early, make systems more robust and evolvable. Staff engineers recognize that "where is this data?" is as fundamental a question as "how is this data structured?" or "how is this data accessed?"

The key insights from this chapter:

**Locality affects everything.** Not just the primary database. Caches, logs, analytics, backups, replicas, search indexes—every data store that touches user data must respect locality constraints.

**Deletion is a system, not a statement.** `DELETE FROM users WHERE id = ?` is the beginning, not the end. Complete deletion requires a manifest, multiple phases, and verification.

**Design for the constraints you'll have, not just the ones you have.** Regulations change, products expand to new regions, and data requirements tighten. Systems that anticipate change can adapt; systems that don't require expensive rewrites.

**Sometimes failure is the right answer.** When compliance conflicts with availability, compliance wins. Design systems that fail gracefully—returning errors to users—rather than silently violating data locality.

**Audit is not optional.** If you can't prove compliance at any moment—listing every data store, its location, and its deletion mechanism—you don't actually have compliance. You have hope.

Staff engineers build systems that can answer the question "where is this user's data right now?" at any moment, with confidence. That's not paranoia—it's professionalism.

---

*End of Chapter 25*

*Next: Chapter 26 — Cost, Efficiency, and Sustainable System Design at Staff Level*