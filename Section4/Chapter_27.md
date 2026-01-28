# Chapter 27: System Evolution, Migration, and Risk Management at Staff Level

---

# Introduction

Every successful system becomes a legacy system. The code that works today must change tomorrow—new requirements emerge, scale increases, costs become unsustainable, compliance mandates arrive, and the organization itself evolves. At Staff level, your job is not to avoid change but to make change safe.

I've led migrations that took years and touched every service in a product area. I've survived incidents caused by partial rollouts that left systems in inconsistent states. I've inherited architectures that were impossible to modify without risk of data loss. The difference between systems that can evolve and systems that calcify is not luck—it's design.

This chapter teaches system evolution and migration as Staff Engineers practice it: as a first-class design concern that shapes architecture from day one. We'll cover why migrations fail, how to design for change, how to identify and contain risk, and how to lead complex multi-team evolutions safely.

**The Staff Engineer's First Law of Evolution**: A system that cannot change safely is already failing. Evolution is not technical debt—it is the natural state of successful systems.

---

## Quick Visual: Evolution Thinking at a Glance

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    EVOLUTION: THE STAFF ENGINEER VIEW                       │
│                                                                             │
│   WRONG Framing: "Build it right, then maintain it"                         │
│   RIGHT Framing: "Build it to change safely"                                │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Before designing, understand:                                      │   │
│   │                                                                     │   │
│   │  1. What will force this system to change in 2 years? 5 years?      │   │
│   │  2. Which decisions are reversible? Which are one-way doors?        │   │
│   │  3. How will I migrate data without downtime?                       │   │
│   │  4. What's the blast radius if this migration fails?                │   │
│   │  5. How many teams must coordinate to make changes safely?          │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   THE UNCOMFORTABLE TRUTH:                                                  │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Migrations fail more often than greenfield projects.               │   │
│   │  The most dangerous code is the code that "just works."             │   │
│   │  You are evaluated on how you manage change, not avoid it.          │   │
│   │  Reversibility is more valuable than speed.                         │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## L5 vs L6 Evolution Decisions

| Scenario | L5 Approach | L6 Approach |
|----------|-------------|-------------|
| **New storage requirement** | "Let's add a new database for this feature" | "How will we migrate existing data? What's the dual-write period? Can we roll back if the new store fails?" |
| **Schema change** | "Add the column, backfill, deploy" | "What's the blast radius? Can we read old and new format simultaneously? How do we handle partial rollout?" |
| **Service decomposition** | "Split the service, update all callers" | "How many teams own callers? What's the migration timeline? Can both old and new coexist indefinitely?" |
| **Deprecating old system** | "Set a deadline, enforce it" | "What's the tail of long-tail users? Who owns the risk of forced migration? What's the escape hatch if we can't meet deadline?" |
| **Performance optimization** | "Rewrite the hot path" | "How do we prove the new path is correct? Can we shadow traffic first? What's the rollback plan?" |

**Key Difference**: L6 engineers treat every change as a potential incident. They design the migration before committing to the destination.

---

# Part 1: Foundations — Why Evolution Is the Default State

## Why All Non-Trivial Systems Must Evolve

A system that doesn't need to change is either trivial or dead. Every successful system faces pressure to evolve:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    WHY SYSTEMS MUST EVOLVE                                  │
│                                                                             │
│   EXTERNAL PRESSURE                          INTERNAL PRESSURE              │
│   ┌─────────────────────────────────┐       ┌─────────────────────────────┐ │
│   │  • Users grow from 1K to 1M     │       │  • Code becomes unmaint-    │ │
│   │  • New features required        │       │    ainable                  │ │
│   │  • Competitors force innovation │       │  • Dependencies go EOL      │ │
│   │  • Compliance laws change       │       │  • Original authors leave   │ │
│   │  • Data locality requirements   │       │  • Performance degrades     │ │
│   │  • Cost pressure increases      │       │  • Technical debt compounds │ │
│   └─────────────────────────────────┘       └─────────────────────────────┘ │
│                                                                             │
│   THE EVOLUTION CERTAINTY:                                                  │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  IF (system_is_successful):                                         │   │
│   │      system_will_need_to_change = TRUE                              │   │
│   │                                                                     │   │
│   │  IF (system_never_changes):                                         │   │
│   │      EITHER system_failed OR system_is_trivial                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Why Migrations Fail More Often Than Greenfield Builds

Building a new system is hard. Migrating a live system is harder. Here's why:

### The Migration Complexity Stack

```
// Pseudocode: Why migrations are harder

GREENFIELD_BUILD:
    requirements = gather_requirements()
    design = create_design(requirements)
    implement(design)
    test(implementation)
    deploy(implementation)
    // Done. No existing users, data, or dependencies.

MIGRATION:
    understand_current_system()           // Often poorly documented
    identify_all_dependencies()           // Hidden dependencies exist
    design_target_system()
    design_migration_path()               // NEW: Must plan the journey
    implement_backward_compatibility()    // NEW: Support old and new
    implement_dual_write()                // NEW: Data consistency
    migrate_incrementally()               // NEW: Can't stop serving traffic
    validate_correctness_continuously()   // NEW: Catch errors during migration
    handle_rollback_scenarios()           // NEW: Must be able to undo
    coordinate_with_all_consumers()       // NEW: Cross-team coordination
    maintain_both_systems_during_migration() // NEW: Double operational burden
    deprecate_old_system()                // NEW: Often takes longer than expected
```

### Migration Failure Modes

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    WHY MIGRATIONS FAIL                                      │
│                                                                             │
│   FAILURE MODE 1: INCOMPLETE UNDERSTANDING                                  │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  "We thought we knew all the callers"                               │   │
│   │  → Discovered batch job that runs monthly after cutover             │   │
│   │  → Job fails, data corruption ensues                                │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   FAILURE MODE 2: DATA INCONSISTENCY                                        │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  "Dual-write was supposed to keep both systems in sync"             │   │
│   │  → Edge case caused write to succeed in old, fail in new            │   │
│   │  → Data diverged, neither source of truth was complete              │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   FAILURE MODE 3: PERFORMANCE REGRESSION                                    │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  "The new system is faster in benchmarks"                           │   │
│   │  → Production traffic patterns differ from benchmarks               │   │
│   │  → P99 latency 3x worse, causing downstream timeouts                │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   FAILURE MODE 4: ROLLBACK IMPOSSIBLE                                       │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  "We'll just switch back if something goes wrong"                   │   │
│   │  → New system modified data in incompatible way                     │   │
│   │  → Old system can't read new format                                 │   │
│   │  → Stuck in broken state, no path forward or back                   │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   FAILURE MODE 5: TIMELINE EXPLOSION                                        │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  "Migration will take 3 months"                                     │   │
│   │  → Long-tail consumers can't migrate on schedule                    │   │
│   │  → 3 months becomes 18 months                                       │   │
│   │  → Team exhausted, system in permanent dual-state                   │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Designing for Correctness vs. Designing for Change

These are different skills, and both are necessary at Staff level.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│           CORRECTNESS VS. CHANGE: TWO DESIGN DIMENSIONS                     │
│                                                                             │
│   DESIGNING FOR CORRECTNESS:                                                │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Focus: Does the system produce correct output?                     │   │
│   │                                                                     │   │
│   │  • Invariants are maintained                                        │   │
│   │  • Edge cases are handled                                           │   │
│   │  • Failures are detected and recovered                              │   │
│   │  • Data is consistent                                               │   │
│   │                                                                     │   │
│   │  Question: "Is this system correct?"                                │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   DESIGNING FOR CHANGE:                                                     │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Focus: Can the system be modified safely?                          │   │
│   │                                                                     │   │
│   │  • Boundaries are clear and contracts are versioned                 │   │
│   │  • Data formats support extension                                   │   │
│   │  • Dependencies are explicit and replaceable                        │   │
│   │  • State can be migrated incrementally                              │   │
│   │                                                                     │   │
│   │  Question: "Can I change this system without breaking it?"          │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   STAFF-LEVEL INSIGHT:                                                      │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  A correct system that cannot change safely becomes incorrect       │   │
│   │  over time. Requirements drift. The world changes. A system that    │   │
│   │  cannot evolve eventually fails to meet its requirements.           │   │
│   │                                                                     │   │
│   │  Changeability is part of long-term correctness.                    │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Why Staff Engineers Are Evaluated on Managing Change

At Google L6, you're evaluated not on whether you can build a system, but on whether you can evolve systems across teams and years. This is explicit in the leveling criteria.

```
// Pseudocode: Staff Engineer change management evaluation

EVALUATION_CRITERIA for L6:
    // Technical excellence in ambiguity
    can_design_system_without_complete_requirements = TRUE
    can_anticipate_future_requirements = TRUE
    
    // Change management capability
    has_led_complex_migrations = TRUE
    has_maintained_availability_during_change = TRUE
    has_coordinated_change_across_multiple_teams = TRUE
    
    // Risk judgment
    can_identify_irreversible_decisions = TRUE
    can_quantify_blast_radius = TRUE
    can_design_rollback_strategies = TRUE
    
    // Impact
    changes_led_have_multi_team_impact = TRUE
    changes_were_completed_without_major_incidents = TRUE
```

### The System That Became Impossible to Modify

**Example**: A payments processing system at a mid-sized company

```
YEAR 1: System Launch
├── Single database with all payment data
├── Monolithic application with payment logic
├── 1,000 transactions/day
├── 2 engineers who built it
└── Works perfectly

YEAR 2: Growth
├── 50,000 transactions/day
├── Added fraud detection as stored procedures
├── Added reporting tables with triggers
├── Original engineers promoted to other teams
└── Still works, getting slower

YEAR 3: Compliance Requirement
├── New regulation: Must store EU data in EU region
├── Current state:
│   ├── All data in single US database
│   ├── 500+ stored procedures with business logic
│   ├── Triggers create cascading updates
│   ├── No documentation of data dependencies
│   └── No one understands the full system
├── Attempted changes:
│   ├── Add EU database replica → Triggers cause write conflicts
│   ├── Shard by region → Can't identify all cross-region queries
│   └── Migrate to new schema → Stored procedures break
└── Result: Impossible to modify without 12+ month rewrite

WHAT WENT WRONG:
├── Business logic in database, not application
├── Implicit dependencies via triggers
├── No contracts between components
├── Knowledge concentrated in departed engineers
└── No evolution planning at design time

WHAT STAFF ENGINEER WOULD HAVE DONE:
├── Business logic in application layer (replaceable)
├── Explicit data contracts, versioned
├── Change log instead of triggers
├── Data locality considered in initial schema
└── Migration playbook written at launch time
```

---

# Part 2: Types of Change Staff Engineers Must Handle

## Evolution Drivers and Their Technical Manifestations

Systems evolve for predictable reasons. Understanding these drivers helps you anticipate change.

### 1. Scale Growth

```
DRIVER: User base grows 10x-100x

TECHNICAL MANIFESTATION:
├── Database queries that were fast become slow (O(n) scans)
├── Single instances hit CPU/memory limits
├── Network bandwidth becomes bottleneck
├── Batch jobs that took 1 hour now take 24 hours
└── Cache hit rates drop as working set grows

NAIVE FIX:
├── Throw more hardware at the problem
├── Add caching everywhere
├── Increase timeout values
└── RISK: Masks underlying issues, creates operational complexity

STAFF-LEVEL APPROACH:
├── Identify the specific bottleneck (measure, don't guess)
├── Evaluate: horizontal scaling, sharding, architecture change?
├── Design migration path to new architecture
├── Implement incrementally with rollback capability
└── Accept short-term complexity for long-term sustainability
```

### 2. New Product Requirements

```
DRIVER: Product team needs features the architecture can't support

TECHNICAL MANIFESTATION:
├── Current data model doesn't fit new use case
├── New feature requires crossing service boundaries
├── Consistency model is wrong for new feature
├── Latency requirements are incompatible with current design
└── Authorization model doesn't extend

NAIVE FIX:
├── Bolt on new feature with workarounds
├── Create special cases in existing code
├── Add another database for the new data
└── RISK: Accumulates complexity, creates inconsistency

STAFF-LEVEL APPROACH:
├── Understand whether this is one feature or a pattern
├── If pattern: evolve the architecture to support it
├── If exception: contain it with clear boundaries
├── Design feature to be removable if requirements change
└── Document the trade-off explicitly
```

### 3. Performance Constraints

```
DRIVER: Latency or throughput no longer meets requirements

TECHNICAL MANIFESTATION:
├── P99 latency drifts up as load increases
├── Throughput plateaus below required capacity
├── Cold starts cause unacceptable latency spikes
├── Cross-region calls add unavoidable latency
└── Serialization/deserialization becomes bottleneck

NAIVE FIX:
├── Add more caching
├── Increase parallelism
├── "Optimize" by adding complexity
└── RISK: Obscures root cause, makes debugging harder

STAFF-LEVEL APPROACH:
├── Profile to identify actual bottleneck
├── Evaluate: is this algorithmic, I/O, or architectural?
├── Algorithmic: optimize the hot path
├── I/O: move data closer or prefetch
├── Architectural: may require significant redesign
└── Validate with production-representative load before rollout
```

### 4. Cost Pressure

```
DRIVER: Infrastructure cost exceeds sustainable level

TECHNICAL MANIFESTATION:
├── Compute costs grow faster than revenue
├── Storage costs compound (data never deleted)
├── Cross-region replication multiplies costs
├── Over-provisioning for peak creates waste
└── Observability data becomes dominant cost

NAIVE FIX:
├── Turn off replicas
├── Reduce redundancy
├── Delete "old" data
└── RISK: Sacrifices reliability, may lose important data

STAFF-LEVEL APPROACH:
├── Understand unit economics (cost per user, per request)
├── Identify largest cost drivers
├── Evaluate: can we change architecture to reduce unit cost?
├── Implement data lifecycle (hot/warm/cold/delete)
├── Right-size provisioning with acceptable burst handling
└── Accept that some costs are load-bearing
```

### 5. Compliance and Locality Changes

```
DRIVER: Legal or regulatory requirements force data handling changes

TECHNICAL MANIFESTATION:
├── Data must move to specific geographic regions
├── Access controls must be implemented/audited
├── Retention policies must be enforced
├── Encryption requirements change
└── Third-party data sharing must be controlled

NAIVE FIX:
├── Replicate data to compliant region
├── Add access controls at application layer
├── Write batch job to delete old data
└── RISK: Incomplete compliance, audit failures, data inconsistency

STAFF-LEVEL APPROACH:
├── Understand the actual legal requirements (work with legal/compliance)
├── Design compliance into data model, not bolted on
├── Implement data lineage tracking
├── Create audit capability from the start
├── Test compliance with adversarial scenarios
└── Plan for regulations to become stricter over time
```

### 6. Organizational Restructuring

```
DRIVER: Team boundaries change, ownership shifts

TECHNICAL MANIFESTATION:
├── Service ownership becomes unclear
├── Shared code has no clear maintainer
├── Different teams have conflicting requirements
├── Knowledge is lost when teams dissolve
└── Deployment coordination becomes complex

NAIVE FIX:
├── Assign ownership by fiat
├── Create "platform team" for shared components
├── Document everything (rarely maintained)
└── RISK: Ownership gaps, coordination overhead, velocity loss

STAFF-LEVEL APPROACH:
├── Design services with clear ownership boundaries
├── Minimize shared code, prefer shared contracts
├── Create self-service interfaces for cross-team use
├── Build systems that require fewer humans to operate safely
└── Accept that org changes will happen and design for it
```

---

# Part 3: Migration as a First-Class Design Concern

## Why Migrations Should Be Anticipated at Design Time

Every design decision creates a migration problem for your future self. Staff Engineers think about migrations while designing, not when forced to migrate.

