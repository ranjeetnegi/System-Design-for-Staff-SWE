# Chapter 28 Supplement: Data Encoding and Schema Evolution

---

# Introduction

Chapter 28 covers database selection and evolution. But data doesn't just live in databases—it flows between services via APIs, message queues, and event streams. The *encoding format* (JSON, Protobuf, Avro) and *schema evolution* rules determine whether you can add a field without breaking consumers, or whether a deployment will cause deserialization failures. This supplement fills that gap.

At Staff level, you're asked to choose encoding formats for high-throughput systems, design backward- and forward-compatible schemas, and migrate consumers when breaking changes are unavoidable. This supplement gives you the depth to answer those questions with precision.

**The Staff Engineer's Encoding Principle**: Schema evolution is not an afterthought. Choose formats that support it (Avro, Protobuf with optional fields). Follow compatibility rules: add optional, never remove or renumber. Plan deprecation timelines. Encoding choice affects latency, storage cost, and compatibility—design for change from day one.

**How to use this supplement**: Read it alongside Chapter 28. When the main chapter discusses data stores, this supplement covers the wire format—how data is encoded for transport between services. For interview prep, focus on the L5 vs L6 tables, the format comparison, schema evolution rules, and the interview essentials. For deep dives, work through the wire format details, the Schema Registry section, and the production incidents. The goal is to build intuition about why encoding choices matter at scale and how to evolve schemas safely across hundreds of services.

---

## Quick Visual: Encoding and Evolution at a Glance

```
┌─────────────────────────────────────────────────────────────────────────────┐
│     DATA ENCODING: FORMAT CHOICE AND SCHEMA EVOLUTION                       │
│                                                                             │
│   L5 Framing: "We use JSON for APIs"                                        │
│   L6 Framing: "JSON for public APIs (tooling, adoption). Protobuf for       │
│                internal high-throughput (50% smaller, 3× faster). Avro for  │
│                event streams (schema in payload, evolution built-in).       │
│                Schema evolution: add optional, never remove. Backward      │
│                compatibility lets new producer, old consumer. Forward      │
│                lets old producer, new consumer."                            │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  THE ENCODING DECISION TREE:                                         │   │
│   │                                                                     │   │
│   │  Who consumes? ──► External devs ──► JSON (tooling, curl, Postman)   │   │
│   │       │                                                             │   │
│   │       └──► Internal services ──► High QPS? ──► Protobuf (gRPC)       │   │
│   │                                      │                               │   │
│   │                                      └──► Event stream? ──► Avro     │   │
│   │                                           (schema registry,          │   │
│   │                                            evolution built-in)       │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  COMPATIBILITY MATRIX:                                               │   │
│   │  Backward: new schema reads old data    ✓ Add optional with default  │   │
│   │  Forward:  old schema reads new data    ✓ Ignore unknown fields      │   │
│   │  Full:     both directions              ✓ Add optional, never remove │   │
│   │  Breaking: neither direction            ✗ Rename, retype, renumber   │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   RULE: Add optional fields. Never remove. Never renumber (Protobuf).       │
│   COST: Wrong format at 100K QPS → 3× bandwidth, 5× CPU for parsing.       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## L5 vs L6: Data Encoding Thinking

| Scenario | L5 Approach | L6 Approach |
|----------|-------------|-------------|
| **Format choice** | "JSON for everything" | "JSON for public APIs (curl, Postman). Protobuf for internal (50% smaller, 3× faster encode). Avro for Kafka (schema registry, evolution). Match format to audience and throughput." |
| **Schema change** | "Add a field" | "Add as optional. Old consumers ignore it. New consumers handle absence. Never remove or renumber. Protobuf: use reserved for deprecated field numbers. Document deprecation timeline." |
| **Breaking change** | "We'll version the API" | "Version (v1, v2) for breaking. Support both during migration. Deprecation window: 6 months. Sunset headers. Monitor for old clients. Expand-contract pattern." |
| **Performance** | "JSON is fine" | "At 100K req/sec, JSON parsing burns 30% CPU. Protobuf: 3× faster encode, 50% smaller on wire. At our scale, switching internal APIs to Protobuf saves 200 cores and 40% bandwidth." |
| **Schema registry** | "We'll document schemas in Confluence" | "Confluence schemas drift. Schema Registry enforces compatibility at write time. Producer can't publish incompatible schema. Registry is the source of truth, not docs." |
| **Cross-language** | "We all use Java" | "Today. In 18 months, the ML team uses Python, the frontend BFF is in Go. Protobuf and Avro generate code for all languages. JSON works everywhere but has no contract." |

**Key Difference**: L6 engineers make encoding decisions based on audience, throughput, evolution needs, and cross-team coordination—not habit. They treat schema as a contract with the future.

---

# Part 1: Format Comparison — JSON vs Protobuf vs Avro

## The Core Trade-off

Every encoding format trades between three axes:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    THE ENCODING TRADE-OFF TRIANGLE                          │
│                                                                             │
│                          Human Readability                                  │
│                               ▲                                             │
│                              / \                                            │
│                             /   \                                           │
│                            / JSON \                                         │
│                           /       \                                         │
│                          /_________\                                        │
│                         /           \                                       │
│                        /     XML      \                                     │
│                       /                 \                                   │
│                      /                   \                                  │
│       Size/Speed ◄──/─── MessagePack ─────\──► Schema/Evolution            │
│                    /                       \                                │
│                   / Protobuf         Avro   \                              │
│                  /                           \                             │
│                 /___________________________  \                            │
│                                                                             │
│   JSON:     Readable ✓  Small ✗  Schema ✗  Evolution: loose               │
│   Protobuf: Readable ✗  Small ✓  Schema ✓  Evolution: field rules         │
│   Avro:     Readable ✗  Small ✓  Schema ✓  Evolution: built-in            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Detailed Comparison

| Property | JSON | Protobuf | Avro | MessagePack | Thrift |
|----------|------|----------|------|-------------|--------|
| **Encoding** | Text | Binary | Binary | Binary | Binary |
| **Size** (100-field msg) | ~800 bytes | ~350 bytes | ~320 bytes | ~500 bytes | ~360 bytes |
| **Encode speed** | Baseline | ~3× faster | ~2.5× faster | ~2× faster | ~3× faster |
| **Decode speed** | Baseline | ~3× faster | ~2× faster | ~1.5× faster | ~3× faster |
| **Schema required?** | No | Yes (.proto) | Yes (.avsc) | No | Yes (.thrift) |
| **Schema in payload?** | No | No | Yes (or ID) | No | No |
| **Human readable?** | Yes | No | No | No | No |
| **Schema evolution** | Loose (no enforcement) | Field numbers + rules | Reader/writer schema | None | Similar to Protobuf |
| **Code generation** | Optional | Required | Optional | Optional | Required |
| **Language support** | Universal | Broad | Broad | Broad | Moderate |
| **gRPC native** | No | Yes | No | No | No |
| **Schema Registry** | No | Yes (Confluent) | Yes (Confluent) | No | No |

## When to Use Which

### JSON — The Universal Lingua Franca

**Use when**: External APIs, debugging, small-scale internal APIs, configuration files.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│   JSON: STRENGTHS AND WEAKNESSES                                            │
│                                                                             │
│   STRENGTHS:                                                                │
│   ✓ Every language, every tool, every developer                             │
│   ✓ curl, Postman, browser devtools — zero setup                            │
│   ✓ Self-describing (field names in payload)                                │
│   ✓ Human-readable for debugging                                           │
│   ✓ No code generation step                                                │
│                                                                             │
│   WEAKNESSES:                                                               │
│   ✗ Verbose: field names repeated in every message                          │
│   ✗ No schema enforcement — "phone" could be string, int, or missing        │
│   ✗ Slow parsing — text to typed values is CPU-intensive                    │
│   ✗ No built-in evolution rules — anything goes                             │
│   ✗ Number precision: 64-bit integers lose precision in JavaScript          │
│   ✗ No native binary support — base64 encoding adds 33% overhead           │
│                                                                             │
│   HIDDEN COST AT SCALE:                                                     │
│   100K req/sec × 800 bytes = 80 MB/sec = 6.9 TB/day                       │
│   Same data in Protobuf: 35 MB/sec = 3 TB/day → 50% bandwidth savings     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**JSON gotchas at scale**:
- **Number precision**: JavaScript's `Number` is IEEE 754 double. Integers > 2^53 lose precision. Use string representation for IDs.
- **Date formats**: No standard. ISO 8601? Unix timestamp? Milliseconds? Document and enforce.
- **Null vs absent**: `{"phone": null}` vs `{}` — semantically different but often conflated.
- **Encoding**: UTF-8 assumed but not always enforced. BOM characters cause parsing failures.

### Protobuf — The Internal Workhorse

**Use when**: Internal service-to-service, gRPC, high-QPS systems, mobile apps (bandwidth matters).

```
┌─────────────────────────────────────────────────────────────────────────────┐
│   PROTOBUF: WHY IT'S DOMINANT FOR INTERNAL APIS                             │
│                                                                             │
│   .proto file (source of truth):                                            │
│   ┌───────────────────────────────────┐                                     │
│   │  syntax = "proto3";               │                                     │
│   │                                   │                                     │
│   │  message User {                   │                                     │
│   │    int64 id = 1;                  │    ◄── Field number = wire identity  │
│   │    string name = 2;               │    ◄── Never renumber                │
│   │    string email = 3;              │    ◄── Never reuse after removal     │
│   │    optional string phone = 4;     │    ◄── Optional: safe to add        │
│   │    reserved 5, 6;                 │    ◄── Prevent accidental reuse      │
│   │    reserved "old_field";          │                                     │
│   │  }                                │                                     │
│   └───────────────────────────────────┘                                     │
│          │                                                                   │
│          ▼  protoc generates                                                │
│   ┌──────────┐  ┌──────────┐  ┌──────────┐                                 │
│   │  Java    │  │  Go      │  │  Python  │   One schema, all languages      │
│   │  stubs   │  │  stubs   │  │  stubs   │                                 │
│   └──────────┘  └──────────┘  └──────────┘                                 │
│                                                                             │
│   ON THE WIRE:                                                              │
│   Field 1 (id): varint → 1 byte for small values                           │
│   Field 2 (name): length-delimited → no field name on wire                 │
│   Result: ~50% smaller than JSON, ~3× faster encode/decode                 │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Avro — The Event Stream Native

