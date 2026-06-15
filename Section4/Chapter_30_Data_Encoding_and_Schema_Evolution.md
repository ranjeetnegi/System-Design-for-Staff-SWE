# Chapter 30 — Part A: Data Encoding and Schema Evolution
### Wire Format Internals: The Invisible Contract Between Services

> "Every byte that crosses a network boundary was put there by a choice someone made. Most engineers never think about that choice. Staff Engineers think about it constantly."

---

## Table of Contents

1. The Invisible Layer: Why Encoding Matters at Staff Level
2. The Four Questions That Drive Format Choice
3. JSON: The Universal Format (Deep Dive)
4. Protobuf: Binary Efficiency (Deep Dive)
5. Avro: Schema-Based Binary (Deep Dive)
6. Parquet: Columnar Format for Analytics
7. FlatBuffers and MessagePack: The Other Formats
8. Performance Numbers Every Staff Engineer Should Know

---

## 1. The Invisible Layer: Why Encoding Matters at Staff Level

You just spent Chapter 29 learning how databases physically store data — B-Trees, WAL, MVCC, connection pooling. All of that happens inside one machine, one process, one database.

Now think about what happens the moment data has to leave that machine.

A user hits your API. Your API service reads a record from the database. It needs to send that record to another internal service — let's say a recommendation engine. How does it send it? Somehow, the object living in memory (fields, types, values) needs to be turned into a stream of bytes, transmitted across a network, and then turned back into an object in memory on the other side.

That "somehow" is **encoding** (also called **serialization**). The reverse — bytes back to object — is **decoding** (or **deserialization**).

Most engineers treat encoding as a solved problem: "just use JSON." And for a personal project, that is completely fine. But at scale, at the L6 level, encoding is a first-class architectural decision with consequences for cost, reliability, and team velocity.

Here is what "just use JSON" looks like across three real production incidents:

---

### Production Incident 1: "Our inter-service bandwidth bill doubled this quarter"

A payments company runs 100,000 requests per second between their transaction service and fraud-detection service. They encode every request as JSON. A routine audit finds they are spending $4,000/month on internal bandwidth they didn't budget for.

Root cause: every JSON message repeats the field names on the wire. The fields `"transactionId"`, `"merchantId"`, `"customerId"`, `"amount"`, `"currency"`, `"timestamp"`, `"status"`, `"countryCode"` are sent as literal text strings in every single one of those 100,000 requests per second. That is about 80 bytes of labels per message — just labels, not even data. At 100K QPS that is 8 MB/sec, 691 GB/day, 20 TB/month. Just for field names.

Switch to Protobuf: field names become 1-byte field numbers on the wire. Same data, one-third the bytes. Problem solved.

---

### Production Incident 2: "Consumer service crashed after producer deployed a new field"

A team adds a new mandatory `paymentMethod` field to a shared data model. They deploy the producer first. The consumer — a downstream service owned by a different team — starts crashing immediately, because their deserialization code throws an exception on an unexpected field.

Root cause: there was no **schema contract** enforced between producer and consumer. JSON is schemaless — anyone can add anything, and consumers have no protection unless they write defensive code. Nobody did.

Switch to Avro with a Schema Registry: new fields must have defaults, and the registry enforces compatibility rules before any deployment. A breaking schema change is caught at CI time, not at 2 AM.

---

### Production Incident 3: "We can't query last year's events in BigQuery"

A team stored a year's worth of Kafka events as raw JSON in Google Cloud Storage, then loaded them into BigQuery for analytics. BigQuery inferred a schema — but JSON has no enforced types. Some events have `"amount": 99.99`, some have `"amount": "99.99"`, some are missing the field entirely. BigQuery guessed `STRING` for the column. Analytics queries break. Re-processing a year of data costs two engineers three weeks.

Root cause: JSON stored in a data lake without a schema is opaque. You cannot reliably query it years later because you don't know what types the fields had.

Switch to Avro or Parquet for event storage: the schema is stored alongside the data. BigQuery reads the schema, knows the types, queries work correctly on day one and year five.

---

### The Staff Engineer Framing

At L6, you think of encoding as a **contract** between services. The format you choose determines:

- What the contract says (schema-enforced vs schemaless)
- Whether violations are caught early (at compile time / deployment) or late (at runtime / 2 AM)
- What it costs to execute the contract (CPU, bandwidth, storage)
- Who can read it (humans vs machines, internal vs external developers)

Here is the full data flow with the encoding layer made visible:

```
  PRODUCER SIDE                                    CONSUMER SIDE
  +------------------+                           +------------------+
  |  Application     |                           |  Application     |
  |  Object in RAM   |                           |  Object in RAM   |
  |  {id: 12345,     |                           |  {id: 12345,     |
  |   name: "Alice"} |                           |   name: "Alice"} |
  +--------+---------+                           +---------+--------+
           |                                               ^
           | ENCODING                                      | DECODING
           | (serialization)                               | (deserialization)
           v                                               |
  +------------------+                           +------------------+
  |  Format Choice   |                           |  Format Choice   |
  |  JSON / Protobuf |                           |  JSON / Protobuf |
  |  Avro / Parquet  |                           |  Avro / Parquet  |
  +--------+---------+                           +---------+--------+
           |                                               ^
           | Byte stream on the wire                       |
           +-------------------+---------------------------+
                               |
                  +------------+-----------+
                  |    NETWORK / STORAGE   |
                  |  HTTP, Kafka, gRPC,    |
                  |  S3, BigQuery, Disk    |
                  +------------------------+

  The format choice happens at BOTH ends.
  Both ends must agree, or data is unreadable.
```

That format choice — that tiny box in the diagram — is what this entire chapter is about.

---

## 2. The Four Questions That Drive Format Choice

Before you name a format in a design interview (or a design doc), you must answer four questions. If you answer them in order, the right format usually becomes obvious.

---

### Question 1: Who consumes the data?

This is the most important question because it determines your constraints.

**External developers** (third-party integrators, mobile clients, partners) need:
- Human-readable format they can inspect with `curl`
- No special tooling required to parse
- Stable, documented schema (ideally OpenAPI spec)
- **Answer: JSON**

**Internal services** (microservices you control, same company, same schema registry) need:
- Efficient encoding (bandwidth and CPU matter at scale)
- Strong schema enforcement (catch breaking changes early)
- No need for human readability at the wire layer (have tooling)
- **Answer: Protobuf, Avro, or Thrift**

**Analytics pipelines** (BigQuery, Spark, Snowflake reading S3):
- Need columnar layout for fast aggregation queries
- Need schema stored with data for long-term readability
- **Answer: Parquet or ORC**

---

### Question 2: What is the QPS?

Query-per-second volume determines whether encoding efficiency is worth the engineering cost.

| QPS Range     | Encoding overhead matters? | Recommended approach              |
|---------------|---------------------------|-----------------------------------|
| < 1,000       | No                        | JSON — simplest, most debuggable  |
| 1K – 10K      | Marginal                  | JSON or MessagePack               |
| 10K – 100K    | Yes                       | Protobuf or Avro                  |
| > 100K        | Absolutely                | Protobuf/Avro, measure everything |

The crossover point is roughly 10,000 requests per second. Below that, the CPU cost of JSON encoding is a rounding error compared to your database query time. Above that, you will feel it in your CPU utilization dashboards.

---

### Question 3: How often does the schema change?

A schema is the structure of your data: the field names, their types, which ones are required.

**Schema changes rarely** (once a month or less): almost any format works. The cost of migration is low because it happens infrequently.

**Schema changes frequently** (weekly or more): you need a format with **schema evolution rules** — formal rules about what kinds of changes are allowed, enforced automatically. Otherwise, each schema change is a manual coordination event between every producer and every consumer.

Protobuf and Avro both have evolution rules. JSON has none. We will cover the rules in detail in Part B of this chapter.

---

### Question 4: What tooling and ecosystem already exists?

Do not fight your ecosystem. Use the format that integrates naturally with the tools you already have.

| System             | Natural format                          |
|--------------------|-----------------------------------------|
| Kafka event stream | Avro + Confluent Schema Registry        |
| gRPC microservices | Protobuf (gRPC is built on Protobuf)    |
| REST APIs          | JSON + OpenAPI spec                     |
| Data lake on S3    | Parquet                                 |
| Redis cache        | MessagePack or JSON                     |
| Game engine        | FlatBuffers                             |

When you answer all four questions, the format choice is usually settled before you debate technology preferences.

---

## 3. JSON: The Universal Format (Deep Dive)

JSON stands for **JavaScript Object Notation**. It was designed to be easy for humans to read and easy for JavaScript to parse. It became the lingua franca of APIs because it is dead simple to work with in any language.

### What JSON Actually Is on the Wire

JSON is plain text encoded in **UTF-8**. There is no binary, no compression, no special encoding. Every character you see when you open a JSON file is exactly what travels across the network.

This simplicity is JSON's greatest strength and its greatest weakness. It means any tool — `curl`, a browser, a text editor — can read it directly. It also means it is verbose.

Let us encode a simple object and count every byte:

```
{"id":12345,"name":"Alice","email":"alice@example.com"}
```

Count the bytes character by character:

```
  Character:  { " i d " : 1 2 3 4 5 , " n a m e " : " A l i c e " , " e m a i l " : " a l i c e @ e x a m p l e . c o m " }
  Byte count:  1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1

  Total: 54 bytes

  Of those 54 bytes:
    - Opening/closing braces:  2 bytes
    - Commas and colons:       5 bytes
    - Quote marks:            14 bytes
    - Field names (id, name, email): 2+4+5 = 11 bytes  <-- LABELS, NOT DATA
    - Actual values (12345, Alice, alice@example.com):  5+5+17 = 27 bytes

  Labels = 11 bytes, Data = 27 bytes
  Labels are 29% of the total message size — and repeated in every single message.
```

Now think about scale. You have a service sending this message 1,000,000 times per day.

```
  Messages per day:        1,000,000
  Bytes in field names:    11 bytes per message
  Total wasted on labels:  11,000,000 bytes = ~10.5 MB per day

  Just for the field names. Every. Single. Day.
```

A real business object with 20 fields has far more label bytes. This is why high-QPS systems care about binary formats.

---

### The JSON Parsing Pipeline

When a service receives JSON bytes, here is everything that has to happen before the application can read a single field:

```
  RAW BYTES (network buffer)
       |
       v
  LEXER (tokenizer)
  - Scan bytes one at a time
  - Emit tokens: STRING, NUMBER, LBRACE, RBRACE, COLON, COMMA, etc.
  - Validate UTF-8 sequences
  - Handle escape sequences (\n, \", \\, \uXXXX)
       |
       v
  PARSER (syntax check)
  - Consume tokens and verify grammar
  - Build Abstract Syntax Tree (AST) or event stream
  - Reject malformed JSON (missing comma, unmatched bracket)
       |
       v
  OBJECT INSTANTIATION
  - For each field name: string comparison against known field names
  - Allocate a new object on the heap
  - Populate fields with parsed values
       |
       v
  GC PRESSURE
  - Every parsed string is a heap allocation
  - Every nested object is a heap allocation
  - Garbage collector eventually has to clean all of this up
  - Under high load: GC pauses, increased latency, tail latency spikes
```

JSON parsing is **CPU-intensive** for three reasons:
1. **String comparison**: to map `"transactionId"` to the right struct field, the parser must compare that 13-byte string against every known field name. For every message. At 100K QPS, that is 100,000 × N string comparisons per second.
2. **UTF-8 validation**: the parser must verify that every byte sequence is valid UTF-8. Binary formats skip this entirely.
3. **Number parsing**: `"12345"` in JSON is a string of characters that must be converted to an integer. This involves character-by-character processing plus bounds checking.

---

### JSON Gotchas That Cause Production Incidents

These are not theoretical concerns. Every one of these has caused real outages.

**Gotcha 1: Number precision — JavaScript's IEEE 754 problem**

JavaScript represents all numbers as 64-bit floating-point (IEEE 754 doubles). This format can represent integers exactly up to 2^53 (approximately 9 quadrillion). Above that, precision is lost.

```
  In Python:
    json.dumps({"order_id": 9999999999999999})
    → '{"order_id": 9999999999999999}'

  In JavaScript (browser or Node.js):
    JSON.parse('{"order_id": 9999999999999999}')
    → { order_id: 10000000000000000 }   // WRONG — lost precision

  The order ID changed by 1. If you look up this order, you get the wrong order.
  This has happened in production with Snowflake IDs and order tracking systems.
```

**Fix**: send large integers as strings in JSON. `{"order_id": "9999999999999999"}`. The consumer parses the string as a 64-bit integer in their language. Ugly but correct.

**Gotcha 2: `null` versus absent — two different semantics, often conflated**

In JSON, there is a meaningful difference between a field being `null` and a field being absent:

```json
  {"phone": null}     // Field exists, value is explicitly null (user has no phone)
  {}                  // Field is absent (we don't know if user has a phone)
```

Many deserializers treat these identically — both result in a `null` value in the target language. But they are semantically different. The first means "we know the user has no phone." The second means "we did not record this information."

If your business logic needs to distinguish "explicitly cleared" from "never set," JSON will fail you silently.

**Gotcha 3: Date formats — no standard, endless pain**

JSON has no date type. Dates are strings. Every team invents their own format:

```
  "2024-01-15"                  // ISO 8601 date only
  "2024-01-15T10:30:00Z"        // ISO 8601 datetime with UTC timezone
  "2024-01-15T10:30:00-05:00"   // ISO 8601 with timezone offset
  1705315800                    // Unix timestamp in seconds
  1705315800000                 // Unix timestamp in milliseconds (10x bigger!)
  "Mon Jan 15 2024"             // Custom human-readable format
```

When services from two different teams or two different languages communicate, date parsing failures are common. The single most dangerous mismatch: seconds vs. milliseconds. A Unix timestamp in seconds treated as milliseconds produces a date in 1970.

**Gotcha 4: Floating point — never use it for money**

```
  In any language that uses IEEE 754 floats:
    0.1 + 0.2 = 0.30000000000000004

  If you store {"price": 0.1} and {"tax": 0.2} and add them:
    total = 0.30000000000000004

  Charge a customer $0.30000000000000004 for enough transactions
  and you will have a regulatory problem.
```

**Fix**: store monetary values as integer cents (`"price_cents": 1099` for $10.99) or as strings (`"price": "10.99"`). Never as floating point.

---

### When JSON IS the Right Choice

Despite all of the above, JSON is the correct choice in many situations:

- **External-facing APIs**: developers integrating with your API can use `curl`. They do not need special tooling. This is worth the inefficiency.
- **Debugging**: when something goes wrong, you can read JSON in a log file or network capture without any decoder.
- **Configuration files**: `package.json`, `tsconfig.json`, settings files. No performance concern.
- **Low QPS internal APIs** (under 1,000 requests/second): the inefficiency is invisible at this scale.
- **Rapid prototyping**: getting something working fast matters more than optimizing encoding.

---

## 4. Protobuf: Binary Efficiency (Deep Dive)

**Protocol Buffers** (Protobuf) was designed at Google to replace text-based formats for internal RPC. The fundamental insight was simple: field names are expensive because they are long strings that repeat in every message. What if instead of the name, you used a small integer — a **field number** — to identify each field?

### Field Numbers Instead of Field Names

You define your schema in a `.proto` file:

```proto
  message User {
    int64  id    = 1;    // field number 1
    string name  = 2;    // field number 2
    string email = 3;    // field number 3
  }
```

The field numbers `1`, `2`, `3` are what appear on the wire — not the strings `"id"`, `"name"`, `"email"`.

This has one enormously important consequence: **field numbers are the permanent identity of each field**. If you rename `name` to `full_name` in your `.proto` file, that is fine — the wire format is unchanged because field number `2` still identifies that field on the wire. But if you change field `2` from a string to an integer, or if you delete field `2` and reuse its number for a different field, you will corrupt data for any consumer running old code.

This is why the cardinal rule of Protobuf is: **never renumber or reuse field numbers**.

---

### Varint Encoding: How Protobuf Squeezes Integers

Protobuf uses a clever encoding called **varint** (variable-length integer) for integer fields. The insight: most integers in practice are small. Using 8 bytes for the number `5` is wasteful. Varint uses fewer bytes for smaller numbers.

Here is how varint works. Each byte stores 7 bits of the actual value. The most significant bit (MSB) of each byte is a **continuation bit**: if it is `1`, more bytes follow; if it is `0`, this is the last byte.

Let us encode the number **300** step by step:

```
  Step 1: Write 300 in binary (32-bit):
    00000000 00000000 00000001 00101100

  Step 2: Split into 7-bit groups, least significant bits first:
    300 in binary:  1_0010110_0
    7-bit groups (LSB first): 0101100  0000010
    (The first group is the 7 least significant bits)

  Step 3: Add continuation bits:
    - First group (not last): MSB = 1  →  1_0101100  = 0xAC
    - Second group (last):    MSB = 0  →  0_0000010  = 0x02

  Result: two bytes  [0xAC, 0x02]
    Binary: 10101100 00000010

  Verification (decode):
    Take 0xAC = 10101100, continuation bit = 1, value bits = 0101100
    Take 0x02 = 00000010, continuation bit = 0, value bits = 0000010
    Concatenate value bits (second group first because LSB-first):
    0000010 0101100 = 100101100 in binary = 256 + 32 + 8 + 4 = 300. Correct.
```

The varint encoding efficiency table:

```
  Integer range           Bytes used   Example
  ────────────────────────────────────────────────
  0  to  127              1 byte       id = 5   → [0x05]
  128  to  16,383         2 bytes      id = 300  → [0xAC, 0x02]
  16,384  to  2,097,151   3 bytes      id = 65536
  up to 2^28 - 1          4 bytes
  up to 2^35 - 1          5 bytes
  up to 2^64              10 bytes (max for 64-bit)
```

Most business IDs are small enough to fit in 1–2 bytes. A 32-bit fixed integer always takes 4 bytes. Varint saves space for the common case.

---

### Wire Types: The Protobuf Type System

Protobuf categorizes fields into **wire types** — a small integer that tells the decoder how to interpret the next bytes:

```
  Wire Type   Meaning                   Used for
  ─────────────────────────────────────────────────────────────────
  0           Varint                    int32, int64, bool, enum
  1           64-bit fixed              fixed64, double
  2           Length-delimited          string, bytes, embedded msgs, packed arrays
  5           32-bit fixed              fixed32, float
```

(Wire types 3 and 4 were deprecated; wire type 6 and 7 are reserved.)

---

### Tag Encoding: The Key That Unlocks Everything

Each field on the wire is prefixed by a **tag**. The tag is a single varint that encodes both the field number and the wire type:

```
  tag = (field_number << 3) | wire_type
```

For field number `2` (the `name` field, a string which has wire type 2):

```
  tag = (2 << 3) | 2 = 16 | 2 = 18 = 0x12
```

This means field number `2` with wire type `2` (string) becomes the single byte `0x12` in the tag position.

**Critical optimization**: field numbers 1 through 15 fit in a single byte tag (because `15 << 3 = 120`, which is under 128 and thus a single varint byte). Field numbers 16 and above require 2 bytes for the tag. Therefore: **assign field numbers 1–15 to your most frequently-sent fields**.

If you have a message that always includes `id`, `timestamp`, and `status`, put those at field numbers 1, 2, and 3. Put rarely-used debug fields at numbers 20 and above.

---

### Byte-Level Anatomy of a Protobuf Message

Let us encode a concrete 3-field message and trace every byte:

```
  Proto definition:
    message Event {
      int64  id        = 1;   // wire type 0 (varint)
      string name      = 2;   // wire type 2 (length-delimited)
      bool   active    = 3;   // wire type 0 (varint)
    }

  Values: id=1, name="Hi", active=true

  ┌──────────────────────────────────────────────────────────────────────┐
  │  BYTE  │  HEX  │  MEANING                                           │
  ├──────────────────────────────────────────────────────────────────────┤
  │   0    │  0x08 │  Tag: field=1, wire_type=0 → (1<<3)|0 = 8         │
  │   1    │  0x01 │  Varint value: 1                                   │
  ├──────────────────────────────────────────────────────────────────────┤
  │   2    │  0x12 │  Tag: field=2, wire_type=2 → (2<<3)|2 = 18        │
  │   3    │  0x02 │  Length of string: 2 bytes follow                  │
  │   4    │  0x48 │  'H' in UTF-8 (72 decimal)                        │
  │   5    │  0x69 │  'i' in UTF-8 (105 decimal)                       │
  ├──────────────────────────────────────────────────────────────────────┤
  │   6    │  0x18 │  Tag: field=3, wire_type=0 → (3<<3)|0 = 24        │
  │   7    │  0x01 │  Varint value: 1 (true)                            │
  └──────────────────────────────────────────────────────────────────────┘

  Total: 8 bytes

  Equivalent JSON: {"id":1,"name":"Hi","active":true}  → 35 bytes
  Protobuf saves 77% for this message.
```

---

### Proto3 vs Proto2: Key Differences

Protobuf comes in two versions. Proto3 is the modern default; Proto2 is older but still common.

```
  Feature                Proto2                    Proto3
  ─────────────────────────────────────────────────────────────────
  Required fields        Yes (required keyword)    No (all optional)
  Default values         Customizable per field    Zero/empty/false always
  Missing field vs zero  Distinguishable           NOT distinguishable
  Extensions             Yes                       No (use Any instead)
  Unknown fields         Dropped on re-serialize   Preserved
  Recommended for new    No                        Yes
```

The most important gotcha in Proto3: **you cannot tell if a field was explicitly set to `0` or was simply absent**.

```proto
  // Proto3:
  message Order {
    int64 quantity = 1;
  }
```

If a message arrives with `quantity = 0`, you cannot know: did the sender set quantity to zero (perhaps a cancelled order), or did the sender not include the quantity field at all (perhaps an older client that does not know about this field)?

**Fix for nullable semantics in Proto3**: use the `google.protobuf` wrapper types:

```proto
  import "google/protobuf/wrappers.proto";

  message Order {
    google.protobuf.Int64Value quantity = 1;   // nullable int64
  }
```

If `quantity` is absent, the field is `null`. If it is present with value `0`, the field is explicitly zero. This costs one extra byte of overhead but gives you nullable semantics.

---

## 5. Avro: Schema-Based Binary (Deep Dive)

**Apache Avro** takes a completely different approach from Protobuf. Protobuf puts field number tags on every value so the decoder knows which field it is looking at. Avro puts **nothing** on the wire except the raw values — no tags, no field names, no type markers.

### The Key Difference: No Field Identifiers on the Wire

Here is a side-by-side comparison of what the two formats put on the wire for the same data:

```
  Data: {id: 42, name: "Alice", active: true}

  Protobuf wire format:
    [tag:id=1,varint] [varint:42] [tag:name=2,string] [len:5] [A][l][i][c][e] [tag:active=3,varint] [varint:1]
    ─────────┬──────────────────────────────────────────────────────────────────────────────────────────────────
             └── Tags tell decoder which field each value belongs to

  Avro wire format:
    [varint:42] [len:5] [A][l][i][c][e] [varint:1]
    ─────┬──────────────────────────────────────────
         └── No tags at all. Just raw values in the order the schema defines them.
```

This means Avro data is meaningless without the schema. You cannot decode even a single byte without knowing the schema used to write it. The values `[84, 10, 65, 108, 105, 99, 101, 1]` could be decoded as a `User` or as an `OrderItem` or as anything else — the bytes themselves give you no clue.

This sounds like a weakness. It is actually a strength: messages are dramatically smaller because they carry zero metadata.

---

### Where the Schema Lives

Since the decoder always needs the schema, Avro has two ways to provide it:

**Option 1: Avro Object Container File (embedded schema)**

Used for files (HDFS, S3). The schema is written once at the beginning of the file, and all records follow. If you read the file years later, the schema is right there.

```
  ┌─────────────────────────────────────────────────────┐
  │  AVRO OBJECT CONTAINER FILE                         │
  ├─────────────────────────────────────────────────────┤
  │  Magic bytes: "Obj" + version (4 bytes)             │
  │  File metadata (JSON schema embedded as bytes)      │
  │  Sync marker (16 random bytes, used for splitting)  │
  ├─────────────────────────────────────────────────────┤
  │  Block 1: count of objects + compressed data        │
  │  Sync marker                                        │
  ├─────────────────────────────────────────────────────┤
  │  Block 2: count of objects + compressed data        │
  │  Sync marker                                        │
  └─────────────────────────────────────────────────────┘
```

**Option 2: Schema Registry (for Kafka)**