```
// Pseudocode: Migration-aware design thinking

FUNCTION design_system(requirements):
    // Standard design process
    architecture = design_architecture(requirements)
    data_model = design_data_model(requirements)
    apis = design_apis(requirements)
    
    // Staff-level addition: migration analysis
    FOR EACH decision IN (architecture, data_model, apis):
        reversibility = assess_reversibility(decision)
        migration_cost = estimate_migration_cost(decision)
        future_flexibility = assess_future_flexibility(decision)
        
        IF reversibility == LOW AND migration_cost == HIGH:
            // This is a one-way door
            document_decision_rationale(decision)
            consider_alternatives(decision)
            require_senior_review(decision)
        
        IF future_flexibility == LOW:
            // This constrains future evolution
            add_extension_points(decision)
            version_the_interface(decision)
    
    RETURN design_with_migration_plan
```

## What Makes a Migration "High Risk"

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    HIGH-RISK MIGRATION INDICATORS                           │
│                                                                             │
│   DATA RISK                                                                 │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  □ Modifying primary data store (not just adding new store)         │   │
│   │  □ Changing data format in place (not adding new format)            │   │
│   │  □ Backfilling data that can't be regenerated                       │   │
│   │  □ Deleting or archiving data                                       │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   CONSISTENCY RISK                                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  □ Dual-write to multiple stores during transition                  │   │
│   │  □ Changing consistency model (strong → eventual or vice versa)     │   │
│   │  □ Migrating distributed state (locks, leases, coordination)        │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   COORDINATION RISK                                                         │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  □ Multiple teams must change simultaneously                        │   │
│   │  □ External clients must update (can't control their timeline)      │   │
│   │  □ Multiple services must deploy in specific order                  │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   REVERSIBILITY RISK                                                        │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  □ Rollback requires data re-migration                              │   │
│   │  □ Old system will be decommissioned before migration proves safe   │   │
│   │  □ New format is not backward-compatible                            │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   STAFF RULE:                                                               │
│   Count the checked boxes. More than 2 = require explicit rollback plan.    │
│   More than 4 = require incident response runbook before starting.          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## One-Way Doors vs. Two-Way Doors

This framing, popularized at Amazon, is critical for Staff-level decision making.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    ONE-WAY DOORS VS. TWO-WAY DOORS                          │
│                                                                             │
│   TWO-WAY DOOR (Reversible):                                                │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Can be undone easily and cheaply.                                  │   │
│   │  Bias toward action. Try it, learn, adjust.                         │   │
│   │                                                                     │   │
│   │  Examples:                                                          │   │
│   │  • Feature flag that can be toggled off                             │   │
│   │  • New API endpoint (can deprecate later)                           │   │
│   │  • Adding a new column (can remove if unused)                       │   │
│   │  • New service that reads from existing data                        │   │
│   │  • Configuration change                                             │   │
│   │                                                                     │   │
│   │  Staff approach: Move fast, monitor, iterate.                       │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   ONE-WAY DOOR (Irreversible):                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Cannot be undone, or reversal is extremely costly.                 │   │
│   │  Requires careful analysis before committing.                       │   │
│   │                                                                     │   │
│   │  Examples:                                                          │   │
│   │  • Deleting data (can't undelete)                                   │   │
│   │  • Breaking API change (clients depend on old behavior)             │   │
│   │  • Database migration that drops old columns                        │   │
│   │  • Multi-year vendor contract                                       │   │
│   │  • Schema change that loses information                             │   │
│   │                                                                     │   │
│   │  Staff approach: Slow down. Get alignment. Plan rollback.           │   │
│   │  Convert to two-way door if possible.                               │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   CONVERTING ONE-WAY TO TWO-WAY:                                            │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Instead of:           Do this:                                     │   │
│   │  ──────────────────    ─────────────────────────────────────────    │   │
│   │  Delete old column     Add new column, deprecate old, delete later  │   │
│   │  Remove old API        Add v2 API, run both, deprecate v1 later     │   │
│   │  Switch databases      Dual-write, prove new works, then cut over   │   │
│   │  Change data format    Support reading both, write new format       │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Migration Strategies (Conceptual)

### 1. Incremental Migration

```
STRATEGY: Migrate in small chunks, validate each chunk, continue.

WHEN TO USE:
├── Large dataset that can be partitioned
├── Migration logic is well-understood
├── Rollback at chunk level is acceptable
└── Timeline allows gradual migration

HOW IT WORKS:
├── Divide data/users/traffic into segments
├── Migrate one segment
├── Validate segment thoroughly
├── If problems: rollback segment, fix, retry
├── If success: continue to next segment
└── Repeat until complete

EXAMPLE: Migrating 1B rows to new schema
├── Segment by user_id modulo (100 segments)
├── Migrate segment 0, validate
├── Migrate segment 1, validate
├── ...continue...
├── If segment 50 has problems, only rollback segment 50
└── Total risk contained to 1% of data at any time
```

### 2. Backward Compatibility

```
STRATEGY: New code handles both old and new format; migrate format gradually.

WHEN TO USE:
├── Can't coordinate all consumers to upgrade simultaneously
├── Rollback must be instantaneous
├── Data format is changing
└── Multiple services read the data

HOW IT WORKS:
├── New code reads old format + new format
├── New code writes new format
├── Old data lazily migrated on read, or batch migrated
├── Once all data is new format, remove old format support
└── Backward compatibility code removed after verification

EXAMPLE: Adding field to data model
├── V1: { name: "Alice" }
├── V2: { name: "Alice", email: null }
├── New code reads both, defaults email to null if missing
├── New code writes V2 always
├── Backfill job converts V1 to V2
├── After verification, remove V1 handling
```

### 3. Dual-Read / Dual-Write (Conceptual)

```
STRATEGY: Write to both old and new system; read from one, compare with other.

WHEN TO USE:
├── Migrating to new storage or service
├── Need to prove new system correctness before cutover
├── Cannot afford data loss or inconsistency
└── Have capacity to run both systems

HOW IT WORKS:
├── PHASE 1: Dual-write enabled
│   ├── All writes go to old AND new system
│   ├── All reads from old system (trusted)
│   └── Compare old vs new reads (shadow mode)
├── PHASE 2: Cutover reads
│   ├── All writes still go to both
│   ├── All reads from new system
│   └── Still writing to old for rollback
├── PHASE 3: Decommission old
│   ├── Disable writes to old system
│   ├── Keep old system read-only for emergency
│   └── Eventually delete old system

RISKS:
├── Dual-write adds latency
├── Partial write failure causes inconsistency
├── Two systems must stay in sync
└── Increased operational complexity during migration
```

### 4. Shadow Traffic

```
STRATEGY: Send copy of production traffic to new system without affecting users.

WHEN TO USE:
├── Migrating to new service implementation
├── Need to validate performance under real load
├── Can replay requests safely (reads, or idempotent writes)
└── Have infrastructure to fork traffic

HOW IT WORKS:
├── Production traffic goes to old system (users served)
├── Copy of traffic sent to new system (result discarded)
├── Compare responses: old vs new
├── Measure latency: old vs new
├── When confident: cutover to new system

RISKS:
├── Side effects in new system (be careful with writes)
├── Shadow traffic doubles load
├── Comparison logic must handle acceptable differences
└── False positives in comparison can delay migration
```

### 5. Feature-Flag-Driven Rollout

```
STRATEGY: Gate new behavior behind flag; enable incrementally.

WHEN TO USE:
├── New code path is risky but reversible
├── Want to test with subset of users/traffic
├── Need instant rollback capability
└── Change is in application logic, not data format

HOW IT WORKS:
├── New code behind IF (flag_enabled(user, feature)):
├── Enable for 1% of users, monitor
├── Enable for 10%, monitor
├── Enable for 50%, monitor
├── Enable for 100%
├── If problems at any stage: disable flag instantly
└── After bake time: remove flag, remove old code

RISKS:
├── Flag combinations create test matrix explosion
├── Long-lived flags become technical debt
├── Must test both paths
└── Monitoring must be flag-aware
```

---

# Part 4: Risk Identification and Containment (Staff Thinking)

## How Staff Engineers Identify Risk Early

Risk identification is a discipline, not a talent. Staff Engineers systematically analyze change for risk.

```
// Pseudocode: Risk identification framework

FUNCTION identify_migration_risks(migration_plan):
    risks = []
    
    // Data risk analysis
    FOR EACH data_change IN migration_plan.data_changes:
        IF data_change.modifies_primary_store:
            risks.add(DataCorruptionRisk(data_change))
        IF data_change.is_destructive:
            risks.add(DataLossRisk(data_change))
        IF data_change.requires_backfill:
            risks.add(BackfillFailureRisk(data_change))
    
    // Dependency risk analysis
    FOR EACH service IN get_all_downstream_services():
        IF migration_affects(service):
            risks.add(DownstreamBreakageRisk(service))
    FOR EACH service IN get_all_upstream_services():
        IF migration_affects(service):
            risks.add(UpstreamBreakageRisk(service))
    
    // Consistency risk analysis
    IF migration_plan.uses_dual_write:
        risks.add(InconsistencyRisk(
            "Partial write failure can cause data divergence"
        ))
    IF migration_plan.changes_consistency_model:
        risks.add(InconsistencyRisk(
            "Application may rely on old consistency guarantees"
        ))
    
    // Coordination risk analysis
    teams_involved = get_teams_affected(migration_plan)
    IF len(teams_involved) > 2:
        risks.add(CoordinationRisk(teams_involved))
    
    // Reversibility analysis
    IF NOT migration_plan.has_rollback_plan:
        risks.add(IrreversibilityRisk(
            "No documented rollback procedure"
        ))
    IF migration_plan.rollback_requires_data_migration:
        risks.add(IrreversibilityRisk(
            "Rollback is not instant—requires data migration"
        ))
    
    RETURN risks
```

## Blast Radius Analysis

Blast radius is the scope of impact if something goes wrong. Staff Engineers always quantify this.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    BLAST RADIUS ANALYSIS FRAMEWORK                          │
│                                                                             │
│   QUESTION 1: What breaks if this fails?                                    │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  □ Single feature        (low: users can use other features)        │   │
│   │  □ Single service        (medium: one product area affected)        │   │
│   │  □ Multiple services     (high: multiple product areas affected)    │   │
│   │  □ All services          (critical: full outage)                    │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   QUESTION 2: How many users are affected?                                  │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  □ < 1%     (low: canary population)                                │   │
│   │  □ 1-10%    (medium: significant but contained)                     │   │
│   │  □ 10-50%   (high: major impact)                                    │   │
│   │  □ > 50%    (critical: majority of users)                           │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   QUESTION 3: Is the impact recoverable?                                    │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  □ Auto-recovers in seconds    (low: users may not notice)          │   │
│   │  □ Recovers with rollback      (medium: minutes of impact)          │   │
│   │  □ Requires manual fix         (high: hours of impact)              │   │
│   │  □ Data loss / unrecoverable   (critical: permanent impact)         │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   QUESTION 4: What's the business impact?                                   │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  □ Internal users only        (low: productivity loss)              │   │
│   │  □ External users, free tier  (medium: reputation risk)             │   │
│   │  □ Paying customers           (high: revenue at risk)               │   │
│   │  □ Regulated / financial      (critical: legal / compliance risk)   │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   BLAST RADIUS SCORE:                                                       │
│   Sum the highest selected level across all questions.                      │
│   Low × 4 = safe to proceed quickly                                         │
│   Any Medium = need monitoring and rollback plan                            │
│   Any High = staged rollout required                                        │
│   Any Critical = require incident response readiness before proceeding      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Control Plane vs. Data Plane Risk

Different kinds of changes carry fundamentally different risks.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CONTROL PLANE VS. DATA PLANE RISK                        │
│                                                                             │
│   DATA PLANE:                                                               │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  The path that user data travels.                                   │   │
│   │  High volume, latency-sensitive, directly visible to users.         │   │
│   │                                                                     │   │
│   │  Examples:                                                          │   │
│   │  • API request handling                                             │   │
│   │  • Database reads and writes                                        │   │
│   │  • User-facing computations                                         │   │
│   │                                                                     │   │
│   │  Risk profile:                                                      │   │
│   │  • Failures are immediately visible                                 │   │
│   │  • High volume means more chances for failure                       │   │
│   │  • But: failures are usually detected quickly                       │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   CONTROL PLANE:                                                            │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  The path that configures/manages the data plane.                   │   │
│   │  Low volume, but affects all data plane operations.                 │   │
│   │                                                                     │   │
│   │  Examples:                                                          │   │
│   │  • Configuration deployment                                         │   │
│   │  • Service discovery                                                │   │
│   │  • Rate limit configuration                                         │   │
│   │  • Feature flags                                                    │   │
│   │                                                                     │   │
│   │  Risk profile:                                                      │   │
│   │  • Failures affect ALL data plane operations                        │   │
│   │  • Low volume means failures may go unnoticed initially             │   │
│   │  • Control plane bugs have multiplied impact                        │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   STAFF INSIGHT:                                                            │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Control plane changes are often MORE dangerous than data plane     │   │
│   │  changes, despite appearing lower-risk (fewer requests, simpler     │   │
│   │  code). A bad config push can take down everything instantly.       │   │
│   │                                                                     │   │
│   │  Rule: Control plane changes need MORE caution, not less.           │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Why Reversibility Matters More Than Speed

```
// Pseudocode: The reversibility principle

SCENARIO: Two migration approaches

APPROACH A: Fast, Irreversible
    time_to_complete = 2 weeks
    rollback_time = 4 weeks (requires reverse migration)
    if_failure_detected:
        impact_duration = rollback_time = 4 weeks
        // Plus reputational/data damage during that time

APPROACH B: Slow, Reversible  
    time_to_complete = 4 weeks
    rollback_time = 5 minutes (feature flag)
    if_failure_detected:
        impact_duration = detection_time + 5 minutes
        // Minimal damage, can retry after fixing

EXPECTED VALUE CALCULATION:
    probability_of_failure = 0.10  // 10% chance something goes wrong
    
    APPROACH A expected_cost:
        0.90 * 2_weeks + 0.10 * (2_weeks + 4_weeks + damage)
        = 1.8 weeks + 0.1 * (6 weeks + damage)
        = 2.4 weeks + damage_risk
    
    APPROACH B expected_cost:
        0.90 * 4_weeks + 0.10 * (4_weeks + 1_hour + minimal_damage)
        = 3.6 weeks + 0.1 * (4 weeks + 1 hour)
        ≈ 4.0 weeks + negligible_damage_risk

STAFF INSIGHT:
    If damage_risk > 2 weeks of engineering time (it usually is):
        APPROACH B is strictly better
    
    The goal is not "finish fast."
    The goal is "finish safely, and be able to recover if wrong."
```

## Risks Staff Engineers Accept vs. Refuse

```
┌─────────────────────────────────────────────────────────────────────────────┐
│            RISKS STAFF ENGINEERS CONSCIOUSLY ACCEPT                         │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  □ Slightly longer migration timeline for reversibility             │   │
│   │  □ Increased operational complexity during transition               │   │
│   │  □ Temporary performance degradation (if bounded and monitored)     │   │
│   │  □ Dual-system costs during migration period                        │   │
│   │  □ Additional testing/validation overhead                           │   │
│   │  □ Feature velocity reduction during migration                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│            RISKS STAFF ENGINEERS REFUSE TO TAKE                             │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  ✗ Irreversible change without proven rollback                      │   │
│   │  ✗ Data migration without verification step                         │   │
│   │  ✗ Big-bang cutover without canary                                  │   │
│   │  ✗ Control plane change without gradual rollout                     │   │
│   │  ✗ Migration that requires all teams to coordinate simultaneously   │   │
│   │  ✗ "We'll fix it in production if something breaks"                 │   │
│   │  ✗ Deleting the old system before new system is proven              │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   STAFF PRINCIPLE:                                                          │
│   "I will accept slowness. I will accept complexity. I will accept cost.    │
│    I will not accept unrecoverable failure modes."                          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Part 4B: Real-World Migration Patterns (Grounded Examples)

The migration strategies above are conceptual. Here's how they apply to real systems Staff Engineers actually build.

## Example 1: Rate Limiter Migration (Redis to Distributed Service)

```
SYSTEM: Global rate limiter used by API gateway
CURRENT STATE: Redis-based counters, single region
TRIGGER: Need multi-region support with local enforcement

MIGRATION CHALLENGE:
├── Rate limiter is in hot path (every request)
├── Latency budget: < 1ms added
├── Accuracy requirement: ±10% of limit
├── Blast radius if broken: ALL API traffic rejected or ALL limits bypassed
└── Can't take downtime—this is critical infrastructure

STAFF-LEVEL MIGRATION PLAN:

Phase 1: Abstract the Rate Limiter Interface
    // Current: Direct Redis calls scattered in code
    // Target: Interface that can have multiple implementations
    
    INTERFACE RateLimiter:
        check_and_increment(key, limit, window) → RateLimitResult
        get_current_count(key, window) → count
    
    // Deploy abstraction, Redis still behind it
    // Rollback: Revert abstraction, no behavior change
    // Risk: LOW

Phase 2: Implement New Distributed Rate Limiter
    // Build new service but don't route traffic to it
    // Run load tests, chaos tests
    // Validate accuracy against known inputs
    // Rollback: Delete new service
    // Risk: LOW (not in production path)

Phase 3: Shadow Mode with Comparison
    FUNCTION check_rate_limit(key, limit, window):
        redis_result = redis_limiter.check(key, limit, window)
        
        // Shadow call—async, non-blocking
        async:
            new_result = new_limiter.check(key, limit, window)
            compare_results(redis_result, new_result)
            IF mismatch > threshold:
                alert("Rate limiter divergence detected")
        
        RETURN redis_result  // Redis still authoritative
    
    // Rollback: Disable shadow calls
    // Risk: LOW (shadow doesn't affect traffic)

Phase 4: Canary with Fallback (1% traffic)
    FUNCTION check_rate_limit(key, limit, window):
        IF canary_enabled(key, 1%):
            TRY:
                result = new_limiter.check(key, limit, window)
                IF result.latency > 5ms:
                    // Too slow, fall back
                    increment_metric("new_limiter_latency_fallback")
                    RETURN redis_limiter.check(key, limit, window)
                RETURN result
            CATCH timeout, error:
                increment_metric("new_limiter_error_fallback")
                RETURN redis_limiter.check(key, limit, window)
        ELSE:
            RETURN redis_limiter.check(key, limit, window)
    
    // Key metrics to monitor:
    // - new_limiter_latency_p99 (must stay < 1ms)
    // - new_limiter_error_rate (must stay < 0.01%)
    // - rate_limit_accuracy_divergence (compare decisions)
    // - downstream_429_rate (should not spike)
    
    // Rollback: Set canary to 0%
    // Risk: MEDIUM (real traffic, but contained)

Phase 5: Gradual Ramp (1% → 10% → 50% → 100%)
    // Each stage requires:
    // - 24 hours at current percentage with clean metrics
    // - No latency regression
    // - No accuracy divergence
    // - No increase in customer complaints
    
    // Abort criteria:
    // - P99 latency > 2ms (normal is < 0.5ms)
    // - Error rate > 0.1%
    // - Accuracy divergence > 15%
    
    // Rollback: Reduce percentage (instant)
    // Risk: MEDIUM → HIGH (increasing with percentage)

Phase 6: Deprecate Redis Rate Limiter
    // After 2 weeks at 100% with clean metrics
    // Remove Redis calls, keep code path as dead code initially
    // Rollback: Re-enable Redis code path
    // Risk: MEDIUM

Phase 7: Remove Redis Infrastructure (ONE-WAY DOOR)
    // After 1 month of stable operation
    // Delete Redis cluster used for rate limiting
    // No rollback—would require rebuilding Redis cluster
    // Risk: HIGH—only proceed with high confidence

FAILURE SCENARIO DURING THIS MIGRATION:

Day 15, at 50% traffic on new limiter:
├── New limiter has bug: doesn't reset counters at window boundary
├── Users at 50% hit rate limit, stay rate limited forever
├── Detection: Spike in 429 errors for specific user cohort
├── Response: Set percentage to 0% (instant rollback)
├── Impact: 50% of users experienced rate limiting for 12 minutes
├── Root cause: Off-by-one error in window calculation
├── Fix: Deploy fix, restart canary at 1%

STAFF INSIGHT:
The rate limiter is control plane for all traffic. Migration here requires 
more caution than typical data plane migrations. 24-hour bake times at each 
percentage are justified by the blast radius.
```

## Example 2: News Feed Migration (Fan-out-on-Write to Fan-out-on-Read)

```
SYSTEM: Social media news feed
CURRENT STATE: Fan-out-on-write (precompute feeds for all followers)
TRIGGER: Celebrity accounts with 10M+ followers cause write amplification

MIGRATION CHALLENGE:
├── Both architectures are valid—different trade-offs
├── Current: Fast reads, slow writes for popular users
├── Target: Hybrid—fan-out-on-write for normal, fan-out-on-read for celebrities
├── Data model changes required
├── User experience cannot degrade during migration
└── Feed consistency expectations are high

STAFF-LEVEL MIGRATION PLAN:

Phase 1: Classify Users (No Behavior Change)
    // Determine threshold for "celebrity" accounts
    FUNCTION is_celebrity(user_id):
        follower_count = get_follower_count(user_id)
        RETURN follower_count > 100,000
    
    // Add classification to user metadata
    // Rollback: Remove classification field
    // Risk: LOW

Phase 2: Dual-Write for Celebrity Posts
    FUNCTION post_content(user_id, content):
        // Write to posts table (existing)
        post_id = save_post(user_id, content)
        
        IF is_celebrity(user_id):
            // NEW: Also write to celebrity_posts table
            save_celebrity_post(user_id, post_id, content)
            // DON'T fan out to followers—will be read on demand
        ELSE:
            // Existing: Fan out to all followers
            fan_out_to_followers(user_id, post_id)
        
        RETURN post_id
    
    // Rollback: Remove celebrity_posts writes
    // Risk: LOW (additional write, no read path change)

Phase 3: Hybrid Read Path (Feature Flagged)
    FUNCTION get_feed(user_id):
        // Get precomputed feed items (existing)
        precomputed = get_precomputed_feed(user_id)
        
        IF feature_flag("hybrid_feed", user_id):
            // NEW: Also fetch recent celebrity posts
            celebrity_following = get_celebrity_following(user_id)
            celebrity_posts = fetch_recent_celebrity_posts(celebrity_following)
            
            // Merge and sort by timestamp
            merged_feed = merge_and_sort(precomputed, celebrity_posts)
            
            // Compare with what pure fan-out-on-write would have shown
            // (shadow comparison for validation)
            async:
                expected_feed = simulate_old_behavior(user_id)
                compare_feeds(merged_feed, expected_feed)
            
            RETURN merged_feed
        ELSE:
            RETURN precomputed
    
    // Rollback: Disable feature flag
    // Risk: MEDIUM (changes user-visible behavior)

Phase 4: Backfill Historical Celebrity Posts
    // Move posts from fan-out approach to celebrity_posts table
    // Idempotent—can run multiple times
    // Rollback: Not needed—old approach still works
    // Risk: LOW

Phase 5: Gradual Rollout of Hybrid Reads
    // 1% → 10% → 50% → 100%
    // Monitor:
    // - Feed load latency (should not increase significantly)
    // - Feed completeness (users shouldn't miss posts)
    // - Celebrity post visibility (should appear in feeds)
    
    // Rollback: Reduce flag percentage
    // Risk: MEDIUM

Phase 6: Stop Fan-out for Celebrities
    // Celebrity posts no longer fan out to follower feeds
    // This saves the write amplification
    // Rollback: Resume fan-out (but feeds might have duplicates)
    // Risk: MEDIUM

FAILURE SCENARIO:

Week 3, at 25% hybrid reads:
├── Bug: Time zone issue causes celebrity posts to appear out of order
├── User reports: "My feed is showing old posts first"
├── Detection: User complaints + feed freshness metrics
├── Response: Reduce feature flag to 0%
├── Impact: 25% of users saw out-of-order feeds for 4 hours
├── Fix: Correct timestamp handling, restart at 1%

STAFF INSIGHT:
Feed ranking is subtle—"correct" is not always obvious. Users don't complain
about missing posts they never knew about, but they DO complain about wrong
ordering. Monitor the metrics users actually care about.
```

## Example 3: API Gateway Migration (Monolith to Microservices Gateway)

```
SYSTEM: API Gateway handling all external requests
CURRENT STATE: Monolithic gateway with routing, auth, rate limiting, logging
TRIGGER: Gateway is deployment bottleneck; teams can't update routing independently

MIGRATION CHALLENGE:
├── Gateway is single point of entry—failure = full outage
├── Current gateway handles 100K requests/second
├── Multiple concerns intertwined (auth, routing, rate limiting)
├── Teams have tribal knowledge of routing rules
└── Can't afford downtime or request loss

STAFF-LEVEL APPROACH:

Phase 1: Extract Configuration from Code
    // Move hardcoded routing rules to configuration
    // No behavior change—just separation
    // Rollback: Revert config extraction
    // Risk: LOW

Phase 2: Introduce Sidecar Pattern
    // Deploy new routing logic as sidecar alongside existing gateway
    // Sidecar receives shadow traffic, doesn't respond to users
    // Compare sidecar routing decisions with existing gateway
    
    TRAFFIC FLOW:
    Client → Load Balancer → [Existing Gateway] → Backend Services
                           ↘ [Sidecar] (shadow, discard response)
    
    // Rollback: Remove sidecar
    // Risk: LOW

Phase 3: Blue-Green Traffic Split
    // Route percentage of traffic to new gateway
    // Both gateways route to SAME backend services
    
    TRAFFIC FLOW:
    Client → Load Balancer ─┬─(90%)─→ [Existing Gateway] → Backend
                           └─(10%)─→ [New Gateway] → Backend (same)
    
    // Key: Same backends, so no data consistency issues
    // Only routing logic is being tested
    
    // Rollback: Route 100% to existing
    // Risk: MEDIUM

Phase 4: Gradual Traffic Shift
    // 10% → 25% → 50% → 75% → 100%
    // At each stage:
    // - Compare latency distributions
    // - Compare error rates
    // - Validate routing correctness (same backend selected)
    
    // Abort if:
    // - P99 latency increases > 10%
    // - Error rate increases > 0.01%
    // - Any routing decision differs

Phase 5: Decommission Old Gateway
    // After 2 weeks at 100% on new gateway
    // Remove old gateway from production
    // Keep code for emergency rollback
    // Risk: MEDIUM

FAILURE DURING MIGRATION:

At 50% traffic on new gateway:
├── New gateway has memory leak—OOMs under sustained load
├── Detection: New gateway pods restarting, latency spikes
├── Response: Route 0% to new gateway (instant)
├── Impact: 50% of users experienced 30-second latency spike
├── Fix: Identify and fix memory leak, restart at 10%

STAFF INSIGHT:
API Gateway is a "thin waist" in the architecture—everything passes through.
The blast radius is always 100% of traffic. This justifies extremely 
conservative rollout percentages and extended bake times.
```

---

# Part 4C: Migration Observability and Metrics

Migrations fail silently more often than they fail loudly. Staff Engineers design observability into the migration itself.

## What to Monitor During Any Migration

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    MIGRATION OBSERVABILITY CHECKLIST                        │
│                                                                             │
│   CATEGORY 1: FUNCTIONAL CORRECTNESS                                        │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  □ Old vs. new system output comparison (shadow mode)               │   │
│   │  □ Data consistency between old and new stores                      │   │
│   │  □ Business logic correctness (same decisions made)                 │   │
│   │  □ Edge case handling (nulls, empty collections, Unicode, etc.)     │   │
│   │                                                                     │   │
│   │  Failure signal: Divergence in any of the above                     │   │
│   │  Action: Pause migration, investigate, fix, resume                  │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   CATEGORY 2: PERFORMANCE                                                   │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  □ P50, P95, P99 latency for new path vs. old path                  │   │
│   │  □ Throughput capacity of new system                                │   │
│   │  □ Resource utilization (CPU, memory, connections)                  │   │
│   │  □ Downstream service impact (are we pushing load elsewhere?)       │   │
│   │                                                                     │   │
│   │  Failure signal: Latency regression > X% or resource exhaustion     │   │
│   │  Action: Rollback traffic percentage, investigate                   │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   CATEGORY 3: ERROR RATES                                                   │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  □ Error rate on new path vs. baseline                              │   │
│   │  □ Error types (timeouts, validation, downstream failures)          │   │
│   │  □ Retry rates (are clients retrying more?)                         │   │
│   │  □ Circuit breaker trips                                            │   │
│   │                                                                     │   │
│   │  Failure signal: Error rate > baseline + threshold                  │   │
│   │  Action: Automatic rollback if threshold exceeded                   │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   CATEGORY 4: DATA MIGRATION PROGRESS                                       │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  □ Percentage of data migrated                                      │   │
│   │  □ Migration throughput (rows/second, events/second)                │   │
│   │  □ Backpressure indicators                                          │   │
│   │  □ Time to completion estimate                                      │   │
│   │                                                                     │   │
│   │  Failure signal: Migration stalled or throughput dropping           │   │
│   │  Action: Investigate bottleneck, adjust rate limiting               │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   CATEGORY 5: ROLLBACK CAPABILITY                                           │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  □ Old system still healthy and ready to receive traffic            │   │
│   │  □ Time since last rollback test                                    │   │
│   │  □ Data sync lag between systems (can we roll back cleanly?)        │   │
│   │  □ Rollback automation working (tested recently)                    │   │
│   │                                                                     │   │
│   │  Failure signal: Rollback path degraded or unavailable              │   │
│   │  Action: STOP migration progress until rollback restored            │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Quantified Migration Decision Thresholds

```
// Pseudocode: Automated migration progression/rollback

MIGRATION_THRESHOLDS:
    // Thresholds for advancing to next percentage
    advance_criteria:
        min_time_at_current_stage: 24 hours
        max_latency_p99_increase: 10%
        max_error_rate_increase: 0.01%
        min_shadow_correctness: 99.9%
        rollback_path_healthy: TRUE
    
    // Thresholds for automatic rollback
    rollback_criteria:
        latency_p99_increase: > 50%
        error_rate: > 0.5%
        data_inconsistency_detected: TRUE
        rollback_path_unhealthy: TRUE
    
    // Thresholds for pausing and alerting
    pause_criteria:
        latency_p99_increase: > 20%
        error_rate: > 0.1%
        shadow_correctness: < 99.5%

FUNCTION evaluate_migration_health():
    metrics = collect_current_metrics()
    
    IF meets_any(metrics, rollback_criteria):
        execute_automatic_rollback()
        page_oncall("Migration auto-rollback triggered")
        RETURN ROLLED_BACK
    
    IF meets_any(metrics, pause_criteria):
        pause_migration_progress()
        alert_team("Migration paused for investigation")
        RETURN PAUSED
    
    IF meets_all(metrics, advance_criteria):
        RETURN READY_TO_ADVANCE
    
    RETURN STABLE_NOT_READY

// Run this evaluation continuously during migration
SCHEDULE evaluate_migration_health() EVERY 5 minutes
```

## Cost of Running Dual Systems

Staff Engineers quantify the cost of migration, not just the benefit.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    MIGRATION COST ANALYSIS                                  │
│                                                                             │
│   SCENARIO: Database migration from PostgreSQL to distributed store         │
│                                                                             │
│   PHASE           DURATION    INFRA COST     ENG COST      TOTAL/MONTH      │
│   ─────────────────────────────────────────────────────────────────────     │
│   Pre-migration   Baseline    $10K/mo        $0             $10K            │
│   Dual-write      8 weeks     $10K + $12K    $20K (2 eng)   $42K            │
│   Shadow + canary 4 weeks     $10K + $12K    $15K (1.5 eng) $37K            │
│   Ramp (50%)      4 weeks     $10K + $12K    $10K (1 eng)   $32K            │
│   Full traffic    2 weeks     $8K + $12K     $5K            $25K            │
│   Decommission    1 week      $12K           $2K            $14K            │
│   Post-migration  Ongoing     $12K           $0             $12K            │
│                                                                             │
│   TOTAL MIGRATION COST:                                                     │
│   ├── Infrastructure: ~$80K additional over 4 months                        │
│   ├── Engineering: ~$150K (3 engineers × 4 months fully loaded)             │
│   ├── Opportunity cost: ~$100K (features not built)                         │
│   └── TOTAL: ~$330K                                                         │
│                                                                             │
│   BENEFIT (annual):                                                         │
│   ├── Reduced infra cost: $10K → $8K = $24K/year savings                    │
│   ├── Improved latency → higher conversion: ~$200K/year                     │
│   ├── Reduced operational burden: ~$50K/year (less on-call time)            │
│   └── TOTAL: ~$274K/year benefit                                            │
│                                                                             │
│   PAYBACK PERIOD: ~14 months                                                │
│                                                                             │
│   STAFF JUDGMENT:                                                           │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Is 14-month payback acceptable?                                    │   │
│   │  • If system is stable and migration is optional: Maybe defer       │   │
│   │  • If current system is hitting limits: Accept the cost             │   │
│   │  • If team is small: Consider opportunity cost more heavily         │   │
│   │  • Factor in: risk of migration failure adds to expected cost       │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Part 5: Applied Migration Scenarios

## Scenario 1: Database Schema Migration for a Live System

### Context

A user profile service stores data in a relational database. The original schema stored user preferences as a JSON blob in a single column. As the product evolved, specific preference fields need to be queryable and indexed.

### Initial State

```
TABLE: user_profiles
├── user_id (PRIMARY KEY)
├── name (VARCHAR)
├── email (VARCHAR)  
├── preferences (JSON BLOB)
│   └── Contains: { theme: "dark", notifications: true, language: "en", ... }
└── created_at (TIMESTAMP)

TRAFFIC:
├── 10,000 reads/second
├── 1,000 writes/second
├── 50M total rows
└── Queries on preferences require full table scan

PROBLEM:
├── Product needs to query "all users with notifications=true"
├── Current query takes 45 minutes (full scan)
├── Feature team blocked, business requirement unmet
└── Must migrate without downtime
```

### Trigger for Change

Product team needs to send targeted notifications based on preference settings. Current architecture cannot support this without unacceptable query times.

### Migration Plan

```
PHASE 1: Add New Columns (Week 1)
├── Add columns: pref_notifications (BOOLEAN), pref_language (VARCHAR)
├── Columns are nullable, default NULL
├── No application changes yet
├── Rollback: Drop columns
└── Risk: LOW (additive change, no data modification)

PHASE 2: Dual-Write (Week 2)
├── Application writes to JSON blob AND new columns
├── Application still reads from JSON blob (source of truth)
├── Verify new columns match JSON for new writes
├── Rollback: Stop writing to new columns
└── Risk: LOW (new columns are redundant, not authoritative)

PHASE 3: Backfill Historical Data (Week 3-4)
├── Batch job reads JSON, populates new columns
├── Process in chunks of 10,000 rows
├── Validate each chunk: new columns match JSON
├── Checkpoint progress, resumable if interrupted
├── Rollback: Stop backfill (new columns become incomplete)
└── Risk: MEDIUM (batch job could affect production load)

Backfill pseudocode:
    FUNCTION backfill_preferences():
        last_processed_id = get_checkpoint()
        
        WHILE TRUE:
            batch = SELECT * FROM user_profiles 
                    WHERE user_id > last_processed_id
                    ORDER BY user_id
                    LIMIT 10000
            
            IF batch.empty():
                BREAK
            
            FOR row IN batch:
                preferences = parse_json(row.preferences)
                UPDATE user_profiles 
                SET pref_notifications = preferences.notifications,
                    pref_language = preferences.language
                WHERE user_id = row.user_id
                
            last_processed_id = batch.last().user_id
            save_checkpoint(last_processed_id)
            
            // Rate limit to avoid production impact
            sleep(100ms)

PHASE 4: Add Indexes (Week 5)
├── CREATE INDEX on pref_notifications
├── CREATE INDEX on pref_language
├── Run during low-traffic window
├── Rollback: Drop indexes
└── Risk: MEDIUM (index creation can affect write performance)

PHASE 5: Cutover Reads (Week 6)
├── Application reads from new columns (with fallback to JSON)
├── Monitor for any discrepancies
├── Feature flag controls read path
├── Rollback: Flip feature flag to read from JSON
└── Risk: MEDIUM (if discrepancy exists, queries return wrong data)

Read pseudocode:
    FUNCTION get_user_preferences(user_id):
        row = SELECT * FROM user_profiles WHERE user_id = user_id
        
        IF feature_flag("read_from_new_columns"):
            IF row.pref_notifications IS NOT NULL:
                RETURN {
                    notifications: row.pref_notifications,
                    language: row.pref_language
                }
            ELSE:
                // Fallback for unbackfilled rows
                log_warning("Reading from JSON fallback")
                RETURN parse_json(row.preferences)
        ELSE:
            RETURN parse_json(row.preferences)

PHASE 6: Deprecate JSON Blob (Week 8+)
├── Stop writing to JSON blob
├── JSON blob becomes stale but exists
├── Monitor for any code still reading JSON
├── Rollback: Resume writing to JSON blob
└── Risk: LOW (JSON still exists, just stale)

PHASE 7: Remove JSON Column (Month 6+)
├── After long bake time, drop preferences column
├── This is a ONE-WAY DOOR
├── Only after extensive validation
├── No rollback possible
└── Risk: HIGH (data deleted, must be certain)
```

### Failure Points

```
FAILURE POINT 1: Backfill Job Affects Production
├── Symptom: Write latency increases during backfill
├── Detection: Latency alerts fire
├── Response: Pause backfill job
├── Prevention: Rate limiting in backfill, run during low traffic

FAILURE POINT 2: Backfill Data Mismatch
├── Symptom: New columns don't match JSON (parsing bug)
├── Detection: Validation queries during backfill
├── Response: Fix parsing, re-run backfill for affected rows
├── Prevention: Extensive testing of parsing logic

FAILURE POINT 3: Read Cutover Returns Wrong Data
├── Symptom: Users see incorrect preferences
├── Detection: User reports, comparison monitoring
├── Response: Flip feature flag to read from JSON
├── Prevention: Shadow reads comparing both paths before cutover
```

### Rollback Strategy

```
ROLLBACK BY PHASE:

Phase 1 (Add columns): DROP COLUMN, no data impact
Phase 2 (Dual-write): Stop writing to new columns
Phase 3 (Backfill): Stop backfill, new columns incomplete but unused
Phase 4 (Indexes): DROP INDEX
Phase 5 (Read cutover): Feature flag flip (instant)
Phase 6 (Deprecate writes): Resume writing to JSON
Phase 7 (Drop column): NO ROLLBACK POSSIBLE

CRITICAL INSIGHT:
├── Phases 1-6 are all reversible
├── Phase 7 is a one-way door
├── Do not proceed to Phase 7 until 100% confident
└── Keep JSON column for months as insurance
```

### Final Stable State

```
TABLE: user_profiles
├── user_id (PRIMARY KEY)
├── name (VARCHAR)
├── email (VARCHAR)
├── pref_notifications (BOOLEAN, indexed)
├── pref_language (VARCHAR, indexed)
├── [preferences column DROPPED]
└── created_at (TIMESTAMP)

IMPROVEMENTS:
├── Query for notifications=true: 45 min → 200ms
├── No JSON parsing overhead on reads
├── Clear schema, better tooling support
└── Feature team unblocked
```

---

## Scenario 2: Service Decomposition (Monolith to Microservices)

### Context

A monolithic e-commerce backend handles orders, inventory, and payments in a single service. The system has grown to the point where:
- Deployments are risky (all functionality in one release)
- Different components have different scaling needs
- Team ownership is unclear
- Development velocity is declining

### Initial State

```
MONOLITH: ecommerce-backend
├── /api/orders        (Order management)
├── /api/inventory     (Inventory checks and updates)
├── /api/payments      (Payment processing)
├── Single database with all tables
├── Shared code: validation, logging, auth
└── Single deployment artifact

PROBLEMS:
├── Inventory team wants to deploy 5x/day
├── Payments team wants to deploy 1x/week (compliance)
├── Order spike requires scaling entire monolith
├── Inventory bug took down payments last month
└── On-call rotation covers too much surface area
```

### Trigger for Change

A critical payment processing bug was caused by an inventory code change. The incident exposed the coupling risk. Leadership mandated separation of payment processing for compliance and reliability.

### Migration Plan

```
PHASE 1: Identify Boundaries (Week 1-4)
├── Map all internal dependencies
├── Identify shared code and data
├── Define API contracts between future services
├── Document what calls what
└── Risk: LOW (analysis only)

Dependency analysis pseudocode:
    FUNCTION map_dependencies():
        components = [Orders, Inventory, Payments]
        dependencies = {}
        
        FOR component IN components:
            dependencies[component] = {
                calls: find_all_function_calls(component),
                data_reads: find_all_table_reads(component),
                data_writes: find_all_table_writes(component),
                shared_code: find_shared_code_usage(component)
            }
        
        // Identify problematic dependencies
        FOR component IN components:
            FOR call IN dependencies[component].calls:
                IF call.target != component:
                    log("Cross-component call: " + call)
        
        RETURN dependencies

RESULT:
├── Orders → Inventory: check_stock(), reserve_stock()
├── Orders → Payments: process_payment(), refund()
├── Inventory → (none)
├── Payments → (none)
└── Shared: auth, logging, validation

PHASE 2: Define Internal APIs (Week 5-8)
├── Create internal interfaces for cross-component calls
├── Orders calls inventory through interface, not direct
├── Still same process, same deployment
├── Rollback: Remove interfaces, revert to direct calls
└── Risk: LOW (no runtime behavior change)

Interface definition:
    INTERFACE InventoryService:
        check_stock(sku, quantity) → StockResult
        reserve_stock(sku, quantity) → ReservationResult
        release_stock(reservation_id) → void
    
    INTERFACE PaymentService:
        process_payment(amount, method, idempotency_key) → PaymentResult
        refund(payment_id, amount) → RefundResult

PHASE 3: Extract Payments Service (Week 9-16)
├── Create new payments-service with same interface
├── Deploy payments-service, not yet receiving traffic
├── Monolith still handles all traffic
├── Rollback: Delete payments-service
└── Risk: LOW (new service is idle)

PHASE 4: Shadow Traffic to Payments (Week 17-20)
├── Monolith sends shadow requests to payments-service
├── Monolith processes payment (authoritative)
├── Compare results: monolith vs. payments-service
├── Payments-service does NOT actually charge cards (read-only shadow)
├── Rollback: Stop shadow traffic
└── Risk: LOW (shadow only, no customer impact)

Shadow implementation:
    FUNCTION process_payment_with_shadow(request):
        // Authoritative path
        result = monolith.process_payment(request)
        
        // Shadow path (async, non-blocking)
        async:
            shadow_result = payments_service.process_payment(request)
            compare(result, shadow_result)
            IF mismatch:
                log_discrepancy(request, result, shadow_result)
        
        RETURN result

PHASE 5: Canary Traffic to Payments (Week 21-24)
├── 1% of real payment traffic → payments-service
├── Monolith is fallback if payments-service fails
├── Monitor: latency, errors, success rate
├── Rollback: Route 0% to payments-service
└── Risk: MEDIUM (real traffic, but small percentage)

PHASE 6: Gradual Traffic Shift (Week 25-32)
├── 1% → 10% → 25% → 50% → 100%
├── Each increase requires validation metrics
├── At each stage, can rollback to previous percentage
├── Rollback: Reduce percentage
└── Risk: MEDIUM to HIGH (increasing as percentage grows)

Traffic routing pseudocode:
    FUNCTION route_payment_request(request):
        percentage = get_config("payments_service_percentage")
        
        IF hash(request.user_id) % 100 < percentage:
            TRY:
                result = payments_service.process_payment(request)
                RETURN result
            CATCH error:
                log_error("Payments service failed, falling back")
                increment_metric("payments_fallback")
                RETURN monolith.process_payment(request)
        ELSE:
            RETURN monolith.process_payment(request)

PHASE 7: Separate Database (Week 33-40)
├── Payments-service gets own database
├── Data migration (see Scenario 1 pattern)
├── Dual-write during transition
├── Rollback: Revert to shared database
└── Risk: HIGH (data separation is complex)

PHASE 8: Remove Payments from Monolith (Week 41+)
├── Delete payments code from monolith
├── This is a ONE-WAY DOOR
├── Only after extended bake time at 100% traffic
├── No rollback without re-adding code
└── Risk: HIGH (irreversible)
```

### Failure Points

```
FAILURE POINT 1: Interface Mismatch
├── Symptom: Payments-service returns different format than expected
├── Detection: Shadow comparison catches discrepancy
├── Response: Fix interface, re-run shadow validation
├── Prevention: Extensive contract testing

FAILURE POINT 2: Latency Regression
├── Symptom: P99 latency increases when payments-service handles traffic
├── Detection: Latency monitoring, SLO alerts
├── Response: Reduce traffic percentage, investigate
├── Prevention: Load testing before canary

FAILURE POINT 3: Database Inconsistency During Split
├── Symptom: Payment records exist in one database but not other
├── Detection: Reconciliation jobs, comparison queries
├── Response: Extend dual-write period, fix sync issues
├── Prevention: Transaction log comparison

FAILURE POINT 4: Network Partition Between Services
├── Symptom: Orders service can't reach payments service
├── Detection: Error rate spike, circuit breaker opens
├── Response: Fallback to monolith (if still available)
├── Prevention: Circuit breakers, retry with backoff, regional redundancy
```

### Rollback Strategy

```
ROLLBACK AT EACH PHASE:

Traffic routing: Change percentage in config (instant)
Service deployment: Roll back deployment (minutes)
Database split: Revert to shared database (complex, hours)
Code removal: Requires re-adding code (days/weeks)

CRITICAL: Maintain fallback to monolith until confident
├── Keep payments code in monolith during transition
├── Route to monolith if payments-service fails
├── Only remove fallback after months of stable operation
```

### Final Stable State

```
ARCHITECTURE:

┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  Orders Service │    │Inventory Service│    │Payments Service │
│  (team: Orders) │    │(team: Inventory)│    │ (team: Payments)│
├─────────────────┤    ├─────────────────┤    ├─────────────────┤
│  orders-db      │    │  inventory-db   │    │  payments-db    │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                     │                       │
         └─────────────────────┼───────────────────────┘
                               │
                         API Gateway

IMPROVEMENTS:
├── Teams deploy independently
├── Inventory can deploy 5x/day, Payments 1x/week
├── Inventory bug cannot crash payments
├── Each service scales independently
├── On-call scope is clear and bounded
└── Compliance team audits only payments-service
```

---

# Part 6: Failure Scenarios During Change

## Scenario: The Partial Rollout That Corrupted Data

### Background

A messaging platform migrated from storing messages in a document database to a new relational database with better query support. The migration used dual-write: write to both old and new, read from new.

### What Happened

```
TIMELINE OF INCIDENT:

Day 0 (Monday):
├── Migration at Phase 5: dual-write active, reading from new DB
├── 100% traffic on new read path
├── Old DB still receiving writes as backup
└── Everything appears stable

Day 1 (Tuesday) 14:32:
├── New DB experiences elevated latency due to index rebuild
├── Write timeout increased, some writes fail
├── Dual-write logic: if new DB write fails, log and continue
├── Old DB receives the write successfully
└── Discrepancy: old DB has message, new DB doesn't

Day 1 16:45:
├── Index rebuild completes, new DB latency normalizes
├── No alerts (write failures were logged, not alerted)
├── Users don't notice (most reads succeed)
└── ~50,000 messages written to old DB only

Day 3 (Thursday):
├── User reports: "My messages from Tuesday are missing"
├── Investigation: message exists in old DB, not in new DB
├── Scope: 50,000 messages over 2-hour window
└── Severity: Data visible to users is incomplete

IMPACT:
├── 50,000 messages invisible to users
├── No data loss (old DB has them)
├── But: old DB no longer queried by application
├── Recovery requires: reading old DB, backfilling to new DB
└── Trust impact: users saw messages "disappear"
```

### Why the Failure Wasn't Obvious Beforehand

```
HIDDEN ASSUMPTIONS:

1. "Dual-write means both DBs always have the data"
   REALITY: Dual-write with fire-and-forget to new DB doesn't guarantee sync
   
2. "We'd notice if writes were failing"
   REALITY: Write failures logged but not alerted; log volume too high to monitor
   
3. "Index rebuild is a routine operation"
   REALITY: Index rebuild during dual-write creates failure window
   
4. "Old DB is backup if something goes wrong"
   REALITY: Old DB not queried after read cutover, so discrepancy invisible

WHAT WAS MISSED:
├── Dual-write error handling was "log and continue"
├── No reconciliation job comparing old and new
├── No alert on dual-write failure rate
├── Old DB writes were backup, but not verified
└── Read path didn't fall back to old DB on miss
```

### What Design or Process Changes Would Have Reduced Risk

```
DESIGN CHANGES:

1. DUAL-WRITE WITH VERIFICATION
   // Instead of fire-and-forget:
   FUNCTION dual_write(message):
       old_result = write_to_old_db(message)
       new_result = write_to_new_db(message)
       
       IF old_result.success AND NOT new_result.success:
           // Queue for retry, not just log
           queue_for_reconciliation(message)
           alert_on_threshold("dual_write_failures")
       
       RETURN old_result  // Old DB is source of truth until cutover

2. RECONCILIATION JOB
   // Run continuously during migration
   FUNCTION reconcile():
       FOR message IN old_db.messages_since(last_reconcile_time):
           IF NOT exists_in_new_db(message.id):
               copy_to_new_db(message)
               log("Reconciled missing message: " + message.id)

3. READ WITH FALLBACK
   // During migration, check old DB if new DB miss
   FUNCTION read_message(id):
       message = new_db.get(id)
       IF message IS NULL:
           message = old_db.get(id)
           IF message IS NOT NULL:
               // Found in old, missing in new - backfill
               async: copy_to_new_db(message)
       RETURN message

PROCESS CHANGES:

1. Alert on dual-write failure rate > 0.01%
2. Block maintenance operations during dual-write phase
3. Require reconciliation verification before read cutover
4. Extend dual-read period (both DBs queried) before single-read
5. Define "migration complete" criteria that includes consistency check
```

---

## Scenario: Latency Regression From Unexpected Query Patterns

### Background

A messaging service migrated from a document store to a relational database for better transaction support. The migration looked successful in staging and early production canary.

### What Happened

```
TIMELINE OF INCIDENT:

Pre-migration:
├── Document store: Flexible schema, denormalized
├── Read pattern: Fetch entire conversation by conversation_id
├── Average read latency: 8ms P50, 25ms P99
└── All conversations same data model

Migration complete at 100% traffic:

Week 1-2: Everything looks good
├── Relational DB: Normalized schema, proper foreign keys
├── Same queries, similar latency in monitoring
└── Team celebrates successful migration

Week 3: Latency alerts start firing
├── P99 latency: 25ms → 180ms
├── Specific conversations affected, not all
├── Pattern: Conversations with 1000+ messages
└── Document store never had this problem

Root cause investigation:
├── Document store: Entire conversation stored as one document
│   └── Fetch conversation = 1 read, regardless of message count
├── Relational DB: Messages in separate table with foreign key
│   └── Fetch conversation = 1 read + N message reads
│   └── For 1000 messages: 1 + 1000 queries (N+1 problem)
├── In staging: Test conversations had 10-50 messages
├── In production: Power users had 1000+ message conversations
└── Latency proportional to conversation length

IMPACT:
├── 5% of users (power users) experienced 7x latency increase
├── Power users are often paying customers
├── Some users switched to competitor citing "app got slow"
└── Rollback not straightforward—schema already normalized
```

### Why This Wasn't Obvious

```
HIDDEN ASSUMPTIONS:

1. "Staging matched production"
   REALITY: Staging data had median conversation size
   Production had long-tail of very large conversations
   
2. "Latency metrics were monitored"
   REALITY: P99 was monitored, but not per-conversation-size
   Large conversations were hidden in aggregate metrics
   
3. "Query patterns were analyzed"
   REALITY: Functional equivalence was tested, not performance equivalence
   Same output doesn't mean same performance characteristics

WHAT WAS MISSED:
├── Load test with production-representative data distribution
├── Performance regression test per data shape
├── Query analysis for N+1 patterns
├── Gradual rollout with user-segment monitoring
└── Latency breakdown by entity size, not just aggregate
```

### Prevention Strategies

```
DESIGN CHANGES:

1. PERFORMANCE CHARACTERIZATION BY DATA SHAPE
   // Before migration, understand the data distribution
   ANALYSIS:
       conversation_size_distribution:
           P50: 23 messages
           P90: 156 messages
           P99: 1,247 messages
           MAX: 12,445 messages
       
       GENERATE test cases for P50, P90, P99, MAX
       REQUIRE performance validation for each

2. QUERY PATTERN ANALYSIS
   // For every read path, analyze query count vs. data size
   
   FUNCTION analyze_query_pattern(operation):
       FOR data_size IN [10, 100, 1000, 10000]:
           query_count = count_queries(operation, data_size)
           IF query_count > O(1):
               flag_as_risk("Query count scales with data size")
               IF query_count > data_size:
                   flag_as_critical("N+1 or worse pattern")

3. SEGMENT-AWARE MONITORING
   // Don't just monitor aggregate latency
   
   METRICS:
       message_fetch_latency_by_conversation_size:
           bucket_small (< 50 messages): histogram
           bucket_medium (50-200 messages): histogram
           bucket_large (200-1000 messages): histogram
           bucket_xlarge (> 1000 messages): histogram
   
   ALERT IF bucket_xlarge.p99 > 2 * bucket_small.p99

4. EAGER LOADING / PAGINATION
   // Fix the N+1 pattern before it ships
   
   // BAD: N+1 queries
   FUNCTION get_conversation(id):
       conv = db.query("SELECT * FROM conversations WHERE id = ?", id)
       messages = []
       FOR msg_id IN conv.message_ids:
           messages.append(db.query("SELECT * FROM messages WHERE id = ?", msg_id))
       RETURN (conv, messages)
   
   // GOOD: Single query with join
   FUNCTION get_conversation(id):
       RETURN db.query("""
           SELECT c.*, m.* 
           FROM conversations c 
           JOIN messages m ON m.conversation_id = c.id 
           WHERE c.id = ? 
           ORDER BY m.created_at
           LIMIT 100
       """, id)
       // Plus: Pagination for large conversations
```

---

## Scenario: Hidden Dependency Failure

### Background

A user service migrated from an in-house authentication system to a standardized identity platform. The migration was staged, tested, and rolled out over 6 weeks.

### What Happened

```
TIMELINE OF INCIDENT:

Migration completed successfully:
├── All user authentication moved to new identity platform
├── Old auth system deprecated and decommissioned
├── 4 weeks of stable operation
└── Old infrastructure deleted

Week 5 post-migration, first of the month:
├── Monthly billing job starts running
├── Billing job uses internal API to fetch user details
├── API returns 500 errors for 15% of users
├── Billing fails, invoices not generated
└── Revenue impact: $2M in delayed invoices

Investigation:
├── Billing job was documented in a different team's wiki
├── Billing job used legacy auth tokens for internal API calls
├── Legacy auth tokens were issued by OLD auth system
├── Old auth system was deleted 1 week ago
├── Legacy tokens could not be validated
└── No one knew billing job existed during migration planning

ROOT CAUSE:
├── Billing job ran monthly—not seen during 4-week validation
├── Billing job was owned by Finance Engineering, not User team
├── Billing job was not in the dependency map
├── Legacy auth tokens had 60-day expiry
│   └── Tokens issued before migration still worked initially
│   └── Started failing as tokens expired
└── No alert on legacy token validation failures

BLAST RADIUS:
├── 15% of users with tokens issued > 30 days ago
├── All monthly batch jobs using internal APIs
├── Revenue systems depending on user data
└── Discovered: 3 other hidden consumers of legacy auth
```

### Why This Wasn't Obvious

```
HIDDEN ASSUMPTIONS:

1. "We inventoried all consumers"
   REALITY: Inventory found all REAL-TIME consumers
   Batch jobs that run monthly/quarterly were invisible
   
2. "4 weeks of stable operation proves migration complete"
   REALITY: 4 weeks doesn't capture monthly or quarterly processes
   Need to run through at least one full business cycle
   
3. "Deleting old system is safe after bake period"
   REALITY: Consumers may be using cached credentials
   Old system must remain available until all credentials expire
   
4. "Team knows all its dependencies"
   REALITY: Cross-team dependencies are often undocumented
   Especially for internal APIs used by batch processes

WHAT SHOULD HAVE HAPPENED:
├── Migration validation period >= longest batch interval (90 days)
├── Old system kept in read-only mode, not deleted
├── Monitoring for legacy auth token validation attempts
├── Proactive outreach to ALL teams, not just known consumers
└── Forced token refresh before old system decommission
```

### Prevention Strategies

```
DESIGN CHANGES:

1. DEPENDENCY DISCOVERY BEYOND REAL-TIME TRAFFIC
   
   // Don't just look at current traffic
   FUNCTION discover_all_consumers(service):
       consumers = []
       
       // Real-time consumers (visible in traffic)
       consumers.extend(analyze_recent_traffic(days=30))
       
       // Batch consumers (may not run frequently)
       consumers.extend(search_codebase_for_api_calls(service))
       consumers.extend(search_ci_cd_for_service_references(service))
       consumers.extend(search_cron_jobs_for_api_calls(service))
       
       // Unknown consumers (broadcast)
       send_company_wide_notice(
           "We are deprecating X. If you use X, contact us."
       )
       WAIT 2 weeks for responses
       
       RETURN deduplicate(consumers)

2. CREDENTIAL EXPIRY TRACKING
   
   // Track when issued credentials will expire
   FUNCTION plan_decommission_timeline(old_service):
       max_credential_lifetime = get_max_token_ttl(old_service)
       last_credential_issued = get_last_credential_issue_time()
       
       earliest_safe_decommission = last_credential_issued + max_credential_lifetime
       
       // Add buffer for unknown consumers
       recommended_decommission = earliest_safe_decommission + 30_days
       
       RETURN recommended_decommission

3. LEGACY SYSTEM MONITORING
   
   // Even after traffic is migrated, monitor old system
   METRICS for old_service:
       token_validation_attempts: counter
       token_validation_failures: counter
       unique_clients_attempting_legacy: set
   
   ALERT IF token_validation_attempts > 0 AFTER migration_complete_date
   // This catches unknown consumers trying to use old system

4. GRACEFUL DEGRADATION FOR BATCH JOBS
   
   // Design internal APIs to fail gracefully
   FUNCTION get_user_for_billing(user_id, auth_token):
       TRY:
           validate_token(auth_token)  // New auth system
       CATCH AuthenticationError:
           TRY:
               validate_legacy_token(auth_token)  // Fallback
               log_warning("Legacy token used", user_id, auth_token.issuer)
               increment_metric("legacy_auth_usage")
           CATCH LegacyAuthNotAvailable:
               // Old system decommissioned
               RETURN AUTHENTICATION_ERROR  // Let caller handle
       
       RETURN get_user(user_id)
```

---

# Part 6B: Testing Strategies During Migration

Migrations require different testing than greenfield development. Staff Engineers design test strategies that catch migration-specific failures.

## Migration Testing Framework

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    MIGRATION TESTING PYRAMID                                │
│                                                                             │
│                           ┌─────────────┐                                   │
│                           │  PRODUCTION │   Canary, shadow, A/B             │
│                           │   TESTING   │   Real traffic, real data         │
│                          ┌┴─────────────┴┐                                  │
│                          │ LOAD TESTING  │   Production-scale traffic       │
│                          │               │   Production data distribution   │
│                         ┌┴───────────────┴┐                                 │
│                         │  INTEGRATION    │   Old + new system together     │
│                         │   TESTING       │   Cross-system consistency      │
│                        ┌┴─────────────────┴┐                                │
│                        │ COMPARISON TESTING│   Same input → same output     │
│                        │                   │   Old system vs. new system    │
│                       ┌┴───────────────────┴┐                               │
│                       │   CONTRACT TESTING  │   API compatibility           │
│                       │                     │   Schema compatibility        │
│                      ┌┴─────────────────────┴┐                              │
│                      │     UNIT TESTING      │   Business logic preserved   │
│                      │                       │   Edge cases handled         │
│                      └───────────────────────┘                              │
│                                                                             │
│   MIGRATION-SPECIFIC ADDITIONS (beyond normal testing):                     │
│   ├── Comparison testing: Verify old and new produce identical results      │
│   ├── Rollback testing: Verify we can go back at each phase                 │
│   ├── Consistency testing: Data stays consistent during dual-write          │
│   └── Long-tail testing: Edge cases that only appear in production data     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Comparison Testing Strategy

```
// Pseudocode: Comparison testing for migration

FUNCTION setup_comparison_testing(old_system, new_system):
    
    // 1. Capture production traffic
    FUNCTION capture_request(request):
        RETURN {
            input: request,
            old_result: old_system.process(request),
            timestamp: now()
        }
    
    // 2. Replay against new system
    FUNCTION compare_systems(captured_requests):
        discrepancies = []
        
        FOR capture IN captured_requests:
            new_result = new_system.process(capture.input)
            
            IF NOT equivalent(capture.old_result, new_result):
                discrepancies.append({
                    input: capture.input,
                    old: capture.old_result,
                    new: new_result,
                    diff: compute_diff(capture.old_result, new_result)
                })
        
        RETURN discrepancies
    
    // 3. Categorize discrepancies
    FUNCTION analyze_discrepancies(discrepancies):
        FOR disc IN discrepancies:
            category = categorize(disc):
                SEMANTIC_DIFFERENCE:
                    // Different behavior—bug or intentional?
                    IF intentional(disc): 
                        document_change(disc)
                    ELSE: 
                        flag_as_bug(disc)
                
                ACCEPTABLE_DIFFERENCE:
                    // Timestamps, UUIDs, formatting
                    add_to_allowlist(disc.pattern)
                
                ORDERING_DIFFERENCE:
                    // Results same but different order
                    IF order_matters: 
                        flag_as_bug(disc)
                    ELSE: 
                        add_to_allowlist(disc.pattern)
                
                PRECISION_DIFFERENCE:
                    // Floating point, rounding
                    IF within_tolerance(disc): 
                        accept(disc)
                    ELSE: 
                        flag_as_bug(disc)

// Run comparison testing before each rollout percentage increase
// Require 99.9%+ match rate before proceeding
```

## Rollback Testing

```
ROLLBACK TEST PLAN (run at each migration phase):

Test 1: Traffic Rollback
├── Precondition: X% traffic on new system
├── Action: Set traffic to 0% on new system
├── Verify: All traffic successfully handled by old system
├── Verify: No errors during switchover
├── Verify: Latency returns to pre-migration baseline
├── Time limit: Complete in < 1 minute

Test 2: Data Rollback (if applicable)
├── Precondition: Dual-write active, new system has new writes
├── Action: Stop writes to new system
├── Verify: Old system has all required data
├── Verify: Reads from old system return correct results
├── Verify: No data loss or corruption
├── Time limit: Complete in < 5 minutes

Test 3: Configuration Rollback
├── Precondition: Feature flag enables new path
├── Action: Disable feature flag globally
├── Verify: All instances switch to old path
├── Verify: No requests use new path after flag change
├── Verify: Propagation complete within SLA (e.g., 30 seconds)

Test 4: Full Rollback Drill
├── Frequency: Weekly during migration
├── Action: Simulate "something is wrong" scenario
├── Execute: Full rollback procedure
├── Measure: Time to complete rollback
├── Verify: System fully operational on old path
├── Document: Any issues encountered

// Pseudocode: Automated rollback drill

FUNCTION run_rollback_drill():
    start_time = now()
    
    // Capture pre-rollback state
    pre_state = capture_system_state()
    
    // Execute rollback
    execute_rollback_procedure()
    
    // Wait for propagation
    wait_for_propagation(max_wait=60_seconds)
    
    // Verify rollback complete
    post_state = capture_system_state()
    
    // Validate
    assertions = [
        post_state.traffic_on_new_system == 0%,
        post_state.error_rate <= pre_state.error_rate,
        post_state.latency_p99 <= pre_state.latency_p99 * 1.1,
        all_health_checks_passing()
    ]
    
    rollback_time = now() - start_time
    
    REPORT {
        rollback_successful: all(assertions),
        rollback_duration: rollback_time,
        issues: [a for a in assertions if not a.passed]
    }
    
    // Restore to pre-drill state
    restore_migration_state(pre_state)
```

---

# Part 7: Organizational and Human Risk (Often Missed)

## How Team Boundaries Increase Migration Risk

Technical migrations don't happen in a vacuum. Organizational structure directly impacts migration risk.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│            ORGANIZATIONAL RISK FACTORS IN MIGRATIONS                        │
│                                                                             │
│   TEAM BOUNDARY RISK                                                        │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Each team boundary = coordination overhead                         │   │
│   │  Each team boundary = potential communication failure               │   │
│   │  Each team boundary = schedule conflict risk                        │   │
│   │                                                                     │   │
│   │  Migration risk ∝ (number of teams)²                                │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   OWNERSHIP AMBIGUITY                                                       │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  "Who owns this during the migration?"                              │   │
│   │  • Old system owner?                                                │   │
│   │  • New system owner?                                                │   │
│   │  • Migration lead?                                                  │   │
│   │                                                                     │   │
│   │  Ambiguity → gaps → incidents                                       │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   KNOWLEDGE LOSS                                                            │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Multi-year migrations outlast team composition:                    │   │
│   │  • Original designers leave                                         │   │
│   │  • Institutional knowledge disappears                               │   │
│   │  • "Why did we do it this way?" becomes unanswerable                │   │
│   │  • Decisions that seemed obvious become mysterious                  │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   COMMUNICATION FAILURES                                                    │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  "We told them about the migration..."                              │   │
│   │  • But they didn't understand the impact                            │   │
│   │  • But the person who received the message left                     │   │
│   │  • But the timeline changed and we didn't update them               │   │
│   │  • But "telling" isn't the same as "confirming readiness"           │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## How Staff Engineers Coordinate Change Across Teams

```
// Pseudocode: Multi-team migration coordination

FUNCTION lead_cross_team_migration(migration):
    // 1. Identify all stakeholders
    stakeholders = identify_all_affected_teams(migration)
    
    FOR team IN stakeholders:
        // Don't just send email—get explicit acknowledgment
        team.contact = get_migration_contact(team)
        team.impact = assess_impact_on_team(migration, team)
        team.readiness = FALSE
    
    // 2. Create shared understanding
    design_doc = create_migration_design_doc(migration)
    FOR team IN stakeholders:
        review = request_review(team, design_doc)
        address_concerns(review)
    
    // 3. Establish checkpoints
    milestones = create_migration_milestones(migration)
    FOR milestone IN milestones:
        milestone.owners = assign_owners(milestone)
        milestone.success_criteria = define_success_criteria(milestone)
        milestone.rollback_plan = define_rollback(milestone)
    
    // 4. Explicit readiness confirmation
    FOR team IN stakeholders:
        // Not "we told them"—"they confirmed readiness"
        WHILE NOT team.readiness:
            check_team_readiness(team)
            IF blockers_exist(team):
                resolve_blockers(team)
            ELSE:
                team.readiness = confirm_readiness(team)
    
    // 5. Execute with visibility
    FOR milestone IN milestones:
        announce_milestone_start(milestone, stakeholders)
        execute_milestone(milestone)
        verify_success(milestone)
        announce_milestone_complete(milestone, stakeholders)
    
    // 6. Post-migration validation
    run_validation_period(migration)
    collect_feedback(stakeholders)
    document_lessons_learned(migration)
```

## Designing Systems to Reduce Cross-Team Risk

```
STAFF PRINCIPLE: Design so that changes require fewer teams to coordinate.

DESIGN PATTERN 1: Clear Ownership Boundaries
┌─────────────────────────────────────────────────────────────────────────────┐
│  BAD: Shared library that all teams modify                                  │
│       → Any change requires coordination with all consumers                 │
│       → Migration requires all teams to update simultaneously               │
│                                                                             │
│  GOOD: Versioned API with backward compatibility                            │
│       → Provider can add new version without coordinating                   │
│       → Consumers migrate on their own timeline                             │
│       → Old version supported until all consumers migrate                   │
└─────────────────────────────────────────────────────────────────────────────┘

DESIGN PATTERN 2: Self-Service Interfaces
┌─────────────────────────────────────────────────────────────────────────────┐
│  BAD: Consumer team must file ticket, wait for provider team                │
│       → Coordination bottleneck                                             │
│       → Migration blocked on human availability                             │
│                                                                             │
│  GOOD: Self-service configuration, documentation, tooling                   │
│       → Consumer team can migrate independently                             │
│       → Provider team provides tools, not hands-on help                     │
└─────────────────────────────────────────────────────────────────────────────┘

DESIGN PATTERN 3: Limit Blast Radius by Design
┌─────────────────────────────────────────────────────────────────────────────┐
│  BAD: Central service that all products depend on                           │
│       → Any change affects everyone                                         │
│       → Migration is all-or-nothing                                         │
│                                                                             │
│  GOOD: Federated or replicated services per product area                    │
│       → Changes can be rolled out incrementally                             │
│       → One product's migration doesn't block others                        │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Limiting Human Requirements for Safe Operation

```
STAFF INSIGHT: The fewer humans required for safe operation, the safer the system.

ANTI-PATTERN: "Alice knows how to do the migration"
├── Alice goes on vacation
├── Alice leaves the company
├── Alice is sick during the critical window
└── Migration is blocked or done unsafely

PATTERN: Runbooks and Automation
├── Every migration step documented
├── Critical steps automated where possible
├── Runbooks tested by someone other than the author
├── No single point of human failure

ANTI-PATTERN: "We need all three teams online to cut over"
├── Scheduling across timezones is hard
├── One team being unavailable blocks everyone
├── Pressure to proceed without full team → mistakes
└── Incident at 3am requires waking multiple people

PATTERN: Staged Rollout with Async Handoffs
├── Each team completes their phase independently
├── Clear criteria for "phase complete"
├── Next team can proceed when criteria met
├── No simultaneous coordination required

// Pseudocode: Minimum human requirement analysis

FUNCTION analyze_human_requirements(migration):
    required_humans = []
    
    FOR step IN migration.steps:
        IF step.requires_manual_action:
            humans = get_humans_who_can_perform(step)
            IF len(humans) == 1:
                risk.add("Single point of failure: " + step)
            required_humans.extend(humans)
    
    IF requires_simultaneous_availability(required_humans):
        risk.add("Coordination risk: all humans must be available together")
    
    IF any_human_in(required_humans, different_timezone):
        risk.add("Timezone coordination required")
    
    RETURN {
        minimum_humans: len(unique(required_humans)),
        risks: risk,
        recommendation: "Reduce to " + calculate_safe_minimum() + " humans"
    }
```

---

# Part 8: Evolution Over Time (Long-Term Thinking)

## How Early Design Choices Constrain Future Evolution

Every design decision creates a path dependency. Some paths are easy to change; others become load-bearing.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│            DESIGN DECISIONS AND THEIR FUTURE CONSTRAINTS                    │
│                                                                             │
│   DECISION: Data serialization format                                       │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Chosen: Custom binary format for performance                       │   │
│   │  Constraint: All future tools must parse custom format              │   │
│   │  Constraint: Schema changes require version negotiation             │   │
│   │  Constraint: Debugging requires custom tooling                      │   │
│   │                                                                     │   │
│   │  Alternative: Standard format (JSON, Protobuf) with known tooling   │   │
│   │  Trade-off: Slightly worse performance, much better evolvability    │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   DECISION: Single global database                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Chosen: All data in one database for simplicity                    │   │
│   │  Constraint: Sharding requires application rewrite                  │   │
│   │  Constraint: Regional isolation requires data migration             │   │
│   │  Constraint: Database technology change is all-or-nothing           │   │
│   │                                                                     │   │
│   │  Alternative: Logical separation from the start                     │   │
│   │  Trade-off: More complexity initially, easier evolution later       │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   DECISION: Tight coupling between services                                 │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Chosen: Direct RPC calls with shared types                         │   │
│   │  Constraint: Can't deploy services independently                    │   │
│   │  Constraint: Schema changes require coordinated deployment          │   │
│   │  Constraint: Service extraction is major project                    │   │
│   │                                                                     │   │
│   │  Alternative: API contracts with versioning                         │   │
│   │  Trade-off: More indirection, but independent evolution             │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Avoiding Premature Abstraction

```
STAFF WISDOM: Premature abstraction is as dangerous as premature optimization.

THE PROBLEM:
├── Engineers see two similar things
├── "Let's abstract this into a framework!"
├── Framework handles both cases
├── Third case arrives—doesn't fit framework
├── Framework becomes complex to handle edge cases
├── Fourth case: even worse fit
├── Framework is now harder to change than duplicated code
└── Team is stuck with the wrong abstraction

// Pseudocode: When to abstract

FUNCTION should_we_abstract(similar_things):
    IF len(similar_things) < 3:
        RETURN "Wait—two examples isn't a pattern"
    
    IF not_confident_about_future_cases:
        RETURN "Wait—abstraction should fit future cases too"
    
    IF abstraction_complexity > sum(individual_complexities) * 0.7:
        RETURN "No—abstraction doesn't reduce net complexity"
    
    IF abstraction_constrains_future_evolution:
        RETURN "Maybe not—flexibility matters more than DRY"
    
    RETURN "Consider abstracting, but keep it minimal"

STAFF RULE:
"Duplication is far cheaper than the wrong abstraction."
                                        — Sandi Metz
```

## Avoiding Irreversible Decisions

```
// Pseudocode: Irreversibility checklist

FUNCTION evaluate_decision_reversibility(decision):
    irreversibility_factors = 0
    
    // Data changes
    IF decision.deletes_data:
        irreversibility_factors += 3
    IF decision.transforms_data_lossy:
        irreversibility_factors += 2
    IF decision.changes_data_schema:
        irreversibility_factors += 1
    
    // External dependencies
    IF decision.exposes_api_to_external_clients:
        irreversibility_factors += 2
    IF decision.creates_external_data_dependency:
        irreversibility_factors += 2
    IF decision.signs_long_term_contract:
        irreversibility_factors += 3
    
    // System coupling
    IF decision.creates_tight_coupling:
        irreversibility_factors += 1
    IF decision.removes_abstraction_layer:
        irreversibility_factors += 1
    
    IF irreversibility_factors >= 3:
        RETURN "HIGH - requires explicit reversal plan before proceeding"
    ELIF irreversibility_factors >= 1:
        RETURN "MEDIUM - document how to reverse if needed"
    ELSE:
        RETURN "LOW - easily reversible"
```

## Leaving Escape Hatches in Designs

```
STAFF PRACTICE: Deliberately leave room for future changes.

ESCAPE HATCH 1: Version Everything
├── APIs have version in path (/v1/, /v2/)
├── Data formats have version field
├── Configuration has schema version
├── Messages have type/version identifier
└── Result: Can introduce new version without breaking old

ESCAPE HATCH 2: Abstraction at Key Boundaries
├── Database access through repository pattern
├── External services through adapter interfaces
├── Configuration through abstraction layer
├── Result: Can swap implementations without rewriting callers

ESCAPE HATCH 3: Feature Flags for Behavior
├── New behavior behind flag
├── Can enable/disable without deployment
├── Can roll back instantly if problems
└── Result: Behavior changes are reversible

ESCAPE HATCH 4: Data Designed for Extension
├── Schema allows unknown fields (forward compatibility)
├── Enums have UNKNOWN value
├── Timestamps stored in standard format
└── Result: Can extend without breaking existing readers

EXAMPLE: Message Queue Integration

// BAD: Direct coupling
FUNCTION send_notification(user, message):
    kafka.send("notifications", serialize(user, message))
    // Changing to different queue requires rewriting all callers

// GOOD: Abstraction with escape hatch
INTERFACE MessageQueue:
    send(topic, message)
    
FUNCTION send_notification(user, message):
    queue = get_message_queue()  // Returns Kafka today, could be SQS tomorrow
    queue.send("notifications", serialize(user, message))
    // Changing queue requires only updating get_message_queue()
```

## Why Simplicity Is the Safest Long-Term Strategy

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    SIMPLICITY AS RISK MANAGEMENT                            │
│                                                                             │
│   COMPLEX SYSTEM EVOLUTION:                                                 │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  • More components = more things that can break                     │   │
│   │  • More interactions = more edge cases                              │   │
│   │  • More abstractions = more layers to understand                    │   │
│   │  • More dependencies = more external changes to track               │   │
│   │                                                                     │   │
│   │  Result: Migrations are harder, take longer, fail more often        │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   SIMPLE SYSTEM EVOLUTION:                                                  │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  • Fewer components = less surface area for change                  │   │
│   │  • Clear boundaries = easier to reason about impact                 │   │
│   │  • Less cleverness = easier to understand and modify                │   │
│   │  • Fewer dependencies = fewer external constraints                  │   │
│   │                                                                     │   │
│   │  Result: Migrations are tractable, predictable, recoverable         │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   STAFF PRINCIPLE:                                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  "Every piece of complexity you add today is a migration you        │   │
│   │   must do tomorrow."                                                │   │
│   │                                                                     │   │
│   │  The question is not "can we build this complex system?"            │   │
│   │  The question is "can we change this complex system safely?"        │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Part 9: Diagrams

## Diagram 1: Before/After Architecture — Service Decomposition

```
┌─────────────────────────────────────────────────────────────────────────────┐
│         BEFORE/AFTER: MONOLITH TO SERVICES MIGRATION                        │
│                                                                             │
│   BEFORE (Monolith):                                                        │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                                                                     │   │
│   │                        ┌─────────────────┐                          │   │
│   │                        │    Monolith     │                          │   │
│   │                        │ ┌─────────────┐ │                          │   │
│   │                        │ │   Orders    │ │                          │   │
│   │                        │ ├─────────────┤ │                          │   │
│   │                        │ │  Inventory  │ │                          │   │
│   │                        │ ├─────────────┤ │                          │   │
│   │                        │ │  Payments   │ │                          │   │
│   │                        │ └─────────────┘ │                          │   │
│   │                        └────────┬────────┘                          │   │
│   │                                 │                                   │   │
│   │                        ┌────────▼────────┐                          │   │
│   │                        │  Shared Database│                          │   │
│   │                        │  (all tables)   │                          │   │
│   │                        └─────────────────┘                          │   │
│   │                                                                     │   │
│   │   Problems: Single deployment, blast radius = everything,           │   │
│   │             shared ownership, scaling limitations                   │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   AFTER (Services):                                                         │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                                                                     │   │
│   │   ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │   │
│   │   │   Orders     │  │  Inventory   │  │   Payments   │              │   │
│   │   │   Service    │  │   Service    │  │   Service    │              │   │
│   │   │  (Team A)    │──│  (Team B)    │──│  (Team C)    │              │   │
│   │   └──────┬───────┘  └──────┬───────┘  └──────┬───────┘              │   │
│   │          │                 │                 │                      │   │
│   │   ┌──────▼───────┐  ┌──────▼───────┐  ┌──────▼───────┐              │   │
│   │   │  Orders DB   │  │ Inventory DB │  │  Payments DB │              │   │
│   │   └──────────────┘  └──────────────┘  └──────────────┘              │   │
│   │                                                                     │   │
│   │   Benefits: Independent deployment, clear ownership,                │   │
│   │             contained blast radius, independent scaling             │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   KEY INSIGHT: The migration is not about the end state—it's about          │
│   getting from BEFORE to AFTER without breaking things.                     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Diagram 2: Migration Phases Over Time

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    MIGRATION PHASES TIMELINE                                │
│                                                                             │
│   PHASE       WEEK 1-4    WEEK 5-8    WEEK 9-12   WEEK 13-16   WEEK 17+     │
│   ────────────────────────────────────────────────────────────────────────  │
│                                                                             │
│   OLD SYSTEM  ████████████████████████████████████████████████░░░░░░░░░░    │
│   (Production)                                   (read-only)  (decommission)│
│                                                                             │
│   NEW SYSTEM  ░░░░░░░░░░██████████████████████████████████████████████████  │
│   (Traffic)    (0%)     (shadow)   (canary)   (ramp)    (100%)   (sole)     │
│                                                                             │
│   DUAL-WRITE  ░░░░░░░░░░██████████████████████████████████████░░░░░░░░░░    │
│   (Active)              (enabled)                     (disabled)            │
│                                                                             │
│   ROLLBACK    ██████████████████████████████████████████████████░░░░░░░░    │
│   CAPABILITY   (instant)                              (complex) (impossible)│
│                                                                             │
│   ────────────────────────────────────────────────────────────────────────  │
│                                                                             │
│   PHASE 1: Preparation                                                      │
│   └── Build new system, no production traffic                               │
│                                                                             │
│   PHASE 2: Shadow                                                           │
│   └── Copy traffic to new system, compare results, don't affect users       │
│                                                                             │
│   PHASE 3: Canary                                                           │
│   └── Small % of real traffic to new system, closely monitored              │
│                                                                             │
│   PHASE 4: Ramp                                                             │
│   └── Gradually increase traffic %, validate at each step                   │
│                                                                             │
│   PHASE 5: Full Traffic                                                     │
│   └── 100% on new system, old system still available for rollback           │
│                                                                             │
│   PHASE 6: Decommission (ONE-WAY DOOR)                                      │
│   └── Remove old system, no rollback possible                               │
│                                                                             │
│   STAFF RULE: Spend most time in phases with rollback capability.           │
│   Only proceed to Phase 6 after extended bake time at Phase 5.              │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Diagram 3: Failure Containment Boundaries

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    FAILURE CONTAINMENT BOUNDARIES                           │
│                                                                             │
│   WITHOUT CONTAINMENT:                                                      │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                                                                     │   │
│   │   ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐                      │   │
│   │   │ Svc1 │─│ Svc2 │─│ Svc3 │─│ Svc4 │─│ Svc5 │                      │   │
│   │   └──────┘ └──────┘ └──────┘ └──────┘ └──────┘                      │   │
│   │      │        │        │        │        │                          │   │
│   │      └────────┴────────┴────────┴────────┘                          │   │
│   │                        │                                            │   │
│   │              ┌─────────▼─────────┐                                  │   │
│   │              │   Shared Database  │                                 │   │
│   │              └───────────────────┘                                  │   │
│   │                                                                     │   │
│   │   Problem: Migration failure in Svc3 or DB affects ALL services     │   │
│   │   Blast radius = 100% of system                                     │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   WITH CONTAINMENT:                                                         │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                                                                     │   │
│   │   ┌───────────────────────────┐   ┌───────────────────────────┐     │   │
│   │   │     BOUNDARY A            │   │      BOUNDARY B           │     │   │
│   │   │  ┌──────┐  ┌──────┐       │   │  ┌──────┐  ┌──────┐       │     │   │
│   │   │  │ Svc1 │──│ Svc2 │       │   │  │ Svc4 │──│ Svc5 │       │     │   │
│   │   │  └──────┘  └──────┘       │   │  └──────┘  └──────┘       │     │   │
│   │   │       │                   │   │       │                   │     │   │
│   │   │  ┌────▼────┐              │   │  ┌────▼────┐              │     │   │
│   │   │  │  DB A   │              │   │  │  DB B   │              │     │   │
│   │   │  └─────────┘              │   │  └─────────┘              │     │   │
│   │   └───────────────────────────┘   └───────────────────────────┘     │   │
│   │                │                              │                     │   │
│   │                └──────────┬───────────────────┘                     │   │
│   │                           │                                         │   │
│   │                    ┌──────▼──────┐                                  │   │
│   │                    │    Svc3     │                                  │   │
│   │                    │  (isolated) │                                  │   │
│   │                    └─────────────┘                                  │   │
│   │                                                                     │   │
│   │   Benefit: Migration failure in Boundary A doesn't affect B         │   │
│   │   Svc3 can be migrated independently                                │   │
│   │   Blast radius = contained to one boundary                          │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   STAFF PRINCIPLE: Design boundaries so that failure stays contained.       │
│   Migrate within boundaries first. Cross-boundary migration last.           │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Diagram 4: Dual-Write Data Flow and Failure Modes

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    DUAL-WRITE DATA FLOW                                     │
│                                                                             │
│   WRITE PATH (Dual-Write Phase):                                            │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                                                                     │   │
│   │   Client                                                            │   │
│   │      │                                                              │   │
│   │      ▼                                                              │   │
│   │   ┌─────────────────────────────────────────────────────────┐       │   │
│   │   │                  Application Layer                      │       │   │
│   │   │  ┌─────────────────────────────────────────────────────┐│       │   │
│   │   │  │  1. Validate request                                ││       │   │
│   │   │  │  2. Write to OLD system (source of truth) ──────────┼┼─► [OLD DB]│
│   │   │  │  3. IF old write succeeds:                          ││       │   │
│   │   │  │     Write to NEW system (async or sync) ────────────┼┼─► [NEW DB]│
│   │   │  │  4. IF new write fails:                             ││       │   │
│   │   │  │     Queue for reconciliation ───────────────────────┼┼─► [QUEUE] │
│   │   │  │  5. Return success (based on old write)             ││       │   │
│   │   │  └─────────────────────────────────────────────────────┘│       │   │
│   │   └─────────────────────────────────────────────────────────┘       │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   FAILURE MODES:                                                            │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                                                                     │   │
│   │   FAILURE 1: Old write succeeds, new write fails                    │   │
│   │   ┌───────────────────────────────────────────────────────────┐     │   │
│   │   │  • Client sees success (correct)                          │     │   │
│   │   │  • Old DB has data (correct)                              │     │   │
│   │   │  • New DB missing data (reconciliation needed)            │     │   │
│   │   │  → Queue for retry, alert if retry fails                  │     │   │
│   │   └───────────────────────────────────────────────────────────┘     │   │
│   │                                                                     │   │
│   │   FAILURE 2: Old write fails (regardless of new)                    │   │
│   │   ┌───────────────────────────────────────────────────────────┐     │   │
│   │   │  • Client sees failure (correct)                          │     │   │
│   │   │  • Don't write to new DB (maintain consistency)           │     │   │
│   │   │  • Client will retry                                      │     │   │
│   │   │  → Standard error handling                                │     │   │
│   │   └───────────────────────────────────────────────────────────┘     │   │
│   │                                                                     │   │
│   │   FAILURE 3: Old write succeeds, new write succeeds but different   │   │
│   │   ┌───────────────────────────────────────────────────────────┐     │   │
│   │   │  • Transformation bug: data differs between systems       │     │   │
│   │   │  • Silent corruption—may not be detected immediately      │     │   │
│   │   │  → Shadow reads + comparison to detect                    │     │   │
│   │   │  → Reconciliation job to fix                              │     │   │
│   │   └───────────────────────────────────────────────────────────┘     │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   RECONCILIATION LOOP:                                                      │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                                                                     │   │
│   │   [QUEUE] ──► [Reconciliation Worker] ──► [NEW DB]                  │   │
│   │                        │                                            │   │
│   │                        ▼                                            │   │
│   │               ┌──────────────┐                                      │   │
│   │               │ Compare with │                                      │   │
│   │               │   OLD DB     │                                      │   │
│   │               └──────────────┘                                      │   │
│   │                        │                                            │   │
│   │           ┌────────────┼────────────┐                               │   │
│   │           ▼            ▼            ▼                               │   │
│   │       [Match]     [Mismatch]   [Missing]                            │   │
│   │          │            │            │                                │   │
│   │        Done       Alert +       Retry                               │   │
│   │                    Fix          Write                               │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   STAFF RULE: OLD system is source of truth until explicitly cut over.      │
│   NEW system failures should never block or fail user requests.             │
│   Reconciliation catches drift; shadow reads validate correctness.          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Part 10: Interview Calibration

## How Google Interviewers Probe Migration and Evolution Thinking

Interviewers don't usually ask directly "How would you migrate this?" Instead, they probe indirectly:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│              HOW INTERVIEWERS PROBE MIGRATION THINKING                      │
│                                                                             │
│   INDIRECT PROBE 1: "How does this scale?"                                  │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  What they're really asking:                                        │   │
│   │  "When this design hits scale limits, how will you evolve it?"      │   │
│   │                                                                     │   │
│   │  L5 answer: "We'd add more servers / shard the database"            │   │
│   │  L6 answer: "The design supports horizontal scaling up to N.        │   │
│   │              Beyond N, we'd need to [specific change]. Here's how   │   │
│   │              we'd migrate to that architecture without downtime..." │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   INDIRECT PROBE 2: "What happens if requirements change?"                  │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  What they're really asking:                                        │   │
│   │  "Is your design flexible or will it require a rewrite?"            │   │
│   │                                                                     │   │
│   │  L5 answer: "We'd add a new component for that requirement"         │   │
│   │  L6 answer: "The design anticipates [likely changes] through        │   │
│   │              [specific extension points]. For [unlikely changes],   │   │
│   │              we'd need to migrate, but the abstraction at [layer]   │   │
│   │              contains that change to [scope]."                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   INDIRECT PROBE 3: "What are the risks?"                                   │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  What they're really asking:                                        │   │
│   │  "Can you identify what could go wrong and how you'd recover?"      │   │
│   │                                                                     │   │
│   │  L5 answer: "The database could fail, so we have replicas"          │   │
│   │  L6 answer: "The highest risk is [specific scenario] because        │   │
│   │              [reason]. The blast radius would be [scope]. We        │   │
│   │              mitigate by [containment strategy] and would           │   │
│   │              recover by [specific rollback approach]."              │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   INDIRECT PROBE 4: "How would you deploy this?"                            │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  What they're really asking:                                        │   │
│   │  "Do you understand incremental rollout and rollback?"              │   │
│   │                                                                     │   │
│   │  L5 answer: "Deploy to staging, test, then deploy to production"    │   │
│   │  L6 answer: "We'd use feature flags for the control plane and       │   │
│   │              staged rollout for the data plane. Starting with 1%    │   │
│   │              canary, monitoring [specific metrics], with instant    │   │
│   │              rollback via [mechanism] if [threshold] is exceeded."  │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Example Interview Questions

```
QUESTION 1: Schema Evolution
"Your system stores user data in a specific schema. Product wants to add
a new field that changes how the data is structured. Walk me through how
you'd make this change on a live system."

WHAT THEY'RE TESTING:
├── Backward compatibility understanding
├── Dual-read/dual-write awareness
├── Rollback planning
└── Data migration incrementality

QUESTION 2: Service Extraction
"You have a monolithic service handling multiple concerns. Product velocity
is suffering because teams block each other. How would you approach 
splitting this into separate services?"

WHAT THEY'RE TESTING:
├── Identifying service boundaries
├── Migration staging and risk management
├── Cross-team coordination awareness
└── Blast radius containment

QUESTION 3: Database Migration
"Your current database is hitting scale limits. You've evaluated alternatives
and want to migrate to a different database technology. How would you do this?"

WHAT THEY'RE TESTING:
├── Dual-write strategies
├── Data consistency during migration
├── Rollback capability preservation
└── Traffic shifting approaches

QUESTION 4: Breaking Change
"You need to make a breaking change to an API that external customers depend on.
How do you approach this?"

WHAT THEY'RE TESTING:
├── Versioning strategy
├── Deprecation timeline management
├── Customer communication
└── Parallel support period planning
```

## Additional Interview Probes for Migration Thinking

```
PROBE 5: "What would you monitor during this rollout?"

L5 RESPONSE:
"We'd monitor error rates and latency."

L6 RESPONSE:
"For this specific migration, I'd monitor:
- Functional correctness: Shadow comparison match rate should stay > 99.9%
- Performance: P99 latency should not increase more than 10%
- Consistency: Dual-write divergence rate should be 0
- Rollback health: Old system capacity should remain available
- Business metrics: Conversion rate shouldn't drop (user-visible impact)

I'd set up automated rollback triggers for:
- Error rate > 0.1% above baseline
- Latency P99 > 50% above baseline
- Any data inconsistency detected

And I'd require these metrics to be stable for 24 hours before advancing
each rollout percentage."
```

```
PROBE 6: "How would you know the migration is complete?"

L5 RESPONSE:
"When we've moved all traffic to the new system."

L6 RESPONSE:
"Migration complete has multiple criteria:

Functional completeness:
- 100% traffic on new system for 2+ weeks
- Zero shadow comparison failures
- All edge cases validated (monthly jobs, quarterly processes)

Operational completeness:
- Runbooks updated for new system
- On-call trained on new system
- Alerting tuned for new system
- Old system dependencies documented and transitioned

Confidence gate:
- Run through at least one full business cycle (monthly, quarterly if applicable)
- Validate with load test at 2x expected peak
- Complete at least one rollback drill successfully

Only after all of these would I consider decommissioning the old system,
and I'd keep it in read-only mode for another month before deletion."
```

## Staff-Level Phrases

These phrases signal Staff-level thinking to interviewers:

```
ON REVERSIBILITY:
"This is a one-way door, so we'd stage it carefully and maintain rollback 
capability until we're confident the new system is stable."

"We prioritize reversibility over speed here—the cost of being wrong is 
higher than the cost of taking longer."

"I want to convert this one-way door into a two-way door by [specific approach]."

ON BLAST RADIUS:
"The blast radius of this change is [scope]. We'd contain it by [mechanism]."

"If this fails, it affects [specific components/users]. We'd detect failure 
via [monitoring] and recover by [rollback approach]."

ON MIGRATION STRATEGY:
"We'd run both systems in parallel during the transition, with the old system 
as source of truth until we've validated the new system at full traffic."

"The migration would be incremental—we can stop or rollback at any phase 
without data loss."

"Before we deprecate the old system, we need [specific validation criteria] 
to prove the new system is ready."

ON RISK:
"The riskiest part of this change is [specific component] because [reason]. 
We'd de-risk it by [approach]."

"I'm not comfortable making this change without [specific safeguard] because 
the failure mode is [description]."
```

## Common Mistake Strong Senior Engineers Make

```
┌─────────────────────────────────────────────────────────────────────────────┐
│     COMMON L5 MISTAKE: FOCUSING ON THE END STATE, NOT THE JOURNEY           │
│                                                                             │
│   SCENARIO: Interview question about migrating to a new database            │
│                                                                             │
│   L5 RESPONSE (Common Mistake):                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  "We'd use [new database] because it handles our scale better.      │   │
│   │   The new schema would look like this... The queries would be       │   │
│   │   more efficient because... The data model supports our use         │   │
│   │   cases better because..."                                          │   │
│   │                                                                     │   │
│   │   [Spends 90% of answer on why the new database is better]          │   │
│   │   [Spends 10% saying "we'd migrate the data over"]                  │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   WHY THIS FAILS:                                                           │
│   ├── Choosing the right destination is L5 work                             │
│   ├── Getting there safely is L6 work                                       │
│   ├── The interviewer already knows the new DB might be better              │
│   └── They want to know if you can execute the migration                    │
│                                                                             │
│   L6 RESPONSE (Staff-Level):                                                │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  "The new database better fits our access patterns, but the         │   │
│   │   real challenge is the migration. Here's my approach:              │   │
│   │                                                                     │   │
│   │   Phase 1: Dual-write to both databases, old DB is source of truth  │   │
│   │   Phase 2: Shadow-read from new DB, compare results                 │   │
│   │   Phase 3: Canary traffic to new DB with fallback                   │   │
│   │   Phase 4: Gradual traffic shift with monitoring                    │   │
│   │   Phase 5: Old DB becomes read-only backup                          │   │
│   │   Phase 6: Decommission old DB (one-way door)                       │   │
│   │                                                                     │   │
│   │   The riskiest phase is [X] because [reason]. We'd mitigate by...   │   │
│   │   Rollback at each phase looks like..."                             │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   INTERVIEWER SIGNAL:                                                       │
│   L6 candidates spend more time on "how do we get there safely" than        │
│   "why is the destination better."                                          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Part 11: Reflection, Brainstorming, and Homework

## Brainstorming Questions

Use these questions to develop your migration and evolution thinking:

### System Risk Analysis

1. **"What change would scare you most in this system?"**
   - What's the riskiest component to modify?
   - Why is it risky? (Data, coupling, blast radius, reversibility)
   - How would you reduce the risk before making the change?

2. **"Where would rollback fail?"**
   - Which changes in this system are truly irreversible?
   - What data transformations lose information?
   - What external dependencies can't be undone?

3. **"What will force this system to change in 2 years?"**
   - What scale threshold will it hit?
   - What requirements are likely to emerge?
   - What dependencies will become problematic?

4. **"If this migration fails at 50%, what happens?"**
   - Is the system in a consistent state?
   - Can you continue forward? Can you roll back?
   - What data is in the "old" state vs. "new" state?

### Design for Evolution

5. **"Which decisions in this design are one-way doors?"**
   - Data format choices
   - External API contracts
   - Vendor dependencies
   - Fundamental architecture patterns

6. **"How many teams must coordinate to change X?"**
   - Is cross-team coordination required for routine changes?
   - Can teams evolve independently?
   - Where are the coupling points?

7. **"What's the minimum viable migration?"**
   - Can you achieve the goal with a smaller change?
   - What's the 80/20 version of this migration?
   - Can you stage it into smaller independent migrations?

8. **"What would make this migration unnecessary?"**
   - Is there an alternative to migrating?
   - Can you achieve the goal by extending rather than replacing?
   - Is the migration driven by real constraints or assumptions?

### Migration-Specific Brainstorming

9. **"What's the hidden dependency in this system?"**
   - What batch jobs, scheduled tasks, or periodic processes exist?
   - What credentials or tokens might outlive the migration window?
   - What downstream systems might cache data from this system?

10. **"How would I test that the migration worked?"**
    - What's my comparison strategy (shadow, replay, synthetic)?
    - What data shapes exist in production that don't exist in staging?
    - How would I know if 0.1% of requests are broken?

11. **"What's the cost of running both systems?"**
    - Infrastructure cost of dual systems
    - Engineering cost of maintaining both
    - Cognitive cost of team context-switching
    - Opportunity cost of not building features

12. **"What would cause this migration to take 3x longer than planned?"**
    - Unknown consumers that can't migrate on schedule
    - Data inconsistencies that require manual remediation
    - Performance issues discovered late in rollout
    - Team member departure mid-migration

### Evolution and Design-Time Brainstorming

13. **"What assumption am I making that will be wrong in 2 years?"**
    - Scale assumptions (10K users → 10M users)
    - Data locality assumptions (single region → global)
    - Consistency assumptions (strong → eventual might be acceptable)
    - Team structure assumptions (one team → multiple teams)

14. **"What would it take to replace this database?"**
    - How tightly coupled is business logic to the data store?
    - Can I swap implementations behind an interface?
    - What would the dual-write period look like?

15. **"If I had to deprecate this API tomorrow, how bad would it be?"**
    - Who are the consumers?
    - Are they internal or external?
    - What's the notification and support burden?

---

## Homework Exercises

### Exercise 1: Design a Migration Plan for a Live System

**Scenario**: You operate a user notification service that stores notification preferences in Redis. You need to migrate to a relational database for better querying and ACID guarantees. The service handles 10,000 requests/second and cannot have downtime.

**Your task**:
1. Design a phased migration plan (minimum 4 phases)
2. For each phase:
   - Describe what changes
   - Define success criteria
   - Define rollback procedure
3. Identify the riskiest phase and explain why
4. Define what metrics you'd monitor during migration
5. Specify when you would abort the migration

**Deliverable**: Written migration plan (1-2 pages)

---

### Exercise 2: Identify Irreversible Decisions in an Existing Architecture

**Scenario**: Review the architecture diagram below (or use a system you work on):

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Web Frontend  │───▶│   API Gateway   │───▶│   Auth Service  │
└─────────────────┘    └────────┬────────┘    └─────────────────┘
                                │
        ┌───────────────────────┼───────────────────────┐
        │                       │                       │
        ▼                       ▼                       ▼
┌───────────────┐    ┌──────────────────┐    ┌──────────────────┐
│ User Service  │    │  Order Service   │    │ Payment Service  │
└───────┬───────┘    └────────┬─────────┘    └────────┬─────────┘
        │                     │                       │
        ▼                     ▼                       ▼
┌───────────────┐    ┌──────────────────┐    ┌──────────────────┐
│   User DB     │    │    Order DB      │    │   Payment DB     │
│  (PostgreSQL) │    │   (PostgreSQL)   │    │  (PostgreSQL)    │
└───────────────┘    └──────────────────┘    └──────────────────┘
```

**Your task**:
1. List 5 decisions in this architecture that would be "one-way doors" (hard to reverse)
2. For each decision, explain:
   - Why it's hard to reverse
   - What the migration would look like if you needed to change it
   - How you would have designed it differently to make it more reversible
3. Rank them by difficulty to migrate (1 = hardest)

**Deliverable**: Analysis document (1-2 pages)

---

### Exercise 3: Failure Mode Analysis

**Scenario**: Your team is planning a migration from synchronous API calls between services to asynchronous messaging via a queue. The migration will happen incrementally—some calls will use the queue while others still use direct API calls.

**Your task**:
1. List 5 failure modes that could occur during this mixed-mode operation
2. For each failure mode:
   - Describe the failure scenario
   - Explain how it would manifest to users
   - Describe how you would detect it
   - Describe how you would recover
3. Recommend: What validation would you require before considering the migration complete?

**Deliverable**: Failure mode analysis (1-2 pages)

---

### Exercise 4: Cross-Team Migration Coordination

**Scenario**: You're leading a migration that affects 4 teams:
- Your team (owns the system being migrated)
- Team A (20% of traffic, using old API)
- Team B (50% of traffic, using old API, different codebase)
- Team C (30% of traffic, external partner, limited availability)

The migration requires all teams to update their client code to use a new API.

**Your task**:
1. Create a communication plan:
   - When and how do you inform each team?
   - What information does each team need?
   - How do you confirm readiness?
2. Create a coordination timeline:
   - What's the order of team migrations?
   - What are the dependencies between team migrations?
   - What happens if one team misses their window?
3. Design the fallback strategy:
   - How long do you support both old and new API?
   - What happens if Team C can't migrate on time?
   - At what point do you force migration vs. extend support?

**Deliverable**: Coordination plan document (2-3 pages)

---

### Exercise 5: Evolution Planning at Design Time

**Scenario**: You're designing a new feature flag system. It will be used by all services in your organization to control feature rollouts.

**Your task**:
1. Identify 3 ways this system will likely need to evolve in the next 3 years
2. For each evolution:
   - Describe the trigger (why the evolution would be needed)
   - Describe the change required
   - Design the current architecture to make this evolution easier
3. Identify 2 design decisions that should be treated as one-way doors
4. For each one-way door:
   - Explain why you're making this commitment now
   - Describe what you'd do if you were wrong

**Deliverable**: Evolution-aware design document (2-3 pages)

---

### Exercise 6: Hidden Dependency Discovery

**Scenario**: You're planning to deprecate an internal authentication service that has been running for 5 years. You need to migrate all consumers to the new identity platform.

**Your task**:
1. Create a dependency discovery checklist:
   - What sources would you search for consumers?
   - How would you find batch jobs that run monthly/quarterly?
   - How would you find services that cache auth tokens?
2. For each type of consumer you might find:
   - How would you notify them?
   - What timeline would you give them?
   - What support would you provide?
3. Design a monitoring strategy:
   - How would you detect unknown consumers after announcing deprecation?
   - What would you do if you found one 1 week before decommission?
4. Define the criteria for when it's safe to fully decommission:
   - How long after last known usage?
   - What about cached credentials?

**Deliverable**: Dependency discovery and deprecation plan (1-2 pages)

---

### Exercise 7: Migration Observability Design

**Scenario**: You're migrating a payment processing service from a synchronous to an asynchronous architecture. The migration will take 3 months and involves dual-write to both systems.

**Your task**:
1. Design the monitoring dashboard for the migration:
   - What metrics would you track?
   - What would trigger an alert?
   - What would trigger automatic rollback?
2. Define thresholds for each rollout percentage:
   - What must be true to advance from 10% to 25%?
   - What must be true to advance from 50% to 75%?
   - What must be true to advance to 100%?
3. Design the comparison testing strategy:
   - How would you verify async processing produces same results as sync?
   - How would you handle timing differences?
   - What would you do about non-deterministic results?
4. Create a rollback runbook:
   - Step-by-step procedure
   - Decision criteria for when to invoke
   - Expected completion time

**Deliverable**: Migration observability design document (2-3 pages)

---

### Exercise 8: Latency Regression Prevention

**Scenario**: You're migrating from a denormalized NoSQL store to a normalized PostgreSQL schema. Historical data shows:
- 80% of entities have < 10 related records
- 15% have 10-100 related records
- 4% have 100-1000 related records
- 1% have > 1000 related records

**Your task**:
1. Identify the latency regression risks:
   - What query patterns might become O(n) in the new schema?
   - Where might N+1 query problems emerge?
2. Design a load test that would catch these issues:
   - What data distribution would you use?
   - What entity sizes would you specifically test?
3. For each risk identified:
   - How would you mitigate it in the new schema design?
   - How would you monitor for it in production?
4. Create segment-aware monitoring:
   - How would you track latency by entity size?
   - What thresholds would you set for each segment?

**Deliverable**: Latency risk analysis and mitigation plan (1-2 pages)

---

### Exercise 9: Migration Cost-Benefit Analysis

**Scenario**: Your team is considering migrating from a managed database service ($15K/month) to a self-managed cluster ($8K/month infrastructure, but requires engineering effort). The migration will take 4 months.

**Your task**:
1. Quantify the migration costs:
   - Infrastructure (running both systems)
   - Engineering (heads-down on migration)
   - Opportunity cost (features not built)
   - Risk cost (expected cost of migration failures)
2. Quantify the benefits:
   - Monthly savings after migration
   - Operational improvements
   - Performance improvements
3. Calculate the payback period
4. Identify the risks that could change the calculation:
   - What could make the migration take 8 months instead of 4?
   - What hidden costs might emerge?
5. Make a recommendation: Migrate or not? Why?

**Deliverable**: Cost-benefit analysis document (1-2 pages)

---

### Exercise 10: Rollback Drill Design

**Scenario**: Your team is halfway through a migration (50% traffic on new system). You've never tested the rollback procedure.

**Your task**:
1. Design a rollback drill that can be safely run in production:
   - What would you actually do?
   - How would you minimize user impact?
   - How would you measure success?
2. Define the rollback procedure:
   - Step-by-step instructions
   - Who needs to be involved?
   - What tools/commands are used?
3. Specify what you'd verify after rollback:
   - Functional correctness
   - Performance
   - Data consistency
4. Document the drill results template:
   - What would you record?
   - How would you share findings with the team?
   - What would trigger a "failed drill" and what would you do?

**Deliverable**: Rollback drill design and procedure document (1-2 pages)

---

## Summary: The Staff Engineer's Evolution Mindset

```
┌─────────────────────────────────────────────────────────────────────────────┐
│              SYSTEM EVOLUTION: STAFF ENGINEER PRINCIPLES                    │
│                                                                             │
│   1. Evolution is the default state                                         │
│      └── Design for change, not just for correctness                        │
│                                                                             │
│   2. Migrations are harder than greenfield                                  │
│      └── The journey matters as much as the destination                     │
│                                                                             │
│   3. Reversibility > Speed                                                  │
│      └── Make one-way doors into two-way doors                              │
│                                                                             │
│   4. Blast radius determines risk                                           │
│      └── Contain failures by design                                         │
│                                                                             │
│   5. Human coordination is often the bottleneck                             │
│      └── Design systems that require fewer humans to change safely          │
│                                                                             │
│   6. Simplicity enables evolution                                           │
│      └── Every complexity you add is a migration you'll do later            │
│                                                                             │
│   7. The old system is your safety net                                      │
│      └── Don't delete it until the new system is proven                     │
│                                                                             │
│   8. Staff Engineers are evaluated on change management                     │
│      └── Not on avoiding change, but on making change safe                  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# End of Chapter 27

This chapter covered System Evolution, Migration, and Risk Management at Staff level. You learned why evolution is inevitable, how to identify and contain risk, how to plan and execute migrations safely, and how to design systems that can change without breaking.

**Key takeaway**: The difference between a senior engineer and a Staff Engineer is not the ability to build systems—it's the ability to change systems safely while they're running. Master this, and you demonstrate the judgment that defines Staff-level work.