**Use when**: Kafka event streams, data pipelines, schema evolution is critical, Hadoop ecosystem.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│   AVRO: SCHEMA-IN-PAYLOAD FOR EVOLUTION                                     │
│                                                                             │
│   Schema (.avsc):                                                           │
│   ┌───────────────────────────────────┐                                     │
│   │  {                                │                                     │
│   │    "type": "record",              │                                     │
│   │    "name": "User",                │                                     │
│   │    "fields": [                    │                                     │
│   │      {"name": "id", "type": "long"},                                   │
│   │      {"name": "name", "type": "string"},                               │
│   │      {"name": "email", "type": "string"},                              │
│   │      {"name": "phone", "type": ["null","string"], "default": null}     │
│   │    ]                              │                                     │
│   │  }                                │                                     │
│   └───────────────────────────────────┘                                     │
│                                                                             │
│   KEY DIFFERENCE FROM PROTOBUF:                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Protobuf: field NUMBERS on wire. Schema needed at both ends.        │   │
│   │  Avro:     field ORDER on wire. Writer schema + reader schema.       │   │
│   │            Schema Registry stores versions. Consumer resolves.       │   │
│   │                                                                     │   │
│   │  Kafka message = [magic byte][schema ID (4 bytes)][Avro payload]     │   │
│   │  Consumer: fetch schema by ID → deserialize with resolution          │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   WHY AVRO FOR KAFKA:                                                       │
│   • Schema ID in every message → consumer always knows schema              │
│   • Reader/writer schema resolution → old consumer reads new data          │
│   • Schema Registry enforces compatibility → can't publish breaking change │
│   • Compact: no field names or numbers on wire → just values in order      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Part 2: Wire Format Deep Dive

Understanding wire formats is what separates "I use Protobuf" from "I know why Protobuf is smaller." At Staff level, you're expected to reason about encoding efficiency.

## JSON Wire Format

```
┌─────────────────────────────────────────────────────────────────────────────┐
│   JSON ON THE WIRE: TEXT, VERBOSE, SELF-DESCRIBING                          │
│                                                                             │
│   {"id":12345,"name":"Alice","email":"alice@example.com","phone":null}      │
│                                                                             │
│   Breakdown:                                                                │
│   {"id":           → 5 bytes (field name + colon + quote)                   │
│   12345            → 5 bytes (number as text)                               │
│   ,"name":"        → 8 bytes                                                │
│   Alice"           → 6 bytes                                                │
│   ,"email":"       → 9 bytes                                                │
│   alice@ex...com"  → 18 bytes                                               │
│   ,"phone":null    → 13 bytes                                               │
│   }                → 1 byte                                                 │
│   Total: ~65 bytes                                                          │
│                                                                             │
│   OVERHEAD: Field names ("id", "name", "email", "phone") repeat in         │
│   every single message. At 1M messages, that's 35 MB just for field names. │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Protobuf Wire Format

```
┌─────────────────────────────────────────────────────────────────────────────┐
│   PROTOBUF ON THE WIRE: BINARY, COMPACT, TAG-LENGTH-VALUE                   │
│                                                                             │
│   Wire types:                                                               │
│   0 = Varint (int32, int64, bool, enum)                                     │
│   1 = 64-bit (fixed64, double)                                              │
│   2 = Length-delimited (string, bytes, nested message, repeated)            │
│   5 = 32-bit (fixed32, float)                                              │
│                                                                             │
│   Encoding of User{id=12345, name="Alice", email="alice@example.com"}:     │
│                                                                             │
│   Field 1 (id=12345):                                                       │
│   ┌──────────┬───────────────────┐                                          │
│   │ Tag: 0x08│ Varint: 0xB960   │  = 3 bytes (field 1, wire type 0)        │
│   └──────────┴───────────────────┘                                          │
│                                                                             │
│   Field 2 (name="Alice"):                                                   │
│   ┌──────────┬──────┬───────────┐                                           │
│   │ Tag: 0x12│Len: 5│ "Alice"   │  = 7 bytes (field 2, wire type 2)        │
│   └──────────┴──────┴───────────┘                                           │
│                                                                             │
│   Field 3 (email="alice@example.com"):                                      │
│   ┌──────────┬───────┬─────────────────────┐                                │
│   │ Tag: 0x1A│Len: 17│ "alice@example.com" │  = 19 bytes                   │
│   └──────────┴───────┴─────────────────────┘                                │
│                                                                             │
│   Total: ~29 bytes (vs ~65 bytes JSON → 55% smaller)                       │
│                                                                             │
│   KEY: No field names on wire. Just field number + wire type in the tag.   │
│   That's why renumbering breaks everything—field 2 IS "name" forever.      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Varint Encoding