Used for streaming. The schema is stored centrally in a **Schema Registry** (Confluent's is the most common). Each Avro-encoded Kafka message starts with:

```
  Byte 0:    0x00         (magic byte — signals Confluent schema registry format)
  Bytes 1-4: 4-byte schema ID (big-endian integer, e.g., 0x00000005 = schema ID 5)
  Bytes 5+:  Avro-encoded data

  Consumer receives the message, reads the schema ID (5),
  fetches schema #5 from the Schema Registry (usually cached after first fetch),
  and uses that schema to decode bytes 5 onward.
```

This is elegant: messages stay small (only 5 bytes of overhead), and the schema is always findable. Schema Registry caches schemas in memory, so the fetch is fast after the first time.

---

### Schema Resolution: The Magic of Avro

Here is where Avro gets interesting. What happens when the producer was using schema version 1, but the consumer has schema version 2 (perhaps it was updated to add a new field)?

Avro calls this **schema resolution**. The algorithm matches fields from the writer schema to fields in the reader schema **by name** (not by position). This is how Avro enables forward and backward compatibility without coordination between producer and consumer deployments.

The rules:

```
  Writer has field X, Reader has field X  → Use writer's value for X
  Writer has field X, Reader lacks field X → Skip X's bytes (reader ignores it)
  Writer lacks field X, Reader has field X → Use X's default value from reader schema
  Type mismatch between writer and reader  → Promote if compatible (int→long→float→double)
                                             Error if incompatible (string→int)
```

Concrete example:

```
  WRITER SCHEMA (v1):                READER SCHEMA (v2):
  {                                  {
    "type": "record",                  "type": "record",
    "name": "User",                    "name": "User",
    "fields": [                        "fields": [
      {"name":"id",   "type":"long"},    {"name":"id",   "type":"long"},
      {"name":"name", "type":"string"}   {"name":"name", "type":"string"},
    ]                                    {"name":"tier", "type":"string",
  }                                       "default":"free"}   // NEW FIELD
                                       ]
                                     }

  Avro bytes written by v1 producer:
    [varint:42] [len:5][Alice]
    (just the raw id and name values, in schema order)

  Resolution by v2 consumer:
    Step 1: Read id  → matches reader field "id" → value = 42
    Step 2: Read name → matches reader field "name" → value = "Alice"
    Step 3: Writer schema has no more fields.
            Reader schema has "tier" with no corresponding writer field.
            → Use default value: "free"

  Result in consumer: {id: 42, name: "Alice", tier: "free"}
  No crash. No coordination needed between teams. No outage.
```

This is the diagram of the full resolution flow:

```
  PRODUCER                   KAFKA TOPIC                  CONSUMER
  (uses schema v1)                                         (uses schema v2)

  User{id=42,name="Alice"}                                 needs: id, name, tier
         │
         │  Avro encode with v1 schema
         v
  [0x00][schema_id=1][42][5][Alice]
         │
         └────────────── message ──────────────────────────────────────────►
                                                                    │
                                                     Reads schema_id=1 from header
                                                     Fetches v1 from Schema Registry
                                                     Fetches v2 (its own reader schema)
                                                                    │
                                                              Resolution:
                                                              id   → 42
                                                              name → "Alice"
                                                              tier → "free" (default)
                                                                    │
                                                                    v
                                                           User{id=42, name="Alice",
                                                                tier="free"}
```

---

### Zigzag Encoding: Making Negative Numbers Efficient

Avro uses varint encoding like Protobuf, but adds **zigzag encoding** for signed integers. Here is the problem: varint is efficient for small positive numbers, but terrible for negative numbers. The number `-1` in standard two's complement 64-bit is `0xFFFFFFFFFFFFFFFF` — a very large unsigned integer — which would take 10 bytes as a varint.

Zigzag encoding maps the signed integer range onto the unsigned integer range by interleaving positives and negatives:

```
  Signed integer  →  Zigzag unsigned integer
  ─────────────────────────────────────────────
       0          →   0
      -1          →   1
       1          →   2
      -2          →   3
       2          →   4
      -3          →   5
       3          →   6
     ...          →  ...
      -n          →  2n - 1
       n          →  2n

  Formula: zigzag(n) = (n << 1) XOR (n >> 63)   (for 64-bit)
```

With zigzag encoding, `-1` maps to `1` (1 varint byte), `-100` maps to `199` (2 varint bytes), and so on. Small absolute values — whether positive or negative — encode efficiently.

---

## 6. Parquet: Columnar Format for Analytics

Parquet is not an encoding format you use for service-to-service communication. It is an **analytics storage format** — designed for systems like BigQuery, Snowflake, Spark, and Hive that run aggregation queries over massive datasets.

Understanding Parquet is a staff-level signal in interviews, because it shows you understand the entire data lifecycle: not just how services communicate, but how data is stored and queried years later.

### The Core Problem with Row Formats for Analytics

Imagine you have a billion-row table of e-commerce orders:

```
  Row 1:  {order_id: 1, user_id: 1001, amount: 49.99, country: "US", status: "shipped", ...}
  Row 2:  {order_id: 2, user_id: 1002, amount: 12.50, country: "UK", status: "pending", ...}
  Row 3:  {order_id: 3, user_id: 1001, amount: 8.99,  country: "US", status: "delivered", ...}
  ...     (1 billion rows)
```

Your analyst runs this query:

```sql
  SELECT country, SUM(amount) FROM orders GROUP BY country;
```

This query touches exactly two columns: `country` and `amount`. It ignores `order_id`, `user_id`, `status`, and every other column.

In a **row format** (JSON, Avro, Protobuf files), data is stored row by row on disk. To read `country` and `amount`, you must read every byte of every row — all columns — and then discard the ones you do not need.

```
  ROW FORMAT ON DISK:
  ┌─────────────────────────────────────────────────────────────────┐
  │ [order_id:1][user_id:1001][amount:49.99][country:US][status...] │  ← read all of this
  │ [order_id:2][user_id:1002][amount:12.50][country:UK][status...] │  ← to get 2 values
  │ [order_id:3][user_id:1001][amount:8.99 ][country:US][status...] │
  │ ... 1 billion rows ...                                          │
  └─────────────────────────────────────────────────────────────────┘
  I/O reads: 100% of data. Useful: 2 columns (maybe 10%).
  Wasted I/O: 90%+
```

In a **columnar format** (Parquet), data is stored column by column. To read `country` and `amount`, you read only those two columns' storage areas:

```
  COLUMNAR FORMAT ON DISK (Parquet):
  ┌──────────────────────┬────────────────────────────────────────────┐
  │  order_id column     │  1, 2, 3, 4, 5, ... (1 billion values)    │  ← NOT READ
  │  user_id column      │  1001, 1002, 1001, ... (1 billion values)  │  ← NOT READ
  │  amount column       │  49.99, 12.50, 8.99, ... (1 billion values)│  ← READ THIS
  │  country column      │  US, UK, US, ... (1 billion values)        │  ← READ THIS
  │  status column       │  shipped, pending, delivered, ...          │  ← NOT READ
  └──────────────────────┴────────────────────────────────────────────┘
  I/O reads: 2 columns only. Useful: 100% of what was read.
  Wasted I/O: 0%.
```

For a table with 20 columns and a query that touches 2 of them, columnar gives you a 10x reduction in I/O. On petabyte datasets, this translates directly to query cost and query speed.

---

### Parquet File Structure

```
  ┌──────────────────────────────────────────────────────────────┐
  │                     PARQUET FILE                             │
  ├──────────────────────────────────────────────────────────────┤
  │  Magic: "PAR1" (4 bytes)                                     │
  ├──────────────────────────────────────────────────────────────┤
  │                  ROW GROUP 1 (~128 MB)                       │
  │  ┌────────────────────────────────────────────────────────┐  │
  │  │ Column Chunk: order_id (all order_id values in group)  │  │
  │  │   Page 1 (~1 MB) │ Page 2 │ Page 3 │ ...              │  │
  │  ├────────────────────────────────────────────────────────┤  │
  │  │ Column Chunk: amount   (all amount values in group)    │  │
  │  │   Page 1 │ Page 2 │ ...                               │  │
  │  ├────────────────────────────────────────────────────────┤  │
  │  │ Column Chunk: country  (all country values in group)   │  │
  │  │   Page 1 │ Page 2 │ ...                               │  │
  │  └────────────────────────────────────────────────────────┘  │
  ├──────────────────────────────────────────────────────────────┤
  │                  ROW GROUP 2 (~128 MB)                       │
  │  (same structure)                                            │
  ├──────────────────────────────────────────────────────────────┤
  │  FILE FOOTER (metadata)                                      │
  │  - Schema (field names, types)                               │
  │  - For each column chunk: min value, max value, null count   │
  │  - Byte offsets so reader can seek directly to any chunk     │
  ├──────────────────────────────────────────────────────────────┤
  │  Footer length (4 bytes) + Magic: "PAR1" (4 bytes)          │
  └──────────────────────────────────────────────────────────────┘
```

The metadata at the end contains min/max values for every column chunk. This enables **predicate pushdown**: if your query filters `WHERE country = 'DE'` and a row group has `min='AA', max='BB'` for the country column, the engine can skip the entire row group without reading it.

---

### Compression in Parquet

Columnar storage compresses far better than row storage, because values in a column are all the same type and often similar in value:

**Dictionary encoding**: for a `country` column with values `US, UK, US, DE, US, US, UK`:
```
  Dictionary: {0: "US", 1: "UK", 2: "DE"}
  Encoded:    [0, 1, 0, 2, 0, 0, 1]

  "US" (2 bytes) → integer 0 (1 byte). For a billion rows: saves ~1 GB for this column alone.
```

**Run-length encoding (RLE)**: for a mostly-uniform column like `status` during a period when most orders are shipping:
```
  Raw:     [shipped, shipped, shipped, pending, pending, delivered, shipped, ...]
  RLE:     [(shipped, 3), (pending, 2), (delivered, 1), (shipped, 1), ...]

  Instead of storing 3 copies of "shipped", store it once with a count of 3.
```

**Delta encoding**: for timestamps that are monotonically increasing:
```
  Raw:     [1705315800, 1705315862, 1705315900, 1705315921]
  Delta:   [1705315800, +62, +38, +21]

  First value in full, rest as small deltas. Deltas fit in 1-2 bytes instead of 8.
```

The real-world compression result: 1 TB of raw JSON event data typically compresses to **150–200 GB as Parquet with Snappy compression** — a 5x to 7x reduction. At $0.023/GB-month on S3, that is a meaningful cost difference for data you keep for years.

---

## 7. FlatBuffers and MessagePack: The Other Formats

### FlatBuffers: Zero-Copy Deserialization

**FlatBuffers** was created at Google for game development and other latency-critical applications. The revolutionary idea: instead of encoding data in a format that requires parsing before you can read it, store the data directly in the **memory layout** it will have after deserialization.

With any other format (JSON, Protobuf, Avro), the workflow is:

```
  Receive bytes  →  Parse/decode (CPU work)  →  Object in memory  →  Read field
```

With FlatBuffers:

```
  Receive bytes  →  (no parsing)  →  Read field directly from byte buffer
```

"Reading a field from a FlatBuffer" means: look up the field's offset in a small table at the start of the buffer, then read the bytes at that offset. For a 32-bit integer field, that is one memory read. There is no copying, no allocation, no garbage collection.

```
  FlatBuffer layout for {id: 42, name: "Alice"}:

  Offset 0:  vtable offset (points to vtable at end of buffer)
  Offset 4:  field offsets in vtable
             field 0 (id)   → offset 8
             field 1 (name) → offset 12
  Offset 8:  42  (4 bytes, int32)
  Offset 12: offset to string "Alice" (4 bytes)
  Offset 16: "Alice" (5 bytes + length prefix)

  To read "id": look up vtable[0] = 8, read int32 at offset 8 = 42. Done.
  No parsing. No allocation. Pure memory access.
```

**When to use FlatBuffers**: latency-critical paths where deserialization time matters — game engines, embedded systems, ML inference pipelines, real-time bidding. The tradeoff is a more complex format: FlatBuffer binaries are larger than Protobuf because of the vtable overhead, and building them requires writing in reverse order (you build leaf nodes before root).

---

### MessagePack: Binary JSON

**MessagePack** is the simplest upgrade from JSON. It uses the same type system as JSON (objects, arrays, strings, numbers, booleans, null) but encodes in binary instead of text.

Why is binary more compact than text? Because text wastes bytes on characters that carry no information:

```
  JSON:        {"id":100}           → 10 bytes
  MessagePack: {id:100}             → approximately 7 bytes

  The quotes, braces, and colon in JSON exist so a human can read it.
  MessagePack encodes the same information with type bytes and length prefixes.
```

Specific MessagePack encoding examples:

```
  Value      JSON encoding    MessagePack encoding
  ─────────────────────────────────────────────────────
  null       "null" (4 bytes) 0xc0 (1 byte)
  true       "true" (4 bytes) 0xc3 (1 byte)
  false      "false"(5 bytes) 0xc2 (1 byte)
  100        "100"  (3 bytes) 0x64 (1 byte, positive fixint)
  "hello"    7 bytes          6 bytes (fixstr length + bytes)
  [1,2,3]    7 bytes          4 bytes (fixarray + 3 fixints)
```

**MessagePack is roughly 20–30% smaller than JSON** for typical payloads, and faster to encode/decode because there is no UTF-8 validation or string-based number parsing.

**When to use MessagePack**: when you need JSON's schemaless flexibility (no .proto or Avro schema to maintain) but you have bandwidth or CPU pressure. Common in Redis clients, some RPC systems, and API gateways that can negotiate content-type.

---

### Format Comparison Table

| Dimension            | JSON       | Protobuf   | Avro       | Parquet    | FlatBuffers | MessagePack |
|----------------------|------------|------------|------------|------------|-------------|-------------|
| Human readable       | Yes        | No         | No         | No         | No          | No          |
| Schema required      | No         | Yes (.proto)| Yes       | Yes        | Yes (.fbs)  | No          |
| Schema on wire       | Implicit   | No (field#)| No (registry)| In file | No          | Implicit    |
| Binary format        | No         | Yes        | Yes        | Yes        | Yes         | Yes         |
| Typical compression  | 1x (base)  | 0.5x       | 0.45x      | 0.1–0.2x   | 0.7x        | 0.7–0.8x    |
| Decode speed         | Slow       | Fast       | Fast       | Fast (col) | Fastest     | Medium      |
| Schema evolution     | Manual     | Formal rules| Formal rules| Formal  | Formal rules| Manual      |
| Best use case        | External API| gRPC/internal| Kafka   | Analytics  | Games/RT    | Cache/Redis |

---

## 8. Performance Numbers Every Staff Engineer Should Know

Numbers without context are useless. Numbers with context change architectural decisions. Here are the benchmarks that matter, with the reasoning behind them.

---

### Encoding/Decoding CPU Cost at 100K QPS

These are approximate representative numbers from industry benchmarks on a modern server (single core):

```
  Format        Encode latency    At 100K QPS           CPU cores consumed
  ────────────────────────────────────────────────────────────────────────
  JSON          ~15 µs / message  1,500,000 µs/sec      ~1.5 cores
  MessagePack   ~8 µs / message   800,000 µs/sec        ~0.8 cores
  Protobuf      ~5 µs / message   500,000 µs/sec        ~0.5 cores
  Avro          ~4 µs / message   400,000 µs/sec        ~0.4 cores
  FlatBuffers   ~1 µs / message   100,000 µs/sec        ~0.1 cores
```

The practical impact: switching one service from JSON to Protobuf at 100K QPS frees approximately **1 CPU core**. If your service runs on 10 instances, that is 10 freed cores. At AWS on-demand pricing ($0.05/core-hour for a c5.xlarge equivalent), that is roughly **$360/month per service**.

---

### Payload Size Comparison

For a representative 10-field business object (IDs, timestamps, strings, booleans):

```
  Format        Typical size    vs JSON
  ─────────────────────────────────────
  JSON          ~800 bytes      1.0x (baseline)
  MessagePack   ~550 bytes      0.69x (31% smaller)
  Protobuf      ~350 bytes      0.44x (56% smaller)
  Avro          ~320 bytes      0.40x (60% smaller)
  Parquet       ~50 bytes/row   0.06x (only for batched columnar, not streaming)
```

FlatBuffers is typically larger than Protobuf for small messages due to vtable overhead (more efficient than Protobuf only when messages are large or deserialization is the bottleneck, not size).

---

### Bandwidth Cost at Scale

This is the calculation that justifies switching formats at the architectural level:

```
  Scenario: Internal service at 100K QPS with JSON payloads

  Daily data transfer:
    100,000 req/sec  ×  800 bytes/req  ×  86,400 sec/day
    = 6,912,000,000,000 bytes/day
    = 6.9 TB/day

  Monthly data transfer:
    6.9 TB/day × 30 days = 207 TB/month

  At $0.01/GB inter-AZ transfer (AWS):
    207,000 GB × $0.01 = $2,070/month for this one service pair

  Switch to Protobuf (56% smaller payloads):
    207 TB → 91 TB/month
    Savings: 116 TB × $0.01 = $1,160/month
    = ~$14,000/year for a single service pair
```

At 1M QPS (a large platform service), multiply these numbers by 10.

---

### The BigQuery/Parquet Storage Calculation

For data lake storage:

```
  Event volume: 100K events/sec × 86,400 sec/day = 8.64 billion events/day

  Storage by format (approximate, typical e-commerce event):
    Raw JSON:           ~1 KB/event → 8.64 TB/day
    Avro (compressed):  ~300 B/event → 2.6 TB/day
    Parquet + Snappy:   ~150 B/event → 1.3 TB/day

  Cumulative after 1 year:
    JSON:    3.15 PB → at $0.023/GB on S3 Standard: $72,450/month
    Parquet: 474 TB  → at $0.023/GB on S3 Standard: $10,897/month

  Annual savings: ~$738,000 for storing the same events in Parquet vs JSON.
  This is the ROI of choosing the right format for your data lake on day one.
```

---

### Summary Decision Framework

```
  ┌─────────────────────────────────────────────────────────────────────────┐
  │                 FORMAT SELECTION FLOWCHART                              │
  ├─────────────────────────────────────────────────────────────────────────┤
  │                                                                         │
  │  Is the consumer external (third-party / browser)?                      │
  │     YES → JSON + OpenAPI spec                                           │
  │     NO  → continue                                                      │
  │                                                                         │
  │  Is this analytics / data lake / batch processing?                      │
  │     YES → Parquet (columnar, compressed, queryable)                     │
  │     NO  → continue                                                      │
  │                                                                         │
  │  Is latency of deserialization the critical constraint?                  │
  │  (game servers, HFT, real-time inference)                               │
  │     YES → FlatBuffers                                                   │
  │     NO  → continue                                                      │
  │                                                                         │
  │  Is this a Kafka event stream?                                          │
  │     YES → Avro + Confluent Schema Registry                              │
  │     NO  → continue                                                      │
  │                                                                         │
  │  Is this gRPC between internal services?                                │
  │     YES → Protobuf (gRPC native)                                        │
  │     NO  → continue                                                      │
  │                                                                         │
  │  Do you want schemaless but smaller than JSON?                          │
  │  (Redis, ad-hoc services)                                               │
  │     YES → MessagePack                                                   │
  │     NO  → JSON (catch-all for internal low-QPS REST)                    │
  │                                                                         │
  └─────────────────────────────────────────────────────────────────────────┘
```

---

## What You Should Carry Into Part B

Part A has given you the complete picture of what each format puts on the wire and why. Before you continue to Part B, you should be able to answer these questions without looking anything up:

- Why does Protobuf use field numbers instead of field names, and what is the consequence of renumbering?
- Why can you not decode Avro without the writer schema?
- What does the `0x00` magic byte at the start of a Kafka Avro message indicate?
- For a 100K QPS internal service, what is the CPU cost difference between JSON and Protobuf?
- Why does columnar storage compress better than row storage?
- What is zigzag encoding for, and what problem does it solve?

Part B will take these formats and ask: what happens when the schema changes? How do producers and consumers evolve independently without coordination outages? That is where **schema evolution rules**, **compatibility modes**, and **Schema Registry** come in.

---

*End of Chapter 30, Part A.*
# Chapter 30: Data Encoding and Schema Evolution
## Part B: Schema Evolution Rules, Schema Registry, gRPC, Migration Patterns, and Cross-Team Governance

---

## 1. Schema Evolution: The Contract With the Future

### The Core Problem

Imagine you have 100 services at your company. They all talk to each other by passing messages. Those messages have a specific shape — fields like `user_id`, `email`, `created_at`. This shape is the **schema**.

Now one producer team changes the schema. Maybe they rename a field. Maybe they remove one. Maybe they add three new ones. The question is: **which of the 100 consumers break?**

This is not a small concern. In large systems, a single Kafka topic might have 50 subscribers. A gRPC service might have 20 callers. One careless schema change can cascade into a Saturday-night production incident affecting hundreds of thousands of users.

Schema evolution is the discipline of changing schemas in ways that do not break existing code, or — when breaking changes are unavoidable — managing that transition safely and deliberately.

### The USB Analogy

Think about USB cables. USB 1.0 had a specific connector and specific pins. USB 2.0 was designed to be **backward compatible** with USB 1.0: if you plugged an old USB 1.0 device into a USB 2.0 port, it still worked. The new port understood old devices. That is backward compatibility.

USB 3.0 added new pins alongside the old pins. If you plugged a USB 3.0 device into an old USB 2.0 port, it still worked (at slower speed) — the old port just ignored the new pins it did not understand. That is forward compatibility.

Now imagine a hypothetical USB 4.0 that completely rearranged the pins. Every old cable would break. Every old device would be confused. That is a **breaking change**.

Schema evolution rules exist so your Avro/Protobuf schemas behave like USB 3.0 and not like the hypothetical USB 4.0.

### Three Compatibility Types

There are three compatibility guarantees, and which one you need depends on your deployment order.

---

#### Backward Compatible: New Schema Reads Old Data

**Definition:** A consumer using the NEW schema can correctly read messages produced by the OLD producer.

**When you need it:** You deploy consumers FIRST, then producers. During the window between those deployments, the new consumers will see messages encoded in the old format. They must handle that gracefully.

```
Timeline:

  t=0      t=1        t=2        t=3
  |--------|----------|----------|-------->
  Deploy   Deploy     Old msgs   New msgs
  new      new        still in   arrive
  consumer producer   queue      

Consumer must handle BOTH formats.
New schema MUST be able to read OLD messages.
```

**What must be true:** Any new field you add must have a default value. If the old producer did not include `phone_number` in the message, the new consumer must have something to fall back on — the default.

```
Old message: { user_id: 42, email: "alice@example.com" }
New schema:  user_id, email, phone_number (default: "")

New consumer reads old message:
  user_id       -> 42             (present, use it)
  email         -> "alice@..."   (present, use it)
  phone_number  -> ""            (absent, use default)

Result: OK, no error
```

---

#### Forward Compatible: Old Schema Reads New Data

**Definition:** A consumer using the OLD schema can correctly read messages produced by the NEW producer.

**When you need it:** You deploy producers FIRST, then consumers. During the window before all consumers are updated, old consumers see messages encoded in the new format. They must not crash.

```
Timeline:

  t=0        t=1        t=2        t=3
  |----------|----------|----------|-------->
  Deploy     Old        Deploy     All
  new        consumers  new        consumers
  producer   see new    consumers  updated
             format

Old consumers MUST tolerate unknown new fields.
```

**What must be true:** Old schemas must be able to ignore fields they do not recognize. In Protobuf, this works automatically — unknown fields are preserved but not parsed. In Avro, field-matching-by-name means unknown fields are simply discarded if there is no matching reader field.

```
New message: { user_id: 42, email: "alice@...", loyalty_tier: "GOLD" }
Old schema:  user_id, email

Old consumer reads new message:
  user_id       -> 42          (known field, use it)
  email         -> "alice@..." (known field, use it)
  loyalty_tier  -> ??? ignored (unknown field, skip it)

Result: OK, no error (as long as format allows ignoring unknowns)
```

---

#### Full Compatible: Both Directions

**Definition:** Both backward AND forward compatible. The new schema can read old data AND old schema can read new data.

**When you use it:** When you cannot control deployment order, or when you have long-lived message queues where old messages sit for hours or days. This is the safest mode and the most restrictive.

**Cost:** You must satisfy BOTH constraints simultaneously. Every new field needs a default (for backward compat). Every removed field must be handled gracefully by old readers (for forward compat).

```
Full Compatibility Requirements:
+--------------------------+----------------------------+
| Change Type              | Allowed?                   |
+--------------------------+----------------------------+
| Add field with default   | YES                        |
| Remove field with default| YES (forward compat OK)    |
| Remove field, no default | NO (forward compat broken) |
| Add field, no default    | NO (backward compat broken)|
| Rename a field           | DEPENDS (see Avro aliases) |
| Renumber a Protobuf field| NO, never                  |
| Change field type        | ONLY safe promotions       |
+--------------------------+----------------------------+
```

---

#### Breaking: Neither Direction Works

**Definition:** Neither old readers can read new data, nor new readers can read old data.

**Examples:** Renaming a field (Avro), renumbering a field (Protobuf), changing `string` to `int`.

**What to do:** You cannot do a rolling deployment. You need a coordinated cutover (all producers and consumers switch simultaneously — which is nearly impossible in large distributed systems) OR you need a version bump (`/v2/` endpoint, new Kafka topic, new schema subject).

```
Compatibility Spectrum:

NONE -------- BACKWARD -------- FORWARD -------- FULL
(anything    (new reads old)   (old reads new)  (both)
 goes)
     ^                                               ^
     Dangerous                                    Safest
     Use only for development               Recommended for
     or internal scratch topics             production systems
```

---

## 2. Protobuf Evolution Rules — Deep Dive With Examples

### The Golden Rule: Field Numbers Are Wire Identity

In Protobuf, every field has a name AND a number. The name (`email`, `user_id`) is for humans and generated code. The number (`1`, `2`, `3`) is what actually goes on the wire.

When Protobuf encodes a message, it writes field number + wire type + value. It does NOT write the field name. So if you change a field number, you change the wire identity of that field — and everything breaks silently.

```protobuf
message User {
  int64  user_id  = 1;   // wire: tag 1, varint
  string email    = 2;   // wire: tag 2, length-delimited
  string name     = 3;   // wire: tag 3, length-delimited
}
```

When encoded: the bytes say "tag 1, here's a varint" / "tag 2, here's a string". No field names in the payload.

---

### Rule 1: Always Add Fields as Optional

In proto3, all fields are optional by default. If a field is absent from the message, it deserializes to the zero value for its type (0 for ints, "" for strings, false for bools).

**Example — adding a new field:**

Old schema:
```protobuf
message User {
  int64  user_id = 1;
  string email   = 2;
  string name    = 3;
}
```

New schema (backward compatible addition):
```protobuf
message User {
  int64  user_id      = 1;
  string email        = 2;
  string name         = 3;
  string phone_number = 4;   // NEW — field number 4, not reusing old numbers
}
```

Old consumers that do not know about field 4 will see `phone_number = ""` (zero value). New consumers reading old messages will see `phone_number = ""` (field absent, use zero value). Both sides handle it fine.

**Never reuse a field number for a different purpose.** Even if field 4 has never been used in production, if it ever existed in a compiled binary, using it for something new silently corrupts data.

---

### Rule 2: Never Remove a Field — Mark It Deprecated and Reserved

If you want to remove a field, you cannot just delete it. You must:

1. Mark it deprecated in a comment so developers know not to use it
2. Add it to `reserved` so the compiler prevents reuse of that number or name

**The danger of removing without `reserved`:**

```
Step 1: You remove field 3 (address) from the schema.
Step 2: Six months later, a new developer adds field 3 (loyalty_tier).
Step 3: There are old consumers with cached messages that still have
        field 3 = "123 Main Street" (address bytes).
Step 4: New consumer sees field 3, decodes it as loyalty_tier (a string).
        Result: loyalty_tier = "123 Main Street" — silently wrong data.
```

This is called **field number recycling** and it is one of the most dangerous Protobuf mistakes.

**The correct removal sequence:**

```protobuf
// BEFORE — field address exists
message User {
  int64  user_id  = 1;
  string email    = 2;
  string address  = 3;   // to be removed
}

// STEP 1 — mark deprecated, keep in schema
message User {
  int64  user_id  = 1;
  string email    = 2;
  string address  = 3 [deprecated = true];   // stop using this, but keep the definition
}

// STEP 2 — after all consumers stop reading field 3, move to reserved
message User {
  reserved 3;          // field number 3 is permanently retired
  reserved "address";  // field name is also retired (prevents name confusion)

  int64  user_id = 1;
  string email   = 2;
}
```

Now if any developer writes `string address = 3;` or `string anything = 3;`, the Protobuf compiler gives an error: "Field number 3 is reserved." The mistake is caught at compile time, not at 3am in production.

---

### Rule 3: Never Renumber Fields

This is the #1 way to silently corrupt data.

```
BEFORE:
  string email   = 2;
  string address = 3;

AFTER (BAD — renumbering):
  string address = 2;   // was 3, now 2
  string email   = 3;   // was 2, now 3

Wire effect:
  Old message bytes say: tag=2 -> "alice@example.com"
  New decoder reads:     tag=2 -> address field
  Result: address = "alice@example.com"
          email   = "" (missing)

Data is silently wrong. No error is thrown.
```

The motivation for renumbering is usually "I want fields in logical order." Never do it. Field numbers are not logical order — they are permanent wire identifiers.

---

### Rule 4: Safe Type Promotions Only

Some type changes are wire-compatible. Some are not.

```
Safe Promotions:
  int32  -> int64   : Both use varint wire type (0). Widening is OK.
  uint32 -> uint64  : Same wire type (0). Safe.
  sint32 -> sint64  : Same wire type (0). Safe.
  string -> bytes   : Both use wire type 2 (length-delimited). Safe.
  bytes  -> string  : Both use wire type 2. Safe (but validate UTF-8).
  fixed32 -> fixed64: NOT safe. Wire type changes (5 -> 1). Breaks.
  int32  -> float   : NOT safe. Wire type changes (0 -> 5). Breaks.
  int32  -> bool    : Technically same wire type 0, but semantics differ.

Wire Types (reference):
  0 = Varint     (int32, int64, uint32, uint64, bool, enum)
  1 = 64-bit     (fixed64, sfixed64, double)
  2 = Length-del (string, bytes, embedded messages, repeated fields)
  5 = 32-bit     (fixed32, sfixed32, float)
```

If you change from wire type 0 to wire type 5, the decoder reads the wrong number of bytes for the field. It either throws a parse error or silently consumes garbage bytes and misaligns all subsequent fields.

**Rule of thumb:** Only change types within the same wire type group, and only for widening promotions (int32 to int64, not int64 to int32).

---

### Rule 5: Enum Values — Add Freely, Never Remove or Renumber

In proto3, if a consumer receives an enum value it does not recognize, it stores it as the integer value but the named accessor returns the zero value (the first enum value). This means:

```protobuf
enum OrderStatus {
  UNKNOWN  = 0;   // default / unknown
  PENDING  = 1;
  SHIPPED  = 2;
  DELIVERED = 3;
  // CANCELLED = 4 added in new producer
}
```

Old consumer receives message with `status = 4` (CANCELLED). The `status` field accessor returns `UNKNOWN` (0). Your code must handle this — do not assume that `UNKNOWN` means the order was never placed. It might mean "the consumer does not know this status yet." Add a check: if status is UNKNOWN for a non-new order, treat it as "needs refresh."

Never remove enum value 0. It is the default and absence of a value. Never renumber existing enum values — same reason as field numbers.

---

### The `reserved` Keyword — All Three Forms

```protobuf
message User {
  reserved 3, 4;        // retired field numbers (single values)
  reserved 10 to 15;    // retired field number range
  reserved "address";   // retired field name (prevents name reuse)
  reserved "old_email", "tmp_field";  // multiple names

  int64  user_id = 1;
  string email   = 2;
  string name    = 5;
}
```

You cannot mix numbers and names in one `reserved` statement. Separate them as shown. The compiler enforces both: no new field may use a reserved number, and no new field may use a reserved name.

---

### The `oneof` Pitfall

`oneof` in Protobuf is a special construct meaning "only one of these fields will be set at a time." Moving an existing field INTO a `oneof` is a **breaking change** even if the field number stays the same.

```
BEFORE:
  string email = 5;

AFTER (breaking — even though field number 5 is kept):
  oneof contact {
    string email = 5;
    string phone = 6;
  }
```

Why is this breaking? Because `oneof` changes the encoded semantics. Old consumers may write multiple fields that belong to the same oneof in the new schema. The new decoder will only keep the last one, silently dropping the others.

Rule: Only ever put NEW fields into a `oneof`. Never migrate an existing field into a `oneof`.

---

## 3. Avro Evolution Rules — Deep Dive With Examples

### How Avro Resolution Works

Avro's evolution model is fundamentally different from Protobuf's. There are no field numbers. Fields are matched by **name**.

When a consumer reads an Avro message, it uses two schemas:
- The **writer schema** — the schema the producer used when encoding the message
- The **reader schema** — the schema the consumer wants the data in

The Avro library compares these two schemas and applies **schema resolution** rules to fill in the gaps.

```
Producer (Writer Schema):        Consumer (Reader Schema):
  user_id: long                    user_id: long
  email: string                    email: string
                                   phone_number: string (default: "")
                                   loyalty_tier: string (default: "STANDARD")

Avro resolution:
  user_id     -> matched by name -> use value from wire
  email       -> matched by name -> use value from wire
  phone_number -> NOT in writer  -> use reader's default ""
  loyalty_tier -> NOT in writer  -> use reader's default "STANDARD"

Result: consumer gets complete object with defaults filled in.
```

This is why Avro is popular for long-term event storage (like Kafka compaction or data warehouses) — as long as schemas are registered and defaults are present, you can evolve schemas across many versions and always deserialize correctly.

---

### Rule 1: New Fields MUST Have Defaults for Backward Compatibility

If you add a new field to the schema, it MUST have a default value.

Why: in backward compatibility mode, the OLD producer will send messages WITHOUT this field. The consumer's reader schema must know how to fill it in.

**Without default — fails:**
```json
{
  "type": "record",
  "name": "User",
  "fields": [
    {"name": "user_id", "type": "long"},
    {"name": "email",   "type": "string"},
    {"name": "phone",   "type": "string"}
  ]
}
```

Old messages have no `phone` field. Avro resolution: "reader wants phone, writer didn't provide it, reader has no default." Result: **AvroTypeException — deserialization failure.**

**With default — works:**
```json
{
  "type": "record",
  "name": "User",
  "fields": [
    {"name": "user_id", "type": "long"},
    {"name": "email",   "type": "string"},
    {"name": "phone",   "type": "string", "default": ""}
  ]
}
```

Old messages have no `phone`. Avro resolution: "reader wants phone, writer didn't provide it, reader default is ''. Use it." Result: **phone = ""**. No error.

---

### Rule 2: Removed Fields MUST Have Defaults for Forward Compatibility

If you remove a field from the reader schema, the old producer will still send that field. For forward compatibility (old producer, new consumer), the consumer must know what to do when it sees a field it no longer cares about.

In Avro, if the writer sends a field that the reader schema does not have, Avro simply discards it. This works without any special default in the reader schema — the extra field is ignored. **However**, if you want forward-AND-backward (full) compatibility, both sides must have defaults so that either party can cope with the other being ahead or behind.

Practically: always add defaults when removing fields from the "canonical" schema in your registry. That way any consumer — whether ahead or behind — can safely deserialize.

---

### Rule 3: Use Aliases for Renaming (NOT Direct Rename)

Renaming a field directly is a **breaking change** in Avro, because field matching is by name.

**Direct rename — breaks:**
```
Old schema: {"name": "userId", "type": "long"}
New schema: {"name": "user_id", "type": "long"}

Resolution: reader looks for "user_id" in writer data.
Writer sends "userId". No match.
Result: reader uses default for user_id (if it has one) or fails.
        "userId" data is silently discarded.
```

**Using aliases — safe:**
```json
{
  "name": "user_id",
  "type": "long",
  "aliases": ["userId"]
}
```

Resolution: reader looks for "user_id" — not found in writer. Checks aliases: "userId" — found! Uses that field's value. Data preserved.

**Important:** aliases are in the READER schema, not the writer schema. You add aliases to tell the reader "if you see data from old writer under this old name, treat it as my new name."

---

### Rule 4: Type Promotion Rules

Avro allows specific type promotions as defined in the spec:

```
Allowed promotions (safe):
  int    -> long           (widening integer)
  int    -> float          (int to float)
  int    -> double         (int to double)
  long   -> float          (long to float — precision loss possible, but Avro allows it)
  long   -> double         (long to double)
  float  -> double         (widening float)
  string -> bytes          (same wire encoding in Avro binary format)
  bytes  -> string         (same wire encoding, validate UTF-8)

NOT allowed (will cause resolution error):
  int    -> string         (type mismatch, no promotion path)
  string -> int            (same)
  long   -> int            (narrowing, not in spec)
  any    -> null           (not a promotion — use union instead)
  array  -> map            (incompatible container types)
```

If you attempt an unsupported type change, Avro throws a `SchemaParseException` during schema resolution, before any data is read.

---

### Avro Union Types for Nullable Fields

By default, Avro types are non-nullable. If you want a field that can be null (absent), you use a **union type**: `["null", "string"]`.

```json
{
  "name": "middle_name",
  "type": ["null", "string"],
  "default": null
}
```

Rules for unions with null:
1. `null` MUST be first in the union array if your default is null (Avro requires the default to match the first type in the union)
2. On the wire: unions are encoded as an integer index (0 for null, 1 for string) followed by the value if non-null
3. If you later add a previously non-nullable field as nullable with a union, old readers that only know the non-union type may be confused

**Adding nullable field to an existing schema:**
```json
// OLD: middle_name did not exist
// NEW: adding it as optional nullable
{
  "name": "middle_name",
  "type": ["null", "string"],
  "default": null
}
```

Old consumers: field absent in writer schema, reader has default null. Avro uses null. Works.
Old producers sending new consumers: field absent in old messages, consumer uses default null. Works.

This is the correct pattern for any field that may not always be present.

---

## 4. Schema Registry — Deep Dive

### What It Enforces

A **Schema Registry** is a centralized service that stores schemas and enforces compatibility rules before any producer is allowed to publish messages.

Without a Schema Registry:
- Producers can publish any schema, even a breaking one
- Consumers break at runtime, during production traffic
- You discover the incompatibility when users report errors

With a Schema Registry:
- Producer tries to register a schema → registry checks compatibility against all previous versions → **rejects** if incompatible
- The rejection happens at producer startup or CI/CD time, not during live traffic
- Consumers fetch schemas by ID to deserialize — schemas are always available and versioned

**Confluent Schema Registry compatibility modes:**

```
+-------------------+--------------------------------------------------+
| Mode              | What It Checks                                   |
+-------------------+--------------------------------------------------+
| NONE              | No checks. Any schema accepted. (Dev/scratch)    |
| BACKWARD          | New schema can read data by previous version.    |
|                   | Deploy consumers first, then producers.          |
| BACKWARD_TRANSITIVE| New schema can read data by ALL previous vers.  |
|                   | Protects consumers far behind in upgrades.       |
| FORWARD           | Previous schema can read data by new version.    |
|                   | Deploy producers first, then consumers.          |
| FORWARD_TRANSITIVE| Any previous schema can read new version's data. |
| FULL              | BACKWARD + FORWARD for last version only.        |
| FULL_TRANSITIVE   | BACKWARD_TRANSITIVE + FORWARD_TRANSITIVE.        |
|                   | Safest. Recommended for shared production topics.|
+-------------------+--------------------------------------------------+
```

**Why TRANSITIVE matters — a concrete scenario:**

Suppose you use FULL (non-transitive). You have schema versions 1, 2, 3, 4, 5. FULL mode checks: "Is version 5 compatible with version 4?" Yes. Great.

But a consumer that was last deployed 3 months ago is still running version 2. It now receives a message encoded with version 5's schema. FULL (non-transitive) never checked "Is v5 compatible with v2?" — only v4 vs v5. The consumer breaks.

FULL_TRANSITIVE checks every pair: v5 vs v4, v5 vs v3, v5 vs v2, v5 vs v1. All must pass. Only then is the schema accepted. The consumer on v2 is safe.

---

### How It Works in Kafka — End to End

Every Avro or Protobuf message on a Kafka topic with Schema Registry uses a specific wire format:

```
Wire format (Confluent encoding):

Byte offset:  0        1        2        3        4       5...
              +--------+--------+--------+--------+--------+------------------+
              | 0x00   |     schema_id (4 bytes, big-endian)     | payload...  |
              +--------+--------+--------+--------+--------+------------------+
               magic    <------------ 32-bit int ----------->   Avro/Protobuf
               byte                                              encoded bytes
```

- **Magic byte 0x00**: signals "this is a Confluent Schema Registry encoded message" (not raw Avro, not raw JSON)
- **Schema ID**: 4-byte integer pointing to the schema version in the registry
- **Payload**: the actual Avro/Protobuf encoded bytes (without any schema embedded)

**Producer flow:**

```
Producer (schema registered at startup):

  1. Define/load schema (e.g., User.avsc)
  2. POST /subjects/users-value/versions  →  Schema Registry
       [compatibility check runs]
       <-  200 OK, schema_id = 42
  3. For each message:
       - Encode payload using schema
       - Prepend [0x00][00 00 00 2A]  (magic + schema_id=42)
       - Publish to Kafka topic
```

**Consumer flow:**

```
Consumer:

  1. Poll message from Kafka
  2. Read first byte: 0x00 (magic byte confirmed)
  3. Read next 4 bytes: schema_id = 42
  4. Check local cache: do I have schema 42?
       YES -> use cached schema  (0ms extra latency)
       NO  -> GET /schemas/ids/42 from Schema Registry  (~5-10ms)
              Cache result locally
  5. Deserialize payload using fetched schema + reader schema
  6. Apply reader schema resolution (fill defaults, ignore unknown fields)
  7. Deliver deserialized object to application code
```

**Full architecture diagram:**

```
                     SCHEMA REGISTRY
                    +---------------+
                    |  schemas DB   |
                    |  (Kafka topic |
                    |  _schemas)    |
                    +-------+-------+
                            |
              +-------------+-------------+
              |                           |
              v                           v
         [register]                  [fetch by ID]
              |                           |
+-------------+-----+           +---------+----------+
|     PRODUCER      |           |      CONSUMER      |
|                   |           |                    |
| 1. Load schema    |           | 1. Read msg        |
| 2. Register ->    |           | 2. Extract ID      |
|    get ID=42      |           | 3. Fetch schema 42 |
| 3. Encode payload |  Kafka    | 4. Deserialize     |
| 4. Prepend header +---------> |                    |
|    [0x00][42]     |  topic    |                    |
+-------------------+           +--------------------+
```

---

### Caching and Availability

The Schema Registry is a critical piece of infrastructure. Its availability directly affects your producer and consumer availability.

**Consumer caching:**

```
Consumer Local Cache:
  schema_id=42 -> UserSchema_v3    (TTL: 5 minutes, or indefinite)
  schema_id=41 -> UserSchema_v2
  schema_id=38 -> OrderSchema_v1

On message arrival:
  schema_id=42 -> cache HIT  -> 0ms extra latency
  schema_id=43 -> cache MISS -> HTTP GET to registry (~5-10ms) -> cache it
```

Consumers typically cache indefinitely (schemas are immutable once registered — a given ID never changes). The `5-minute TTL` is sometimes used for safety, but most implementations keep schemas in memory for the process lifetime.

**Producer caching:**

Producers should register schemas at startup, not per-message. The startup flow:

```
Startup:
  POST /subjects/users-value/versions with schema
  GET  /subjects/users-value/versions/latest (verify)
  Cache: schema_id = 42

Per message:
  Use cached schema_id = 42 (no network call)
```

**What happens when the registry goes down:**

```
Registry DOWN scenario:

  Existing consumers with cached schemas:
    - cache HIT for all known IDs -> still work fine
    - Will process messages for hours/days from cache

  Existing consumers seeing a NEW schema ID (never cached):
    - cache MISS -> HTTP GET fails -> deserialization error
    - Message dropped or sent to dead-letter queue

  Producers with a NEW schema (not yet registered):
    - POST /subjects fails -> cannot get schema_id
    - Cannot encode messages -> producer STOPS sending
    - This is a hard failure — new schema types cannot flow
```

**HA setup for registry:**

```
                +--------+   +--------+   +--------+
                | Reg-1  |   | Reg-2  |   | Reg-3  |
                +--------+   +--------+   +--------+
                     |            |            |
                     +-----+------+-----+------+
                           |                   
                     Load Balancer              
                           |                   
                +----------+----------+        
                |  Kafka topic:       |        
                |  _schemas           |        
                |  (source of truth)  |        
                +---------------------+        

All 3 registry instances read/write to _schemas Kafka topic.
State is shared. Any instance can serve any request.
If one instance fails, load balancer routes to the other two.
```

---

### Schema Subjects and Naming Conventions

A **subject** in Schema Registry is the namespace under which schema versions are tracked. Each subject has its own version history and compatibility setting.

**Default naming (TopicNameStrategy):**

```
Kafka topic: "user-events"
  Value schema subject: "user-events-value"
  Key schema subject:   "user-events-key"
```

When you register `UserEvent` schema for the `user-events` topic, it goes under the subject `user-events-value`. Version 1 is the first registered, version 2 is the next, etc.

**Advanced: TopicRecordNameStrategy**

What if you want to put MULTIPLE different event types on one Kafka topic (a common pattern for "event log" topics)?

```
Topic: "customer-events"
  Subject: "customer-events-CustomerCreated"
  Subject: "customer-events-CustomerDeleted"
  Subject: "customer-events-CustomerUpdated"
```

Each event type has its own schema evolution history. A change to `CustomerCreated` does not affect `CustomerDeleted`. You can have different compatibility rules per subject.

**RecordNameStrategy** (least common):

```
Subject is just the record name, regardless of topic:
  Subject: "com.example.CustomerCreated"
```

Allows the same schema to be used across multiple topics with one registration. Useful for shared event types in a domain model.

---

## 5. gRPC — Deep Dive

### Why gRPC Matters for Encoding Decisions

**gRPC** is a Remote Procedure Call framework built on top of HTTP/2, using Protobuf for serialization, with code generation. When you choose gRPC, you are choosing Protobuf encoding + HTTP/2 transport + streaming capabilities + generated client/server stubs.

The alternative (REST + JSON) gives you human-readable payloads and universal tooling but costs you: larger payload sizes, no code generation, no streaming, HTTP/1.1 limitations.

Understanding gRPC requires understanding HTTP/2 first.

---

### HTTP/1.1 vs HTTP/2: The Transport Layer

**HTTP/1.1 problems:**

```
HTTP/1.1 with 3 requests, 1 connection:

Client                    Server
  |--- Request 1 -------->|
  |<-- Response 1 --------|
  |--- Request 2 -------->|   (must wait for response 1)
  |<-- Response 2 --------|
  |--- Request 3 -------->|   (must wait for response 2)
  |<-- Response 3 --------|

Problem: head-of-line blocking. One slow response blocks the queue.
Workaround: open 6 parallel connections per domain (browsers do this).
Cost: connection overhead x6, no single-connection benefits.
```

**HTTP/2 with multiplexing:**

```
HTTP/2 with 3 requests, 1 connection (3 streams):

Client                              Server
  |--- Stream 1: Request 1 -------->|
  |--- Stream 2: Request 2 -------->|   (no waiting!)
  |--- Stream 3: Request 3 -------->|
  |<-- Stream 2: Response 2 --------|   (out-of-order fine)
  |<-- Stream 1: Response 1 --------|
  |<-- Stream 3: Response 3 --------|

All 3 RPCs in flight simultaneously on one TCP connection.
No head-of-line blocking at the HTTP layer.
(Note: TCP-level HOL blocking still exists, solved by QUIC/HTTP3)
```

**HTTP/2 advantages relevant to gRPC:**

- **Multiplexing:** 100 RPCs on 1 connection, no connection pool exhaustion
- **Binary framing:** no text parsing overhead, smaller frame headers
- **HPACK header compression:** repeated headers (Authorization token, Content-Type: application/grpc) compressed across requests — can reduce header overhead by 80%+
- **Bidirectional streaming:** both client and server can send streams of messages on one connection at the same time

---

### The L7 Load Balancing Problem — The #1 gRPC Gotcha

HTTP/2 uses ONE long-lived TCP connection from client to server. This creates a fundamental load balancing problem.

**L4 load balancer (traditional TCP balancer):**

```
L4 Load Balancer distributes TCP CONNECTIONS:

Client A ---TCP conn---> L4 LB ---TCP conn---> Backend-1
Client B ---TCP conn---> L4 LB ---TCP conn---> Backend-2
Client C ---TCP conn---> L4 LB ---TCP conn---> Backend-1

With HTTP/1.1: each request was a new or pooled connection ->
  L4 LB saw many connections -> distributed load reasonably well.

With HTTP/2: client makes ONE connection, sends 1000 RPCs on it.
  L4 LB sees: Client A -> one connection -> Backend-1.
  Backend-1 gets ALL 1000 RPCs from Client A.
  Backend-2 gets 0 RPCs from Client A.
```

**The real problem — uneven distribution:**

```
10 client pods × 1 gRPC connection each = 10 connections total
L4 LB assigns connections at time-of-connect:
  Backend-1: 4 client connections -> 4000 RPCs/sec
  Backend-2: 4 client connections -> 4000 RPCs/sec
  Backend-3: 2 client connections -> 2000 RPCs/sec

If backends auto-scaled up to 6:
  Backend-4: 0 connections -> 0 RPCs/sec  (completely idle!)
  Backend-5: 0 connections -> 0 RPCs/sec
  Backend-6: 0 connections -> 0 RPCs/sec
```

**Fix: L7 load balancer (Envoy, Traefik, Istio sidecar):**

An L7 load balancer understands HTTP/2 framing. It distributes individual **HTTP/2 streams** (i.e., individual RPCs), not TCP connections.

```
L7 (Envoy) Load Balancing distributes HTTP/2 STREAMS (individual RPCs):

Client A ----HTTP/2 conn----> Envoy ----RPC 1---> Backend-1
                                    ----RPC 2---> Backend-2
                                    ----RPC 3---> Backend-3
                                    ----RPC 4---> Backend-1  (round-robin)
                                    ----RPC 5---> Backend-2
                                    ...

Client A has ONE connection (to Envoy).
Envoy multiplexes across ALL backends.
Each RPC goes to a different backend.
Load is distributed evenly even with 1 client connection.
```

```
Architecture with Envoy:

  [Client Service]
       |
       | 1 HTTP/2 connection
       v
  [Envoy Sidecar / Ingress]
       |           |           |
       v           v           v
  [Backend-1] [Backend-2] [Backend-3]   <- per-RPC load balancing
```

**Important:** If you are using gRPC without a service mesh or L7 LB, you WILL have load imbalance problems at scale. This is not a theoretical concern — it is observed in practice whenever you scale gRPC backends.

---

### Streaming Patterns With Use Cases

gRPC defines four streaming modes in the `.proto` service definition:

```protobuf
service DataService {
  // 1. Unary: one request, one response
  rpc GetUser (GetUserRequest) returns (User);

  // 2. Server streaming: one request, many responses
  rpc WatchMarketPrice (WatchRequest) returns (stream PriceUpdate);

  // 3. Client streaming: many requests, one response
  rpc UploadChunks (stream FileChunk) returns (UploadSummary);

  // 4. Bidirectional streaming: both sides stream simultaneously
  rpc SyncEdits (stream EditEvent) returns (stream EditEvent);
}
```

**Unary RPC** — standard request/response:
- Use case: user lookup by ID, creating a resource, any CRUD operation
- Behavior: client sends one message, waits, server replies with one message, stream closes
- Same semantics as an HTTP REST call

**Server streaming** — one request, many responses:
- Use case: live stock prices, event subscriptions, progress updates for a long job, paginated result sets
- Behavior: client sends request and waits; server pushes responses as they are ready; server closes when done
- Client iterates: `for update := range stream { ... }`

**Client streaming** — many requests, one response:
- Use case: uploading a large file in chunks, batch insert of events, sending a long audio recording for transcription
- Behavior: client sends many messages; server accumulates; when client closes the stream, server sends one response
- Server iterates: `for { chunk, err := stream.Recv(); if err == io.EOF { break } }`

**Bidirectional streaming** — both sides stream simultaneously:
- Use case: chat application, collaborative document editing sync, multiplayer game state, two-way data pipeline
- Behavior: both sides can send and receive independently; neither side waits for the other to finish
- Fully asynchronous: server can respond to message 3 before client has sent message 5

---

### gRPC Status Codes vs HTTP Status Codes

gRPC defines its own status code system, independent of HTTP status codes. At API gateways, you must translate.

```
gRPC Status Code   HTTP Equivalent   When to Use
----------------   ---------------   ------------------------------------------
OK                 200               Success
CANCELLED          499               Client cancelled the request
UNKNOWN            500               Unknown error (catch-all)
INVALID_ARGUMENT   400               Bad request parameters (wrong type, missing)
DEADLINE_EXCEEDED  504               Timeout — caller's deadline passed
NOT_FOUND          404               Resource not found
ALREADY_EXISTS     409               Resource already exists (conflict)
PERMISSION_DENIED  403               Caller lacks permission
UNAUTHENTICATED    401               No valid credentials
RESOURCE_EXHAUSTED 429               Rate limit exceeded, quota exhausted
FAILED_PRECONDITION 400             System not in required state
ABORTED            409               Concurrency conflict (optimistic lock fail)
OUT_OF_RANGE       400               Value out of valid range
UNIMPLEMENTED      501               RPC not implemented on server
INTERNAL           500               Internal server error
UNAVAILABLE        503               Server temporarily unavailable (retry safe)
DATA_LOSS          500               Unrecoverable data loss or corruption
```

**Deadline propagation — why it matters:**

gRPC passes deadlines through the entire call chain automatically. When service A calls service B with a 500ms deadline, and B calls C with a derived deadline, C knows it only has time left from A's original budget.

```
User request arrives at A: deadline = now + 500ms

A calls B: gRPC automatically sets B's deadline = same absolute time
B calls C: C's deadline = same absolute time

If A's deadline is 500ms from now, and B takes 200ms:
  C only has 300ms remaining. C knows this. C can fail fast
  instead of doing a 400ms database query that will be cancelled anyway.

Without deadline propagation:
  C starts a 400ms query -> completes -> sends response back
  B forwards to A -> A has already timed out -> response dropped
  C's 400ms of work was wasted, database load was wasted
```

Always propagate context (which carries the deadline) through all downstream gRPC calls. In Go: `ctx` must be passed to every gRPC call. In Java: the gRPC interceptor handles it automatically.

---

## 6. Migration Patterns

### Expand-Contract: The Zero-Downtime Schema Change

**Expand-Contract** (also called Parallel Change) is the standard pattern for making what would be a breaking change into a safe, gradual migration.

**Full worked example: rename "email" to "contact_email" in a Protobuf message**

The naive approach (rename field) is a breaking change — field names exist in JSON interop and code, and if you also change the field number, it breaks wire encoding.

The safe approach has three phases:

---

**Phase 1 — EXPAND: Add the new field, keep the old one, write both**

```protobuf
// Schema version during Expand phase
message User {
  int64  user_id       = 1;
  string email         = 3;           // OLD field — still written by producer
  string contact_email = 5;           // NEW field — also written by producer

  // Producer writes BOTH fields with the same value:
  //   email = "alice@example.com"
  //   contact_email = "alice@example.com"
}
```

Producer behavior during expand:
```python
def encode_user(user):
    return User(
        user_id       = user.id,
        email         = user.email,        # old field
        contact_email = user.email,        # new field (same value)
    )
```

During this phase, all existing consumers see `email` as before — nothing breaks. New consumers can start reading `contact_email`.

---

**Phase 2 — MIGRATE: Switch consumers to new field over weeks**

```
                   Time
Week 1: producer writes both fields
        consumer team A migrates to contact_email   [A done]
Week 2: consumer team B migrates                   [A,B done]
Week 3: consumer team C migrates                   [A,B,C done]
Week 4: all consumers verified, monitoring shows
        no reads on old "email" field

Migration monitoring metric:
  email_field_reads_total{service="order-svc"}    -> trending toward 0
  contact_email_field_reads_total{service="order-svc"} -> increasing
```

You add a metric on the consumer side to track which field is being read. When `email_field_reads_total` across all services is zero, you know migration is complete.

Send a runbook to all teams: "The `email` field in `User` message will be removed after 2026-09-01. Please migrate to `contact_email`. Monitoring dashboard: [link]."

---

**Phase 3 — CONTRACT: Stop writing old field, reserve the number**

```protobuf
// Schema version after migration complete
message User {
  reserved 3;        // was: email — field number retired
  reserved "email";  // field name retired

  int64  user_id       = 1;
  string contact_email = 5;  // NEW canonical field
}
```

Producer stops writing field 3. All consumers read field 5. Old field number 3 is reserved to prevent accidental reuse.

**Timeline visualization:**

```
Phase:        |--- EXPAND ---|--- MIGRATE ---|--- CONTRACT ---|
              Week 1         Weeks 2-4       Week 5+

Producer:     write email    write email     stop email
              write          write           write
              contact_email  contact_email   contact_email

Consumer A:   read email     READ            read contact_email
                             CONTACT_EMAIL
Consumer B:   read email     read email      READ CONTACT_EMAIL
Consumer C:   read email     read email      READ CONTACT_EMAIL
              (migrates in week 3)
```

The key insight: at no point is there a moment where producers and consumers must simultaneously switch. Each team migrates independently. Old and new coexist.

---

### Dual-Write Pattern: For Storage Schema Changes

When the schema change is in a database (not a message format), you cannot use Avro/Protobuf compatibility rules. Instead, use dual-write:

**Scenario:** migrating from a `users` table with a single `address` column to a new `user_addresses` table.

```
Phase 1 — DUAL WRITE:
  Application writes to BOTH old table (address column)
  AND new table (user_addresses).
  Application READS from old table (source of truth).

Phase 2 — SHADOW READ:
  Application reads from old table (production data).
  Application ALSO reads from new table (shadow).
  Compare results. Log discrepancies.
  When discrepancy rate < 0.01%: proceed.

Phase 3 — FLIP READ:
  Application reads from new table (source of truth).
  Application still writes to old table (rollback safety net).
  Monitor for errors.

Phase 4 — DECOMMISSION:
  Stop writing to old table.
  Drop old column after X days of clean operation.
```

**The dual-write atomicity problem:**

```
Write 1: INSERT into old table   -> SUCCESS
Write 2: INSERT into new table   -> NETWORK TIMEOUT

Result: old table has new row, new table does not.
        Tables are now DIVERGED.
```

Fix: Use the **outbox pattern**:
1. Write ONLY to the primary store (old table), in the same transaction, also write to an `outbox` table
2. A CDC (Change Data Capture) process reads the outbox and propagates to the new table
3. If the CDC fails, it retries — eventual consistency, but no silent data loss

---

### API Versioning for Breaking Changes

When Expand-Contract is not enough (true breaking change in a public API), you need explicit versioning.

**URL versioning (most common):**

```
GET /v1/users/42       <- old behavior
GET /v2/users/42       <- new behavior (breaking schema change)
```

Pros: explicit, easy to route, easy to test, browsers/curl can distinguish  
Cons: URL proliferation, old versions accumulate forever unless actively removed

**Header versioning:**

```
GET /users/42
Accept: application/vnd.mycompany.v2+json

Response:
Content-Type: application/vnd.mycompany.v2+json
{body in v2 format}
```

Pros: clean URLs, version is metadata  
Cons: harder to test with browsers, clients must remember to set header

**Deprecation headers (tell clients their version is dying):**

```
HTTP/1.1 200 OK
Content-Type: application/json
Deprecation: true
Sunset: Sat, 01 Sep 2026 00:00:00 GMT
Link: <https://api.example.com/v2/users/42>; rel="successor-version"

{v1 response body}
```

Clients that parse these headers can log warnings, alert their teams, or automatically redirect.

**Deprecation timeline:**

```
T+0:   /v2/users launches. /v1/users still works.
       Announce deprecation: email, docs, Sunset header.

T+90d: Begin enforcement. /v1/users returns 400 for new apps
       (based on client ID). Existing apps still work.

T+180d: /v1/users returns 410 Gone for all callers.
        Any caller still using v1: incident, urgent migration needed.

T+270d: /v1 code removed from service. Endpoint gone.
```

The **410 Gone** (not 404 Not Found) signals "this intentionally no longer exists — stop trying."

---

## 7. Cross-Team Schema Governance

### The Schema as a Shared Contract

When 50 teams share an event schema, the schema is no longer just a technical artifact — it is a **contract** between teams. One team's well-intentioned refactoring can break 49 other teams' services, potentially generating incidents across the entire company.

Without governance:
- Team A renames a field on a Friday afternoon
- 30 consumers fail Monday morning
- Post-mortem: "schema change not communicated"
- Result: blame, incidents, distrust

With governance:
- Schema changes go through a PR review process
- Compatibility is checked automatically in CI
- Breaking changes require an RFC (Request for Comments) and a migration window
- Schema owners are notified of downstream consumers

---

### Central Schema Repository Pattern

```
Monorepo or dedicated schema repo:
  schemas/
    events/
      user-events/
        UserCreated.avsc
        UserDeleted.avsc
      order-events/
        OrderPlaced.proto
        OrderShipped.proto
    contracts/
      user-service/
        UserAPI.proto    <- gRPC service definition

CI pipeline on every PR:
  1. buf lint              <- check style, naming conventions
  2. buf breaking          <- check compatibility against main branch
  3. Schema Registry API   <- check compatibility against registry
  4. Notify schema owners  <- PR mention/slack alert
  5. Auto-generate clients <- publish generated code packages
```

**buf lint** enforces style rules:
- Field names are snake_case
- Enum values are UPPER_SNAKE_CASE
- Messages use PascalCase
- All fields have comments
- No reserved field numbers being reused

**buf breaking** detects breaking changes:

```
$ buf breaking --against .git#branch=main

schemas/events/user-events/UserCreated.proto:
  Field "email" with number 3 changed type from "string" to "int64".
  Previously existing field "name" with number 2 deleted without reservation.

ERROR: 2 breaking changes detected.
```

CI fails. PR cannot merge. Schema author must fix before the change lands.

---

### The Ownership Model

```
Schema ownership hierarchy:

  Producer Team (OWNER):
    - Owns the .proto / .avsc file
    - Has final say on schema decisions
    - Responsible for maintaining backward compat
    - Must review and approve all consumer-requested changes

  Consumer Teams (CONTRIBUTORS):
    - Can open PRs requesting NEW optional fields
    - Cannot remove fields (only owner can, after migration)
    - Cannot change existing field types or numbers
    - Should comment on deprecation PRs with migration timeline

  Platform/Infrastructure Team (GOVERNANCE):
    - Sets compatibility mode in Schema Registry (usually FULL_TRANSITIVE)
    - Approves compatibility mode exceptions
    - Runs the buf CI pipeline
    - Resolves disputes between producer and consumer teams
```

**RFC process for breaking changes:**

When a breaking change is genuinely necessary (not avoidable with Expand-Contract), the team must:

1. Write an RFC document explaining: why the change is needed, what is breaking, proposed migration path, timeline
2. Share RFC with all known consumer teams (derived from Schema Registry consumer group tracking)
3. Wait for RFC review period (2 weeks minimum)
4. Receive sign-off from consumer teams
5. Implement with 3-month dual support window (both v1 and v2 schemas active)
6. Execute migration with clear milestones

This process feels slow. It is intentional. Breaking schema changes in distributed systems have O(number of consumers) blast radius. The friction of the RFC process exists to make the team genuinely consider whether the breaking change is necessary.

---

### Schema Versioning in CI — The Full Pipeline

```
Developer workflow:

  git checkout -b add-loyalty-tier
  # Edit UserCreated.avsc: add loyalty_tier field with default "STANDARD"
  git commit
  git push
  # Open PR

CI pipeline (automated):

  Step 1: buf lint
          -> PASS (field name, casing conventions OK)

  Step 2: buf breaking --against .git#branch=main
          -> PASS (new field with default is backward compatible)

  Step 3: Schema Registry compatibility check
          curl -X POST https://registry/compatibility/subjects/user-events-value/versions/latest \
               -d '{"schema": "<new schema JSON>"}'
          -> {"is_compatible": true}
          -> PASS

  Step 4: Auto-generate clients
          -> Generate Java, Python, Go packages from .avsc
          -> Publish to internal artifact registry (e.g., Artifactory)
          -> Post comment on PR: "Generated clients published at v2.3.1"

  Step 5: Notify downstream teams
          -> Post Slack message in #schema-changes: "UserCreated v2.3 adds loyalty_tier"
          -> Auto-assign schema owner as required reviewer

  Step 6: Merge (after owner approval + CI pass)
          -> Schema auto-registered to Schema Registry on merge
          -> Producer team picks up new generated client version
```

---

## 8. Real Incident: Avro Schema Without Default Blocks 200 Services

### The Setup

Company X runs a large e-commerce platform. The Loyalty team wants to add a `loyalty_tier` field to the shared `CustomerEvent` Avro schema. This schema is consumed by 200 downstream services — analytics, personalization, email marketing, fraud detection, recommendations.

The Loyalty team is experienced engineers but relatively new to Avro. They write the new field:

```json
{
  "type": "record",
  "name": "CustomerEvent",
  "namespace": "com.example.events",
  "fields": [
    {"name": "customer_id",  "type": "long"},
    {"name": "event_type",   "type": "string"},
    {"name": "timestamp_ms", "type": "long"},
    {"name": "loyalty_tier", "type": "string"}
  ]
}
```

Notice: `loyalty_tier` has **no default value**.

### What Happened

The Schema Registry is configured in BACKWARD mode (new schema must be readable by old consumers).

Compatibility check logic:
- New schema adds `loyalty_tier`
- Old consumers don't have `loyalty_tier` in their reader schema
- Old consumer sees a writer schema WITH `loyalty_tier`
- In Avro: if writer has a field, reader must either have that field (matched by name) or have a default for it in their reader schema
- Old consumer reader schema has no `loyalty_tier` and no default in its own schema
- Result: old consumers CANNOT deserialize messages written with the new schema

Wait — actually the check works in reverse: new schema reading old data.

In BACKWARD mode: "Can the NEW schema (with loyalty_tier, no default) read OLD messages (without loyalty_tier)?"

Old messages don't have `loyalty_tier`. New reader schema requires it (no default). **AvroTypeException.** Schema Registry rejects the registration.

```
Producer attempts to start:
  POST /subjects/customer-events-value/versions
  -> 409 Conflict
  -> {"error_code": 409, "message": "Schema being registered is incompatible with an earlier schema"}

Producer startup fails.
Producer pod: CrashLoopBackOff.

Downstream effect:
  - CustomerEvent topic stops receiving new events
  - 200 consumer services: no new events arriving
  - Analytics: stale dashboards
  - Email marketing: no welcome emails for new signups
  - Personalization: degraded recommendations
  - Fraud detection: missing real-time signals
  - Business impact: measurable drop in conversion for 4 hours
```

### Root Cause Analysis

The Loyalty team understood WHAT to add but not WHY Avro requires defaults. The reasoning:

In BACKWARD compatibility: the new schema must be able to read OLD data. Old messages don't have `loyalty_tier`. Without a default, the new schema cannot deserialize old messages. The registry rejects it.

```
The mental model they had:
  "loyalty_tier is a new field, consumers don't have it yet,
   so it doesn't affect them."

The correct mental model:
  "loyalty_tier is new. Old MESSAGES don't have it.
   My new schema must be able to read those old messages.
   Without a default, I can't fill in loyalty_tier when reading old data.
   The registry catches this before I can deploy."
```

### The Fix

1. Add `"default": "STANDARD"` to the `loyalty_tier` field:

```json
{
  "name": "loyalty_tier",
  "type": "string",
  "default": "STANDARD"
}
```

2. Re-register the schema:

```
POST /subjects/customer-events-value/versions
-> 200 OK
-> {"id": 47}
```

3. Producer starts successfully. Events flow.

4. Old consumers receive events with `loyalty_tier`:
   - Old consumers whose reader schema doesn't have `loyalty_tier`: Avro discards the field (forward compat — reader ignores unknown writer fields) — works fine
   - After teams update their reader schemas: `loyalty_tier = "GOLD"` / `"STANDARD"` / `"PLATINUM"` correctly resolved

5. Events that arrived BEFORE the fix: retroactively processed by replay consumer (Kafka allows re-reading from offset 0 on the topic).

Total downtime: 4 hours. With proper CI checks, this would have been caught before merge with a 2-second error message.

### Prevention

**Immediate (process):**
- PR template checklist for schema changes:
  ```
  Schema Change Checklist:
  [ ] All new fields have "default" values
  [ ] Removed fields have defaults or are handled in reader schemas
  [ ] buf lint passes locally before pushing
  [ ] Schema Registry compatibility check passes locally
  [ ] Downstream consumer teams notified (Slack + PR mention)
  ```

**Medium-term (tooling):**
- Add Avro schema linting to CI that specifically checks: "every field in this schema has a default value"
- Schema Registry compatibility check runs on every PR (not just at producer deploy time)
- Custom lint rule in buf: "avro fields must have defaults"

**Long-term (culture):**
- Internal workshop: "Avro Schema Evolution for Engineers" — 30-minute session covering writer/reader schemas, resolution rules, default requirements
- On-call runbook updated: "If a producer is in CrashLoopBackOff with Schema Registry 409 errors, check for missing defaults on new fields"
- Architecture Review Board adds schema evolution review to all new service design documents

The most important prevention: move the check LEFT (earlier in the development cycle). Catching it in a 2-second CI failure saves 4 hours of production incident.

---

## Summary Table: Which Format, Which Rules

```
+-------------------+------------------+---------------------------+
| Concern           | Protobuf         | Avro                      |
+-------------------+------------------+---------------------------+
| Field identity    | Field NUMBER     | Field NAME                |
| Add field safely  | Any number,      | Must have default value   |
|                   | no default needed|                           |
| Remove field      | reserved + mark  | Ensure forward compat     |
|                   | deprecated       | with defaults             |
| Rename field      | DON'T (break)    | Use aliases in reader     |
| Type promotion    | Same wire type   | Avro spec promotions only |
| Schema matching   | Tag-based        | Name-based resolution     |
| Registry format   | Protobuf binary  | [0x00][schema_id][payload]|
| Unknown fields    | Preserved        | Discarded                 |
| Null fields       | Zero value       | Union ["null", "string"]  |
+-------------------+------------------+---------------------------+
```

---

Schema evolution is not a feature. It is an ongoing discipline. Every field you add, every field you remove, every rename — these are decisions with consequences measured in hours of incident time and in the trust between teams. The rules in this chapter exist because real systems have failed in exactly these ways. Follow them, automate the checks, and make the constraints visible in code review before they become visible in production metrics.
# Chapter 30: Data Encoding and Schema Evolution — Part C

## Production Incidents, L5 vs L6 Calibration, Brainstorming Questions, Homework, and Quick Reference

---

## Production Incidents

These five incidents are drawn from real production patterns. Each one exposes a failure mode that is easy to miss during design but painful to discover at runtime. Read each as a case study: understand not just what broke, but why the system allowed it to break, and what structural change actually fixed it.

---

### Incident 1: Protobuf Field Number Reuse — Silent Data Corruption

**Trigger**

A team cleaned up a .proto file during a quarterly maintenance sprint. Field 5 had been `address` (type `string`). It had been unused for four months. The engineer deleted it and added a new field 5: `phone_number` (type `int64`). The .proto file compiled cleanly. Unit tests passed. Code review approved the cleanup. The change shipped.

**Impact**

Any consumer that had not yet deployed the updated .proto file continued reading field 5 as a `string`. In Protobuf wire format, `string` has wire type 2 (length-delimited). `int64` has wire type 0 (varint). When an old consumer received a message where field 5 carried an `int64` value, it tried to parse those bytes as a length-delimited string. For some integer values, the varint encoding produced bytes that looked like a short string — garbage characters. For others, the computed string length exceeded the remaining bytes in the message, and the parser threw a decode error, causing the consumer to drop the entire record silently. Corrupted data was stored in the user profile database for six hours before detection.

**Discovery**

An anomaly detection alert fired on the `address` field in the user profile service. The field population rate fell from 99.2% to 31% and the average byte length jumped from 24 bytes to 3 bytes — statistically impossible for real addresses. The on-call engineer traced the anomaly to the .proto change within 20 minutes.

**Root Cause**

Field numbers in Protobuf are permanent wire identifiers. They determine how bytes are read on the wire. Reusing a field number with a different type means any decoder still on the old schema silently misinterprets the new bytes — no checksum, no version header, no error in most cases. The team treated field numbers like variable names: reusable once the old one is gone. They are not.

**Fix**

The field was reassigned to a new number (field 12). Field 5 was marked `reserved` in both its numeric and name forms:

```protobuf
message UserProfile {
  reserved 5;
  reserved "address";
  string phone_number = 12;
}
```

The `reserved` keyword causes the Protobuf compiler to emit an error if anyone later tries to assign field number 5 or the name `address` to a new field in this message type.

**Prevention**

`buf breaking` was integrated into CI — it rejects any change that reuses a field number, removes a non-reserved field, or changes a field type. All .proto changes now require review from an engineer familiar with wire format semantics.

---

### Incident 2: JSON Number Precision — Wrong Order IDs in Frontend

**Trigger**

The order service generated order IDs as `int64`. The largest ID in production was `9,007,199,254,743,001`, which exceeds `2^53` — the threshold above which IEEE 754 double-precision floating point cannot represent every integer exactly. The JSON API returned IDs as bare numbers:

```json
{"order_id": 9007199254743001}
```

**Impact**

JavaScript parses all JSON numbers as `Number` (IEEE 754 double). `Number(9007199254743001)` evaluates to `9007199254743000` — the last digit is silently rounded. No exception is thrown. About 0.01% of orders had IDs in the affected range. Users in that set saw the wrong order details page. Some attempted to cancel or reorder using the corrupted ID, which returned "order not found." The issue was live for two weeks before a customer support ticket identified the pattern.

**Discovery**

A support ticket noted that a user's confirmation email linked to a different order. The support engineer saw the IDs differed by exactly 1. A frontend engineer recognized the `2^53` precision loss immediately.

**Root Cause**

IEEE 754 double-precision floating point has a 53-bit significand. Integers above `9,007,199,254,740,991` cannot all be represented — they round to the nearest representable value. JSON has no separate integer type. Browsers and JavaScript engines follow IEEE 754. This constraint is silent — no error, no warning, just a slightly wrong number.

**Fix**

The API was updated to return `order_id` as a JSON string:

```json
{"order_id": "9007199254743001"}
```

The JavaScript client was updated to parse it as `BigInt` where arithmetic was needed and to use string equality for comparisons.

**Prevention**

The OpenAPI spec was updated to declare all `int64` fields as `type: string, format: int64`. A linter check was added to CI that flags any `int64` field annotated as `type: integer` in the OpenAPI spec. The API design guide was updated with a dedicated section on large integer handling.

---

### Incident 3: Schema Registry Single Point of Failure

**Trigger**

The Schema Registry was deployed as a single instance with no HA configuration. During a routine version upgrade, the instance restarted. JVM startup plus schema topic replay took eight minutes.

**Impact**

During those eight minutes, 47 producer services that were in the middle of rolling deployments failed to start. Each new producer instance calls the Schema Registry on startup to register or verify its schema. With the registry unreachable, the registration call timed out, the startup health check failed, and Kubernetes killed the pod before it entered a ready state. Existing producer instances — already running with cached schemas — were unaffected. No messages were lost. But 47 deployment pipelines were stuck. The queue of stalled deployments took 40 minutes to drain after the registry recovered.

**Discovery**

All 47 deployment pipeline alerts fired within a 90-second window. The common failing step was the schema registration call. The on-call engineer confirmed registry unavailability in under two minutes.

**Root Cause**

The team did not classify the Schema Registry as critical infrastructure. The assumption was that because the registry is only called at startup or schema change time — not on every message — its availability was less important than Kafka's. This assumption fails in a microservices environment with continuous deployment: at scale, new instances are starting constantly across the fleet, and the registry is being called every few minutes.

**Fix**

The Schema Registry was redeployed as a three-instance cluster behind an internal load balancer. The `_schemas` Kafka topic was moved to a dedicated internal Kafka cluster with replication factor 3. Producer startup logic was updated to distinguish "registry unreachable — retry with exponential backoff, do not abort" from "schema incompatible — abort immediately."

**Prevention**

Schema Registry was reclassified as Tier-1 infrastructure: 99.95% uptime SLA, on-call rotation, runbook, and change-freeze windows aligned with the Kafka cluster. It was added to the infrastructure health dashboard alongside Kafka and the service mesh.

---

### Incident 4: gRPC Behind an L4 Load Balancer — Nine of Ten Backends Idle

**Trigger**

A team migrated a high-traffic internal API from REST/JSON to gRPC/Protobuf for payload size reduction. They deployed the gRPC service behind the existing AWS load balancer, which was configured in TCP passthrough mode (L4) for this service — a detail no one checked during the migration.

**Impact**

Within 30 minutes of the rollout, p99 latency was ten times higher than the REST API had been. Monitoring showed 8 of 10 backend pods at 2% CPU and 2 pods at 98% CPU. The 2 overloaded pods were dropping requests due to thread pool exhaustion, causing timeouts. The service was measurably worse in every dimension than the REST API it replaced.

**Discovery**

The per-pod CPU imbalance was visible on the metrics dashboard within minutes of the rollout. The connection between L4 load balancing and HTTP/2 multiplexing was identified during root cause analysis.

**Root Cause**

HTTP/2 multiplexes all requests between a client and server over a single long-lived TCP connection. An L4 load balancer routes at the TCP connection level — it does not inspect what is happening inside the connection. Each of 100 client pods opened one TCP connection. The load balancer distributed those 100 connections across 10 backends. Some backends happened to receive connections from the highest-traffic clients. With HTTP/2, those connections stayed pinned indefinitely — the L4 balancer had no visibility into the per-stream activity and no mechanism to rebalance.

**Fix**

Envoy was deployed as an L7 sidecar proxy via Istio. Envoy understands HTTP/2 and distributes load at the gRPC stream level, not the TCP connection level. After the switch, CPU was evenly distributed across all 10 pods. p99 latency dropped to 40% below the original REST baseline.

**Prevention**

A mandatory item was added to the deployment checklist: any service using gRPC must verify that L7 load balancing is in place before production rollout. This check was also added as a static configuration lint in the platform team's service scaffolding templates.

---

### Incident 5: Avro Schema in Parquet Data Lake — Reader/Writer Schema Mismatch

**Trigger**

Events from a Kafka topic (Avro-serialized, schemas in Confluent Schema Registry) were written to S3 as Parquet via Kafka Connect. After six months, the schema was evolved: the field `legacy_code` (string, default `null`) was removed. The removal was Avro-backward-compatible. A new schema version was registered. The Kafka Connect pipeline began writing new Parquet files with the new schema.

**Impact**

Six months later, the analytics team ran a query spanning three years of historical data. The query failed with schema errors on all partitions older than six months. Two data science projects were blocked for four days while the incident was investigated and a workaround was built.

**Root Cause**

Parquet embeds the writer schema in the file footer. When reading, Parquet requires either an exact schema match or explicit schema projection. Unlike Avro's native reader — which performs schema resolution between writer and reader schemas — the Parquet reader does not perform Avro-style evolution. The Kafka Connect job had written Parquet files using whatever Avro schema was active at write time, with no metadata in the file or the S3 path that recorded the Avro schema ID. The analytics team had no mechanism to look up which schema version had written each partition.

**Fix**

A PySpark repair job re-read each historical partition using the correct Avro writer schema (looked up from the registry) and rewrote it in Parquet with a canonical unified schema, backfilling `legacy_code` as `null` for new records. Going forward, the Kafka Connect configuration was updated to embed the Avro schema ID in Parquet file-level metadata, and a custom reader wrapper was built that fetches the correct writer schema from the registry before opening any historical partition.

**Prevention**

Any schema change involving field removal now requires a data lake impact assessment: which partitions exist, what schema versions were used to write them, and whether historical reads will succeed with the proposed change. A CI job was added that tests reads against a sample of historical partitions for every schema change.

---

## L5 vs L6 Calibration

In a system design interview, the difference between an L5 and L6 answer is not primarily about knowing more facts. It is about depth of reasoning, anticipating failure modes, and demonstrating that your recommendations come with a rollout plan, monitoring strategy, and rollback option. The following table shows the same question answered at each level. Study the L6 answers for the pattern: they name the failure mode, explain the mechanism, and propose a measurable exit criterion.

---

**Dimension: Format selection**

- L5: "We use JSON everywhere, it's easy to debug."
- L6: "For internal services at >10K QPS, I'd measure serialization CPU overhead and wire size first. JSON makes sense for public APIs where external consumers need tooling. For internal high-QPS paths, Protobuf gives roughly 50% payload reduction and 3x encode/decode speedup. I'd also ask whether consumers span multiple languages — Protobuf's generated clients reduce integration cost across Go, Java, and Python services. Debugging use case is solved with structured logging, not by keeping the wire format human-readable."

---

**Dimension: Schema evolution**

- L5: "We'll version the endpoint when we need to change something."
- L6: "Endpoint versioning is a last resort — it forks the codebase and doubles maintenance burden. I'd use expand-contract: add the new field as optional with a default, deploy producers, migrate consumers to read it, instrument who is still reading the deprecated field, then remove it after a defined sunset window. For external consumers I'd give 6–12 months and surface deprecation warnings in response headers from day one."

---

**Dimension: Breaking change**

- L5: "We'd coordinate with all consumers over Slack and plan a cutover."
- L6: "Slack coordination doesn't scale past 5 teams and leaves no audit trail. For a breaking change: file an RFC, run old and new schemas in parallel via expand-contract, instrument which consumers are still on the deprecated field using metrics, set an automated sunset date that trips a CI gate blocking deployment of the deprecated field after the date passes. Require consumers to explicitly opt in to the new schema before the old one is removed."

---

**Dimension: Protobuf field removal**

- L5: "Delete it from the .proto file and redeploy."
- L6: "Never delete — deprecate. Annotate with `[deprecated = true]`, stop writing the field in producers, confirm via metrics that no consumer is reading it, then remove and mark the number as `reserved`. The reserved keyword prevents future reuse. `buf breaking` in CI enforces this automatically. The timeline depends on how fast consumers adopt new builds; instrument field read frequency to know when it is safe to proceed."

---

**Dimension: Avro new field**

- L5: "Just add it to the schema and register the new version."
- L6: "The new field must have a default value or it breaks backward compatibility — old consumers reading new messages have no value to populate a field that didn't exist in their schema. Verify the compatibility mode in the registry is BACKWARD or FULL before registering. If this schema is read in batch pipelines that process months-old data, also verify that all historical partitions will still be readable with the new reader schema. BACKWARD_TRANSITIVE is safer for this case than BACKWARD."

---

**Dimension: Schema Registry down**

- L5: "We restart it and wait for producers to come back up."
- L6: "Producers with cached schemas continue normally — they don't need the registry for every message. Producers attempting to register a new schema will fail. Design producers to retry registration with exponential backoff and not abort the deployment. For the registry itself: three-instance HA cluster behind a load balancer, `_schemas` topic with replication factor 3, treated as Tier-1 infrastructure. Cache schemas locally in the producer process so a registry restart does not affect in-flight message production."

---

**Dimension: gRPC performance**

- L5: "Switch from REST to gRPC, it's faster out of the box."
- L6: "gRPC is faster only if load balancing is correct. HTTP/2 multiplexes over a single TCP connection — an L4 load balancer sees one connection per client and cannot rebalance individual streams. You need L7 load balancing via Envoy or Istio. Also: gRPC does not work in browsers without gRPC-Web. Set deadlines on every RPC — unbounded gRPC calls are a reliability hazard. Performance gain over REST is real but only materializes after you have resolved the load balancing issue."

---

**Dimension: QPS threshold for binary**

- L5: "Switch when it feels slow."
- L6: "Benchmark serialization CPU at current QPS as a baseline. JSON serialization typically costs 5–15% of CPU in a hot service. At >10K QPS, measure the actual cost. At >100K QPS, binary encoding is almost always justified by both CPU savings and payload size reduction, which also lowers network egress cost. The exact crossover depends on message structure; run a benchmark with your actual schema before deciding."

---

**Dimension: Cross-team schema change**

- L5: "Ping them on Slack and get their sign-off."
- L6: "File a schema change PR in the shared schema repo, run `buf breaking` or Avro compatibility check as a CI merge gate, write an RFC for any breaking change, announce in a schema-changes mailing list, give a migration window with a specific end date, and track consumer migration on a dashboard. Breaking changes require explicit approval from all affected team leads, not just an acknowledgment on Slack."

---

**Dimension: Data lake encoding**

- L5: "Dump JSON from Kafka to S3, we can process it later."
- L6: "JSON in S3 is expensive to query at scale — Athena scans every byte of every file. Migrate to Parquet via Kafka Connect (Avro source to Parquet sink), partitioned by date and event type for predicate pushdown. Store the Avro writer schema ID in Parquet metadata so historical reads can use the correct schema. For existing JSON data, batch-convert with Spark or Glue. Expect 80–90% storage reduction and query speedups of 10–50x."

---

**Dimension: gRPC streaming vs REST**

- L5: "Use WebSockets if you need streaming."
- L6: "WebSockets are appropriate for browser-to-server streaming but add protocol complexity for internal services. gRPC offers three streaming modes: server streaming for server-push subscriptions, client streaming for bulk uploads, and bidirectional for interactive sessions. For high-frequency server push with backpressure, gRPC server streaming via HTTP/2 flow control is cleaner than WebSockets. For browsers that cannot use gRPC, a REST+SSE fallback or gRPC-Web gateway handles the translation layer."

---

**Dimension: ID encoding in JSON**

- L5: "We use int64 for IDs, that's fine."
- L6: "int64 IDs above 2^53 lose precision silently in JavaScript's Number type. Any ID above 9,007,199,254,740,991 is at risk. Always return int64 IDs as strings in JSON APIs. Document this in the OpenAPI spec with `type: string, format: int64`. Add a linter rule to catch int64 fields annotated as integer in the spec. Keep int64 internally for storage and arithmetic — the string conversion is only at the API boundary."

---

## Cross-Topic Brainstorming Questions

These twenty questions are designed for deliberate practice. None has a single correct answer. For each, the goal is to reason through tradeoffs, identify failure modes, and explain choices at the specificity an interviewer expects at L6. Work through these in writing before an interview — vague verbal summaries do not build the muscle for a whiteboard conversation.

### Theme A: Format Selection

**1.** You are designing an internal order processing service that handles 200,000 requests per second. The team wants to use JSON for easy debugging. How do you evaluate this decision, quantify the cost of JSON at that QPS, and what do you recommend? What observability do you build to support the debugging use case without paying the full JSON performance cost in production?

*What to think about:* At 200K RPS, JSON serialization CPU cost is real — benchmark it against Protobuf with your actual schema. Quantify the difference in payload bytes per second (bandwidth cost). Then separate the "debugging" use case from the "production" use case: engineers can debug with sampled structured logs or a shadow JSON endpoint, while the production path uses Protobuf. The answer is not "use JSON" or "use Protobuf" — it is "measure, then separate concerns."

**2.** A mobile app needs to call your backend. Bandwidth is constrained to 3G in the primary market. The team is deciding between JSON, Protobuf, and FlatBuffers. How does each format's wire size and parsing cost matter differently on a mobile device versus a server? Which do you choose and under what conditions would you choose differently?

*What to think about:* On mobile, both wire size and parse time matter — a server with 64 cores and fast RAM can absorb JSON parse cost easily; a mobile device on 3G cannot. FlatBuffers adds zero-copy access but requires schema discipline similar to Protobuf. Protobuf is the practical choice for most teams because the tooling is mature. Consider whether the mobile client can also receive a REST/JSON fallback for debugging and testing purposes without impacting the production binary path.

**3.** You are building a real-time dashboard that streams metrics from 10,000 IoT sensors at one sample per second each — 10,000 events per second, each event small but frequent. How do you design the encoding layer, considering both the ingest path and the read path for the dashboard?

*What to think about:* The ingest path cares about throughput and payload size — Protobuf over gRPC or a Kafka binary format. The read path for the dashboard cares about query latency and freshness. Consider whether the dashboard reads from the same stream (requires a streaming query engine) or from a pre-aggregated time-series store. The encoding choice for the ingest path and the storage format for the query path may differ.

**4.** An ML team stores model predictions in Kafka for downstream consumers in Python, Java, and Go. Each prediction includes a float array of 512 dimensions. What encoding format and tooling do you recommend, and what specific concern arises from the float array in your chosen format?

*What to think about:* Protobuf and Avro both support float arrays, but the serialization cost and schema evolution story differ. A 512-dimension float array is 2KB of payload at 32 bits per float. The specific concern with Protobuf is that `repeated float` has no length annotation — it works but schema evolution for the array itself (changing dimension count) is awkward. With Avro, the array is typed but cross-language float precision behavior (32 vs 64 bit) must be explicitly defined. Also consider: do all consumers need all 512 dimensions, or would projection reduce payload size significantly?

**5.** Your team stores five years of event data in S3 as newline-delimited JSON. New analytics queries need to run in under 10 seconds on 1TB of data. What is the migration path to Parquet, and how do you ensure queries against historical JSON data continue to work during the transition?

*What to think about:* The migration path is a batch conversion job (Spark or Glue) that reads JSON partitions and writes Parquet partitions. The dual-read problem during transition can be solved by registering both the JSON and Parquet paths in the Glue Data Catalog as separate tables, or by using a view that unions both. The key question is how long the transition lasts — if it takes 3 months to convert 5 years of data, you need a strategy for data added during those 3 months. Run new data directly to Parquet from a set cutover date.

### Theme B: Schema Evolution

**6.** You need to rename a field in a Protobuf message used by 30 services across 5 teams. Protobuf does not support field rename as a first-class operation. Walk through the exact migration steps and realistic timeline, including how you know when it is safe to complete each phase.

*What to think about:* Protobuf field names are used in JSON serialization and in generated code, but not on the binary wire — only field numbers appear on the wire. So "renaming" for binary consumers means updating generated code. For JSON consumers the old name breaks. The migration uses a combination of `json_name` option (to alias the new name in JSON output), a new field alongside the old, and an expand-contract cycle. The timeline depends on how quickly all 30 services can ship updates — instrument which services are still reading the old field name before removing it.

**7.** A team wants to add a new required field to an Avro schema on a Kafka topic with 90-day message retention. Walk them through why "required field" is structurally incompatible with a message queue, and what they should do instead.

*What to think about:* A message queue retains old messages. If a new required field has no default, any reader using the new schema that encounters an old message (written before the field existed) will fail — it cannot fill in a value the message does not contain. "Required" in a schema registry context means "required at write time, with no fallback for old messages." The correct approach is always: add with a default, let producers start writing the field, give consumers a migration window, then (if truly needed) consider enforcing presence at the application layer, not the schema layer.

**8.** Two services share a .proto file in a monorepo. Team A needs to remove a field they own. Team B still reads that field. Team A has a hard deadline in two weeks. How do you resolve this, and what does the deprecation process look like?

*What to think about:* The two-week deadline does not change the technical constraint — the field cannot be removed until Team B stops reading it. What Team A can do in two weeks: annotate the field with `[deprecated = true]`, add a `reserved` clause as a forward-looking commitment, and stop writing the field from their producers. The field still exists on the wire; Team B is unaffected. The removal can happen after Team B migrates. The negotiation here is about the deprecation announcement timeline, not the removal timeline. Escalate to a platform team or engineering manager if Team A has a hard deadline that truly requires the field to vanish from the .proto file.

**9.** You are migrating a JSON REST API to Protobuf for a service with 50 external customers whose release cycles range from 2 weeks to 6 months. Design the full migration strategy, including how you maintain both JSON and Protobuf simultaneously and how you enforce the JSON API sunset.

*What to think about:* Maintain both formats behind the same endpoint using content negotiation (`Accept: application/x-protobuf` vs `Accept: application/json`). This lets fast-moving customers migrate immediately while slow customers take the full 6 months. Track adoption by counting requests with each Accept header. Set a sunset date (12 months is standard for external APIs) and communicate it in response headers from day one using the `Deprecation` and `Sunset` HTTP headers. After the sunset date, return `406 Not Acceptable` for JSON requests. Provide SDK updates to all 50 customers with concrete code examples and a migration guide.

**10.** An Avro schema has 15 versions over three years. Some consumers run weekly batch jobs that may read messages written up to six months ago. What Schema Registry compatibility mode do you configure, and how does that choice constrain what schema changes are permissible going forward?

*What to think about:* `BACKWARD_TRANSITIVE` is the correct mode here. It ensures a reader with the current schema can read data written with any prior version — including messages from six months ago on an older schema version. The constraint this imposes: you can only add fields with defaults (never remove required fields, never change field types). This is stricter than `BACKWARD` (which only checks against the immediately prior version). The tradeoff is safety versus schema flexibility. For a system with long-lived batch consumers, the stricter mode is the right default and the operational discipline it enforces — add-with-default only — is good practice regardless.

### Theme C: Schema Registry and gRPC

**11.** The Schema Registry is down and a new producer service is starting up for the first time in production — its schema has never been registered. What happens? How do you design the producer startup path to handle this gracefully without cascading into a deployment failure across unrelated services?

*What to think about:* A new producer that has never registered its schema cannot fall back to a cache — there is nothing to cache yet. The options are: (1) fail fast and surface a clear error rather than producing malformed messages; (2) retry registration with exponential backoff during startup, delaying the service ready state rather than aborting; (3) pre-register schemas in a separate deployment step before any producer instances start (recommended for critical services). The key design principle is that the schema registration failure should be isolated — it should not affect services that are already running. Only new deployments should be affected.

**12.** Your gRPC service serves both mobile clients and internal services. Mobile needs Protobuf for efficiency; partner teams need a REST interface. How do you serve both without maintaining two separate service implementations? What tooling enables this, and what are the tradeoffs?

*What to think about:* The standard approach is gRPC-Gateway — a code-generation tool that generates a reverse proxy that translates HTTP/JSON requests to gRPC calls, driven by annotations in the .proto file. This means you define the service once in .proto, and both the gRPC server and the REST proxy are generated from the same definition. The tradeoff: not all gRPC features map cleanly to REST (streaming, bidirectional), and the REST API surface is constrained by what gRPC-Gateway supports. For simple request-response APIs, this works well. For streaming APIs, you may need a separate REST+SSE or WebSocket pathway.

**13.** A gRPC service deployed behind an AWS NLB shows severe load imbalance — some pods at 90% CPU, others at 5%. Walk through the root cause, explain why this happens structurally with HTTP/2, and describe the fix including any tradeoffs it introduces.

*What to think about:* The root cause is HTTP/2 multiplexing combined with L4/L7 confusion. Describe the mechanism precisely: one long-lived TCP connection per client, L4 balancing distributes connections (not streams), so high-traffic clients that happened to land on the same backend pin all their traffic there. The fix (Envoy sidecar for L7 stream-level balancing) adds latency from the proxy hop — typically 0.1–0.5ms — and introduces a new dependency on Istio/Envoy. The tradeoff is worth it for any gRPC service under real load.

**14.** You want to run schema compatibility checks on every PR in CI. For Protobuf: what tool do you use and what does it check? For Avro: same questions. What category of breaking change would pass both checks but still break consumers in production?

*What to think about:* For Protobuf: `buf breaking` checks field number reuse, field type changes, field removal, and service signature changes. For Avro: the Schema Registry's compatibility check API validates a proposed schema against existing versions in the configured compatibility mode. What both miss: semantic breaking changes. Renaming a field in Protobuf is not caught by `buf breaking` (the binary is unaffected, but JSON consumers break). Changing the meaning or allowed values of a string field is invisible to schema checks. Application-level contracts that exist only in documentation cannot be mechanically enforced.

**15.** An event-driven system has 100 producers and 200 consumers. A new mandatory business field must be added to a core event schema. Design the rollout strategy, including the transition period where some producers write the field and some do not.

*What to think about:* "Mandatory" at the business level does not mean "required" at the schema level — you should add it as optional with a default (empty string or null) in the schema. Phase 1: deploy the schema with the new optional field, no producers write it yet. Phase 2: migrate producers one by one to write the field — consumers that care about the field now start receiving it. Phase 3: after all 100 producers have been confirmed to write the field (instrument write frequency), the field is effectively mandatory in practice. Phase 4 (optional): enforce the field at the application layer via validation in the consumer, not via schema enforcement. Track producer migration on a dashboard and set a deadline for phase 3 completion.

### Theme D: Cross-Topic

**16.** A team stored events as JSON in Kafka for six months. The data science team now cannot run queries efficiently — Athena scans take 15 minutes per query on 3 months of data. What architectural decisions led here, and what is the remediation plan that does not require downtime for producers?

*What to think about:* The root architectural decision was choosing a storage format optimized for write convenience (JSON) rather than read efficiency (columnar). JSON in S3 requires Athena to scan every byte of every file for every query. The remediation does not require producer downtime: set up a Kafka Connect S3 Sink that writes new data to a separate Parquet prefix from this point forward. Run a parallel batch conversion job (Spark or Glue) to convert historical JSON partitions to Parquet. Keep both prefixes available in separate Athena tables during the transition. Once historical conversion and validation are complete, consolidate into a single table and stop the JSON ingestion path.

**17.** Your system uses Protobuf internally but exposes a JSON REST API to mobile clients. An internal field is an `int64` user ID. What is the risk when serializing this to JSON for mobile, what is the correct handling, and how do you document this in the API spec?

*What to think about:* The risk is IEEE 754 double precision loss for IDs above 2^53. The correct handling is to serialize the field as a JSON string at the API gateway layer, not as a number. If you are using Protobuf's built-in JSON serialization, use the `jstype = JS_STRING` field option or configure the serializer to output int64 as string. In the OpenAPI spec: declare the field as `type: string, format: int64` with a note that this is a large integer serialized as a string for JavaScript compatibility. Add a linter check that catches any int64 field declared as `type: integer` in the spec.

**18.** You are designing a system where producers write 50 million events per day and consumers must reprocess events from two years ago. How does encoding choice affect schema evolution flexibility, storage cost, and the operational complexity of supporting two-year-old consumers?

*What to think about:* Over two years, the schema will evolve. With JSON, schema evolution is implicit — old and new messages look the same to the reader, but consumers must handle missing or extra fields defensively. With Avro, schema evolution is explicit and managed — but you must keep all historical schemas in the registry and ensure that a reader with a current schema can handle data written with any schema from the past two years (this requires BACKWARD_TRANSITIVE). Storage cost: JSON at 50 million events/day accumulates fast; Avro or Parquet is significantly cheaper. For reprocessing: the consumer needs to know which schema version was used to write each message and must be able to read it. With Kafka + Avro + Schema Registry, this is automatic via the schema ID in the message header.

**19.** A load test on a gRPC service shows Protobuf deserialization at 15% of CPU despite Protobuf being known to be fast. What are the three most likely causes, and how would you investigate and reduce each one?

*What to think about:* Cause 1: large nested messages with deep field traversal — profile with CPU sampling to see which message types are most expensive to deserialize and whether flattening the schema reduces cost. Cause 2: large `repeated` fields (lists) — each element is deserialized individually; if a response contains thousands of repeated sub-messages, the cost adds up. Consider pagination or streaming instead of large lists. Cause 3: reflection-based deserialization — some Protobuf libraries (particularly older Java or Python bindings) use runtime reflection rather than generated code. Verify that generated stubs are being used, not a generic dynamic message parser. Also check whether deserialization is happening multiple times (e.g., once at the gateway and once in the service).

**20.** A new microservice must consume from three Kafka topics: Topic A uses JSON, Topic B uses Avro with Schema Registry, Topic C uses Protobuf with schemas in a Git repo. How do you design the consumer service to handle all three encodings without the code becoming unmaintainable?

*What to think about:* The design principle is to decode at the boundary and work with a canonical internal representation. Create a deserializer interface with three implementations: one for each encoding. Each deserializer takes raw bytes and a topic name and returns a domain object. The consumer logic works only with domain objects and is encoding-agnostic. The three deserializers are independently testable. For the long term, document this as technical debt — having three encoding formats in one system is a legacy of separate team decisions, not a desirable steady state. A migration plan to converge on one encoding (likely Avro or Protobuf) for all internal topics should be on the roadmap.

---

## Homework Exercises

Work through each exercise in writing before reading the hint. The hint is for self-grading — use it to identify what you missed, not to guide your initial answer.

---

### Exercise 1: Design the Encoding Strategy for a Ride-Sharing Platform

**Scenario**

A ride-sharing platform processes 3 million trips per day. At peak, 50,000 trips are active concurrently. There are 20 internal services and one mobile app. The four core events are:

- `TripStarted` — emitted once at the beginning of each trip
- `LocationUpdate` — emitted every 5 seconds per active trip (10,000 events/second at peak)
- `TripEnded` — emitted once at the end of each trip
- `PaymentProcessed` — emitted once per trip after the ride concludes

**What to design**

1. The encoding format for each event type with a specific justification based on volume, consumers, and evolution requirements.
2. The schema evolution strategy for each event type, including compatibility mode.
3. Schema Registry deployment: instance count, HA configuration, and behavior during a 5-minute outage at peak load.
4. How the mobile app interacts with the encoding layer and why you do or do not expose internal gRPC directly to mobile clients.

**L6 hint**

`LocationUpdate` at 10,000 events/second with tight latency requirements points to Protobuf over gRPC streaming — smallest payload and fastest encode/decode. `TripStarted` and `TripEnded` need durability and cross-service fanout, which favors Avro in Kafka with Schema Registry. `PaymentProcessed` carries financial data that may be audited months later — Avro schema enforcement and historical readability matter here. The mobile app should receive a JSON gateway API. Exposing internal gRPC to mobile clients requires gRPC-Web, adds tooling complexity, and couples mobile release cycles to internal proto changes.

**What a strong answer includes:**

- A clear per-event-type justification table (format, volume, reason) rather than one blanket choice
- Explicit Schema Registry HA configuration: 3 instances, dedicated Kafka cluster for `_schemas`, Tier-1 SLA
- Behavior during a 5-minute registry outage at peak: producers with cached schemas continue uninterrupted, new deployments during the outage retry with backoff
- A JSON API gateway between mobile clients and the internal gRPC layer, with Protobuf internally and JSON externally — not gRPC-Web unless you explicitly justify it
- FULL_TRANSITIVE compatibility mode for `PaymentProcessed` because financial events may be reprocessed months later

---

### Exercise 2: Schema Migration Without Downtime

**Scenario**

Current Avro schema in production for 18 months: a `UserEvent` record with three fields — `id` (long), `action` (string), `timestamp` (long). The topic has 200 consuming services.

Three changes are now required simultaneously:

1. Add `user_agent` (string, optional) — for behavioral analytics
2. Add `country_code` (string, optional, 2 characters) — for geo segmentation
3. Rename `action` to `event_type` — old name conflicts with a reserved word in a new analytics framework

**What to design**

1. The complete migration strategy with numbered phases.
2. The specific mechanism for handling the rename using Avro's native capabilities.
3. A timeline with observable go/no-go criteria at each phase, not just calendar dates.
4. The rollback plan if consumers begin failing in phase 2.

**L6 hint**

Add `user_agent` and `country_code` with defaults first — this is safe and backward-compatible, and the sooner producers write them, the more data is available before consumers migrate. For the rename: use Avro's `aliases` feature — create `event_type` and give it an alias of `action`. Both names resolve to the same field during the transition. Migrate consumers to read `event_type` at their own pace. Go/no-go criterion before removing `action`: zero reads of the deprecated field in the past 30 days across all 200 consumers, confirmed by instrumented read-frequency metrics.

**What a strong answer includes:**

- Phase 1: add `user_agent` and `country_code` with defaults, register new schema, deploy producers that write them — no consumer changes required
- Phase 2: add `event_type` field with alias `action`, register new schema, deploy producers that write `event_type` — consumers still work via alias
- Phase 3: migrate all 200 consumers to read `event_type` instead of `action`, tracked by a dashboard showing read frequency per field per service
- Go/no-go for Phase 4: zero reads of `action` field across all consumers for 30 consecutive days
- Phase 4: remove `action` alias and `action` field, register new schema
- Rollback plan for Phase 3 failure: revert the consumer service to the previous build; the schema change is backward-compatible so no schema rollback is needed

---

### Exercise 3: Debug a Schema Compatibility Failure

**Scenario**

A producer's deployment log shows:

```
Schema registration failed: Incompatible schema (BACKWARD_TRANSITIVE).
Proposed change: removed field "legacy_source" (string, field 7).
The field has a default value of "".
```

The engineer believes this should be safe because the field has a default value. The Schema Registry is rejecting it.

**What to work through**

1. Define `BACKWARD_TRANSITIVE` precisely and explain how it differs from `BACKWARD`.
2. Explain why removing a field with a default value can still fail a `BACKWARD_TRANSITIVE` check.
3. Describe the historical condition that causes this failure — what would be true about an earlier schema version?
4. Provide two paths to resolution: one that allows the removal to proceed, and one that does not require modifying historical data.

**L6 hint**

`BACKWARD` means a reader with the new schema can read data written with the immediately previous version. `BACKWARD_TRANSITIVE` means a reader with the new schema can read data written with any prior version — all the way back to version 1. If `legacy_source` was added in schema version 3 without a default (before the default was added in a later version), then removing the field now means a reader with the current schema cannot handle data written by version 3. The transitive check catches this because it validates against all historical versions. One fix: change compatibility mode to `BACKWARD` (validates only against the previous version), documented explicitly. Safer fix: add a default to the field in the version 3 schema record by submitting a corrective schema update, then remove the field in the next version. This preserves full transitive compatibility.

**What a strong answer includes:**

- A precise definition of BACKWARD_TRANSITIVE: a reader with the new schema can read data written with any prior schema version, not just the immediately previous one
- Identification of the specific historical condition: `legacy_source` was added without a default in an earlier version (e.g., version 3), making it required for data written at that schema version
- Two concrete resolution paths with tradeoffs stated clearly: changing the compatibility mode to BACKWARD is faster but reduces the safety guarantee; correcting the historical schema record preserves full transitive safety
- Recognition that the engineer's mental model was correct for the simple case (BACKWARD: removing a field with a default is safe against the previous version) but incomplete for the transitive case (BACKWARD_TRANSITIVE: it must be safe against all historical versions, including ones that may have introduced the field without a default)

---

### Exercise 4: Design gRPC for a 50K RPS Internal API

**Scenario**

A product catalog service handles 50,000 lookups per second from 30 consumer services. Requirements:

- p99 latency under 5ms for single-product lookups
- Bulk catalog export of up to 500,000 entries for batch jobs
- Consumers in Go, Java, Python, and Rust
- Partial failures must be structured — missing product returns a gRPC error, not a crash
- All RPCs must be instrumented for distributed tracing and latency percentiles

**What to design**

1. The `.proto` service definition with at least unary, server streaming, and one additional RPC type.
2. Load balancing strategy with the specific proxy or service mesh and the reason for that choice.
3. How deadlines propagate from caller to service and what happens when a deadline is exceeded mid-stream.
4. Retry strategy: which gRPC status codes are safe to retry, which are not, and why.
5. Observability metadata attached to each RPC and how it flows to the tracing system.

**L6 hint**

Use unary RPCs for single-product lookups — independent, easy to retry, amenable to client-side caching. Use server streaming for catalog export — the server pages through 500K entries and streams them without materializing the full result in memory. Client streaming is appropriate for bulk upsert. All RPCs must set deadlines; a caller without a deadline holds a server goroutine indefinitely. In Go and Java, deadlines propagate via context. For retries: `UNAVAILABLE` is safe to retry. `NOT_FOUND` is idempotent but retrying will not help. `INTERNAL` and `DATA_LOSS` should not be retried automatically. For observability: inject trace context into gRPC metadata headers; emit per-RPC latency histograms labeled by method and status code.

**What a strong answer includes:**

- Three distinct RPC types in the .proto definition: unary for single lookup, server streaming for catalog export, client streaming or bidirectional for bulk operations
- Explicit L7 load balancing justification: Envoy sidecar via Istio, not L4 — with a sentence explaining why (HTTP/2 stream-level distribution)
- Deadline propagation: all RPCs set a deadline via context, the deadline is inherited by any downstream calls made by the handler, and mid-stream deadline expiry cancels the stream gracefully rather than leaving the server writing to a dead client
- Retry policy: retryable on UNAVAILABLE (with exponential backoff and jitter), not retryable on NOT_FOUND, INVALID_ARGUMENT, or ALREADY_EXISTS
- Observability: trace ID in gRPC metadata header propagated to downstream services; per-method latency histograms at p50/p95/p99; error rate by status code; connection pool utilization

---

### Exercise 5: Migrate a JSON Data Lake to Parquet

**Scenario**

Three years of events are stored as gzipped JSON in S3, partitioned as `s3://bucket/events/year=YYYY/month=MM/day=DD/`. Total size: approximately 40TB gzipped. Athena queries on a single day's data take 10–20 minutes. Target: single-day queries complete in under 30 seconds with at least 70% storage cost reduction.

**What to design**

1. Migration strategy for the historical data, including job parallelism and sequencing.
2. Target Parquet schema, compression codec choice, and partitioning scheme.
3. Ongoing ingestion pipeline so all new data arrives in Parquet from migration completion onward.
4. Validation approach: how you confirm migrated Parquet data matches source JSON exactly.
5. Fallback plan: how long you retain original JSON files and the condition under which you delete them.

**L6 hint**

Partition the migration by year and month and run parallel Spark or Glue jobs — this allows incremental progress and per-partition validation before proceeding. Use Zstd compression in Parquet for the best balance of storage reduction and query speed with modern Athena. Partition by `date` and `event_type` for predicate pushdown. Validate by running count and aggregate queries against matching JSON and Parquet partitions and comparing results — any mismatch blocks the pipeline. Deploy a Kafka Connect Avro-to-Parquet pipeline on the same day migration completes so no new JSON files are created. Retain original JSON for 90 days post-migration and delete only after confirming no active dashboards or pipelines reference the old paths.

**What a strong answer includes:**

- Phase plan with explicit sequencing: historical migration by month (parallel jobs), cutover to Parquet for new data, 90-day JSON retention, then deletion
- Codec choice with tradeoff: Zstd for storage reduction, Snappy if read throughput is the bottleneck, with a recommendation to benchmark on a representative sample
- Partitioning at `date` and `event_type` with a note on cardinality — too many distinct `event_type` values can result in too many small files, so grouping event types into families may be needed
- Validation: row count equality and aggregate equality (sum of a numeric field) on a 5% sample of each partition before marking it complete
- Fallback: Glue Data Catalog is updated to point at Parquet tables, but JSON tables remain registered and queryable for 90 days; any dashboard or pipeline can fall back by name
- Expected query time and storage reduction with numbers: sub-30 seconds, 80–90% storage reduction

---

## Interview Strategy: How to Approach Encoding Questions

Encoding and schema evolution questions in L6 interviews are often embedded inside a larger system design question — the interviewer asks you to design a ride-sharing backend or an event-driven payment system, and encoding is one layer you need to address. The following patterns help you handle these questions well.

**Name the format early, then justify it.** Do not just say "we'll use Protobuf." Say: "For internal services above 50K RPS, I'd choose Protobuf for the wire size and serialization performance — roughly half the payload of JSON and three times faster encode/decode. The generated clients also reduce integration cost across our Go and Java services. For the public API I'd keep JSON for external developer tooling." The justification is what separates an L6 answer from an L5 answer.

**Treat schema evolution as a first-class concern.** The most common mistake in encoding questions is to choose a format and never discuss how the schema will evolve when business requirements change. An L6 interviewer will push on this. Volunteer the evolution strategy before being asked: "For Avro in Kafka, I'd configure BACKWARD_TRANSITIVE compatibility so that consumers reading six-month-old messages will still work after we add new optional fields. All new fields will have defaults."

**Connect encoding to downstream systems.** The encoding format in Kafka does not live in isolation. It affects how data is written to the data lake, how analytics teams query it, and whether historical reprocessing is possible. When you choose Avro for Kafka, mention that you'll write to S3 as Parquet via Kafka Connect, and that you'll embed the writer schema ID in the Parquet metadata to support historical reads. This shows you understand the full data lifecycle, not just the streaming layer.

**Surface failure modes proactively.** At L6, you are expected to identify what can go wrong before being asked. When discussing gRPC, mention that L7 load balancing is required — the interviewer may not know to test you on this, but mentioning it signals operational experience. When discussing Protobuf, mention field number permanence. When discussing Schema Registry, mention HA requirements. Proactively naming failure modes and their mitigations is the clearest signal that you have operated these systems at scale.

**Give concrete numbers.** "Protobuf is faster" is an L5 answer. "Protobuf is roughly 50% smaller on the wire and 3x faster to encode and decode for typical schemas — at 100K RPS, that difference in serialization CPU can save one or two backend nodes" is an L6 answer. Anchor your recommendations to the numbers in this chapter.

**Structure your answer as a decision, not a recitation.** An interviewer does not want to hear a list of facts about Protobuf. They want to see you make a decision, justify it against the constraints of the problem, name the tradeoffs, and explain what monitoring you would add to know if the decision was wrong. The structure is: here is what I would choose, here is why it fits this specific problem, here is what could go wrong, and here is how I would detect it early.

**Use the incidents as evidence in your answers.** When you recommend HA for the Schema Registry, say: "We had an incident where a single-instance registry caused 47 deployment pipeline failures across a 8-minute window — I'd deploy at least 3 instances behind a load balancer and treat it as Tier-1 infrastructure." Grounding recommendations in concrete failure scenarios makes answers significantly more credible than recommendations made in the abstract.

---

## Common Mistakes and How to Avoid Them

These are the encoding and schema mistakes that surface repeatedly in production systems and in system design interviews. Being able to name them, explain the mechanism, and describe the prevention is as important as knowing the happy path.

**Treating Protobuf field numbers as mutable.** Field numbers are wire identifiers — they are permanent. Engineers who learn this by reading documentation internalize it; engineers who learn it by causing a corruption incident never forget it. The prevention is `reserved` keywords plus `buf breaking` in CI.

**Adding Avro fields without defaults.** Adding a required field to a shared schema means every existing consumer must deploy before any new message can be produced. In practice, this is impossible across independent teams. All new Avro fields must have default values, always.

**Deploying gRPC behind an L4 load balancer.** The L4/L7 distinction is non-obvious to engineers coming from HTTP/1.1 backgrounds where one request per connection was the norm. HTTP/2 multiplexing changes the load balancing model entirely. Verify the load balancer type before any gRPC rollout.

**Storing JSON in the data lake without a migration plan.** JSON is a reasonable starting point. It becomes a cost and performance problem when data volume grows. The mistake is not the initial choice — it is failing to plan the migration to columnar format before the volume makes it expensive.

**Treating Schema Registry as a low-criticality service.** In a microservices environment with continuous deployment, the Schema Registry is called constantly by new instance startups across the fleet. A single-instance registry is a single point of failure for all event streaming producers.

**Returning int64 IDs as JSON numbers.** Small int64 values are below `2^53` and appear fine in testing. The problem only materializes months or years later when IDs grow large. The fix must be designed in from the start.

**Ignoring the data lake implications of encoding choices.** When you choose JSON for Kafka today, you are also choosing to pay the analytics query cost months from now when the data science team starts querying the data lake. The encoding decision at ingest time is also a decision about query performance and storage cost at rest. These are not separable.

**Assuming schema changes are "just code changes."** A schema change in a shared system is a distributed coordination problem. The schema is a contract between producers and consumers that may be deployed independently at different times. A schema change that is not backward-compatible is not safe to deploy independently — it requires coordinated deployment, which is expensive and risky. This is why backward compatibility modes and expand-contract patterns exist: to let schema changes be deployed independently, just like good API versioning.

**Using `buf breaking` as the only safety check for Protobuf.** `buf breaking` catches structural wire format issues: field number reuse, type changes, field removal. It does not catch semantic changes — renaming a field (the binary is unchanged, but JSON serialization and generated code names change), changing the meaning of an enum value, or adding a field that other teams interpret as required by convention. Structural safety checks are necessary but not sufficient.

---

## Quick Reference Card

Use this section for rapid review before an interview. It consolidates the key decisions, rules, and numbers from the full chapter.

---

### Format Selection Matrix

| Use Case | Recommended Format | Reason |
|---|---|---|
| Public REST API | JSON + OpenAPI | Maximum tooling support, external developer adoption, human-readable for debugging |
| Internal high-QPS RPC | Protobuf + gRPC | ~50% smaller payload, ~3x faster encode/decode, streaming support, generated multi-language clients |
| Kafka event streams | Avro + Schema Registry | Built-in schema evolution, enforcement at produce time, compact binary encoding |
| Data lake and analytics | Parquet | Columnar storage enables predicate pushdown, 80–90% size reduction vs JSON, fast scans |
| Mobile API with bandwidth constraints | Protobuf | Smallest payload, lowest parse cost on device |
| Debugging and development | JSON | Human-readable, no tooling required to inspect |
| Long-term archival with strict schema | Avro in object storage | Schema embedded in file, supports evolution via schema resolution |

---

### Schema Evolution Quick Rules

**Protobuf**

- NEVER renumber an existing field. The number is permanent.
- NEVER reuse a field number after deletion. Wire type mismatch causes silent data corruption.
- ALWAYS mark removed field numbers as `reserved`. Mark removed field names as `reserved` too.
- Deprecate before deleting: annotate with `[deprecated = true]`, stop writing the field, confirm consumers have migrated via metrics, then remove.
- Adding optional fields is always safe. Adding required fields is always a breaking change.
- Use `buf breaking` in CI to enforce these rules automatically.

**Avro**

- ALWAYS provide a default value when adding a new field. Without a default, old messages cannot be read by a new reader schema.
- ALWAYS provide a default value before removing a field. Remove the writer first, then remove the field from the schema.
- Use `aliases` to rename a field without breaking readers — the old name becomes an alias on the new field name.
- Compatibility modes: BACKWARD (new schema reads old data), FORWARD (old schema reads new data), FULL (both directions). For batch consumers reading historical data, use FULL_TRANSITIVE or BACKWARD_TRANSITIVE.

**General**

- Full compatibility — only add optional fields with defaults — is the most restrictive and the safest default for shared schemas.
- Expand-contract is the universal pattern for breaking changes without coordinated deploys: expand (add new), migrate consumers, contract (remove old).
- Never ship a breaking change without a defined migration window, a deprecation signal visible to consumers, and an automated sunset gate.

---

### Avro Compatibility Mode Cheat Sheet

| Mode | What it guarantees | When to use it |
|---|---|---|
| BACKWARD | New schema can read data written with the previous schema version | Default for most services; safe for rolling upgrades where consumers deploy before producers |
| FORWARD | Old schema can read data written with the new schema version | When producers deploy before consumers; ensures old consumers don't break on new messages |
| FULL | Both BACKWARD and FORWARD | Safest for services where deploy order is not controlled; most restrictive — only add optional fields with defaults |
| BACKWARD_TRANSITIVE | New schema can read data written with any prior schema version | Services with long-lived consumers or batch jobs that read months-old data |
| FORWARD_TRANSITIVE | Old schema can read data written with any newer schema version | Rarely needed; useful when you can't guarantee consumers upgrade on time across many versions |
| FULL_TRANSITIVE | Both BACKWARD_TRANSITIVE and FORWARD_TRANSITIVE | Most restrictive: only add optional fields with defaults, forever — used for financial or compliance data with multi-year retention |
| NONE | No compatibility enforcement | Local development or throwaway topics only — never in shared production systems |

---

### Anti-Patterns to Name in Interviews

When an interviewer asks "what can go wrong?" or "what would you avoid?", referencing these patterns by name shows operational depth.

**"Just use JSON everywhere."** This is the most common default. It is correct for external APIs and development. It is wrong for internal services at high QPS or for data lake storage at scale. The cost is serialization CPU and storage — quantify it.

**"We'll coordinate the cutover."** Coordinating a breaking schema change by telling 20 teams to deploy simultaneously is operationally dangerous. The correct answer is expand-contract — make the change backward-compatible, migrate incrementally, remove the old field only after all consumers have migrated.

**"We'll just version the endpoint."** Endpoint versioning multiplies your maintenance burden. Every bug fix must be applied to every version. After three major versions, the codebase has three copies of every API handler. Use expand-contract first. Version endpoints only for truly incompatible API surface changes.

**"The Schema Registry is just a utility."** Every team that has had a registry outage during a deployment wave learns this lesson. The registry is Tier-1 infrastructure. Treat it accordingly before the outage, not after.

**"gRPC is automatically faster than REST."** gRPC behind an L4 load balancer can be slower than REST behind an L7 load balancer. The performance story requires the full system to be configured correctly: L7 balancing, connection pooling, deadline propagation, and appropriate streaming modes.

---

### Key Numbers

| Metric | Value |
|---|---|
| JSON vs Protobuf payload size | Protobuf is approximately 50% smaller for typical schemas |
| JSON vs Protobuf encode/decode speed | Protobuf is approximately 3x faster |
| JSON vs Parquet storage size | Parquet is 80–90% smaller for analytics workloads (columnar + compression) |
| Schema Registry cache hit latency | 0ms (in-process cache after first fetch) |
| Schema Registry first fetch latency | 5–10ms over the network |
| Schema Registry HA minimum | 3 instances behind a load balancer |
| `_schemas` topic replication factor | 3, on a dedicated Kafka cluster |
| Maximum safe JavaScript integer | 9,007,199,254,740,991 (2^53 - 1) |
| gRPC load balancing requirement | L7 is required — L4 causes severe imbalance with HTTP/2 multiplexing |
| Avro vs JSON in Kafka | Avro is typically 40–60% smaller with schema registry overhead amortized |
| Parquet query speedup vs JSON in Athena | Typically 10–50x for filtered queries on large datasets |
| Protobuf field number range | 1–15 use 1 byte on the wire; 16–2047 use 2 bytes; prefer 1–15 for frequently-used fields |
| gRPC Envoy proxy overhead | Typically 0.1–0.5ms additional latency per RPC for the sidecar proxy hop |
| JSON to Parquet migration throughput | A 4-node Spark cluster can convert roughly 1TB of JSON per hour depending on message size |

---

### Decision Checklist for Encoding Choices

Before finalizing an encoding format, answer each of these questions explicitly:

1. Who are the consumers? Internal services only, or external developers who need stable tooling and SDK support?
2. What is the request rate? Above 10K QPS, measure serialization CPU. Above 100K QPS, binary encoding is almost always the correct choice.
3. How often does the schema change? Frequently-changing schemas benefit from Schema Registry enforcement over ad-hoc coordination.
4. How long is data retained? Data retained for years requires schema version metadata and an evolution strategy that works for readers built months after the data was written.
5. What languages do consumers use? Protobuf and Avro generate clients for most languages; JSON requires no generation but also provides no schema enforcement.
6. Is this data read analytically at scale? If yes, the target format is Parquet in a data lake, even if the ingest format is different.
7. Does the API cross a browser or mobile boundary? Browsers cannot use gRPC without gRPC-Web. Mobile clients incur real cost from large payloads on constrained networks.
8. Are there int64 IDs in the API response? If yes and consumers include JavaScript, all int64 fields must be returned as strings.
9. What is the schema evolution velocity? Teams that change schemas frequently need Schema Registry + compatibility enforcement; teams that rarely change schemas can use lighter governance.
10. Is there a data lake or analytics downstream? If yes, design the Kafka-to-Parquet pipeline at the same time as the Kafka encoding strategy — retrofitting it later is expensive.
11. Does this service cross organizational boundaries (external customers, partners, public API)? If yes, treat breaking changes as requiring a 6–12 month deprecation window, not a 2-sprint migration sprint.
12. What is the failure mode if the Schema Registry is unavailable? Design producers to degrade gracefully (retry, use cached schema) rather than fail hard and cascade into deployment outages across unrelated services.

---

---

## Closing Notes

Data encoding is infrastructure. It is not a detail to decide at the end of a system design — it is a foundational choice that affects every system that touches the data: the service that produces it, the service that consumes it, the pipeline that moves it, and the analytics system that queries it months later. The failure modes covered in this chapter — silent data corruption from Protobuf field number reuse, JavaScript integer precision loss, Schema Registry as a single point of failure, gRPC behind an L4 load balancer, Parquet reader/writer schema mismatch — are not edge cases. They are predictable consequences of choices that seemed reasonable at the time. The L6 signal is knowing these failure modes before you encounter them, not after.

The patterns in this chapter recur across every system at scale:

- The expand-contract pattern applies to any shared interface change, not just schema evolution.
- The L7 versus L4 load balancing distinction applies to any HTTP/2-based protocol, not just gRPC.
- The int64-in-JSON problem applies to any large numeric identifier exposed in a JavaScript-consumed API.
- The Schema Registry HA problem applies to any shared coordination service that producers depend on at startup.

Learn the patterns, not just the examples. The specific technologies change. The underlying failure modes remain stable.

Review Parts A and B of this chapter before an interview to ensure the wire format mechanics, Schema Registry internals, and gRPC streaming modes are fresh. Use this Part C as a final check: can you walk through each incident cold, explain the L6 answer for each calibration dimension without prompting, and sketch the design for each homework exercise in under 15 minutes?

---

*End of Chapter 30.*
## Supplemental Brainstorming: Chapter 30 -- Data Encoding and Schema Evolution

*Questions 5-50: Complete topic coverage and cross-chapter integration.*

*The four questions already in the main chapter cover introductory format selection. This supplement provides the depth needed for L6 interview performance.*

---

### Section A: JSON Deep Dive (Q5-Q12)

---

**Question 5 -- JSON number precision at scale**

A payments platform sends inter-service JSON messages containing 64-bit order IDs (Snowflake IDs, e.g., 1708234567890123456). The IDs are fine in Python and Java services. A new JavaScript-based analytics dashboard starts consuming the same API and reports duplicate orders, wrong totals, and corrupted links. Nobody changed the IDs.

- Explain why IEEE 754 double precision causes Snowflake IDs to silently corrupt in JavaScript. What is the exact threshold (2^53) and why does it matter for Snowflake IDs that encode timestamps and worker IDs in the upper bits?
- List three concrete fixes ordered by migration cost: (a) send IDs as JSON strings, (b) add a separate `string` field alongside the integer field for transitional compatibility, (c) adopt a binary format for the internal API. What are the tradeoffs of each?
- A new engineer says "just validate the ID on the JavaScript side." Explain why client-side validation cannot fix this: by the time JavaScript parses `JSON.parse('{"id":1708234567890123456}')`, the precision is already lost -- the number arrives at the JavaScript runtime already rounded. Where does the loss happen?
- Follow-up: Your Java service calls `json.dumps(order_id)` in Python and sends it to a Java consumer. Java's `ObjectMapper` parses JSON numbers as `long` by default. Is the Java consumer safe? What if it parses as `Double`?

---

**Question 6 -- JSON null vs. absent: two semantics, one representation**

Your user profile service stores whether a user has a phone number. Some users have no phone (null). Some users have never been asked (field absent). Your fraud system makes different decisions based on these two cases: `null` means "verified no phone," `absent` means "unknown." The service uses JSON. Three months after launch, the fraud team reports their model accuracy has dropped: it is treating "unknown phone" as "no phone."

- Trace the data flow: show how a JSON serializer that omits `null` fields and one that includes them produces different bytes on the wire, and how a deserializer that maps both to `null` loses the distinction.
- Design a fix using JSON: (a) use sentinel values (empty string, `-1`), (b) always include `null` explicitly and document the convention, (c) use a wrapper object `{"set": true, "value": null}`. Evaluate each against readability and interoperability.
- Now design the same fix in Protobuf using `google.protobuf.StringValue` wrapper. Show the proto definition and explain what the consumer sees when the field is present-but-null vs. absent.
- Follow-up: Avro uses union types `["null", "string"]` to express nullable fields. Show the Avro schema for a nullable phone number field. What does the wire look like when value is null vs. when value is a string?

---

**Question 7 -- JSON parsing cost under load: when does it actually matter?**

A senior engineer argues: "JSON parsing is fast enough. Modern hardware does it in microseconds. Binary formats are premature optimization." You are designing a service that will handle 80,000 requests per second on 8 application servers, each with 16 vCPUs. The average payload is 900 bytes JSON. Give a data-driven answer.

- Compute: at 80K QPS and approximately 10 microseconds per JSON decode, how many CPU core-seconds per second does JSON parsing consume across the fleet? How does that compare to Protobuf at approximately 4 microseconds?
- Identify the specific phases of JSON parsing that dominate CPU cost: UTF-8 validation, string comparison for field name matching, number string-to-integer conversion, heap allocation for parsed strings. For a message with 15 fields, estimate the number of string comparisons required per message if the parser does linear scan.
- The service is also CPU-bound on business logic. What is the opportunity cost of spending 1.5 CPU cores on JSON parsing when those cores could serve business logic? At $0.048/vCPU-hour on a c5.2xlarge, what is the annual cost of that wasted capacity?
- Follow-up: A proposal is to use a streaming JSON parser (SAX-style, event-based) instead of a full document parser. What does this save? What does it NOT save?

---

**Question 8 -- JSON date formats: the milliseconds vs. seconds landmine**

Your event pipeline stores clickstream events as JSON. The `event_time` field has been written by four different producer teams over three years. You are now building a real-time fraud detection model that needs accurate event timestamps to the millisecond. When you load a sample of 10 million events, you find timestamps ranging from year 1970 to year 2024 in the same field.

- Explain exactly what happens when a Unix timestamp in seconds (e.g., 1705315800) is treated as milliseconds by a consumer: what date does it produce? What is the factor of 1000 off, and how does this manifest in a time-series chart?
- Catalog all timestamp formats you might find in a production JSON field and their risks: Unix seconds, Unix milliseconds, ISO 8601 with Z suffix, ISO 8601 with offset, custom strings like "Mon Jan 15 2024". Which formats are ambiguous between seconds and milliseconds?
- Design a remediation strategy for an existing pipeline: (a) schema audit to catalog all format variants, (b) normalization layer that detects and converts, (c) how do you detect whether a number is seconds or milliseconds heuristically (hint: current time in seconds is ~1.7 billion; values above 10^12 are milliseconds).
- Follow-up: Protobuf has `google.protobuf.Timestamp` (seconds + nanos fields). Avro uses `"logicalType": "timestamp-millis"` on a long. How do these solve the ambiguity problem? What remains ambiguous even with these types?

---

**Question 9 -- JSONB in PostgreSQL vs. raw JSON: when does it matter?**

Your application stores user preferences as a JSON blob in PostgreSQL. The team chose `jsonb` (binary JSON) column type. A new engineer asks: "Why not just use `text` or `json` type? What does `jsonb` actually buy us?"

- Explain the difference between PostgreSQL `json` (stored as text, re-parsed on every access), `jsonb` (stored as binary, pre-parsed, supports indexing), and `text` (opaque string, no JSON operations). What does each type cost on write? On read? On query with a `WHERE preferences->>'theme' = 'dark'` filter?
- `jsonb` supports GIN indexes. Explain what a GIN index on a `jsonb` column stores (each key-path and value gets an index entry) and what query shapes it accelerates vs. what it cannot accelerate (e.g., range queries on numeric values within JSON).
- Your product team wants to query "all users who logged in in the last 7 days AND have dark mode enabled." The `last_login` is a normal timestamp column; `theme` is inside the JSONB blob. How does the query planner combine a B-tree index on `last_login` with a GIN index on preferences? What are the risks of putting `last_login` inside JSONB instead?
- Follow-up: At what point should you stop putting fields in JSONB and normalize them into proper columns? Name three signals: field is frequently filtered/sorted in WHERE/ORDER BY, field is used in joins, field needs referential integrity constraints. What is the cost of migrating a heavily-used JSONB key into a proper column in a live table?

---

**Question 10 -- JSON schema validation and OpenAPI: the soft contract**

Your team publishes an external REST API consumed by 300 enterprise partners. The API returns JSON. A schema change in the response (renaming `customer_id` to `customerId` for camelCase consistency) causes 47 partner integrations to break overnight. Post-mortem reveals: no formal schema contract was enforced. Partners were told the schema verbally.

- Compare three approaches to enforcing JSON schema: (a) JSON Schema (draft-07) validated at the gateway, (b) OpenAPI 3.0 spec as the contract with partner sign-off, (c) contract testing using Pact (consumer-driven contracts). What does each catch? What does each miss? When does a rename get caught vs. slip through?
- OpenAPI spec enforces what the server CAN send, but not what it DOES send unless there is runtime validation. Describe a setup where the API gateway validates outbound responses against the OpenAPI spec before releasing to partners. What is the latency overhead of response validation per request?
- Design a breaking-change notification process: (a) versioned URL paths (/v1/, /v2/), (b) deprecation headers with sunset dates, (c) dual-field period where both `customer_id` and `customerId` are present in responses. How long should a dual-field period last for enterprise partners?
- Follow-up: Protobuf and Avro both provide machine-enforceable schema contracts that catch breaking changes at compile time or registry registration time. If your external API must remain JSON, what is the minimum process discipline to get equivalent safety? Is it achievable in practice?

---

**Question 11 -- JSON floating point and money: the $0.00000001 problem**

Your fintech platform stores transaction amounts as JSON floating-point numbers. A new reconciliation report shows a discrepancy of $0.10 across 1 million transactions. The discrepancy is not from rounding at display time -- it is from accumulated floating-point error in the storage layer.

- Demonstrate with code-level reasoning how `0.1 + 0.2 = 0.30000000000000004` in IEEE 754 double precision. If you store this and add it to a running total 1 million times, what is the accumulated error? Why does this matter for a bank's general ledger?
- List the three correct representations for monetary amounts: (a) integer cents/pence (`"amount_cents": 1099`), (b) string decimal (`"amount": "10.99"`), (c) integer with explicit scale factor embedded in the schema. What are the tradeoffs of each -- overflow risk, human readability, compatibility with SQL `DECIMAL(19,4)` columns?
- Your Kafka topic currently uses `"amount": 10.99` (float). You need to migrate to `"amount_cents": 1099` (int). Design the migration: dual-field period, consumer code update order, which field is authoritative during transition, how to detect divergence between the two fields.
- Follow-up: PCI-DSS compliance requires exact audit trails of financial amounts. If a float amount is stored, re-read, and displayed, and there is a discrepancy from rounding, is this a compliance violation? How do auditors view float-stored financial data?

---

**Question 12 -- JSON schema-less freedom vs. downstream chaos: the data lake scenario**

A startup uses JSON for everything: Kafka events, REST responses, S3 data lake storage. Three years later, the data science team tries to train a model on historical events. They load 2TB of S3 JSON files into Spark. The job fails: the inferred schema keeps conflicting because field `user_age` was sometimes an integer, sometimes a string, sometimes missing.

- Explain the root cause: JSON has no enforced schema, producers change over time, and schema inference (what Spark does when reading JSON) is non-deterministic when multiple schema versions coexist in one dataset.
- Design a retroactive remediation: (a) scan all files to identify all unique schema variants, (b) build a normalization job that reads each variant and writes a unified Parquet output with a fixed canonical schema, (c) handle type conflicts (`user_age: "25"` vs `user_age: 25`) with explicit casting rules. What are the risks of automated casting (e.g., `user_age: "unknown"` cannot be cast to int)?
- Compare the cost of fixing this retroactively (engineer-weeks) against the cost of enforcing Avro + Schema Registry from day one (setup time). At what company stage does schema discipline become ROI-positive?
- Follow-up: Had the team used Avro for Kafka events from the start, what exactly would have prevented this scenario? (Answer: schema enforced at write time, schema embedded with or referenced from each file, Avro resolution handles field additions with defaults.) What would NOT have been prevented? (Answer: intentional incompatible schema changes if NONE compatibility mode was used.)

---

### Section B: Protobuf Mastery (Q13-Q20)

---

**Question 13 -- Field numbers: the wire identity trap**

A new engineer joins your team and is excited to "clean up" the old `.proto` files. They rename `cust_id` to `customer_id` (fine), remove the deprecated `legacy_address` field (bad), and -- to make things "logically ordered" -- renumber all fields so they go 1, 2, 3, 4, 5 in alphabetical order of field name. The CI pipeline passes. The deployment goes out. Within 15 minutes, the customer service dashboard shows corrupted data: order amounts appearing in name fields, booleans where IDs should be.

- Trace exactly what goes wrong when field numbers are renumbered: show a concrete before/after schema and the wire bytes that old consumers interpret under the new field number mapping. Why does this produce no parse error but silently wrong data?
- The `reserved` keyword exists to prevent this class of mistake. Show the correct procedure for the field removal: (a) mark `legacy_address` as deprecated in comments, (b) move it to `reserved` before deleting, (c) add the field name to `reserved` to prevent name reuse. At what stage does the compiler catch a reservation violation?
- This incident passed CI. What additional checks would have caught it before production: (a) proto-breaking-change linter (e.g., buf lint with `buf breaking`), (b) integration test that decodes a golden message encoded with old schema using new schema and checks values, (c) Protolock (a dedicated Protobuf linter for breaking changes)?
- Follow-up: How does Google manage Protobuf schema compatibility across thousands of engineers? (Answer: .proto files in a central repo, strict review process for any change to field numbers, automated linting, and a rule that proto files are immutable once shipped externally -- new versions get new message names or new files.)

---

**Question 14 -- Varint encoding: the optimization that bites you on negative numbers**

Your service encodes a status field as a `sint32` in Protobuf. A new team member changes it to `int32` to match the integer type used in the database schema. The service is handling 200K QPS. After the change, CPU usage for encoding goes up 15% and average message size grows from 180 bytes to 220 bytes. The change involved a field that frequently holds negative status codes like -1 (unknown), -2 (error), -3 (timeout).

- Explain varint encoding and why the number -1 takes 10 bytes as an `int32` varint but only 2 bytes as a `sint32` (zigzag) varint. Derive the zigzag formula: `zigzag(n) = (n << 1) XOR (n >> 31)` for 32-bit. Show the encoding of -1 and -3 in both representations.
- At 200K QPS, the message grew by 40 bytes per message. Compute: daily bandwidth increase, monthly bandwidth cost at $0.01/GB, annual cost. Is this a trivial optimization or a meaningful budget line?
- Name the four Protobuf integer types and their wire cost for negative numbers: `int32` (always 10 bytes for negatives), `sint32` (zigzag, 1-2 bytes for small negatives), `fixed32` (always 4 bytes, no varint), `sfixed32` (always 4 bytes, signed). When would you use `fixed32` over `int32`? (Answer: when values are large uniformly-distributed integers like cryptographic hashes, where varint buys nothing and adds encoding overhead.)
- Follow-up: The field also holds large positive status codes in the range 1,000,000-9,999,999 (representing event type IDs). For `int32` varint, how many bytes do values in that range take? Is `fixed32` more efficient for that range? (Answer: values up to 268 million fit in 4 varint bytes, same as fixed32, so there is no benefit for that range specifically.)

---

**Question 15 -- Proto3 default values: the nullable semantics trap**

Your order service has a Protobuf field `int64 discount_amount = 5`. In the business logic, `discount_amount = 0` means "no discount." A consumer service is asked to display a "Discount Applied" badge only when a discount was actually set by the system, not just defaulted to zero. The consumer cannot tell the difference and shows the badge on orders where no discount was set.

- Explain the fundamental limitation: in Proto3, all scalar fields have a default of zero/empty/false. If a producer does not set a field, it is omitted from the wire. When the consumer decodes, it gets zero. The consumer cannot distinguish "producer set this to zero" from "producer never set this field."
- Present the `google.protobuf.Int64Value` wrapper solution: show the proto import and field definition. Explain the wire overhead (wrapper is an embedded message, adds 1-2 bytes). Show how the consumer checks for presence: `if (msg.hasDiscountAmount())` vs just reading the value.
- In Proto2, `optional` keyword gave explicit has-bit tracking. Explain how Proto2 solved this problem without wrapper types. Why did Proto3 remove required/optional in favor of all-optional with no has-bits? (Answer: Google's operational experience showed that `required` caused more breakage than it prevented, so Proto3 made all fields optional-and-trackless for simplicity.)
- Follow-up: Proto3 added `optional` keyword back in a later revision (proto3 optional). How does this work and how does it differ from Proto2 optional? (Answer: generates a has-bit via a synthetic oneof under the hood, same wire format as before but with generated `hasField()` accessor.)

---

**Question 16 -- Protobuf backward and forward compatibility: what is actually safe?**

Your team maintains a Protobuf schema for a shared `UserEvent` message used by 12 different services. A product request requires: (1) rename `user_name` to `display_name`, (2) remove `deprecated_session_token`, (3) change `event_count` from `int32` to `int64`, (4) add new field `experiment_ids` (a repeated string). Which changes are safe to do in a rolling deployment and which require a coordinated cutover?

- For each change, classify as safe/unsafe and explain the wire-level reason: (1) rename is safe for old readers (they see same field number), but new readers calling `display_name` get empty if reading old messages that populated `user_name` -- the data is there at the same field number but the generated accessor has changed; (2) field removal -- safe at wire level if field numbers are reserved, but old consumers will no longer populate the field; (3) `int32` to `int64` -- same varint wire type (0), safe promotion, widening; (4) adding a `repeated` field with no data is zero bytes on wire, safe.
- Change (1) is the trickiest: what does the wire actually look like for the old and new schema? The bytes for `user_name` sit at field number N. If `display_name` also uses field number N, new code reading old data gets the value correctly -- but only if the field number is identical. Confirm: renaming in Protobuf is safe AS LONG AS the field number does not change and the type does not change.
- Design a four-step process for removing `deprecated_session_token` safely across 12 services: (a) mark deprecated, (b) remove all write-side usage (no more producers setting it), (c) remove all read-side usage (consumers stop reading it), (d) add to `reserved`. What monitoring helps confirm no producer is still writing this field? (Answer: add a metric that counts non-zero occurrences of the field at consumers.)
- Follow-up: A service uses `unknown_fields` preservation to pass through fields it does not recognize. How does this interact with field removal? (Answer: if a relay service sits between producer and consumer and strips unknown fields on re-serialization, old data can be silently dropped -- this is a classic "thin relay" anti-pattern.)

---

**Question 17 -- gRPC: when HTTP/2 multiplexing becomes a liability**

Your microservices architecture uses gRPC for all internal communication. You have 20 client pods talking to 5 server pods behind an L4 load balancer (AWS NLB). Load tests show server pods are heavily imbalanced: two pods handle 70% of traffic, three handle 30%, and occasionally one pod hits CPU saturation while others are idle.

- Explain the root cause: HTTP/2 uses persistent connections. An L4 load balancer distributes TCP connections, not HTTP/2 streams. Each gRPC client establishes one connection per server. At startup, connections are distributed randomly. If 12 of 20 clients happen to connect to the same 2 servers first, those servers handle 60% of traffic -- and this distribution does not rebalance unless connections are re-established.
- Present the solution architecture using a service mesh or client-side load balancing: (a) client-side LB where the gRPC client resolves DNS to all server IPs and round-robins streams across them -- requires client configuration; (b) L7 proxy like Envoy or Istio sidecar that terminates HTTP/2 from the client and opens new HTTP/2 connections to backends, load-balancing at the stream level. Draw the connection topology for each.
- An alternative approach: use an L7 ALB (AWS ALB) instead of NLB. Explain how ALB handles HTTP/2: it terminates the client connection, then makes new backend connections, load-balancing at the request level. What is the overhead of this approach? (Answer: ALB adds ~1ms latency and cannot do bidirectional streaming because it must buffer the full request before forwarding.)
- Follow-up: You need bidirectional streaming gRPC (client and server both send continuous message streams). Which load balancing approaches work? (Answer: only client-side LB or a pass-through proxy that understands HTTP/2 streams works -- ALB-style L7 termination breaks bidirectional streaming.)

---

**Question 18 -- Protobuf schema governance: who owns the .proto files?**

Your platform has grown to 40 engineering teams. Twenty different `.proto` files define shared message types used across team boundaries. Three teams are now blocked: Team A wants to add a field, but it conflicts with a field being added by Team B. Team C has been waiting 6 weeks for a review of their schema change. Meanwhile, a fourth team deployed a schema change without review that broke two consumers.

- Design a schema governance model with clear ownership: (a) single Schema team that owns all shared protos (high consistency, bottleneck), (b) producing team owns the proto, consuming teams have veto rights (distributed, coordination cost), (c) schema registry with automated compatibility checking replaces human review for safe changes, human review required only for breaking changes. Evaluate each for a 40-team org.
- Describe the technical infrastructure for option (c): a CI check that runs `buf breaking` against a baseline version for every PR that touches a `.proto` file. Safe changes (add field, add enum value) pass automatically. Breaking changes (remove field, renumber) fail CI and require explicit sign-off from affected consumers.
- Schema changes often require coordinating producer and consumer deployments. Design a "schema change runbook" that teams must follow: (a) add field with default to proto, (b) merge, (c) update consumers to handle new field, (d) update producer to populate new field, (e) confirm all consumers are deployed before producer starts sending. How do you verify step (e) across 40 teams?
- Follow-up: Large companies (Google, Uber, LinkedIn) publish Protobuf schemas externally for partner integrations. How do they handle backward compatibility when external partners cannot be forced to update? (Answer: indefinite backward compatibility on external schemas, internal schemas can evolve faster, versioned packages for external releases.)

---

**Question 19 -- gRPC vs. REST: the honest comparison**

Your team is starting a new service that will be called by 8 internal services and 2 external partners. The tech lead wants to use gRPC for everything. A dissenting engineer argues REST+JSON is simpler and more debuggable. Give the principled comparison and a concrete recommendation.

- List gRPC's genuine advantages over REST+JSON for internal services: (a) strongly-typed contracts with code generation -- no hand-written HTTP client, no mistyped field names; (b) Protobuf payload -- 40-60% smaller, 3x faster to encode/decode; (c) HTTP/2 multiplexing and streaming; (d) generated server stubs enforce the contract. These are real, measurable benefits at 10K+ QPS.
- List gRPC's genuine disadvantages: (a) tooling friction -- you cannot `curl` a gRPC endpoint; debugging requires `grpcurl` or Postman with protobuf plugin; (b) browser clients cannot call gRPC directly without gRPC-Web and a proxy; (c) HTTP/2 requires TLS in most cloud environments, adding setup complexity; (d) external partners are unlikely to have Protobuf tooling. These are real costs.
- For the 2 external partners: the honest answer is REST+JSON with an OpenAPI spec. For the 8 internal services: gRPC is the right default IF you have a protobuf build system set up. Describe the hybrid architecture: gRPC internally, an API gateway that translates gRPC to JSON/REST for external partners (e.g., using grpc-gateway or Envoy transcoding).
- Follow-up: gRPC has four communication patterns: unary (one request, one response), server-side streaming, client-side streaming, bidirectional streaming. Give a concrete use case for each where the streaming pattern is genuinely better than polling REST, not just a different way to do the same thing.

---

**Question 20 -- Migrating from JSON to Protobuf: the zero-downtime playbook**

Your high-traffic payment processing service runs at 150K QPS between a producer and 6 consumers. It currently uses JSON over HTTP. You need to migrate to Protobuf to reduce bandwidth and CPU. You cannot take a downtime window. The migration must be invisible to users. Walk through the complete migration plan.

- Phase 1 -- dual encoding: producer sends BOTH formats in the response (e.g., `protobuf_payload` base64 in the JSON body, or content negotiation using `Accept: application/protobuf`). Why is content negotiation the cleaner approach? What header does the consumer send? How does the producer detect which format to return?
- Phase 2 -- consumer migration: describe the rollout order -- update consumers one at a time, verifying each one switches to Protobuf and decodes correctly before moving to the next. What metrics confirm successful migration for each consumer? (Answer: track parse error rate and encoding type breakdown in the consumer's telemetry.)
- Phase 3 -- producer cutover: once all consumers are on Protobuf, the producer drops JSON support. What is the risk at this moment? (Answer: a consumer that was missed in the audit is still expecting JSON -- it will break.) How do you find missed consumers? (Answer: monitor request logs for any consumer still sending `Accept: application/json` or not sending the Protobuf accept header.)
- Follow-up: The migration takes 6 weeks. During that time, the producer must maintain both JSON and Protobuf serialization code. What is the operational risk of this dual-maintenance period? (Answer: a bug fix or schema change made in one serializer may not be mirrored in the other, leading to format divergence -- add a property-based test that encodes a message in both formats and verifies round-trip equivalence.)

---

### Section C: Avro and Schema Registry (Q21-Q28)

---

**Question 21 -- Schema-on-read: the power and the danger**

Your Kafka pipeline was started 18 months ago with schema version 1 (5 fields). Today, schema version 8 is in use (12 fields, 3 fields removed, 2 fields renamed via aliases). A new data science team wants to query historical events going back 18 months. They write a Spark job that reads all Kafka offsets from day one using the current schema (version 8).

- Explain schema-on-read: in Avro, the schema used at read time can be different from the schema used at write time. The Avro library runs resolution between the writer schema (fetched from the registry by the schema ID embedded in each message) and the reader schema (version 8). Walk through resolution for a message written with schema v1 that has fields the reader does not expect and is missing fields the reader wants.
- Fields removed between v1 and v8: the writer sends them, the reader's schema does not include them. Avro silently skips those bytes. Is data lost? (Answer: the data is in the bytes, not surfaced by this reader -- another reader with a different schema could read them. They are not corrupted, just not presented.)
- Fields added between v1 and v8: the reader wants them, the writer did not send them. Avro uses the reader schema's default value. If any of these fields have no default, what happens? (Answer: AvroTypeException -- deserialization fails for those messages. This is why FULL_TRANSITIVE compatibility mode requires defaults on all new fields going back to v1.)
- Follow-up: How would you validate, before running the full Spark job, that all 18 months of messages can be safely deserialized with the current schema? (Answer: sample-based validation -- read 1000 messages from each month, attempt deserialization, capture and inspect failures. Fix defaults and run the full job only after sample passes.)

---

**Question 22 -- Confluent Schema Registry internals: how the compatibility check works**

A new engineer needs to register a schema change for the `checkout-events-value` subject in your production Schema Registry. The change adds a new required field (no default). They are surprised when the Registry rejects it. Explain exactly what the Registry checks and how it decides to reject.

- Walk through the Registry's compatibility check algorithm for FULL mode: fetch all registered versions for the subject, for each registered version run forward-compatibility check (old schema can read new schema's data) and backward-compatibility check (new schema can read old schema's data). Where in this algorithm does the missing default cause failure?
- The Registry stores schemas in a Kafka topic called `_schemas`. Explain the structure of this topic: each message is a key (subject name + version number) and value (the full schema JSON). Why is a Kafka topic used rather than a relational database? (Answer: Kafka provides durability, replication, and ordered log -- Registry instances replay the topic to rebuild their in-memory state on startup. This is the same event sourcing pattern used in other distributed systems.)
- The engineer asks: "Can I override the compatibility mode just for this one registration?" Yes -- the Registry allows per-subject and global compatibility settings. Explain the risk of temporarily switching the subject to NONE mode, registering the breaking schema, then switching back. (Answer: any producer or consumer that deploys during the NONE window could register or receive an incompatible schema, and the protection is gone for those concurrent operations.)
- Follow-up: The Registry also supports schema normalization and canonicalization. Explain why `{"type":"record","name":"User","fields":[{"name":"id","type":"long"}]}` and `{ "name" : "User" , "type" : "record" , "fields" : [ { "type" : "long" , "name" : "id" } ] }` are the same schema. How does the Registry detect this to avoid registering duplicate schemas?

---

**Question 23 -- Avro vs. Protobuf for event streaming: the definitive comparison**

Your team is adopting Kafka for a new event streaming platform. You must choose between Avro and Protobuf for message encoding. You have 15 producer services and 40 consumer services. Events must be queryable in a data lake. Give the full analysis.

- Message size: Avro is typically 5-10% smaller than Protobuf for the same data because it has zero per-field overhead (no tags) vs. Protobuf's 1-2 byte tag per field. For a 20-field event at 200K QPS, compute the bandwidth difference. Is it material?
- Schema evolution: both support backward/forward compatibility but through different mechanisms. Avro uses field-name matching and requires defaults; Protobuf uses field-number tagging and zero-value defaults. Which is safer in practice? (Answer: Avro is stricter about requiring explicit defaults, which catches more compatibility mistakes at schema registration time. Protobuf's zero-value default for unset fields can silently hide missing data.)
- Tooling ecosystem: Avro has first-class support in Confluent Schema Registry, Spark, Hive, Flink, Presto, and BigQuery. Protobuf has first-class support in gRPC, Google Cloud Dataflow, and BigQuery (limited). If your consumers include both Java microservices AND a Spark analytics pipeline, which format has fewer integration surprises?
- Follow-up: A third option is Protobuf with Confluent Schema Registry's Protobuf serializer. This gives you Protobuf encoding with Registry-managed compatibility checks. Describe the tradeoff: you get Protobuf's gRPC compatibility and code generation discipline, but the Registry compatibility check for Protobuf is less mature than for Avro. When would you choose this hybrid?

---

**Question 24 -- Schema Registry in multi-team environments: subject ownership**

You have 30 Kafka topics shared across 8 teams. The Schema Registry has global compatibility set to BACKWARD. Team A owns the `order-created-value` subject and has just registered version 7. Team B, a consumer of this topic, discovers that version 7 broke their deserialization (a field they depended on was removed without a deprecation period).

- Explain how a field removal can pass BACKWARD compatibility check but still break a consumer. (Answer: BACKWARD means "new schema can read old data." It checks that the new schema, when reading an old message, can resolve all fields. It does NOT check that old consumers reading new messages can handle the removed field. That is FORWARD compatibility. If the Registry is set to BACKWARD only, forward breaks are not caught.)
- Design the Registry configuration for this team structure: (a) global default FULL mode, (b) per-subject overrides for specific topics that need looser rules (e.g., NONE for internal scratch topics), (c) a schema change proposal process requiring consumer team sign-off before a breaking change is registered. What tooling supports step (c)? (Answer: a schema change CI workflow that lists all consumers of a subject via topic subscription metadata and notifies their repositories via GitHub PR comment.)
- Team B asks: "We want to be notified before any change to schemas we consume." Design this notification system. What data does the Registry expose that makes this possible? (Answer: Registry exposes consumer group membership via Kafka admin API -- you can list which consumer groups read each topic and map those to teams via a service catalog.)
- Follow-up: FULL_TRANSITIVE vs. FULL: when does the distinction matter? Give a concrete scenario where FULL passes but FULL_TRANSITIVE fails. (Answer: Schema v5 is compatible with v4 (FULL passes), but v5 is not compatible with v2 because v2 did not have a default for a field added in v3. A consumer still on v2 (because they skipped upgrades) will fail on v5 messages. FULL_TRANSITIVE would have caught this at v3 registration time.)

---

**Question 25 -- Avro schema resolution edge cases: aliases and type promotions**

Your team needs to rename the field `userId` to `user_id` (camelCase to snake_case standardization) and change `amount` from `int` to `long` (to handle larger values) in a live Avro event stream. Both changes seem straightforward. Walk through the complete safe migration for each.

- Rename using aliases: the new schema renames `userId` to `user_id` and adds `"aliases": ["userId"]` to the field. Explain the resolution: old messages have a field named `userId` -- the reader looks for `user_id`, does not find it, then checks aliases, finds `userId`, matches. New messages have `user_id` -- direct match. Show the Avro schema JSON for both old and new. What happens to a consumer that still has the old schema reading a new message (which has `user_id` not `userId`)? (Answer: the old reader looks for `userId`, does not find it in the new message, uses the old schema's default if any -- the rename must be symmetric, adding alias to BOTH directions or using FULL_TRANSITIVE mode to verify.)
- Type promotion from `int` to `long`: Avro spec allows `int` -> `long` as a safe promotion. Show what the wire difference is: Avro uses zigzag varint for both -- the wire bytes for a small integer are identical in int and long. What is the risk for very large `long` values being read by a consumer with the old `int` schema? (Answer: if the long value exceeds `Integer.MAX_VALUE` (2^31 - 1), the old schema will overflow or error on resolution.)
- Describe a migration sequence that is safe during a rolling deployment where some producers and consumers are on v1 and some are on v2: (a) register new schema with alias + type promotion in Registry under FULL_TRANSITIVE, (b) Registry validates all previous versions can read new messages and new schema can read all previous messages, (c) deploy consumers first (they can read both old `userId/int` and new `user_id/long`), (d) deploy producers.
- Follow-up: Avro supports logical types: `"logicalType": "date"` on an `int`, `"logicalType": "timestamp-millis"` on a `long`. If you change a plain `int` field to an `int` with a `date` logical type, is this a breaking change? (Answer: the wire encoding is identical -- both are zigzag varints. Whether this is breaking depends on whether consumers use the logical type annotation -- some ignore it, some enforce it. Treat it as potentially breaking and verify with consumers.)

---

**Question 26 -- Schema Registry high availability: designing for the failure case**

Your production Kafka cluster processes 500K messages/sec. All messages use Avro with Confluent Schema Registry. The Schema Registry is a single instance running on a VM. The platform architecture review flags this as a single point of failure. Design the HA Schema Registry setup and explain the failure modes.

- Confluent Schema Registry stores its state in a Kafka topic (`_schemas`). Because of this, multiple Registry instances can run concurrently -- they all read from and write to the same Kafka topic. Draw the architecture: 3 Registry instances behind a load balancer, all consuming from `_schemas`. Explain leader election: Schema Registry uses a leader-follower model within the cluster, where only the leader handles writes (schema registrations) and all nodes handle reads. How is the leader elected? (Answer: via ZooKeeper or Kafka's own group coordination, depending on version.)
- Consumer caching is the key availability mechanism. Explain: a consumer that has seen schema ID 42 caches it in-memory for the process lifetime. If the Registry goes down, that consumer can continue deserializing messages with schema ID 42 indefinitely. What breaks? (Answer: only new schema IDs never seen before -- if a new producer version registers schema ID 43 and a consumer has never fetched it, the consumer fails on those messages until the Registry is restored.)
- Design the failure mode matrix: (a) Registry down, all schemas cached -- producers and consumers continue normally; (b) Registry down, new schema needed -- producers cannot register, block until Registry returns; (c) Registry down, new message with unknown schema ID arrives at consumer -- consumer drops message or sends to dead-letter queue. What is the correct handling for (c)?
- Follow-up: Some teams implement a "schema cache warm-up" on consumer startup: on boot, the consumer pre-fetches all schemas from the Registry for all subjects it subscribes to. What is the risk of this approach? (Answer: if a new message with a new schema ID arrives before the consumer fetches that schema, the consumer still fails. Pre-fetching reduces the cache miss window but does not eliminate it. The correct solution is to pre-fetch schemas for all registered versions of each subject, not just the latest.)

---

**Question 27 -- Kafka + Avro end-to-end: tracing a message from producer to consumer**

Describe the complete lifecycle of a single Avro-encoded Kafka message, from the moment application code calls `producer.send()` to the moment the consumer application code receives the deserialized object. Include every interaction with the Schema Registry, every byte on the wire, and every cache lookup.

- Producer side (5 steps): (1) application creates an Avro object `UserCreated{user_id=42, email="alice@example.com"}`; (2) Avro serializer checks its local schema cache -- schema registered? Yes, schema_id=17; (3) Avro serializer encodes the object using schema 17: raw Avro bytes (no tags, just values in schema order); (4) serializer prepends magic byte `0x00` and schema_id 17 as 4-byte big-endian `0x00000011`; (5) Kafka client sends the full bytes to the Kafka broker. Show the byte layout.
- Kafka broker: the broker is schema-agnostic. It sees an opaque byte array with a key and value. It stores it in the partition log. Explain: the broker does NOT validate the schema, does not talk to the Registry, does not parse the Avro content. This is by design -- the broker is transport-layer only.
- Consumer side (5 steps): (1) consumer polls message from Kafka, receives raw bytes; (2) Avro deserializer reads byte 0 -- `0x00` confirms Confluent format; (3) reads bytes 1-4 -- schema_id=17; (4) checks local cache -- hit or miss? If miss, GET `http://registry/schemas/ids/17`, cache result; (5) runs schema resolution with writer schema (id=17) and reader schema (consumer's registered schema), delivers deserialized object. Show which step adds latency and why the first message for a new schema ID is slower.
- Follow-up: The consumer's reader schema is version 3 of `UserCreated`. The message was encoded with writer schema version 1 (two fields fewer). Walk through the resolution: what fields are missing from the wire, where do the defaults come from, what does the consumer's object look like after resolution?

---

**Question 28 -- Avro for data lake storage vs. Kafka streaming: different requirements**

Your team uses Avro for both Kafka event streaming (via Schema Registry) and for data lake storage in S3 (Avro Object Container Files). A review reveals the two uses have different requirements that are creating operational friction. Analyze and design the right approach for each use case.

- Kafka streaming requirement: schema must be retrievable without the file, because messages are individual and cannot carry the full schema. Schema ID in the message header pointing to Registry is the right design. Schema evolution must be safe for rolling deployments.
- Data lake storage requirement: the file must be self-contained and readable years later even if the Schema Registry is decomissioned or unavailable. Avro Object Container Files embed the schema in the file header. Explain why this is the correct format for long-term storage and how the embedded schema enables reading files without any external dependency.
- The friction: producers write to Kafka using the Confluent 5-byte header (magic + schema_id). A downstream job reads from Kafka and writes to S3 as Avro Object Container Files. Show how this translation job works: (a) read message from Kafka, (b) strip the 5-byte Confluent header, (c) fetch the writer schema from Registry using the schema_id, (d) write Avro OCF to S3 with the schema embedded in the file header.
- Follow-up: A year later, the team wants to query S3 Avro files using Athena. Athena does not natively support Avro as efficiently as Parquet. Design the storage pipeline evolution: produce Kafka -> Avro OCF in S3 (raw layer) -> Spark job converts to Parquet with explicit schema (analytics layer). What schema governance is needed to ensure the Parquet schema matches the current Avro schema?

---

### Section D: Parquet and Columnar Formats (Q29-Q34)

---

**Question 29 -- Predicate pushdown: the optimization that makes Parquet fast**

A Spark job reads a 5TB Parquet dataset in S3 containing e-commerce order events. The query filters `WHERE country = 'DE' AND order_date >= '2024-01-01'`. Without any optimization, Spark would read all 5TB. With Parquet predicate pushdown, it reads approximately 200GB. Explain the mechanism that achieves this 25x reduction.

- Row group statistics: each Parquet file has a footer containing, for each row group, the min and max value of every column. Explain how a filter `country = 'DE'` can be evaluated against these statistics without reading any actual row data. If a row group has `min_country = 'US', max_country = 'US'`, can it be skipped? Yes. If it has `min_country = 'CA', max_country = 'FR'`, can it be skipped? Yes (DE is not in range). If it has `min_country = 'AU', max_country = 'ZZ'`, can it? No -- DE falls within this range.
- Column chunk statistics: within a row group, each column chunk also has min/max. Once a row group passes the row group filter, the query engine uses column chunk statistics to skip page groups. Explain the hierarchy: file footer -> row group stats -> column chunk stats -> data pages. At what level does predicate pushdown operate for Spark vs. for Parquet native readers?
- Dictionary encoding interaction: the `country` column likely uses dictionary encoding (small set of distinct values). Explain how the dictionary itself (a small lookup table stored at the beginning of the column chunk) can be evaluated against the predicate before reading any data pages. If the dictionary for a column chunk contains `{US, UK, CA}` and the filter is `country = 'DE'`, the entire column chunk can be skipped without reading data pages.
- Follow-up: Predicate pushdown works well for equality and range filters. What query patterns does it NOT help with? (Answer: `LIKE '%germany%'` substring matches cannot be evaluated from min/max stats; aggregations without WHERE clauses must read all data; JOINs cannot be pushed down into individual files unless broadcast joins are used.)

---

**Question 30 -- Row groups: size tuning and its impact on query performance**

A Parquet file is written with the default row group size of 128 MB. A DBA argues for 512 MB row groups to "improve compression." An engineer argues for 32 MB row groups for "better parallelism." Your Spark cluster has 100 executors, each with 4GB of memory. The dataset is 10TB.

- Explain the read-side impact of row group size: each row group is the unit of work for predicate pushdown. Larger row groups mean fewer, larger chunks to skip. Explain the tradeoff: a 512 MB row group that passes the predicate pushdown filter requires reading 512 MB, even if only 10% of rows match the actual WHERE clause (within the row group). Smaller row groups allow finer-grained skipping.
- Explain the write-side impact: row groups are buffered in writer memory before being flushed. A 128 MB row group requires roughly 128 MB of writer-side memory. A 512 MB row group requires 512 MB per writer thread. For a Spark write job with 100 partitions, what is the peak memory requirement for 512 MB vs. 128 MB row groups?
- The parallelism argument: when Spark reads a Parquet file, it typically creates one task per row group (or per file, if the file has one row group). With 512 MB row groups in a 10 TB dataset: approximately 20,000 row groups -> 20,000 potential tasks. With 128 MB row groups: approximately 80,000 tasks. Given 100 executors with 4 tasks each (400 concurrent tasks), which row group size gives better cluster utilization?
- Follow-up: A specific query pattern is "give me all orders from user_id = 42." If the Parquet files are sorted by `order_date` (time-partitioned), rows for user 42 are scattered across many row groups -- predicate pushdown does not help much. What file organization (sorting by user_id, or a secondary sort) would help this query? What is the cost of re-sorting the data?

---

**Question 31 -- Parquet compression codecs: Snappy vs. Gzip vs. Zstd**

Your data lake stores 3PB of Parquet data in S3. Storage cost is $0.023/GB/month. Compute cost for writing data (Spark EMR clusters) is significant. You are evaluating whether to change the compression codec from Snappy to Zstd. Give the engineering analysis.

- Compare the three codecs on the dimensions that matter for a data lake: (a) compression ratio (Gzip typically 30-40% better than Snappy, Zstd level 3 matches Gzip ratio with 3-5x faster decompression), (b) CPU cost at decompression time (Snappy is fastest, Gzip is slowest, Zstd sits in between but is tunable by level), (c) splittability (all three are splittable at the Parquet page level within a row group, so this is not a differentiator for Parquet unlike for raw files).
- Compute the storage cost difference at 3PB between Snappy and Zstd: assume Snappy achieves 3x compression on the raw data (1PB compressed), Zstd level 3 achieves 4x (750TB compressed). Monthly savings: 250TB * $0.023/GB = $5,750/month. Annual: $69,000. Is this worth the migration cost?
- The compute cost question: if Zstd decompression is 2x faster than Gzip but 30% slower than Snappy, and your Spark queries are CPU-bound on decompression, switching from Snappy to Zstd saves storage but may increase query costs. How do you measure whether the query CPU cost increase offsets the storage savings?
- Follow-up: Parquet also supports page-level compression with ZSTD_DICTIONARY mode, which combines Zstd compression with pre-built dictionaries shared across pages in a column chunk. When does this help significantly? (Answer: when column values repeat frequently across pages but the per-page dictionary would miss cross-page correlations. Useful for columns with limited global cardinality but high local cardinality.)

---

**Question 32 -- Columnar vs. row-based storage: when columnar loses**

A team proposes migrating their OLTP (online transaction processing) database from PostgreSQL (row-based) to a columnar database because "columnar is faster." You have to explain when this is wrong.

- Write pattern analysis: in a row-based database, inserting a new row is one sequential write (the whole row is written together). In a columnar database, inserting a new row means writing one value to each column file. For a 50-column table, a single row insert becomes 50 separate write operations. Explain why this makes columnar formats terrible for high-frequency single-row inserts (OLTP).
- Read pattern analysis: an OLTP query like `SELECT * FROM orders WHERE order_id = 12345` needs all columns for one row. In a columnar store, this requires reading one page from each of 50 column chunks. In a row store, this is one sequential read of the row. For "fetch one complete record" queries, row-based is dramatically faster.
- The actual use case for columnar: `SELECT country, SUM(amount) FROM orders GROUP BY country` -- reads 2 columns out of 50, across all rows. Columnar reads only those 2 columns; row-based must scan all 50. For analytics, columnar wins. For OLTP, row wins. This is why the industry has OLTP (PostgreSQL, MySQL) and OLAP (ClickHouse, Snowflake) as separate categories.
- Follow-up: Some databases (ClickHouse, DuckDB, SAP HANA) offer columnar storage for analytics workloads as a first-class database product. Compare Parquet files on S3 to a ClickHouse table: Parquet is a file format (read via Spark/Athena/Presto, no server required), ClickHouse is a database (server required, supports real-time inserts, richer query planner). When would you use each?

---

**Question 33 -- Parquet schema evolution: reading files written with older schemas**

Your data lake has 3 years of Parquet files. Schema version 1 had 8 columns. Schema version 4 (current) has 14 columns. A Spark job needs to read all 3 years of data into one DataFrame with the current 14-column schema.

- Explain how Parquet handles missing columns during read: unlike Avro (which embeds resolution in the format spec), Parquet's schema evolution is handled by the reader (Spark). When Spark reads a file that lacks a column present in the target schema, it fills that column with `null` by default. Show this in a Spark read configuration: `spark.read.option("mergeSchema", "true").parquet("s3://...")`.
- `mergeSchema` mode: when enabled, Spark reads the schema footer from each Parquet file and merges all schemas to create a superset schema. For 3 years of files with 4 different schemas, what does the merged schema look like? What is the performance cost of `mergeSchema`? (Answer: Spark must read the footer of every file to determine the schema before reading any data -- for a dataset with millions of files, this footer scan takes significant time.)
- Type conflicts: schema version 1 has `user_id` as `int32`. Schema version 3 changed it to `int64`. When Spark merges these schemas, it sees conflicting types for the same column. Explain Spark's behavior: it promotes to the wider type (`int64`) if it is a safe promotion, but if the types are incompatible (e.g., `int` vs `string`), the merge fails. How do you handle this operationally?
- Follow-up: Rather than `mergeSchema`, a better practice is to manage schema versions explicitly: store each schema version in a Hive metastore or AWS Glue catalog, and use the catalog schema (not file-inferred schema) as the authoritative definition. How does this change the Spark job? (Answer: Spark reads from the catalog schema, maps Parquet columns by name, fills missing with null. No footer scan needed for schema -- just for data. Performance is significantly better.)

---

**Question 34 -- Parquet vs. Avro for the landing zone: the format selection decision**

Your data pipeline writes raw events from Kafka to S3 (the "landing zone"), then transforms them into an analytics-ready layer. You must choose between Avro and Parquet for the landing zone. Make the decision with full justification.

- Avro advantages for landing zone: (a) row-based format -- writing one event at a time is efficient, no need to buffer a row group of 128MB before flushing; (b) schema embedded in Avro OCF files -- self-describing without external catalog; (c) streaming write support in Spark Structured Streaming and Flink out of the box; (d) easy to append new events (add to end of file or write new files). Avro was designed for streaming writes; Parquet was designed for batch writes.
- Parquet disadvantages for landing zone: (a) row group buffering -- to get good Parquet files (128MB+ row groups), you must buffer events in memory before flushing, introducing latency; (b) small Parquet files (from frequent flushes) have high overhead per row group and poor predicate pushdown efficiency; (c) Parquet optimized for read performance, not write throughput.
- The landing zone recommendation: use Avro for the landing zone (streaming writes, one-event-per-message semantics), then run a periodic compaction job (hourly or daily) that reads Avro and writes Parquet to the analytics layer. This gives you write-optimized landing storage and read-optimized analytics storage.
- Follow-up: Delta Lake and Apache Iceberg are table formats built on Parquet that add streaming write support via transaction logs. Explain how Delta Lake solves the small-files problem: writes go to small Parquet files, a background `OPTIMIZE` command compacts them into larger files while the log tracks which files are "current." Does this change your landing zone recommendation? (Answer: if you are already investing in Delta Lake or Iceberg, you can write directly to the analytics layer; if you are not, Avro landing + Parquet analytics remains the simpler pattern.)

---

### Section E: Schema Evolution Strategy (Q35-Q42)

---

**Question 35 -- Backward vs. forward vs. full compatibility: making the right choice per topic**

Your Kafka cluster has three types of topics: (1) `payment-events` -- critical, used by compliance and fraud, consumed by services that rarely upgrade; (2) `analytics-events` -- internal, consumers upgrade frequently; (3) `experiment-flags` -- producers change frequently, consumers must always be backward compatible. Map each topic to the correct compatibility mode with justification.

- `payment-events` justification: consumers rarely upgrade means you may have consumers 3-4 schema versions behind. FULL_TRANSITIVE is required -- every new schema version must be readable by every previous consumer version, not just the immediate predecessor. Any field added must have a default (for backward compat), and no field that an old consumer depends on can be removed (for forward compat).
- `analytics-events` justification: if both producers and consumers upgrade frequently and you control the deployment order (consumers first), BACKWARD is sufficient. The new schema can always read old data (because old messages still exist in Kafka), and new consumers are deployed before new producers. But if deployment order is not controlled, FULL is safer.
- `experiment-flags` justification: producers change frequently (new experiment flags added constantly), consumers must handle new flags gracefully (ignore unknown flags). This is the definition of FORWARD compatibility -- the old consumer (old schema) must be able to read data from the new producer (new schema). If experiment flags are also read far in the past, consider FORWARD_TRANSITIVE.
- Follow-up: A team argues "just use FULL_TRANSITIVE for everything -- it is safest." What is the operational cost of FULL_TRANSITIVE? (Answer: every new schema must be compatible with ALL previous versions. Adding a field requires a default. Removing a field is nearly impossible without a long deprecation period. Teams move slower. For internal high-churn topics, this is too restrictive. Use the minimum necessary compatibility mode per topic.)

---

**Question 36 -- Zero-downtime schema evolution: the four-phase deployment pattern**

Your team maintains a `UserProfile` message used by 8 services. You need to add a field, change a field's type, and eventually remove a deprecated field. Design the complete multi-phase deployment that achieves all three changes with zero downtime and no required service coordination.

- Phase 1 -- add new field with default: register new schema version with `loyalty_tier` field, default `"STANDARD"`. Deploy producers first or consumers first? (Consumers first -- backward compat means new schema reads old data. Consumers deployed to handle `loyalty_tier = "STANDARD"` default. Then producers start populating the field.) Timeline: deploy consumers, wait for full rollout (could be days), deploy producers.
- Phase 2 -- type change (int to long for `order_count`): same varint wire type in Protobuf, safe promotion. Register new schema. Deploy consumers (new readers can decode long where they used to expect int, within range). Deploy producers (start sending long values). What is the risk if a producer sends a long value exceeding `Integer.MAX_VALUE` before consumers are updated? (Answer: overflow or decode error on old consumers. Mitigate by monitoring: alert if `order_count` exceeds 2 billion before all consumers are updated.)
- Phase 3 -- remove deprecated field `legacy_referral_code`: stop all producers from writing this field first. Monitor for 30 days to confirm no producers write it (use consumer-side telemetry: count messages where `legacy_referral_code` is non-empty). After confirmed empty, remove from consumer code. After confirmed no consumer reads it, add to `reserved` and remove from schema. Register new schema version.
- Follow-up: This four-phase process takes months for one set of changes. Design a schema change fast-track for emergency changes (e.g., a security field must be added immediately). What conditions justify skipping phases? What are the risks? (Answer: emergency additions with defaults can be single-phase if you accept a brief window of missing defaults. Removals can never be fast-tracked safely.)

---

**Question 37 -- Cross-service schema contracts: who owns the schema?**

Your company has a `OrderCreated` event produced by the Order Service and consumed by 9 downstream services: Inventory, Shipping, Analytics, Finance, Fraud, Customer Notifications, Loyalty, Returns, and a Partner Integration service. The Order Service wants to rename `customer_id` to `user_id`. Each of the 9 consumers has business logic tied to `customer_id`. Who owns the schema, who approves the change, and how is the migration executed?

- Ownership models: (a) producer-owned schema -- Order Service decides, notifies consumers, consumers must adapt; (b) consumer-driven contracts -- each consumer publishes its requirements, producer must satisfy all of them; (c) shared ownership via schema committee -- cross-team review. Argue for consumer-driven contracts (Pact-style) for this scenario: it makes consumer requirements machine-checkable, catches breaking changes in CI before deployment.
- The rename migration: in Avro, rename using aliases (safe). In Protobuf, rename is safe at wire level (field number unchanged) but generated accessor changes name. For each consumer service, the impact of the rename: they must update their code to use `user_id` instead of `customer_id` -- this is a code change, not just a schema change. Who coordinates 9 code changes across 9 teams?
- Design the migration tracking system: (a) a shared document listing each consumer's adoption status, (b) a Kafka consumer group lag metric per service (if a service has stopped consuming, they may have broken), (c) a feature flag or schema version negotiation that lets the producer serve both field names simultaneously during the transition.
- Follow-up: The Partner Integration service consumes `OrderCreated` events and forwards them to 3 external partners who have hardcoded `customer_id` in their parsers. The rename cannot happen until all 3 external partners update their code -- which may take 6-12 months. How do you manage this extended parallel period? (Answer: maintain two Kafka topics -- `order-created-v1` with old schema and `order-created-v2` with new schema -- and a fanout job that writes to both. Shut down v1 only after all external partners have migrated.)

---

**Question 38 -- Schema versioning strategies: URL versioning vs. header versioning vs. content negotiation**

Your REST API has been live for 2 years with 150 enterprise customers. The current schema (`v1`) has accumulated technical debt: inconsistent field naming, missing fields, and a response structure that makes it hard to add new resource types. You must design `v2` with breaking changes. Choose and justify your versioning strategy.

- URL versioning (`/v1/orders`, `/v2/orders`): most common and most explicit. Pros: crystal clear to clients which version they are on, each version can have completely different implementation, easy to deprecate by monitoring which version traffic. Cons: duplicate route handling in code, clients must actively migrate. For enterprise APIs where customers are slow to migrate, this is the correct choice.
- Header versioning (`API-Version: 2024-01`): API has one URL, behavior determined by request header. Pros: clean URLs, allows granular feature versioning by date. Cons: difficult to test (cannot just change URL in browser), harder for API gateways and caches to route intelligently, clients may not set headers consistently. Used by Stripe and GitHub.
- Content negotiation (`Accept: application/vnd.myapi.v2+json`): industry standard approach. Pros: RESTfully correct, works with HTTP caching semantics. Cons: complex for clients to implement, not widely understood. Rarely used in practice outside very standards-heavy organizations.
- For enterprise with slow migration: URL versioning with a sunset policy. Define `v1` sunset date (minimum 18 months out), provide automated migration tooling, track `v1` vs `v2` usage per customer, offer guided migration support for top 20 customers. After sunset, `v1` returns `410 Gone` with a migration guide URL in the body.
- Follow-up: During the `v1`/`v2` parallel period, how do you avoid maintaining two separate codebases? Design an internal architecture where both `/v1` and `/v2` map to the same business logic, with request/response transformation layers that translate between external schema versions and the internal canonical model. What design patterns support this? (Answer: adapter pattern at the API boundary, canonical internal representation, per-version transformer classes.)

---

**Question 39 -- Compatibility mode transitions: changing the Registry setting**

Your team has been running the Schema Registry with BACKWARD compatibility for 2 years. You now realize you need FULL_TRANSITIVE (because consumers far behind in upgrades are breaking on new schemas). Changing the compatibility mode for an existing subject is easy -- one API call. But the existing registered schemas may not satisfy FULL_TRANSITIVE when checked retroactively. How do you safely make this transition?

- Retroactive compatibility check: when you change a subject from BACKWARD to FULL_TRANSITIVE, the Registry does NOT retroactively validate all existing schema versions against each other. The new mode only applies to future registrations. Explain the risk: you now have schemas 1-50 registered under BACKWARD. Some pairs (e.g., v40 vs v20) may not be FULL_TRANSITIVE compatible. You will not know until a consumer on v20 tries to read v50+ data and fails.
- Auditing existing schemas: design a script that checks all existing schema pairs for FULL_TRANSITIVE compatibility using the Registry's compatibility check API (`POST /compatibility/subjects/{subject}/versions/{version}`). For a subject with 50 versions, this is 50*49/2 = 1225 compatibility checks. What are the incompatible pairs, and what do you do about them?
- Forward path: once you identify incompatible pairs, the options are: (a) acknowledge the risk and rely on consumer version monitoring to ensure no consumer is far enough behind to hit an incompatible pair, (b) create a new schema subject (`orders-events-v2`) starting fresh under FULL_TRANSITIVE mode, migrate producers and consumers to the new subject. Option (b) is cleaner but requires coordinating a topic migration.
- Follow-up: Some teams adopt a "schema contract testing" approach instead of relying on Registry compatibility modes: write explicit tests that encode a message with each writer schema version and decode it with each reader schema version, asserting no errors and correct field values. This catches compatibility issues the Registry's mode-based check might miss (e.g., semantic breaking changes that are structurally valid). How do you scale this across 20 schema subjects each with 30 versions?

---

**Question 40 -- Wire format vs. storage format: different requirements, different choices**

A senior engineer makes the claim: "We should use the same format everywhere -- Avro for Kafka AND for our S3 data lake AND for our internal REST APIs." Challenge this claim by analyzing the distinct requirements of wire formats (service-to-service) vs. storage formats (data lake).

- Wire format requirements: low serialization latency (milliseconds matter), compact encoding per message (thousands of messages per second), schema must be external (cannot embed per-message, too expensive), support for streaming (message-at-a-time, not batched), forward/backward compatibility during rolling deployments. Avro and Protobuf are both good fits.
- Storage format requirements: high compression ratio (TB to PB scale, storage cost matters), efficient column-level reads for analytics (aggregation queries skip irrelevant columns), schema must be self-contained in the file (readable years later without external dependency), optimized for batch reads (thousands of rows per I/O operation, not one at a time), support for partition pruning and predicate pushdown. Parquet and ORC are designed for this; Avro is not.
- REST API requirements: human readability for external developers, universal tooling (curl, Postman, browser devtools), no special decoder needed, schema documentation via OpenAPI. JSON is the right choice; Avro and Protobuf are wrong for external APIs.
- The correct answer: use the right format for each context. Avro for Kafka streaming, Parquet for S3 analytics, JSON for external REST APIs. A translation layer between contexts (Kafka -> S3: Avro to Parquet conversion job; internal API gateway: Protobuf to JSON transcoding). The cost of translation is small compared to the benefit of each format being optimal for its context.
- Follow-up: Apache Iceberg and Delta Lake use Parquet as the underlying file format but add a transaction log that supports streaming writes. Does this change the analysis? (Answer: somewhat -- you can now write to Parquet in a streaming pattern, solving the "Parquet requires large row group buffers" problem. But the REST API and Kafka encoding decisions are unaffected.)

---

**Question 41 -- Binary vs. text format trade-offs: the debugging argument**

The infrastructure team proposes standardizing on Protobuf for all 200 internal services. A senior operations engineer objects: "When something goes wrong at 3am, I need to read the raw messages in the logs. With Protobuf, I see binary garbage. JSON, I can read it immediately." This is a legitimate concern. How do you address it without abandoning binary efficiency?

- The 3am readability problem is real: in a JSON world, `grep "user_id.*12345" /var/log/service.log` finds the relevant request immediately. In a Protobuf world, you see raw bytes in the log that require a decoder with the `.proto` file. Acknowledge this is a genuine operational cost.
- Tooling solutions: (a) `protoc --decode` with the proto file can decode Protobuf from stdin; (b) `grpcurl` can call gRPC endpoints and format responses as JSON; (c) build a log viewer that automatically decodes Protobuf fields using registered schemas, presented as JSON in the log UI. Evaluate each by the constraint: a new on-call engineer at 3am must be able to use it without prior training.
- Architecture solution: log at the application level in JSON (after decoding), not at the wire level. The service decodes the incoming Protobuf message immediately, then logs the decoded struct as JSON for observability. The Protobuf encoding is only on the wire -- logs are always human-readable JSON. This is the standard pattern: binary on the wire, JSON in logs and traces.
- Follow-up: Distributed tracing (OpenTelemetry) captures request/response context. In a gRPC system, tracing can automatically serialize the request and response Protobuf as JSON in the trace payload using the protobuf JSON mapping. How does this work? (Answer: all Protobuf messages can be serialized to canonical JSON using the Protobuf JSON format spec. Tracing libraries do this automatically for gRPC spans. The developer sees JSON in Jaeger or Tempo without any extra work.)

---

**Question 42 -- Schema versioning for machine learning models: the feature store problem**

Your machine learning platform uses a feature store that serves features as JSON to model training and inference. The fraud detection model was trained on features where `transaction_count_7d` was computed as an integer. Six months later, a data engineering change makes it a float. The model's inference accuracy drops from 94% to 87% without any model retraining -- the feature schema changed under it.

- Explain the ML-specific schema stability requirement: trained models are compiled with expectations about feature types, ranges, and semantics. A schema change that would be harmless for a microservice (int to float is a safe type promotion) can be catastrophic for a model (the model's learned coefficients assume integer values, float values shift the distribution).
- Design a feature schema versioning system: (a) feature schemas are versioned in a feature registry (analogous to Schema Registry but for ML features); (b) models are trained against a pinned schema version (e.g., `fraud-features-v3`); (c) any schema change creates a new version -- models must be retrained and validated before the new version is used for inference; (d) old schema versions are served in parallel during the model transition period.
- The operational challenge: when a data engineering team changes how a feature is computed, they may not realize it affects an ML model. Design a governance check: before any feature schema change is merged, an automated check queries the model registry to find all models trained on that feature version and notifies their owners. Change is blocked until model owners confirm impact assessment.
- Follow-up: In the NLP/LLM era, "schema" extends to prompt templates. If your LLM-powered service has a prompt template with specific field names, and a schema change removes a field the prompt uses, the model output degrades silently. How do you apply schema evolution principles to prompt versioning?

---

### Section F: Cross-Chapter Integration (Q43-Q50)

---

**Question 43 -- Ch30 + Ch28: migrating JSONB to Protobuf in PostgreSQL**

Your PostgreSQL database stores 800 million user events as JSONB in a column called `payload`. A performance audit shows the JSONB column uses 2.4TB of storage. Analysis shows Protobuf encoding would reduce it to approximately 960GB (60% reduction). Estimate the migration risk and design the zero-downtime plan.

- Storage and query impact: JSONB in PostgreSQL supports GIN indexes and operator queries (`payload->>'event_type' = 'purchase'`). If you switch to `bytea` (raw Protobuf bytes), all GIN indexes are lost and SQL queries against the payload are impossible. You must extract any queryable fields into proper columns BEFORE switching. Enumerate which fields are used in WHERE/ORDER BY/GROUP BY across all application queries -- these must become proper typed columns.
- The migration plan: (a) add proper typed columns for all queryable fields alongside the JSONB column; (b) backfill the typed columns from the JSONB data (a slow migration query that runs for days on 800M rows); (c) update application code to write to both JSONB and typed columns; (d) update queries to use typed columns instead of JSONB; (e) switch payload column to `bytea` for non-queryable metadata; (f) drop JSONB column and GIN indexes.
- Risk of JSONB data that does not parse to Protobuf: over 800 million events, some will have malformed JSON, unexpected types (strings where ints are expected), or fields from old schema versions. Design the backfill job with a dead-letter table for events that fail Protobuf encoding, and a human review process for the dead-letter items.
- Follow-up: After migrating to Protobuf bytea, a new requirement arrives: "We need to query events by `experiment_id` (a field inside the Protobuf payload) for A/B test analysis." How do you add this capability without switching back to JSONB? (Answer: add a separate `experiment_id` column with a B-tree index, populated by an application-level write and a backfill for historical data. Binary payloads are not queryable; extract all query-needed fields as typed columns.)

---

**Question 44 -- Ch30 + Ch29: Parquet row groups vs. ClickHouse MergeTree storage layout**

A data engineering team is deciding between storing analytics events in Parquet on S3 (queried via Presto/Trino) vs. storing them in ClickHouse (a columnar OLAP database). Both use columnar storage internally. Compare the storage layouts and the query execution paths, then give a recommendation.

- Parquet storage layout: data is organized into row groups (horizontal partitions) each containing column chunks. The row group size (default 128MB) is the unit of predicate pushdown. Files are on object storage (S3) -- read requires network I/O, typically 100-500ms for the first byte. Presto/Trino are the query engines: they distribute query planning and execution across a coordinator and workers.
- ClickHouse MergeTree storage layout: data is stored in "parts" (equivalent to row groups), each part containing per-column bin files. Parts are local on NVMe SSDs -- read latency is microseconds to milliseconds, not hundreds of milliseconds. ClickHouse has its own query execution engine optimized for vectorized SIMD operations across column data. `PREWHERE` clause pushes filters before other conditions, similar to Parquet predicate pushdown but executed in the storage engine.
- Key differences: (a) Parquet is a file format, not a database -- you need an external compute engine (Spark, Presto) that scales independently; ClickHouse is a database -- compute is co-located with storage, lower I/O latency; (b) Parquet on S3 scales storage independently of compute (pay per TB stored, scale compute up for query bursts); ClickHouse requires capacity planning for both compute and storage together; (c) Parquet is the standard for ecosystem tools (dbt, Airflow, data science tooling); ClickHouse has less ecosystem integration but better raw query performance.
- Recommendation framework: high query frequency, sub-second latency required, team can manage a ClickHouse cluster -> ClickHouse. Occasional analytics queries, variable compute needs, tight S3 storage budget, need for ecosystem tool integration -> Parquet + Presto/Athena. Both approaches are columnar; the difference is operational complexity vs. query performance.
- Follow-up: ClickHouse can also read Parquet files directly (`SELECT * FROM file('data.parquet', Parquet)`). Does this blur the distinction? (Answer: yes, for ad-hoc queries. But for production analytics with SLA requirements, ClickHouse native tables with MergeTree are significantly faster than reading external Parquet files.)

---

**Question 45 -- Ch30 + Ch33/34: zero-downtime Kafka schema migration from JSON to Avro**

Your Kafka topic `user-events` has been producing JSON for 2 years. It has 40 consumer groups across 15 teams. A schema change by one producer broke 3 consumers last quarter (JSON has no schema enforcement). You are now mandated to migrate to Avro + Confluent Schema Registry. Design the complete zero-downtime migration.

- Phase 1 -- registry setup and schema definition: install Schema Registry (or use Confluent Cloud), define the canonical Avro schema for `user-events` (capturing all field names and types from the current JSON contract), register it under subject `user-events-value` with FULL_TRANSITIVE compatibility. This is pure infrastructure, zero impact on producers or consumers.
- Phase 2 -- parallel topic strategy: create a new topic `user-events-avro`. Update producers to write to BOTH topics: JSON to `user-events` (unchanged), Avro to `user-events-avro`. This adds approximately 5-10% producer overhead but is safe. Consumers can now be migrated one-by-one to `user-events-avro` at their own pace.
- Phase 3 -- consumer migration: for each of the 15 teams, provide: (a) the Avro schema and a code sample for their language (Java, Python, Go), (b) a test Kafka cluster where they can validate their new consumer reads `user-events-avro` correctly, (c) a deadline (8 weeks). Track migration status via consumer group metrics in the Kafka admin API.
- Phase 4 -- producer cutover and old topic deprecation: once all consumer groups have migrated to `user-events-avro` (confirmed by zero lag on `user-events` for those groups), stop producers from writing to `user-events`. Set `user-events` retention to 7 days. After 7 days, delete the topic. Update Schema Registry to be the enforcement point going forward.
- Follow-up: During Phase 3, a consumer that reads both topics for 8 weeks must handle both JSON and Avro events. What is the cleanest implementation? (Answer: a router layer at the consumer that inspects byte 0 of the message -- if it is `0x00` (Confluent magic byte), deserialize as Avro; otherwise parse as JSON. This dual-mode consumer runs during the transition and is removed post-migration.)

---

**Question 46 -- Ch30 + Ch35: Spark reading multi-version Parquet files from a batch pipeline**

A batch pipeline writes Parquet to S3 daily. It has been running for 3 years. The schema has evolved 4 times: v1 (8 columns), v2 (10 columns, 2 added), v3 (11 columns, 1 added, 1 renamed), v4 (current, 12 columns, 1 removed, 2 added). A new Spark job must read all 3 years of data for a historical analysis. Design the schema resolution strategy.

- `mergeSchema` limitations: enabling `mergeSchema` on the S3 prefix will attempt to union all 4 schema versions. The renamed column (v2 name vs v3 name) will appear as TWO separate columns -- most rows will have one null, one populated. The removed column (in v3) will appear as null in v3+ files but populated in v1/v2 files. These nulls are not errors but are semantically confusing.
- Design an explicit schema resolution layer: define the target "canonical schema" (v4 plus any columns removed that are needed for historical analysis). Write a per-version transformation: for each file partition (identified by date-based S3 prefix), apply a version-specific transformation that renames columns, fills in defaults for missing columns, and casts types to the canonical schema. Union the transformed DataFrames.
- Handling the renamed column (v2 to v3): identify the S3 prefixes that contain v2 data (by date range or by reading a metadata file you should maintain). For v2 partitions, select the old column name and alias it to the new name before union. For v3+ partitions, the new name is already correct.
- Handling the removed column: if the removed column is needed for the historical analysis, it exists in v1/v2 files (by date prefix). Read it from those partitions, set to null for v3+ partitions. Union gives you a sparse column that is populated for the relevant date range.
- Follow-up: Going forward, how do you prevent this multi-version complexity from accumulating? (Answer: (a) maintain a schema version registry keyed by date range; (b) run a quarterly "schema normalization" job that rewrites old Parquet files to the current schema before adding too many version permutations; (c) adopt Delta Lake or Iceberg which tracks schema evolution per commit and handles mergeSchema transparently through the transaction log.)

---

**Question 47 -- Ch30 + Ch36: Avro schema registry replication across 3 regions**

Your platform operates in 3 AWS regions: us-east-1, eu-west-1, ap-southeast-1. Each region has its own Kafka cluster and its own Confluent Schema Registry instance. Events are replicated across regions using Kafka MirrorMaker 2. An engineer in us-east-1 deploys a new schema version. A producer in eu-west-1 sends events using the new schema 2 minutes later (before schema replication has arrived). The eu-west-1 consumer cannot deserialize those events. Design the replication strategy that prevents this.

- Root cause: Schema Registry instances are independent per region. A schema registered in us-east-1 has ID=47 there. When MirrorMaker replicates the event to eu-west-1, the event still has schema_id=47 in its header. The eu-west-1 Registry has never seen ID=47. Consumer fails with "Schema not found: 47."
- Option 1 -- active-passive Registry: one region (us-east-1) is the authoritative Registry. All other regions forward schema registrations to us-east-1 and read from a replicated local cache. The replication lag is the key risk. Implement: (a) forward-write proxy in each region that sends registrations to the primary, (b) streaming replication from primary to secondaries using the `_schemas` Kafka topic replication (MirrorMaker replicates `_schemas` topic alongside event topics), (c) consumers in secondaries can read local registry once the schema arrives.
- Option 2 -- pre-flight schema sync: before any producer deploys in eu-west-1, require that the schema is also registered in the eu-west-1 Registry. Implement as a deployment gate: CI/CD pipeline for eu-west-1 deployments checks that all schemas the producer uses are registered in eu-west-1 Registry before allowing deployment. Schema IDs will differ across regions (eu-west-1 may assign ID=52 to the same schema us-east-1 calls ID=47). This requires ID remapping.
- Option 3 -- globally unique schema IDs: design the Registry to use globally unique IDs across regions (e.g., region prefix in the ID: us-east-1 uses IDs 1M-2M, eu-west-1 uses 2M-3M). MirrorMaker replicates events; schema replication ensures each region has all schemas. Consumers accept any schema ID regardless of origin region.
- Follow-up: Schema replication lag of 30 seconds is acceptable for eventual consistency. But if a producer deploys in us-east-1 and immediately starts producing at 100K QPS, the eu-west-1 consumers will fail for 30 seconds. Compute: 100K events/sec * 30 sec = 3 million events dropped or dead-lettered. Is this acceptable? What SLA does your cross-region Schema Registry replication need to support the RTO for schema propagation?

---

**Question 48 -- Ch30 + Ch37: GDPR deletion of Protobuf-encoded events in Kafka**

A user submits a GDPR right-to-erasure request. Their email address is in field 3 (`string email = 3`) of a Protobuf schema used for Kafka events. These events are stored in Kafka topics with 90-day retention and also in S3 for long-term analytics. Kafka's immutable log makes deletion non-trivial. Design the compliant solution.

- Kafka immutability: Kafka topic partitions are immutable append-only logs. You cannot "delete" a specific record from the middle of the log. Options: (a) wait for retention period to expire (90 days) -- but GDPR requires deletion "without undue delay," typically 30 days; (b) compact topic with a tombstone -- only works if events use the user's ID as the Kafka message key, and only deletes the key (the event payload remains until cleanup); (c) rewrite the topic -- dangerous and operationally expensive.
- Crypto-shredding: the correct approach. Encrypt the PII field (email) with a per-user encryption key stored in a separate key management service. When a deletion request arrives, delete the user's encryption key. All existing events still exist in Kafka but the email field is now ciphertext that cannot be decrypted. The data is effectively deleted without modifying Kafka. This satisfies GDPR: the data cannot be re-identified without the key.
- Protobuf-specific implementation: the email field is field 3. Modify the schema to store the email as `bytes encrypted_email = 3` (or keep as string and store base64-encoded ciphertext). At write time, encrypt with the user's key. At read time, decrypt before use. On deletion, KMS key is deleted -- all events with that user's email become undecryptable.
- S3 long-term storage: S3 supports object versioning and S3 Object Lambda. One approach: write a Lambda function triggered by deletion requests that reads and rewrites affected Parquet files with the PII field zeroed out. This is operationally expensive at scale. The crypto-shredding approach is far simpler for both Kafka and S3.
- Follow-up: Nulling vs. removing vs. crypto-shredding: (a) nulling field 3 produces a valid Protobuf message where `email = ""` -- the record still exists, the field is empty. Is this GDPR-compliant? (Depends: if you can link the null record to a specific individual via other fields like user_id, it is not compliant on its own); (b) removing field 3 from the schema does not delete the bytes in existing messages -- they remain on wire, just ignored by consumers with the new schema; (c) crypto-shredding is the only approach that satisfies both "data is gone" and "Kafka log is untouched."

---

**Question 49 -- Ch30 + Ch38: ROI of JSON to Protobuf migration for a 10M response/day API**

Your service handles 10 million API responses per day. Each response is currently JSON, averaging 5KB. A Protobuf migration would reduce the average response to 1.2KB. Your engineering team is sized at 8 engineers. Calculate the ROI and decide whether to prioritize this migration.

- Bandwidth calculation: current daily data transfer = 10M * 5KB = 50GB/day = 1.5TB/month. Protobuf: 10M * 1.2KB = 12GB/day = 360GB/month. Reduction: 1.14TB/month. At AWS CloudFront egress pricing ($0.085/GB for first 10TB), savings: 1140 * $0.085 = $96.90/month. At internal AWS inter-AZ pricing ($0.01/GB), savings: 1140 * $0.01 = $11.40/month. The CDN savings are more significant if responses are cached at the edge.
- CPU calculation: at 10M responses/day (approximately 115 requests/second), JSON encoding at 15 microseconds each: 115 * 15us = 1.7ms/sec of CPU, approximately 0.002 cores. Protobuf at 5us: 0.6ms/sec, approximately 0.0007 cores. The CPU savings are negligible at this QPS -- 115 QPS is nowhere near the 10K+ threshold where encoding CPU matters.
- Client-side benefit: mobile clients downloading 5KB vs 1.2KB responses. If your API serves mobile devices, the 75% payload reduction directly improves perceived performance (faster page loads, lower mobile data usage for users). This is harder to quantify in dollars but has real user experience impact. For an app with 1 million active users downloading responses daily: 4TB/day less mobile data transferred. This benefits users on metered data plans.
- Engineering cost: migrating 10M API responses/day to Protobuf requires: (a) defining and maintaining `.proto` schemas, (b) updating client SDKs for all consumers, (c) testing and validation, (d) documentation for external consumers. Estimate: 6-8 weeks of engineering time. At a fully-loaded engineer cost of $250K/year ($4,800/week), this is approximately $30,000-40,000 of engineering cost.
- ROI verdict: at $96.90/month bandwidth savings, payback period is 300+ months (25+ years) on infrastructure savings alone. The migration is NOT cost-justified on bandwidth and CPU alone at this scale. The correct decision is to defer unless there is a user-facing latency or mobile data benefit that justifies the cost. The migration makes sense at 100M+ responses/day or if clients are latency-sensitive.
- Follow-up: What changes this analysis? (Answer: (a) if the QPS is 10x higher (1 billion responses/day), bandwidth savings become $960/month and CPU savings are material; (b) if the API serves embedded/IoT devices with severe bandwidth constraints; (c) if the response format is nested and repetitive, making JSON disproportionately verbose relative to Protobuf -- the 5KB vs 1.2KB ratio depends heavily on message structure.)

---

**Question 50 -- Ch30 synthesis: the encoding decision in a staff-level system design interview**

You are in a system design interview. The interviewer asks you to design a large-scale ride-hailing platform (150M trips/year, 10M active drivers, real-time location updates). Walk through the encoding decisions for every data flow in the system, justifying each choice.

- Driver location updates (50K updates/second, driver app to backend): use Protobuf. Reasoning: (a) internal service communication, not external; (b) 50K QPS -- encoding CPU and bandwidth matter; (c) location update is a small fixed schema (`driver_id`, `lat`, `lng`, `timestamp`, `speed`) -- Protobuf's 4-field message is approximately 30 bytes vs. 120 bytes JSON, saving 90 bytes * 50K/sec = 4.3 MB/sec = 371 GB/month in bandwidth; (d) gRPC for the transport layer gives HTTP/2 multiplexing for many concurrent driver connections.
- Trip events (trip started, completed, cancelled) on Kafka: use Avro + Confluent Schema Registry. Reasoning: (a) events are consumed by Billing, Routing, Analytics, ML Fraud Detection, Driver Ratings -- 6+ consumers; (b) schema evolution is critical (new fields for electric vehicle support, new trip statuses); (c) Avro on Kafka is the standard pattern with Schema Registry enforcing FULL_TRANSITIVE compatibility; (d) events land in S3 as Avro OCF, then converted to Parquet for analytics.
- Rider-facing REST API (mobile app, web): use JSON + OpenAPI. Reasoning: (a) external consumers (mobile SDKs, third-party integrators); (b) 2M requests/day (~23 QPS) -- encoding overhead is negligible; (c) human-readable for debugging by external developers; (d) OpenAPI spec published for partner integrations.
- Analytics data in S3 (trip history, driver behavior, surge pricing models): use Parquet. Reasoning: (a) 150M trips/year = ~400K trips/day; (b) queries are analytical ("average trip duration by city by hour"), touching 2-3 columns out of 20; (c) Parquet columnar storage reduces I/O by 10x for these queries; (d) Snappy compression reduces storage by 5x vs JSON; (e) schema evolution via Spark mergeSchema or Iceberg table format.
- Internal microservice REST APIs (surge pricing service to driver matching service): use Protobuf with gRPC. Reasoning: (a) internal, latency-sensitive (surge pricing must be reflected in driver assignments within 1 second); (b) gRPC gives bidirectional streaming for the matching engine to push driver candidates as they are found, without polling; (c) strong schema contract between teams that evolve independently.
- Follow-up: The interviewer asks: "You used five different formats. Is that too complex?" The correct answer: no -- each format is optimal for its context. The complexity is managed by: (a) translation layers at boundaries (Kafka to S3: Avro to Parquet converter; gRPC to REST: API gateway transcoder); (b) schema governance (Schema Registry for Kafka, proto linting for gRPC, OpenAPI spec for REST); (c) monitoring that detects encoding failures early. The alternative -- using JSON everywhere -- is operationally simpler but fails at scale on bandwidth, CPU, and schema safety.

---

---

### Section G: Quick-Fire Reference Questions (Q51-Q60)

*These are short-answer questions covering definitions, numbers, and one-liner traps that appear in staff interviews. Each tests whether you have internalized the concept or are just pattern-matching.*

---

**Question 51 -- Tag size optimization**

You are designing a Protobuf message with 30 fields. Fields 1-15 take a 1-byte tag on the wire. Fields 16+ take a 2-byte tag. Which fields should get numbers 1-15? (Answer: the most frequently populated fields -- fields that appear in every message. Rarely-populated optional fields can use numbers 16+. Debug/audit fields that appear in 1% of messages should use numbers 20+. Never waste a 1-byte tag slot on a rarely-sent field.)

---

**Question 52 -- Avro file magic bytes**

A data engineer opens an Avro Object Container File in a hex editor. The first 4 bytes are `4F 62 6A 01`. What do they mean? (Answer: `4F 62 6A` = ASCII "Obj", which is the Avro OCF magic. `01` is the format version. Together they confirm this is a valid Avro Object Container File, version 1. Any reader should check for this magic before attempting to parse the file as Avro.)

---

**Question 53 -- Schema Registry: which Kafka topic stores schemas?**

Where does Confluent Schema Registry actually store its schemas? (Answer: in a Kafka topic named `_schemas`. This topic has compaction enabled so only the latest value per key (subject+version) is retained. Schema Registry instances replay this topic on startup to rebuild their in-memory state. Because it is a Kafka topic, it inherits Kafka's durability and replication guarantees. The Registry itself is therefore stateless between the `_schemas` topic and its local cache.)

---

**Question 54 -- gRPC streaming types and HTTP/2 relationship**

Why can gRPC do bidirectional streaming but REST/HTTP1.1 cannot? (Answer: HTTP/1.1 is half-duplex on a single connection -- the client sends a request, then the server sends a response. One direction at a time. HTTP/2 supports full-duplex streams: both client and server can send frames concurrently on the same stream ID. gRPC uses this to implement bidirectional streaming: the client sends a stream of request messages while the server simultaneously sends a stream of response messages. REST APIs on HTTP/1.1 cannot do this without websocket upgrades or SSE hacks.)

---

**Question 55 -- Parquet footer: what is in it and why it is read first**

When Spark reads a Parquet file, it reads the footer LAST in the file FIRST. Why? (Answer: Parquet files are written front-to-back but designed to be read back-to-front. The footer, at the end of the file, contains: the schema, for each row group the byte offset and size, and for each column chunk the min/max statistics. By reading the footer first, the query engine knows exactly which row groups to read and which to skip, without scanning any data. This is why Parquet files store metadata at the end -- the writer writes data first (streaming), then writes the footer with offsets once all data is flushed.)

---

**Question 56 -- Compatibility direction mnemonic**

Students confuse BACKWARD and FORWARD compatibility. Give a reliable mnemonic. (Answer: think about which code is NEW. BACKWARD compatibility -- the NEW consumer can read data produced by OLD producer. The new consumer "looks backward" at old data. FORWARD compatibility -- the OLD consumer can read data from the NEW producer. The old consumer "looks forward" at new data it has never seen. FULL = both simultaneously. A memory trick: BACKWARD compatibility protects the READER upgrade (new reader, old writer). FORWARD compatibility protects the WRITER upgrade (new writer, old reader). Deploy consumers first for BACKWARD. Deploy producers first for FORWARD.)

---

**Question 57 -- Why Avro has no field identifiers on the wire**

A candidate says: "Avro is less efficient than Protobuf because it needs the schema to decode." Is this correct? (Answer: this is backwards. Avro is MORE space-efficient than Protobuf precisely because it puts NO field identifiers on the wire. Protobuf puts a 1-2 byte tag (field number + wire type) before every field value. Avro puts nothing -- just the raw values in schema order. The schema is external, fetched once from the Registry and cached. The tradeoff: Avro data without its schema is meaningless (you cannot even tell what type a field is), while Protobuf data without the .proto file is partially interpretable using wire type information. Avro trades decoding self-sufficiency for compactness.)

---

**Question 58 -- JSON Schema vs. OpenAPI vs. Protobuf: enforcement level**

Rank these three schema enforcement mechanisms from weakest to strongest, and explain why: (1) JSON Schema with runtime validation, (2) OpenAPI spec with code generation but no runtime validation, (3) Protobuf with generated stubs. (Answer: weakest is (2) OpenAPI without runtime validation -- the spec exists but nothing enforces it at runtime; a server can return any shape and the spec is just documentation. Middle is (1) JSON Schema with runtime validation -- at least the contract is enforced at runtime, but validation happens after the bytes arrive, not before, and schema mismatches are runtime errors in production. Strongest is (3) Protobuf -- the schema is enforced at code generation time (your code literally cannot access a field that does not exist in the schema), at serialization time (the encoder rejects values that do not match the type), and at deserialization time (unknown fields are handled by protocol, not left to the application). The earlier in the pipeline a violation is caught, the cheaper it is to fix.)

---

**Question 59 -- Delta encoding in Parquet: when it applies**

A Parquet file stores a column of Unix timestamps for events, all from the same day (values like 1705315800, 1705315862, 1705315900). The column uses delta encoding. What is stored on disk? (Answer: the first value is stored as a full 8-byte integer. Each subsequent value is stored as the delta from the previous: +62, +38, +21, etc. These deltas are small integers that fit in 1-2 varint bytes instead of 8 bytes for the full timestamp. For a column of 10 million monotonically increasing timestamps, delta encoding reduces the column storage by approximately 75% (8 bytes -> 2 bytes average per value). Delta encoding is automatically chosen by Parquet writers for columns that the statistics show are monotonically increasing or have small value-to-value differences.)

---

**Question 60 -- The schema migration that cannot be rolled back**

You are about to deploy a schema change that removes a field. After deployment, you discover a bug and need to roll back. Describe why rolling back a field removal is more dangerous than rolling back most other deployments. (Answer: a field removal is a two-step wire change. Step 1: producers stop sending the field (backward compatible). Step 2: consumers stop reading it. If you roll back the producer to the version that sends the field, but consumers are already on the version that ignores it, the field values are being sent but silently discarded. Rolling back the consumer to the version that reads the field is safe. The dangerous scenario: producer is rolled back to send the field, consumer was also rolled back to read it, but those rolled-back consumers expect the field at the field number that is now in `reserved`. If someone added a different field at the same number during the intervening time, data is now misinterpreted. This is why field removals require `reserved` BEFORE removal -- it prevents any new field from reusing the number even during a rollback window.)

---

*End of Supplemental Brainstorming: Chapter 30 -- Data Encoding and Schema Evolution.*
*Total: 56 questions (Q5-Q60) across 7 sections covering all major topics and cross-chapter connections.*