Protobuf uses variable-length integers. Small numbers use fewer bytes:

| Value | Bytes Used | Fixed32 Would Use |
|-------|-----------|-------------------|
| 0–127 | 1 byte | 4 bytes |
| 128–16,383 | 2 bytes | 4 bytes |
| 16,384–2,097,151 | 3 bytes | 4 bytes |
| > 2 billion | 5 bytes | 4 bytes |

**Staff insight**: If your IDs are sequential (1, 2, 3...), varint saves significantly. If they're random 64-bit UUIDs, varint offers no advantage over fixed64. Design IDs with encoding in mind.

## Avro Wire Format

```
┌─────────────────────────────────────────────────────────────────────────────┐
│   AVRO ON THE WIRE: PURE VALUES, NO TAGS                                    │
│                                                                             │
│   Avro does NOT put field names or field numbers on the wire.               │
│   It relies on schema resolution: writer schema + reader schema.            │
│                                                                             │
│   Writer schema defines field ORDER. Data is encoded in that order.         │
│                                                                             │
│   Encoding of User{id=12345, name="Alice", email="alice@example.com"}:     │
│                                                                             │
│   ┌──────────────┬───────────────┬───────────────────────┐                  │
│   │ zigzag(12345)│ len + "Alice" │ len + "alice@ex...com"│                  │
│   │  3 bytes     │  6 bytes      │  18 bytes             │                  │
│   └──────────────┴───────────────┴───────────────────────┘                  │
│                                                                             │
│   Total: ~27 bytes (smallest of all three)                                 │
│                                                                             │
│   BUT: Reader MUST have the writer's schema to decode.                     │
│   In Kafka: schema ID is prepended → Schema Registry lookup.               │
│   Without schema: the bytes are meaningless.                                │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Schema Resolution: How Avro Handles Evolution

```
┌─────────────────────────────────────────────────────────────────────────────┐
│   AVRO SCHEMA RESOLUTION: WRITER SCHEMA + READER SCHEMA                     │
│                                                                             │
│   Writer (v2):                     Reader (v1):                             │
│   ┌─────────────────────┐          ┌─────────────────────┐                  │
│   │ fields:              │          │ fields:              │                  │
│   │   id    (long)       │          │   id    (long)       │   ✓ Match      │
│   │   name  (string)     │          │   name  (string)     │   ✓ Match      │
│   │   email (string)     │          │   email (string)     │   ✓ Match      │
│   │   phone (string|null)│          │                      │   ← Ignored    │
│   └─────────────────────┘          └─────────────────────┘                  │
│                                                                             │
│   Resolution:                                                               │
│   1. For each field in reader schema, find matching field in writer schema  │
│   2. If found → use writer's value                                          │
│   3. If not found in writer → use reader's default                          │
│   4. If writer has field not in reader → skip (ignore)                      │
│                                                                             │
│   This is why Avro evolution "just works":                                  │
│   • New field with default → old readers use default (backward compatible)  │
│   • Removed field with default → new readers use default (forward compat)  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Part 3: Schema Evolution Rules — The Contract With the Future

Schema evolution is the most critical aspect of encoding at Staff level. A wrong schema change can break every consumer downstream—immediately or, worse, silently.

## Compatibility Types

```
┌─────────────────────────────────────────────────────────────────────────────┐
│   COMPATIBILITY: WHAT CAN CHANGE WITHOUT BREAKING?                          │
│                                                                             │
│   BACKWARD COMPATIBLE:                                                      │
│   New schema can read data written by old schema.                           │
│   "New consumer, old producer" — the most common upgrade path.              │
│                                                                             │
│   Producer (v1) ──► [old data] ──► Consumer (v2) ✓                          │
│                                                                             │
│   Allowed: Add field with default. Remove field.                            │
│   Why: Consumer v2 has defaults for missing fields.                         │
│                                                                             │
│   ─────────────────────────────────────────────────────────────────────────  │
│                                                                             │
│   FORWARD COMPATIBLE:                                                       │
│   Old schema can read data written by new schema.                           │
│   "Old consumer, new producer" — needed for rolling deployments.            │
│                                                                             │
│   Producer (v2) ──► [new data] ──► Consumer (v1) ✓                          │
│                                                                             │
│   Allowed: Add field (old consumer ignores). Remove field with default.    │
│   Why: Consumer v1 ignores unknown fields, uses defaults for removed ones. │
│                                                                             │
│   ─────────────────────────────────────────────────────────────────────────  │
│                                                                             │
│   FULL COMPATIBLE:                                                          │
│   Both directions work. Most restrictive. Safest.                           │
│                                                                             │
│   Allowed: Add optional field with default. That's basically it.           │
│   This is what Schema Registry "FULL" mode enforces.                       │
│                                                                             │
│   ─────────────────────────────────────────────────────────────────────────  │
│                                                                             │
│   BREAKING (NONE):                                                          │
│   Neither direction works. Requires coordinated migration.                  │
│                                                                             │
│   Causes: Rename field. Change type. Remove required field.                │
│   Impact: Deserialization failure. Data loss. Production incident.          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Protobuf Evolution Rules

| Rule | Do | Don't | Why |
|------|-----|-------|-----|
| **Adding fields** | Add as `optional` with new field number | Add as `required` | Required fields can't be absent in old producers |
| **Removing fields** | Mark deprecated, stop writing, add `reserved` | Delete the field definition | Prevents accidental reuse of field number |
| **Field numbers** | Keep forever | Renumber or reuse | Field number IS the wire identity |
| **Field types** | Keep or use compatible promotions | Change `int32` to `string` | Wire type mismatch → deserialization crash |
| **Field names** | Rename freely | — | Names are only for code; wire uses numbers |
| **Enums** | Add new values | Remove or renumber values | Old consumers may receive unknown enum values |
| **Oneof** | Add fields to oneof | Move existing field into oneof | Changes wire format |
| **Default values** | Proto3: always zero/empty/false | Rely on custom defaults | Proto3 has no custom defaults |

### Safe Type Promotions (Protobuf)

| From | To | Safe? |
|------|----|-------|
| int32 | int64 | Yes (widening) |
| int32 | sint32 | No (different encoding) |
| fixed32 | fixed64 | No (different wire type) |
| string | bytes | Yes (same wire type 2) |
| single field | repeated | Yes (additive) |

### The `reserved` Keyword

```protobuf
message User {
  int64 id = 1;
  string name = 2;
  // Field 3 was "email" — removed in v2.
  // Field 4 was "address" — removed in v3.
  reserved 3, 4;
  reserved "email", "address";
  
  string contact_email = 5;  // New field, new number
}
```

**Why**: If a future developer adds a new field with number 3, old consumers still reading field 3 as "email" would deserialize the new field's bytes as a string—silently producing garbage. `reserved` prevents this.

## Avro Evolution Rules

| Rule | Do | Don't | Why |
|------|-----|-------|-----|
| **Adding fields** | Add with default value | Add without default | Reader using old schema needs a default for missing field |
| **Removing fields** | Remove fields that have defaults | Remove fields without defaults | Writer using old schema still sends the field; reader must handle |
| **Renaming fields** | Use `aliases` | Rename directly | Reader matches by name; rename without alias breaks resolution |
| **Changing types** | Use union types (`["null", "string"]`) | Change `long` to `string` | Type mismatch in resolution → failure |
| **Field order** | Change freely | — | Avro matches by name, not position, during resolution |

### Avro Aliases: Renaming Without Breaking

```json
{
  "type": "record",
  "name": "User",
  "fields": [
    {"name": "user_id", "type": "long", "aliases": ["id"]},
    {"name": "full_name", "type": "string", "aliases": ["name"]}
  ]
}
```

Old data with field "id" matches new field "user_id" via alias. No data migration needed.

---

# Part 4: Schema Registry — The Source of Truth

## Why a Registry?

Without a registry, schema compatibility is an honor system. With 200 services and 50 teams, honor systems fail.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│   SCHEMA REGISTRY: ENFORCED COMPATIBILITY                                   │
│                                                                             │
│   WITHOUT REGISTRY:                                                         │
│   ┌─────────┐                              ┌─────────┐                      │
│   │Producer │ ──► "I hope this schema      │Consumer │                      │
│   │(Team A) │     is compatible" ──────►   │(Team B) │ ← Breaks at 3 AM    │
│   └─────────┘                              └─────────┘                      │
│                                                                             │
│   WITH REGISTRY:                                                            │
│   ┌─────────┐     ┌───────────────┐         ┌─────────┐                     │
│   │Producer │ ──► │Schema Registry│ ──►     │Consumer │                     │
│   │(Team A) │     │               │         │(Team B) │                     │
│   └─────────┘     │ 1. Validate   │         └─────────┘                     │
│                   │    compat     │                                          │
│                   │ 2. Assign ID  │   Producer CANNOT publish if             │
│                   │ 3. Store      │   schema is incompatible.                │
│                   └───────────────┘   Breaking change rejected at build.    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Confluent Schema Registry

The de facto standard for Kafka environments. Supports Avro, Protobuf, and JSON Schema.

### Compatibility Modes

| Mode | Rule | Use Case |
|------|------|----------|
| **BACKWARD** | New schema can read old data | Default. Safe for consumer upgrades. |
| **BACKWARD_TRANSITIVE** | New schema can read ALL old data (not just previous) | When consumers may be many versions behind |
| **FORWARD** | Old schema can read new data | Safe for producer upgrades |
| **FORWARD_TRANSITIVE** | Old schema can read ALL new data | When producers may be many versions behind |
| **FULL** | Both backward and forward | Most restrictive. Safest for bidirectional. |
| **FULL_TRANSITIVE** | Full compatibility across all versions | Highest safety. Recommended for critical topics. |
| **NONE** | No compatibility check | Dangerous. Only for development. |

### How It Works with Kafka

```
┌─────────────────────────────────────────────────────────────────────────────┐
│   KAFKA + SCHEMA REGISTRY: END-TO-END FLOW                                  │
│                                                                             │
│   PRODUCER SIDE:                                                            │
│   1. Producer serializes message with schema                                │
│   2. Serializer checks: is this schema registered?                          │
│   3. If new schema: POST to registry → compatibility check                  │
│   4. If compatible: registry assigns schema ID                              │
│   5. Message on wire: [magic byte 0x0][schema ID: 4 bytes][Avro payload]   │
│                                                                             │
│   ┌────────┐    ┌──────────────┐    ┌───────────┐    ┌───────────┐         │
│   │Producer│ ──►│ Avro         │ ──►│ Schema    │ ──►│ Kafka     │         │
│   │ code   │    │ Serializer   │    │ Registry  │    │ Broker    │         │
│   └────────┘    └──────────────┘    └───────────┘    └───────────┘         │
│                  register schema     validate &                             │
│                  if new              assign ID                              │
│                                                                             │
│   CONSUMER SIDE:                                                            │
│   1. Consumer reads message from Kafka                                      │
│   2. Deserializer extracts schema ID from first 5 bytes                    │
│   3. Fetches writer schema from registry (cached locally)                  │
│   4. Resolves writer schema vs reader schema (consumer's compiled schema)  │
│   5. Deserializes payload using resolved schema                             │
│                                                                             │
│   ┌───────────┐    ┌──────────────┐    ┌───────────┐    ┌────────┐         │
│   │ Kafka     │ ──►│ Avro         │ ──►│ Schema    │ ──►│Consumer│         │
│   │ Broker    │    │ Deserializer │    │ Registry  │    │ code   │         │
│   └───────────┘    └──────────────┘    └───────────┘    └────────┘         │
│                     extract schema ID   fetch writer                        │
│                                         schema by ID                        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Registry Operations

| Operation | When | Risk |
|-----------|------|------|
| Register new schema | New version of producer | Rejected if incompatible |
| Check compatibility | CI/CD pipeline | Block deployment if breaking |
| Get schema by ID | Consumer deserialization | Cache miss → registry call (add latency) |
| Delete schema version | Cleanup deprecated | Can't undo; only soft-delete first |
| Change compatibility mode | Per-subject override | Loosening mode can allow future breaks |

### Registry as Infrastructure

**Availability**: If the registry goes down, producers fail to register new schemas and consumers fail to fetch unfamiliar schemas. Cached schemas continue to work. Run the registry with HA (replicated, behind load balancer).

**Caching**: Consumers cache schema ID → schema mapping locally. First-time fetch adds ~5ms. Subsequent: 0ms. Cache size is typically small (hundreds of schemas, not thousands).

---

# Part 5: gRPC and Protobuf Integration

## Why gRPC Matters for Encoding Decisions

gRPC uses Protobuf as its default serialization. Choosing Protobuf often means choosing gRPC, which brings additional capabilities.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│   gRPC STACK: HTTP/2 + PROTOBUF + CODE GENERATION                           │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  .proto definition:                                                  │   │
│   │  service UserService {                                               │   │
│   │    rpc GetUser (GetUserRequest) returns (User);                      │   │
│   │    rpc ListUsers (ListUsersRequest) returns (stream User);           │   │
│   │    rpc CreateUser (User) returns (CreateUserResponse);               │   │
│   │  }                                                                   │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│          │                                                                   │
│          ▼  protoc + gRPC plugin                                            │
│   ┌──────────────┐  ┌──────────────┐                                       │
│   │ Client Stub  │  │ Server Stub  │   Type-safe, cross-language           │
│   │ (generated)  │  │ (generated)  │                                       │
│   └──────┬───────┘  └──────┬───────┘                                       │
│          │                 │                                                │
│          └────── HTTP/2 ───┘                                               │
│                  │                                                          │
│   HTTP/2 benefits:                                                          │
│   • Multiplexing: multiple RPCs on one connection                          │
│   • Bidirectional streaming                                                │
│   • Header compression (HPACK)                                             │
│   • Binary framing (not text)                                              │
│                                                                             │
│   COMPARISON: REST/JSON vs gRPC/Protobuf                                   │
│   ┌──────────────┬──────────────────┬──────────────────┐                   │
│   │              │  REST/JSON       │  gRPC/Protobuf   │                   │
│   │ Payload size │  Large           │  ~50% smaller    │                   │
│   │ Latency      │  Higher          │  Lower           │                   │
│   │ Streaming    │  SSE or WS       │  Native          │                   │
│   │ Contract     │  OpenAPI (opt)   │  .proto (req)    │                   │
│   │ Browser      │  Native          │  grpc-web proxy  │                   │
│   │ Debugging    │  curl            │  grpcurl          │                   │
│   │ Load balancer│  Any L7          │  gRPC-aware L7   │                   │
│   └──────────────┴──────────────────┴──────────────────┘                   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### gRPC Streaming Patterns

| Pattern | Description | Use Case |
|---------|-------------|----------|
| **Unary** | One request, one response | Standard CRUD |
| **Server streaming** | One request, stream of responses | Feed, live updates |
| **Client streaming** | Stream of requests, one response | File upload, bulk ingest |
| **Bidirectional streaming** | Stream both directions | Chat, real-time sync |

### gRPC Gotchas at Scale

- **Load balancing**: gRPC uses long-lived HTTP/2 connections. L4 load balancers distribute connections, not requests. Need L7 (Envoy, Istio) for per-request balancing.
- **Browser support**: No native browser gRPC. Need grpc-web proxy (Envoy) or connect-web.
- **Debugging**: Binary payloads aren't curl-friendly. Use `grpcurl` or `grpc_cli`.
- **Timeouts**: gRPC has built-in deadline propagation. Set deadlines, or RPCs can hang indefinitely.
- **Error codes**: gRPC uses its own status codes (OK, UNAVAILABLE, DEADLINE_EXCEEDED, etc.), not HTTP status codes. Map carefully at API gateway boundaries.

---

# Part 6: Migration Patterns for Schema Changes

## The Expand-Contract Pattern

The safest way to make breaking schema changes. Works for any encoding format.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│   EXPAND-CONTRACT: BREAKING CHANGE WITHOUT BREAKING CONSUMERS               │
│                                                                             │
│   Goal: Rename "email" to "contact_email"                                   │
│                                                                             │
│   PHASE 1 — EXPAND (Add new, keep old):                                     │
│   ┌────────────────────────────────────────────────────────────────────┐    │
│   │  message User {                                                     │    │
│   │    int64 id = 1;                                                    │    │
│   │    string name = 2;                                                 │    │
│   │    string email = 3;            ← Still present                     │    │
│   │    string contact_email = 5;    ← New field added                   │    │
│   │  }                                                                  │    │
│   │                                                                     │    │
│   │  Producer writes BOTH email and contact_email.                      │    │
│   │  Old consumers read email. New consumers read contact_email.        │    │
│   └────────────────────────────────────────────────────────────────────┘    │
│                                                                             │
│   PHASE 2 — MIGRATE (Move consumers to new field):                          │
│   ┌────────────────────────────────────────────────────────────────────┐    │
│   │  Over 2–4 weeks, all consumer teams switch to contact_email.        │    │
│   │  Monitor: who still reads email? → Dashboard, logs, metrics.        │    │
│   │  When zero consumers read email → proceed to phase 3.               │    │
│   └────────────────────────────────────────────────────────────────────┘    │
│                                                                             │
│   PHASE 3 — CONTRACT (Remove old field):                                    │
│   ┌────────────────────────────────────────────────────────────────────┐    │
│   │  message User {                                                     │    │
│   │    int64 id = 1;                                                    │    │
│   │    string name = 2;                                                 │    │
│   │    reserved 3;                   ← Prevent reuse                    │    │
│   │    reserved "email";             ← Prevent reuse                    │    │
│   │    string contact_email = 5;     ← Only field                       │    │
│   │  }                                                                  │    │
│   └────────────────────────────────────────────────────────────────────┘    │
│                                                                             │
│   TIMELINE: 4–12 weeks depending on consumer count and team coordination   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## API Versioning for Breaking Changes

When expand-contract isn't sufficient (e.g., fundamentally restructured message), version the API.

| Strategy | Mechanism | Pros | Cons |
|----------|-----------|------|------|
| **URL versioning** | `/v1/users`, `/v2/users` | Explicit, cacheable | URL proliferation |
| **Header versioning** | `Accept: application/vnd.api.v2+json` | Clean URLs | Hidden, not cacheable |
| **Query param** | `/users?version=2` | Easy to add | Messy, not RESTful |
| **Content negotiation** | `Content-Type: application/vnd.user.v2+proto` | HTTP-native | Complex |

### Deprecation Timeline

| Phase | Action | Duration | Monitoring |
|-------|--------|----------|------------|
| **Announce** | Document deprecation; communicate to consumers | Day 0 | — |
| **Sunset header** | Add `Deprecation: true`, `Sunset: <date>` to v1 responses | Immediate | Log clients using v1 |
| **Dual support** | Maintain v1 and v2 side by side | 3–6 months | Track v1 usage percentage |
| **Warning** | Return deprecation warnings in v1 responses | Month 4–5 | Alert teams still on v1 |
| **Soft sunset** | Rate-limit v1 or return 299 warnings | Month 5–6 | Monitor for breakage |
| **Hard sunset** | Return 410 Gone for v1 | After sunset date | Verify zero traffic |

## Dual-Write for Data Store Migrations

When the schema change affects stored data (not just wire format):

```
┌─────────────────────────────────────────────────────────────────────────────┐
│   DUAL-WRITE: SCHEMA CHANGE IN STORAGE                                      │
│                                                                             │
│   1. Write to old format AND new format simultaneously                       │
│   2. Read from old format (source of truth)                                 │
│   3. Validate: compare old vs new reads                                     │
│   4. Switch reads to new format                                             │
│   5. Stop writing old format                                                │
│   6. Backfill/migrate remaining old data                                    │
│                                                                             │
│   DANGER: Dual-write is NOT atomic. If write to new fails and old succeeds,│
│   data diverges. Use change-data-capture (CDC) or outbox pattern instead   │
│   for critical data.                                                        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Part 7: Performance and Cost at Scale

## Benchmarks: Why Format Choice Matters at High QPS

| Metric | JSON | Protobuf | Avro | Impact at 100K QPS |
|--------|------|----------|------|-------------------|
| **Payload size** | 800 B | 350 B | 320 B | JSON: 80 MB/s. Protobuf: 35 MB/s. **Saves 45 MB/s bandwidth.** |
| **Encode time** | 15 µs | 5 µs | 6 µs | JSON: 1.5 CPU-sec/sec. Protobuf: 0.5 CPU-sec/sec. **Saves ~65% CPU.** |
| **Decode time** | 20 µs | 6 µs | 8 µs | JSON: 2 CPU-sec/sec. Protobuf: 0.6 CPU-sec/sec. **Saves ~70% CPU.** |
| **GC pressure** | High (many string allocs) | Low (pre-allocated) | Medium | JSON: 2× GC pauses in Java at high QPS |

### When Does Format Matter?

```
┌─────────────────────────────────────────────────────────────────────────────┐
│   WHEN FORMAT CHOICE IMPACTS COST                                           │
│                                                                             │
│   < 1K QPS:    Format doesn't matter. Use JSON for simplicity.             │
│   1K–10K QPS:  Format starts to matter for bandwidth and CPU.              │
│   10K–100K QPS: Protobuf saves significant infrastructure cost.            │
│   > 100K QPS:  Format is a critical cost driver. Binary required.          │
│                                                                             │
│   BANDWIDTH COST (AWS, inter-AZ):                                          │
│   JSON at 100K QPS:     80 MB/s = ~$2,400/month cross-AZ                  │
│   Protobuf at 100K QPS: 35 MB/s = ~$1,050/month cross-AZ                  │
│   Savings: $1,350/month = $16,200/year for ONE service                     │
│   With 50 internal services: ~$810,000/year in bandwidth alone             │
│                                                                             │
│   CPU COST:                                                                │
│   JSON parsing at 100K QPS: ~4 CPU cores dedicated to serialization        │
│   Protobuf at 100K QPS: ~1.2 CPU cores                                    │
│   Savings: 2.8 cores × $50/core/month = $140/month per service             │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Storage Impact

For event streams (Kafka, data lake), encoding format directly affects storage cost:

| Retention | JSON (per topic) | Protobuf | Avro | Savings |
|-----------|------------------|----------|------|---------|
| 7 days, 100K msg/sec, 800B avg | 48 TB | 21 TB | 19 TB | 55–60% |
| 30 days | 207 TB | 91 TB | 83 TB | 55–60% |
| 1 year | 2.5 PB | 1.1 PB | 1.0 PB | 55–60% |

**Staff insight**: At petabyte scale, switching from JSON to Avro on Kafka topics can save hundreds of thousands of dollars per year in storage costs alone—before counting bandwidth and CPU.

---

# Part 8: Cross-Language and Cross-Team Considerations

## The Polyglot Reality

At scale, services are written in multiple languages. Encoding format must work across all.

| Format | Java | Go | Python | Rust | JavaScript | C++ |
|--------|------|-----|--------|------|-----------|-----|
| JSON | Jackson, Gson | encoding/json | json | serde_json | native | nlohmann |
| Protobuf | protobuf-java | protobuf-go | protobuf-python | prost | protobufjs | protobuf-cpp |
| Avro | avro-java | goavro | fastavro | apache-avro | avsc | avro-cpp |

### Cross-Language Gotchas

| Issue | Format | Problem | Solution |
|-------|--------|---------|----------|
| **Integer overflow** | JSON | JS loses precision > 2^53 | Use string for large IDs |
| **Enum handling** | Protobuf | Unknown enum value → 0 in proto3 | Handle unknown values explicitly |
| **Timestamp** | All | No universal standard | Use google.protobuf.Timestamp or ISO 8601 |
| **Decimal precision** | Protobuf | No native decimal type | Use string or custom message with mantissa/exponent |
| **Map ordering** | JSON | Object key order not guaranteed | Don't rely on order; use arrays if order matters |
| **Null semantics** | Protobuf | Proto3 has no null; zero value = default | Use wrapper types (google.protobuf.StringValue) or optional |

## Schema Governance Across Teams

```
┌─────────────────────────────────────────────────────────────────────────────┐
│   SCHEMA GOVERNANCE: WHO OWNS THE SCHEMA?                                   │
│                                                                             │
│   ANTI-PATTERN: Every team defines their own User message.                  │
│   Result: 15 different User schemas, incompatible, unmaintainable.          │
│                                                                             │
│   PATTERN: Schema ownership model                                           │
│                                                                             │
│   ┌─────────────────┐                                                       │
│   │ Schema Repo      │  ← Central repo for .proto / .avsc files            │
│   │ (monorepo or     │  ← CI validates compatibility                       │
│   │  dedicated repo) │  ← PR review required for changes                   │
│   └────────┬────────┘                                                       │
│            │                                                                │
│            ▼                                                                │
│   ┌──────────────────┐                                                      │
│   │ CI/CD Pipeline    │                                                      │
│   │ • Lint schema     │                                                      │
│   │ • Check compat    │ ← Schema Registry compatibility check               │
│   │ • Generate stubs  │ ← Publish to language-specific package registries   │
│   │ • Publish artifact│                                                      │
│   └──────────────────┘                                                      │
│            │                                                                │
│   ┌────────┼────────┐                                                       │
│   ▼        ▼        ▼                                                       │
│   Java    Go      Python   ← Teams consume generated stubs as dependencies │
│   pkg     mod     pkg                                                       │
│                                                                             │
│   OWNERSHIP RULES:                                                          │
│   • Producer team owns the schema                                           │
│   • Consumer teams can request changes via PR                               │
│   • Breaking changes require RFC + deprecation timeline                    │
│   • Schema changes require compatibility check in CI                       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Part 9: JSON Schema and Validation

Even when using JSON (for public APIs), Staff Engineers add schema validation to prevent drift.

## JSON Schema

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "id": {"type": "integer"},
    "name": {"type": "string", "minLength": 1, "maxLength": 255},
    "email": {"type": "string", "format": "email"},
    "phone": {"type": ["string", "null"]}
  },
  "required": ["id", "name", "email"],
  "additionalProperties": false
}
```

### JSON Schema vs Protobuf vs Avro

| Property | JSON Schema | Protobuf | Avro |
|----------|------------|----------|------|
| **Validation** | Rich (regex, min/max, format) | Basic (types only) | Basic (types, defaults) |
| **Code generation** | Optional | Required | Optional |
| **Wire format** | Text (JSON) | Binary | Binary |
| **Evolution** | Manual (no built-in compat check) | Field number rules | Schema resolution |
| **Tooling** | OpenAPI, swagger | protoc, buf | Confluent, Avro tools |
| **Use case** | Public API validation | Internal RPC | Event streams |

### OpenAPI and JSON Schema

OpenAPI (Swagger) specifications use JSON Schema for request/response validation. For public APIs:

1. **Define schema in OpenAPI spec** — source of truth
2. **Generate client SDKs** — openapi-generator for all languages
3. **Validate at gateway** — API gateway validates requests against schema
4. **Version in spec** — `info.version` tracks API version

---

# Part 10: Testing Schema Changes

## Compatibility Testing in CI

```
┌─────────────────────────────────────────────────────────────────────────────┐
│   SCHEMA CHANGE CI PIPELINE                                                  │
│                                                                             │
│   Developer changes .proto / .avsc file                                     │
│          │                                                                   │
│          ▼                                                                   │
│   ┌─────────────────────────────────┐                                       │
│   │  1. LINT                         │                                       │
│   │  • buf lint (Protobuf)           │                                       │
│   │  • avro-tools lint (Avro)        │                                       │
│   │  • Style guide compliance        │                                       │
│   └─────────────┬───────────────────┘                                       │
│                 │                                                            │
│                 ▼                                                            │
│   ┌─────────────────────────────────┐                                       │
│   │  2. COMPATIBILITY CHECK          │                                       │
│   │  • buf breaking (Protobuf)       │                                       │
│   │  • Schema Registry compat API    │                                       │
│   │  • Compare new vs last N versions│                                       │
│   └─────────────┬───────────────────┘                                       │
│                 │ ✗ Breaking? → Block PR                                    │
│                 │ ✓ Compatible? → Continue                                  │
│                 ▼                                                            │
│   ┌─────────────────────────────────┐                                       │
│   │  3. GENERATE STUBS               │                                       │
│   │  • protoc for all languages      │                                       │
│   │  • Verify compilation succeeds   │                                       │
│   └─────────────┬───────────────────┘                                       │
│                 │                                                            │
│                 ▼                                                            │
│   ┌─────────────────────────────────┐                                       │
│   │  4. INTEGRATION TEST             │                                       │
│   │  • Serialize with new schema     │                                       │
│   │  • Deserialize with old schema   │                                       │
│   │  • Deserialize with new schema   │                                       │
│   │  • Verify round-trip correctness │                                       │
│   └─────────────┬───────────────────┘                                       │
│                 │                                                            │
│                 ▼                                                            │
│   ┌─────────────────────────────────┐                                       │
│   │  5. PUBLISH                      │                                       │
│   │  • Register with Schema Registry │                                       │
│   │  • Publish generated stubs       │                                       │
│   │  • Notify consumer teams         │                                       │
│   └─────────────────────────────────┘                                       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Buf: Modern Protobuf Tooling

`buf` is the modern Protobuf linter and compatibility checker:

| Command | What It Does |
|---------|-------------|
| `buf lint` | Enforce naming conventions, style guide |
| `buf breaking` | Detect breaking changes vs previous version |
| `buf generate` | Generate code for all configured languages |
| `buf push` | Push schema to Buf Schema Registry |

### Contract Testing

Beyond schema compatibility, test the semantic contract:

| Test Type | What It Validates | Tool |
|-----------|------------------|------|
| **Schema compat** | Can old consumer deserialize new message? | Schema Registry, buf |
| **Contract test** | Does the producer send what the consumer expects? | Pact, Spring Cloud Contract |
| **Integration test** | End-to-end with real serialization/deserialization | Custom |
| **Canary validation** | New schema in production, monitoring for errors | Canary deployment + metrics |

---

# Part 11: Production Incidents and Failure Modes

## Incident 1: Field Number Reuse

**Scenario**: Team A removed field 5 (`address`) from a Protobuf message and later added field 5 (`phone_number`, type `int64`). Old consumers still in production tried to deserialize field 5 as `address` (string).

**Impact**: Deserialization didn't crash (wire type 2 for both string and bytes), but the data was garbage. Consumers stored corrupted phone numbers for 6 hours before detection.

**Root cause**: No `reserved` statement. No compatibility check in CI.

**Fix**: Add `reserved 5; reserved "address";`. Add `buf breaking` to CI. Backfill corrupted data.

**Lesson**: `reserved` exists for exactly this reason. Add it to every removed field, always.

## Incident 2: JSON Number Precision

**Scenario**: Backend generated 64-bit order IDs (e.g., `9007199254740993`). Frontend received these via JSON API. JavaScript's `Number` lost precision: `9007199254740993` became `9007199254740992`.

**Impact**: 0.01% of orders showed wrong order IDs in the UI. Customers reported "wrong order" for 2 weeks before the pattern was identified.

**Root cause**: JSON spec doesn't define integer precision. JavaScript uses IEEE 754 doubles (53-bit mantissa).

**Fix**: Serialize large IDs as strings in JSON: `{"order_id": "9007199254740993"}`. Update all API responses.

**Lesson**: If IDs can exceed 2^53, always use string representation in JSON APIs.

## Incident 3: Schema Registry Outage

**Scenario**: Schema Registry went down for 30 minutes during a deployment. Producers with new schemas couldn't register and failed to send messages. Consumers with cached schemas continued normally.

**Impact**: 30-minute message blackout for all producers deploying new schemas. Existing producers (no new schemas) were unaffected.

**Root cause**: Single-node Schema Registry without HA.

**Fix**: Deploy Schema Registry in HA mode (multiple instances, shared Kafka backend topic `_schemas`). Add local schema caching to producers for fallback.

**Lesson**: Schema Registry is on the critical path for producers. Treat it as Tier 1 infrastructure.

## Incident 4: Avro Default Value Missing

**Scenario**: Team added a new field `loyalty_tier` to an Avro schema without a default value. Schema Registry was in BACKWARD mode and rejected the schema.

**Impact**: Deployment blocked. Team had to add `"default": "STANDARD"` and re-submit. 2-hour delay.

**Root cause**: Team didn't understand Avro backward compatibility rules (new fields MUST have defaults for backward compat).

**Fix**: Added schema change checklist to PR template. Added pre-commit hook that runs Avro compatibility check locally.

**Lesson**: Avro backward compatibility requires defaults on new fields. Forward compatibility requires defaults on removed fields.

## Incident 5: gRPC Load Balancing Failure

**Scenario**: After switching from REST/JSON to gRPC/Protobuf, all traffic went to a single backend instance. The other 9 instances were idle.

**Impact**: One instance at 95% CPU, 9 instances at 2% CPU. Tail latency spiked 10×.

**Root cause**: L4 load balancer distributed TCP connections, not requests. gRPC uses one long-lived HTTP/2 connection per client. All requests multiplexed on that single connection went to the same backend.

**Fix**: Switched to L7 load balancer (Envoy) that understands HTTP/2 and distributes individual gRPC calls.

**Lesson**: gRPC requires L7 load balancing. L4 balancers see one connection and send all traffic to one backend.

---

# Part 12: Decision Frameworks

## Encoding Format Decision Matrix

```
┌─────────────────────────────────────────────────────────────────────────────┐
│   DECISION: WHICH ENCODING FORMAT?                                          │
│                                                                             │
│   Start here:                                                               │
│                                                                             │
│   Who consumes the data?                                                    │
│   │                                                                         │
│   ├── External developers / browsers                                        │
│   │   └── JSON (with JSON Schema / OpenAPI for validation)                  │
│   │                                                                         │
│   ├── Internal services (same org)                                          │
│   │   │                                                                     │
│   │   ├── QPS > 10K or latency-sensitive?                                   │
│   │   │   └── Protobuf + gRPC                                              │
│   │   │                                                                     │
│   │   ├── Event stream (Kafka)?                                             │
│   │   │   └── Avro + Schema Registry (or Protobuf + Schema Registry)       │
│   │   │                                                                     │
│   │   └── Low QPS, small team?                                              │
│   │       └── JSON is fine. Add Protobuf when scale demands it.            │
│   │                                                                         │
│   └── Data lake / analytics?                                                │
│       └── Parquet (columnar), Avro (row-based), or ORC                     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Schema Evolution Decision Tree

```
┌─────────────────────────────────────────────────────────────────────────────┐
│   DECISION: HOW TO EVOLVE THE SCHEMA?                                       │
│                                                                             │
│   What kind of change?                                                      │
│   │                                                                         │
│   ├── Add a field                                                           │
│   │   └── Add as optional, with default → Compatible. Ship it.             │
│   │                                                                         │
│   ├── Remove a field                                                        │
│   │   ├── Protobuf: mark deprecated, add reserved, stop writing            │
│   │   └── Avro: remove from schema (must have had default)                 │
│   │                                                                         │
│   ├── Rename a field                                                        │
│   │   ├── Protobuf: rename freely (wire uses numbers, not names)           │
│   │   └── Avro: use aliases                                                │
│   │                                                                         │
│   ├── Change a field's type                                                 │
│   │   ├── Safe promotion (int32→int64): OK                                 │
│   │   └── Incompatible (int→string): BREAKING. Use expand-contract.        │
│   │                                                                         │
│   └── Restructure the message                                               │
│       └── BREAKING. Version the API (v1→v2). Deprecation timeline.         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Part 13: Interview Essentials

## Quick-Fire Answers

**"JSON vs Protobuf?"** — "JSON for public APIs—tooling, adoption, debuggability. Protobuf for internal—50% smaller payloads, 3× faster encode/decode, critical at high QPS. Trade-off: Protobuf requires code generation and isn't human-readable; JSON is loose but universal. Match format to audience and scale."

**"How do you evolve a schema without breaking consumers?"** — "Add optional fields with defaults. Old consumers ignore new fields. New consumers handle absence with defaults. Never remove or renumber fields in Protobuf. For breaking changes, use expand-contract: add new field, migrate consumers, remove old. For major restructures, version the API with a 6-month deprecation window and sunset headers."

**"Why Avro for Kafka?"** — "Avro embeds schema ID in the payload; Schema Registry stores and validates schemas. Enables backward/forward compatibility—consumer can be weeks behind and still deserialize. Schema Registry enforces compatibility at write time, so producers can't publish breaking changes. Protobuf also works with Schema Registry, but Avro's schema resolution (reader/writer schema) is purpose-built for evolution."

**"What's backward vs forward compatibility?"** — "Backward: new consumer can read old data. Forward: old consumer can read new data. Full: both. For rolling deployments, you need forward compatibility—during rollout, old instances receive new messages. For consumer upgrades, you need backward. For safety, enforce full: add optional fields with defaults, never remove."

**"What's a Schema Registry and why do we need one?"** — "A Schema Registry is a central service that stores schema versions and enforces compatibility rules. Without it, schema compatibility is an honor system—teams promise not to break things but eventually do. With a registry, the producer literally cannot publish an incompatible schema. It's the enforcement mechanism for schema contracts across hundreds of services."

**"How does gRPC relate to Protobuf?"** — "gRPC is an RPC framework that uses Protobuf as its default serialization. The .proto file defines both the message types and the service interface. Benefits: type-safe cross-language, HTTP/2 (multiplexing, streaming, compression), binary and compact. Gotcha: needs L7 load balancing (not L4), no native browser support (needs grpc-web proxy), harder to debug than curl."

## Staff-Level Interview Walkthrough: "Design the Schema Strategy for a New Microservices Platform"

**Step 1 — Clarify audience and scale**: "Who consumes? External partners need JSON APIs with OpenAPI specs. Internal services will use gRPC/Protobuf—we expect 50+ services, 10K+ QPS inter-service. Event streams on Kafka will use Avro with Schema Registry."

**Step 2 — Define schema governance**: "Central schema repo for .proto and .avsc files. CI validates compatibility with buf and Schema Registry API. Producer team owns the schema. Consumer teams request changes via PR. Breaking changes require an RFC."

**Step 3 — Evolution strategy**: "Full compatibility mode on Schema Registry for all Kafka topics. For gRPC APIs: add optional fields, never remove or renumber. For breaking changes: expand-contract with 3-month migration window."

**Step 4 — Cross-cutting concerns**: "All messages include trace_id, timestamp, and schema_version as standard fields. Use google.protobuf.Timestamp for times. String representation for IDs > 2^53 in JSON APIs."

**Step 5 — Failure modes**: "Schema Registry in HA mode. Local schema cache on consumers. If registry is down, producers with new schemas fail; existing schemas continue. Alerting on registry availability and compatibility rejection rate."

---

## Appendix: Configuration Quick Reference

### Protobuf Best Practices

| Practice | Rule |
|----------|------|
| Field numbering | Start at 1. Numbers 1–15 use 1 byte for tag. Use these for frequent fields. |
| Field removal | Add `reserved` for number and name. Never reuse. |
| Enums | Always include `UNKNOWN = 0` as first value. Proto3 uses 0 as default. |
| Timestamps | Use `google.protobuf.Timestamp`, not int64 millis. |
| Money | Use string or custom `Money` message (amount + currency). Never float. |
| Optional vs required | Proto3: all fields are optional. Use wrapper types for nullable semantics. |
| Packages | Use reverse domain: `com.company.service.v1`. |

### Avro Best Practices

| Practice | Rule |
|----------|------|
| Defaults | ALWAYS provide defaults for new fields. Required for backward compat. |
| Union types | Use `["null", "type"]` for nullable fields. Null first = default is null. |
| Naming | Use camelCase for field names. Use dot-separated namespace. |
| Logical types | Use `"logicalType": "timestamp-millis"` for timestamps. |
| Schema ID | 4-byte schema ID prepended to every Avro message in Kafka. |

### Schema Registry Configuration

| Setting | Recommended | Why |
|---------|-------------|-----|
| Compatibility mode | FULL_TRANSITIVE | Safest. Both directions, all versions. |
| Auto-register | Disabled in production | Prevent accidental schema registration. Register in CI only. |
| Schema cache TTL | 5 minutes | Balance freshness vs registry load |
| HA mode | 3+ instances | Registry is on critical path |

---

## Appendix: Common Misconceptions

| Misconception | Reality |
|---------------|---------|
| "Protobuf is always better than JSON" | For public APIs, JSON is better (tooling, adoption). Format choice depends on audience. |
| "Schema evolution is free" | It requires rules, tooling, and discipline. Without enforcement, schemas drift. |
| "Avro and Protobuf are interchangeable" | Different wire formats, different evolution models. Avro uses schema resolution; Protobuf uses field numbers. |
| "JSON Schema = schema enforcement" | JSON Schema validates but doesn't prevent evolution breakage. No built-in compatibility checking. |
| "gRPC replaces REST" | gRPC is better for internal high-QPS. REST/JSON remains better for public APIs and browser clients. |
| "Schema Registry is optional for Kafka" | Without it, schema compatibility is unenforceable. Critical for production Kafka deployments. |
| "Field names matter on the Protobuf wire" | Only field numbers matter. You can rename fields freely without breaking anything. |
| "Proto3 required fields enforce presence" | Proto3 has no required fields. All fields are optional. Use wrapper types for nullable semantics. |

---

## Further Reading

| Topic | Resource |
|-------|----------|
| Schema evolution theory | *Designing Data-Intensive Applications* (Kleppmann) — Ch 4 |
| Protobuf language guide | [Protocol Buffers docs](https://developers.google.com/protocol-buffers) |
| Avro specification | [Apache Avro](https://avro.apache.org/) |
| Confluent Schema Registry | [Schema Registry docs](https://docs.confluent.io/platform/current/schema-registry/) |
| buf (Protobuf tooling) | [buf.build](https://buf.build/) |
| gRPC | [grpc.io](https://grpc.io/) |
| JSON Schema | [json-schema.org](https://json-schema.org/) |
| OpenAPI | [openapis.org](https://www.openapis.org/) |

---

*This supplement supports Chapter 28 (Databases), Chapter 33 (Event-Driven), and Chapter 39 (System Evolution). Read alongside Ch 2 (APIs) for API versioning, Ch 33 Supplement (Kafka Internals) for Kafka-specific encoding, and Ch 39 Supplement (Deployment & Ops) for rollout of schema changes.*
