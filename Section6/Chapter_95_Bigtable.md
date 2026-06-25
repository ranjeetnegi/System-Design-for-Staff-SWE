# Chapter 84: Bigtable — Google's Distributed Wide-Column Store

> In 2006, Google published a paper describing Bigtable: a system for storing structured data across thousands of machines, serving everything from the web search index to Google Earth to Gmail. The key insight was simple but powerful — take a sorted map, scale it to petabytes, and design the API to make the storage layout explicit to the programmer. That API is the "row key," and mastering it is what separates an L4 Bigtable user from an L6 system designer.

---

## Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                    CHAPTER 84 AT A GLANCE                           │
│                                                                     │
│  Part 1:  The Problem Bigtable Solved  — why Google built it        │
│  Part 2:  The Data Model               — rows, columns, cells,      │
│                                          timestamps                 │
│  Part 3:  Architecture                 — Chubby, Master, Tablet     │
│                                          Servers, Client            │
│  Part 4:  Tablets                      — how tables are split and   │
│                                          located                    │
│  Part 5:  The LSM Tree                 — how data is stored         │
│                                          internally                 │
│  Part 6:  The Write Path               — WAL → MemTable →           │
│                                          compaction                 │
│  Part 7:  The Read Path                — MemTable + SSTable lookup  │
│  Part 8:  Row Key Design               — the skill that defines     │
│                                          L5 vs L6                   │
│  Part 9:  Limitations and              — HBase, Cassandra, Spanner, │
│           What Came After               DynamoDB                    │
│  Part 10: Interview Application        — how to use Bigtable in an  │
│                                          interview                  │
│  Part 11: Staff-Level Q&A Drill        — 10 L6 interview questions  │
│                                          with model answers         │
│                                                                     │
│  Real Life Incidents, Exercises, Homework at the end                │
└─────────────────────────────────────────────────────────────────────┘
```

**The one thing to remember:** Bigtable is a sorted map where YOU control the sort key (the row key). Everything about Bigtable's performance — reads, writes, scans, hotspots — flows from how you design that row key. A bad row key means a slow, unscalable system. A great row key means blazing performance. This is the central skill.

---

## Part 1: The Problem Bigtable Solved

### The situation in 2004–2005

Google's search index wasn't just a list of web pages. It was a massive structured dataset: for every URL on the web, Google tracked crawl metadata, link graph data, PageRank scores, per-language index entries, and anchor text. This was structured data — not just bytes on disk like GFS stored.

The previous solution was ad-hoc: different teams at Google used different storage backends (MySQL replicas, custom flat-file formats, GFS files with custom indexing). Each team reinvented the same wheel: figuring out how to partition the data, how to handle failures, how to serve reads at scale. Google needed a single, shared system that could store structured data at petabyte scale, serve both batch (MapReduce) and online (user-facing) workloads, and be operated by a central infrastructure team instead of each product team.

The requirement list was demanding:
- Store hundreds of petabytes of structured data
- Handle millions of read/write operations per second
- Serve both small random reads (a user viewing their Gmail inbox) and large batch scans (a MapReduce job processing the entire web index)
- Allow columns to be added dynamically without schema migration
- Store multiple versions of each cell (timestamps)
- Run on commodity hardware with automatic failure recovery

No existing database (Oracle, MySQL, PostgreSQL) could handle this at Google's scale in 2004. Google built Bigtable.

### The analogy

Imagine a giant spreadsheet. It has millions of rows and thousands of columns. The rows are always sorted alphabetically by the row label. Each cell in the spreadsheet can hold multiple versions of a value, each labeled with a timestamp ("here's what this cell contained at 2 PM, here's what it contained at 3 PM").

Now imagine this spreadsheet is so large that it can't fit on one machine, so it's split into horizontal strips (a strip is a group of consecutive rows). Each strip lives on a different server. A "librarian" server knows which server holds which strip. When you want to read a cell, you ask the librarian which server has the row you want, then go directly to that server.

That is Bigtable. The rows are sorted by row key. The strips are called tablets. The librarian is the Master. The servers holding the tablets are Tablet Servers. The cells can have multiple timestamped versions.

### What workloads Bigtable was designed for

```
┌─────────────────────────────────────────────────────────────────────┐
│               BIGTABLE'S TARGET WORKLOADS (2004–2006)               │
│                                                                     │
│  Google Search Index                                                │
│  • Row key: URL                                                     │
│  • Columns: crawl timestamp, PageRank, per-language index entry     │
│  • Access: MapReduce batch scans + online lookups by URL            │
│                                                                     │
│  Google Earth (Keyhole merger)                                      │
│  • Row key: geographic tile identifier                              │
│  • Columns: satellite imagery at different resolutions              │
│  • Access: online lookups by tile location + zoom level             │
│                                                                     │
│  Gmail (Orchid/Titan project)                                       │
│  • Row key: user_id + timestamp                                     │
│  • Columns: subject, body, sender, labels, read-status              │
│  • Access: online reads of a user's inbox (prefix scan on user_id)  │
│                                                                     │
│  Personalized Search                                                │
│  • Row key: user_id                                                 │
│  • Columns: query history, click history, preferences               │
│  • Access: online lookups by user + batch processing                │
└─────────────────────────────────────────────────────────────────────┘
```

### Intern → Staff Progression (Part 1)

| Level | How they understand the Bigtable problem |
|-------|------------------------------------------|
| **Intern** | "It's a NoSQL database." True but meaningless — all NoSQL databases are different. |
| **L3** | Knows it's a key-value store used by Google. Cannot explain the data model or why Google built it. |
| **L4** | Understands the structured data requirement. Knows it's used by Search, Earth, Gmail. Cannot explain the architecture. |
| **L5** | Can articulate why existing databases couldn't handle the scale. Can explain the data model (rows, columns, timestamps). |
| **L6** | Can explain why Bigtable's design choices follow from its workload requirements. Can explain the design space: why a sorted map instead of a hash map, why column families instead of arbitrary columns, why multi-version cells. Can identify when a new system design problem is "Bigtable-shaped." |

### Common Interview Mistakes — Part 1

**Mistake 1: Calling Bigtable "a NoSQL database."**
This is technically true but signals shallow understanding. Bigtable is a specific type of NoSQL store — a wide-column store or sorted key-value store. Saying "it's NoSQL" puts it in the same category as MongoDB (document store), Redis (in-memory key-value), and Neo4j (graph database) — completely different designs. When you say "wide-column store sorted by row key," you've said something meaningful. When you say "NoSQL," you've said almost nothing.

**Mistake 2: Confusing Bigtable with a relational database.**
Bigtable has no SQL, no joins, no foreign keys, no transactions spanning multiple rows (in the original design), and no schema enforcement for columns. The "table" in Bigtable is a loose analogy. The actual model is a sorted multi-dimensional map. Treating it like MySQL with a different performance profile will lead you to design solutions that Bigtable fundamentally cannot provide.

**Mistake 3: Not knowing what products used Bigtable.**
In a Google Staff interview, "tell me about Bigtable" is a test of whether you've actually thought about it in context. Knowing that Search, Earth, Gmail, and Analytics all used Bigtable — and WHY each fit the data model — demonstrates real understanding. If you can only recite the architecture without knowing the use cases, you're pattern-matching on a paper you half-read.

### Real Incident (Part 1): The Pre-Bigtable Pain at Google

Before Bigtable, Google's web crawl index was stored in a combination of GFS files and custom per-team databases. When the GoogleBot team needed to add a new field to the crawl data (say, a "language detection confidence score"), they had to coordinate with multiple teams, migrate enormous datasets, and update processing jobs across the entire pipeline — a process that could take weeks. The lack of a shared, schema-flexible storage system meant every new feature required a migration project.

Bigtable solved this with its "column family" model: you define a column family (like `language_data`) and then add arbitrary columns within that family (`confidence_score`, `detected_language`, `charset`) without any migration. New columns can appear in some rows and not others. The web crawl team could add `language_data:confidence_score` to rows where they had data and leave it absent in older rows — no migration, no coordination. This column-flexibility was a primary design motivation and a major source of Bigtable's adoption inside Google.

---

## Part 2: The Data Model

### What a Bigtable table actually is

A Bigtable table is a sparse, distributed, persistent, sorted, multi-dimensional map. Let's unpack each word:

- **Sparse**: a row doesn't have to have values in all columns. Most rows have values in a small subset of columns.
- **Distributed**: split across many servers automatically.
- **Persistent**: data survives server restarts.
- **Sorted**: rows are sorted in lexicographic (alphabetical) order by row key. This is the most important word.
- **Multi-dimensional**: each cell is indexed by (row key, column family, column qualifier, timestamp).
- **Map**: it's fundamentally a key → value lookup.

### The four dimensions of a cell

Every piece of data in Bigtable is located by four coordinates:

```
┌─────────────────────────────────────────────────────────────────────┐
│                    THE BIGTABLE CELL ADDRESS                        │
│                                                                     │
│  table["row_key"]["column_family:column_qualifier"][timestamp]      │
│                                                                     │
│  Example:                                                           │
│  table["com.google.www"]["content:html"][1705312000] = "<html>..."  │
│                                                                     │
│  row_key:          "com.google.www"                                 │
│                    (the URL, reversed for locality — see Part 8)    │
│                                                                     │
│  column_family:    "content"                                        │
│                    (defined at table creation time, all columns in  │
│                     this family stored together on disk)            │
│                                                                     │
│  column_qualifier: "html"                                           │
│                    (arbitrary string within the family, no schema)  │
│                                                                     │
│  timestamp:        1705312000                                        │
│                    (Unix timestamp, auto-assigned or user-provided)  │
│                    (multiple timestamps = multiple versions of same  │
│                     cell, newest returned by default)               │
└─────────────────────────────────────────────────────────────────────┘
```

### Column families vs column qualifiers

This is the distinction most candidates get wrong. A **column family** is like a drawer in a filing cabinet — it's a logical grouping that also determines physical storage (all columns in the same family are stored together on disk). Column families must be declared when the table is created. You can have a few dozen column families at most.

A **column qualifier** is like a label on a file inside the drawer. It can be anything — a string, a URL, an integer — and can be created dynamically without changing the schema. You can have millions of different column qualifiers within a family.

```
BIGTABLE SCHEMA EXAMPLE: Web Crawl Table

TABLE: webtable

Row Key: com.cnn.www  (reversed URL for locality)
┌────────────────────────────────────────────────────────┐
│ Column Family: "content"  (stores crawled HTML)         │
│   content:html  [t=1705312000]  "<html>CNN...</html>"  │
│   content:html  [t=1705225600]  "<html>CNN...</html>"  │
│                 (two versions — newest shown by default)│
├────────────────────────────────────────────────────────┤
│ Column Family: "anchor" (stores links TO this page)     │
│   anchor:cnnsi.com      "CNN"                          │
│   anchor:my.look.ca     "CNN.com"                      │
│   anchor:news.google.com "CNN - Breaking News..."      │
├────────────────────────────────────────────────────────┤
│ Column Family: "metadata"                               │
│   metadata:language        "en"                        │
│   metadata:pagerank        "0.847"                     │
│   metadata:crawl_status    "200"                       │
└────────────────────────────────────────────────────────┘

Row Key: com.google.maps  (different URL, different columns)
┌────────────────────────────────────────────────────────┐
│ Column Family: "content"                               │
│   content:html  [t=1705399200]  "<html>Maps...</html>" │
├────────────────────────────────────────────────────────┤
│ Column Family: "anchor" (no anchor data for Maps yet)  │
│   (empty — sparse!)                                    │
├────────────────────────────────────────────────────────┤
│ Column Family: "metadata"                              │
│   metadata:language        "en"                        │
│   metadata:pagerank        "0.921"                     │
│   (no crawl_status — sparse!)                          │
└────────────────────────────────────────────────────────┘
```

### Multi-version cells: why timestamps matter

Each cell can hold multiple versions of its value, each with a different timestamp. By default, when you read a cell, you get the most recent version. But you can also:
- Ask for the version at a specific timestamp: "give me what this page looked like on January 1st"
- Ask for the last N versions: "give me the last 3 crawls of this URL"
- Configure the table to automatically garbage-collect old versions (keep only the last 3, or delete anything older than 7 days)

This time-travel capability was critical for Google's web crawl: each URL's page content changes over time, and having multiple versions lets you compare the current version to the previous crawl to detect changes.

### The sorted row key: why order matters enormously

Bigtable stores rows in sorted lexicographic order by row key. This is not a detail — it's the central design decision that makes Bigtable useful.

**Sequential scan performance:** If your rows are sorted by URL (`com.cnn.www`, `com.google.maps`, `com.google.news`), then all google.com URLs are adjacent in the table. A scan for all google.com URLs reads a contiguous block of storage — extremely fast. If rows were in random order (like a hash map), a query for "all google.com URLs" would require reading the entire table.

**Range queries:** Because rows are sorted, you can do efficient range scans: "give me all rows where the row key starts with `com.google`" becomes a single sequential read from the first matching key to the last. In a hash-based store, this query is impossible without a full table scan.

The sorted order is what makes row key design so important (covered in depth in Part 8). Your row key determines what queries are fast and what queries are slow.

### Intern → Staff Progression (Part 2)

| Level | Understanding of the data model |
|-------|--------------------------------|
| **Intern** | "It's a table with rows and columns." Misses timestamps, column families, and the sorted order. |
| **L3** | Knows about row keys and column families. Cannot explain the difference between column family and column qualifier. Cannot explain why rows are sorted. |
| **L4** | Can explain the four coordinates (row, family, qualifier, timestamp). Understands sparse columns. |
| **L5** | Can explain why the sorted order matters for scan performance. Understands the garbage collection options for old versions. Can read and write the cell address notation. |
| **L6** | Can design the complete data model for a given system — choosing row key, column families, column qualifiers, and version retention policy. Can explain the trade-offs of each choice. Can redesign an existing schema when given performance constraints. |

### Common Interview Mistakes — Part 2

**Mistake 1: Treating column qualifiers as a fixed schema.**
Column qualifiers are dynamic. You can add `anchor:any-new-website-url` to a row without any schema change. This is intentional — it's what makes Bigtable "schema-flexible." Candidates who say "I'd add a new column by running ALTER TABLE" are confusing Bigtable with a relational database.

**Mistake 2: Forgetting that the sort order is lexicographic, not numeric.**
Row keys are sorted as byte strings, not as numbers. This means `"10"` sorts before `"9"` (because `"1" < "9"` lexicographically). If your row keys are timestamps or user IDs stored as strings, you MUST zero-pad them to ensure correct sort order: `"0000000010"` sorts before `"0000000009"` — wait, that's still wrong. `"0000000009"` sorts before `"0000000010"` which is correct. Not zero-padding means `"1000000000"` sorts before `"9"`, which is almost certainly wrong. This is a classic Bigtable gotcha that causes subtle ordering bugs.

**Mistake 3: Not knowing what column families control physically.**
All data within a column family is stored together on disk (in the same SSTable files). This means reads that access only one column family are much more efficient than reads that access many column families — the disk I/O is proportional to the amount of data read, and data in a different column family requires reading a different file. Column family selection is a physical locality decision, not just a logical grouping decision.

### Brainstorming Questions — Part 2

**Q: Why does Bigtable store multiple timestamped versions of the same cell instead of just the latest value?**

The multi-version design solves a real problem in data pipelines: you often want to know not just what the current value is but what it was before. In Google's web crawl, the "current" page content is stored alongside the "previous" page content so that the indexing pipeline can detect which parts of a page changed — you only need to re-index the parts that changed, which saves enormous compute resources. Without multi-version cells, you'd need to store previous versions in a separate system or in adjacent columns (like `content:html_prev`), which is awkward and wastes space.

The timestamp model also enables a clean "point-in-time query" capability: read this row as it appeared on January 1st by specifying a timestamp. For analytics systems (like Google Analytics), this is invaluable — you can reconstruct the historical state of a user's data as of any past date without storing separate snapshots. The alternative (storing historical snapshots as separate rows or in a separate table) is more complex and less efficient because it duplicates the row key and all unchanged columns.

The garbage collection configuration (keep last N versions, or delete versions older than T days) is what prevents multi-version cells from consuming unbounded storage. In practice, most tables are configured with `versions: 3` or `max_age: 7d` — you retain just enough history to be useful, and older data is automatically purged during compaction.

---

**Q: Bigtable is sorted by row key but NOT sorted within a row (columns are not sorted). Why not sort columns too?**

The row sort order serves a clear purpose: efficient range scans across rows (all rows with a given row key prefix). But sorting columns within a row would serve a different purpose — efficient scans across columns within a single row. In practice, rows in Bigtable tend to have at most a few hundred columns (even with dynamic qualifiers), so scanning all columns in a row is fast even without sorting. The additional complexity of sorted column qualifiers would not justify the benefit.

More importantly, Bigtable's physical storage already provides an efficient way to access a subset of columns: column families. All data in one column family is stored together on disk. If you only want to read the `content` family, you don't read the `anchor` or `metadata` families at all — you get physical locality for free through family separation. Within a family, columns are stored in sorted order by qualifier, giving you efficient prefix scans within a family (e.g., "give me all `anchor:` columns starting with `anchor:cnn`").

The design decision is: use column families for physical locality (explicit at schema creation time), and allow arbitrary qualifiers within a family (dynamic, no schema). This is the "wide column" in "wide-column store" — the column space can be extremely wide (millions of qualifiers) but accessed efficiently through family isolation. Sorting ALL columns across all families would break the family isolation that makes column-family-based I/O efficient.

---

**Q: GFS stores bytes. Bigtable stores structured data. But Bigtable's values are actually just byte strings — how does structured data get stored?**

Bigtable's values are opaque byte strings. Bigtable has no idea whether the bytes in a cell represent a UTF-8 string, a serialized Protocol Buffer, an integer, or a JPEG image. This is intentional: Bigtable provides ordering and versioning, but NOT data interpretation. The application owns the serialization format.

In practice, Google's internal applications almost always stored Protocol Buffers (protobufs) as Bigtable values. A protobuf is a compact binary format that defines field names and types in a schema. The application serializes a proto to bytes, stores the bytes in Bigtable, and deserializes the bytes on read. The advantage: protobufs are forward and backward compatible — you can add new fields without migrating existing data, because old readers just ignore unknown fields.

This design also means Bigtable itself never needs to be modified when data schemas evolve. Bigtable stores bytes; proto schema evolution is handled in the application layer. This separation of concerns is a key reason Bigtable could serve so many different Google products without needing product-specific modifications.

### Additional Common Interview Mistakes — Part 2 (Extended)

**Mistake 1: Treating column qualifiers as a fixed schema.**
Column qualifiers are dynamic. You can add `anchor:any-new-website-url` to a row without any schema change. This is intentional — it's what makes Bigtable "schema-flexible." Candidates who say "I'd add a new column by running ALTER TABLE" are confusing Bigtable with a relational database.

**Mistake 2: Forgetting the lexicographic sort order trap with numeric values.**
Row keys are sorted as byte strings, not as numbers. The string `"9"` sorts AFTER `"10"`, `"11"`, ... `"99"`, `"100"` — because the first byte of `"9"` (ASCII 57) is greater than the first byte of `"1"` (ASCII 49). So a row key of `"user_9"` sorts AFTER `"user_100"`, which is almost certainly not what you want. The fix is zero-padding: `"user_0000000009"` sorts before `"user_0000000100"`. This is a classic Bigtable gotcha that causes ordering bugs in production that are very hard to debug because data LOOKS correct in isolation but is in the wrong order when scanned.

**Mistake 3: Not knowing that column families determine physical storage.**
A candidate says "column families are just logical groupings." Wrong. All data within a column family is stored in the same SSTable blocks on disk — physically together. A read that touches only the `content` column family reads ONLY the SSTable blocks for `content`. It does NOT read the `anchor` or `metadata` blocks. This matters enormously for performance: a read that spans 3 column families reads 3x the SSTable data compared to a read that touches only 1 family. Column family selection is a physical I/O locality decision, not just organizational preference.

**Mistake 4: Not accounting for timestamp behavior when writing.**
When you write a cell without specifying a timestamp, Bigtable auto-assigns the current server-side timestamp. This sounds fine until you have two writes that happen in the same millisecond — they get the same timestamp and one silently overwrites the other (the last writer wins within a timestamp). In high-frequency write scenarios (1M writes/second per tablet), timestamp collisions are real. The fix is to use a monotonically increasing logical timestamp or to include a unique component (like a UUID suffix) in the column qualifier to distinguish writes that occur at the same millisecond.

### Real Incident (Part 2): The 2007 Proto Versioning Bug

In 2007, a Google team was storing Protocol Buffer (protobuf) serialized objects as Bigtable cell values. This is a common and generally correct pattern — protobufs are compact, efficient, and forward/backward compatible. The team used the column qualifier to identify which proto type the cell contained. For example, a cell storing a `UserProfile` proto would be stored at column qualifier `userprofile`.

The problem appeared when they added a new field to the `UserProfile` proto — a field called `language_preference`. In proto3, adding a new field is backward compatible: old readers that don't know about `language_preference` simply ignore it. New readers can read both old (field absent, defaults to empty string) and new (field present) records. This should work fine.

What went wrong: the team was using proto2 (not proto3), which has required fields. They added `language_preference` as a `required` field. In proto2, a required field that is absent causes deserialization to FAIL — not return a default, but throw an error. Old records in Bigtable did not have `language_preference` (because it didn't exist when they were written). When new reader code tried to deserialize old records, it failed. But here was the silent part: the failure was being caught and swallowed in a catch-all exception handler — the application returned empty results for affected rows instead of throwing an error. For weeks, data for older users was silently missing. The team discovered it only when a user complained about lost data.

The root cause was twofold: (1) using a proto2 required field (never use required fields in proto2 for data stored in external systems — always use optional), and (2) no column qualifier versioning. The column qualifier `userprofile` gave no indication of which schema version was used to serialize the data. The fix had two parts: (a) migrate all existing records to include `language_preference` (a backfill MapReduce job) and convert the field from required to optional, and (b) add a schema version to the column qualifier going forward: `userprofile_v2`, `userprofile_v3`, etc. With versioned column qualifiers, old readers can explicitly detect that a cell contains a newer schema version they don't understand and handle it gracefully (e.g., skip the row, use the last known version). This incident is a canonical example of why you should never store opaque serialized data without versioning metadata alongside it — whether that versioning is in the column qualifier, in a separate "schema version" column, or in a header within the value bytes.

---

## Part 3: Architecture

### The four components

Bigtable has four components: **Chubby** (a distributed lock service), the **Master**, **Tablet Servers**, and the **Client Library**.

```
┌─────────────────────────────────────────────────────────────────────┐
│                    BIGTABLE ARCHITECTURE                            │
│                                                                     │
│  ┌────────────────────────────────────────────────────────────┐    │
│  │                   CHUBBY (lock service)                    │    │
│  │  • Master election (only one master at a time)             │    │
│  │  • Tablet server registration ("I'm alive, I hold         │    │
│  │    tablets X, Y, Z")                                       │    │
│  │  • Root tablet location (start of tablet lookup chain)    │    │
│  │  • Access control lists (who can read/write each table)   │    │
│  └────────────────────────────────────────────────────────────┘    │
│                           │                                         │
│                           │ Chubby informs Master                   │
│                           ▼                                         │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                      MASTER                                 │   │
│  │  • Assigns tablets to Tablet Servers                        │   │
│  │  • Detects Tablet Server failures (via Chubby)              │   │
│  │  • Balances load across Tablet Servers                      │   │
│  │  • Handles table creation/deletion                          │   │
│  │  • NOT in the read/write data path                          │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐             │
│  │ TABLET SRV 1 │  │ TABLET SRV 2 │  │ TABLET SRV 3 │  ...        │
│  │              │  │              │  │              │             │
│  │ tablet A     │  │ tablet C     │  │ tablet E     │             │
│  │ tablet B     │  │ tablet D     │  │ tablet F     │             │
│  │              │  │              │  │              │             │
│  │ (serves reads│  │ (serves reads│  │ (serves reads│             │
│  │  and writes  │  │  and writes  │  │  and writes  │             │
│  │  for its     │  │  for its     │  │  for its     │             │
│  │  tablets)    │  │  tablets)    │  │  tablets)    │             │
│  └──────────────┘  └──────────────┘  └──────────────┘             │
│                           │                                         │
│                    (reads/writes go to GFS)                         │
│                           ▼                                         │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                         GFS                                  │   │
│  │  • Stores SSTable files (the actual data)                   │   │
│  │  • Stores write-ahead logs (WAL)                            │   │
│  │  • Provides fault-tolerant storage beneath Bigtable         │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  CLIENT LIBRARY (not shown): talks to Chubby to find root tablet,  │
│  then finds its tablet server, then reads/writes directly.         │
│  Master is NOT in read/write path.                                 │
└─────────────────────────────────────────────────────────────────────┘
```

### Chubby: the distributed lock service

Chubby is a distributed lock service built on Paxos consensus. Think of it as a very small, very reliable key-value store that provides strong consistency guarantees. Bigtable uses Chubby for four critical purposes:

1. **Master election**: only one machine can be the Bigtable Master at any time. The Master holds a Chubby lock. If the Master crashes, the lock is released and another machine can acquire it to become Master.

2. **Tablet server discovery**: each Tablet Server registers itself in Chubby when it starts. The Master watches Chubby for new registrations (new Tablet Servers coming online) and registration deletions (Tablet Servers failing or shutting down).

3. **Root tablet location**: the start of the three-level tablet location hierarchy (explained in Part 4) is stored in Chubby. This is how clients begin the lookup process to find any tablet.

4. **Access control**: which users/services can read or write each table. Stored as ACL files in Chubby.

### The Master's role

The Master is responsible for administrative operations — not data operations. Specifically:
- Assigning tablets to Tablet Servers when the system starts or when a Tablet Server fails
- Detecting Tablet Server failures (by watching Chubby for Tablet Server session expiration)
- Rebalancing tablets across Tablet Servers when load is uneven
- Creating and deleting tables
- Garbage collecting old SSTable files that are no longer referenced

**Crucially: the Master is NOT in the read or write path.** Once a client knows which Tablet Server holds a tablet, it communicates directly with that Tablet Server. The Master is never involved in individual row reads or writes. This is the same architectural principle as GFS (Master out of data path) applied to Bigtable.

### Tablet Servers

Tablet Servers are the workhorses. Each Tablet Server manages a set of tablets (typically 10–1,000 tablets per server). For each tablet it serves, the Tablet Server handles:
- All reads and writes for that tablet's row range
- Splitting tablets that have grown too large
- Compaction (merging in-memory data with on-disk data to free memory)

Tablet Servers do NOT hold data durably themselves. All data is ultimately stored in GFS (as SSTable files and write-ahead log files). If a Tablet Server crashes, another Tablet Server can pick up its tablets from GFS — the data is safe in GFS regardless of which Tablet Server was serving it.

### Intern → Staff Progression (Part 3)

| Level | Understanding of the architecture |
|-------|----------------------------------|
| **Intern** | "There's a server that stores data." |
| **L3** | Knows there's a master and tablet servers. Cannot explain Chubby's role or the GFS dependency. |
| **L4** | Understands the three-tier architecture. Understands that the Master is not in the read/write path. |
| **L5** | Can explain Chubby's four roles. Understands that Tablet Servers use GFS for durability. Can explain what happens when a Tablet Server crashes (tablets reassigned, data safe in GFS). |
| **L6** | Can explain the full dependency chain: Bigtable depends on Chubby for coordination and GFS for storage. Can reason about failure scenarios: Chubby unavailable → Master can't function → new tablet assignment blocked, but existing reads/writes continue via cached tablet locations. Can articulate the design trade-offs of using Chubby vs. a Paxos group per tablet. |

### Common Interview Mistakes — Part 3

**Mistake 1: Not knowing that Bigtable depends on GFS.**
Bigtable stores its data (SSTables and WALs) in GFS. Tablet Servers are stateless with respect to their data — the actual bytes live in GFS. This means a Tablet Server failure does NOT lose data; the data is safe in GFS. When another Tablet Server takes over a tablet, it just reads the SSTable files from GFS. Without knowing this GFS dependency, you can't explain how Bigtable achieves durability.

**Mistake 2: Thinking the Master is in the read/write path.**
Same mistake as GFS. The Master assigns tablets but doesn't participate in individual row operations. Once the client has the tablet location (from the three-level lookup, explained in Part 4), all reads and writes go directly to the Tablet Server. The Master never sees individual rows.

**Mistake 3: Confusing Chubby with ZooKeeper.**
Chubby and ZooKeeper serve similar purposes (distributed coordination) but have key differences. Chubby is a coarse-grained lock service — it's designed for a small number of long-held locks (like "I am the Bigtable Master"), not for fine-grained coordination. ZooKeeper is often used for fine-grained coordination. For interview purposes: Chubby is to Bigtable what ZooKeeper is to HBase. ZooKeeper is the open-source analogue of Chubby, created partly in response to the Chubby paper.

### Cold-Start Read: The Complete Message Sequence

When a client has NO cached tablet locations (a brand-new client, or a client whose entire cache has been invalidated), it must do the full three-level lookup before it can read a single row. Here is the exact sequence of messages:

```
COLD-START READ SEQUENCE: client wants table["com.cnn.www"]["content:html"]

  CLIENT              CHUBBY            ROOT TABLET       METADATA          USER TABLET
                                        SERVER            TABLET SERVER     SERVER (TS-7)
    |                    |                 |                  |                |
    |-- [1] Read ------->|                 |                  |                |
    |   "where is        |                 |                  |                |
    |    root tablet?"   |                 |                  |                |
    |                    |                 |                  |                |
    |<-- [2] Response ---|                 |                  |                |
    |   "root tablet is  |                 |                  |                |
    |    on TS-1, port   |                 |                  |                |
    |    port 4321"      |                 |                  |                |
    |                    |                 |                  |                |
    |-- [3] Read ---------------------------->                |                |
    |   "what METADATA                     |                  |                |
    |    tablet holds                      |                  |                |
    |    webtable?"                        |                  |                |
    |                                      |                  |                |
    |<-- [4] Response ----------------------                  |                |
    |   "METADATA tablet for               |                  |                |
    |    webtable is on TS-3"              |                  |                |
    |                                      |                  |                |
    |-- [5] Read --------------------------------------------->                |
    |   "what user tablet                              |       |                |
    |    holds com.cnn.www?"                           |       |                |
    |                                                  |       |                |
    |<-- [6] Response ----------------------------------       |                |
    |   "tablet for rows                               |                        |
    |    com.a→com.f is on TS-7"                       |                        |
    |                                                                           |
    |-- [7] READ ---------------------------------------------------------------->
    |   "give me webtable                                                       |
    |    com.cnn.www /                                                          |
    |    content:html"                                                          |
    |                                                                           |
    |<-- [8] RESPONSE -----------------------------------------------------------
    |   "<html>CNN...</html>"
    |   (data returned from MemTable or SSTable on TS-7)

  SUMMARY:
  Message 1-2: Client → Chubby (root tablet location)
  Message 3-4: Client → Root Tablet Server (METADATA tablet location)
  Message 5-6: Client → METADATA Tablet Server (user tablet location)
  Message 7-8: Client → User Tablet Server (actual data read)

  Total round trips on cold start: 4
  Total round trips on warm cache (all locations known): 1 (just msg 7-8)

  CLIENT CACHES:
  After msg 2: client caches "root tablet is on TS-1"
  After msg 4: client caches "METADATA tablet for webtable is on TS-3"
  After msg 6: client caches "com.a→com.f tablet is on TS-7"
  All future reads to com.cnn.www go directly to TS-7 (msg 7-8 only)
```

This diagram shows why the three-level hierarchy has a significant warmup cost for a brand-new client, but amortizes to near-zero overhead once the cache is hot. A long-running client process almost never hits Chubby or the root tablet for normal operations.

### Additional Common Interview Mistakes — Part 3 (Extended)

**Mistake 1: Not knowing that Bigtable depends on GFS.**
Bigtable stores its data (SSTables and WALs) in GFS. Tablet Servers are stateless with respect to their data — the actual bytes live in GFS. This means a Tablet Server failure does NOT lose data; the data is safe in GFS. When another Tablet Server takes over a tablet, it just reads the SSTable files from GFS. Without knowing this GFS dependency, you can't explain how Bigtable achieves durability.

**Mistake 2: Thinking the Master is in the read/write path.**
Same mistake as GFS. The Master assigns tablets but doesn't participate in individual row operations. Once the client has the tablet location (from the three-level lookup, explained in Part 4), all reads and writes go directly to the Tablet Server. The Master never sees individual rows.

**Mistake 3: Confusing Chubby with ZooKeeper.**
Chubby and ZooKeeper serve similar purposes (distributed coordination) but have key differences. Chubby is a coarse-grained lock service — it's designed for a small number of long-held locks (like "I am the Bigtable Master"), not for fine-grained coordination. ZooKeeper is often used for fine-grained coordination. For interview purposes: Chubby is to Bigtable what ZooKeeper is to HBase. ZooKeeper is the open-source analogue of Chubby, created partly in response to the Chubby paper.

**Mistake 4: Not knowing what happens to in-flight reads/writes during a Chubby outage.**
A common interview mistake is to say "if Chubby goes down, Bigtable goes down." This is wrong. Existing reads and writes to tablets continue because clients have cached tablet locations. The Chubby outage only blocks: new client startups (can't do cold-start lookup), new tablet assignments by the Master, and Master failover. Ongoing operations on already-cached tablet locations proceed normally. This is a crucial distinction — Chubby is NOT in the hot data path.

### Real Incident (Part 3): The 2008 Chubby Outage

In 2008, Chubby experienced a roughly 30-minute outage at a Google data center. The sequence of events exposed exactly which parts of Bigtable depend on Chubby and which don't.

During the outage: existing Bigtable clients that had cached tablet locations continued reading and writing normally — they had no need to contact Chubby. Tablet Servers that were already running continued serving their tablets. The Bigtable Master, however, could not renew its Chubby lock. After a timeout period, the Master considered itself no longer the authoritative Master and stepped down. (This is a safety mechanism: a Master that can't reach Chubby might be partitioned, and another Master might have taken over. The old Master should not continue acting as Master in this case.) With no Master running, new tablet assignments were impossible — if a Tablet Server crashed during the Chubby outage, its tablets could not be reassigned to another server.

New clients starting up during the outage could not look up the root tablet location (that lookup requires reading a Chubby file). These new clients failed immediately with connection errors. Applications that were already running and had warm caches continued operating normally.

When the Chubby outage ended, the most serious problem was a thundering herd of METADATA queries. During the outage, some Tablet Servers had crashed (routine failures that happen in any large cluster). Their tablets had not been reassigned. When Chubby came back, the Master restarted, detected all the unassigned tablets, and triggered a mass reassignment. Simultaneously, all new clients that had been failing suddenly started their cold-start lookup sequences. Both floods hit the METADATA tablets at the same time — the METADATA servers became a bottleneck for several minutes after the Chubby outage ended.

The two fixes that came out of this incident: (1) the Bigtable client library began caching the root tablet location in local process memory with a long TTL, allowing the client to bypass Chubby for the first level of the hierarchy even after a process restart in many cases. (2) Google improved Chubby's availability through additional replicas and better network path redundancy. But the more important lesson was design validation: the system behaved exactly as intended during the outage — ongoing operations continued, only new operations and administrative functions were blocked. The architecture of keeping Chubby and the Master out of the data path was the reason a 30-minute coordination outage didn't cause a 30-minute user-visible outage.

### Brainstorming Questions — Part 3

**Q: What happens if Chubby becomes unavailable? Does Bigtable stop working?**

Chubby unavailability has different impacts on different parts of Bigtable. Existing reads and writes to existing tablets continue normally — because clients already have tablet locations cached and Tablet Servers already have their tablet assignments. The running system keeps running without Chubby for as long as sessions don't expire.

What breaks when Chubby is unavailable: new tablet server registrations, Master failover (the old Master can't renew its lock and a new Master can't acquire it), and new access control checks. If the Master crashes while Chubby is unavailable, Bigtable has no Master until Chubby comes back — tablets can't be reassigned, load can't be rebalanced, and table creation/deletion is blocked. However, all existing reads and writes to existing tablets continue via direct client-to-Tablet-Server communication.

This is a documented GFS and Bigtable pattern: the metadata/coordination tier (Master, Chubby) can be unavailable without making the data tier unavailable. Google's workloads tolerated short coordination outages (a few minutes of Master unavailability) without impacting user-facing reads and writes. This is an important design principle: design for partial failure, and clearly separate what can keep running from what is blocked when each component fails.

---

**Q: How does a Tablet Server failure get detected and recovered?**

Tablet Server failures are detected via Chubby. Each Tablet Server maintains a session with Chubby (a persistent connection with a lease). If the Tablet Server crashes or becomes network-partitioned, its Chubby session expires after the lease timeout (typically a few seconds to a minute). Chubby notifies the Master that the Tablet Server's session is gone.

The Master marks all tablets that were assigned to the failed Tablet Server as "unassigned." It then assigns these tablets to other Tablet Servers that have available capacity. The new Tablet Server picks up the tablet by reading its SSTable files from GFS (which are always up-to-date because all writes were committed to GFS before being acknowledged). The new Tablet Server also replays the tablet's write-ahead log from GFS to recover any writes that were in the Tablet Server's in-memory MemTable but not yet flushed to SSTable. After log replay, the tablet is fully up-to-date and ready to serve requests.

From the client's perspective: reads and writes to the failed tablet return errors during the reassignment window (seconds to a minute). The client library retries automatically. Once the tablet is reassigned to a new server, requests succeed. The total unavailability window for a specific tablet during a Tablet Server failure is typically 30–120 seconds.

---

**Q: Can Bigtable serve both OLTP (low-latency, single-row lookups) and OLAP (high-throughput, full-table scans) workloads simultaneously? What are the risks?**

Bigtable can technically serve both workloads simultaneously — the architecture doesn't distinguish between single-row reads and range scans. A Tablet Server handles all reads for its tablets regardless of whether they're point lookups or full scans. In practice, however, mixing OLTP and OLAP workloads on the same Bigtable cluster creates resource contention that degrades both.

The problem is that full-table scans (OLAP queries) consume enormous GFS bandwidth and Tablet Server CPU. A MapReduce job doing a full scan of a 1TB table reads 1TB of SSTable data from GFS over the course of the job. During that scan, the Tablet Servers serving the scanned tablets are I/O saturated — their GFS read bandwidth is consumed by the scan, leaving little bandwidth for concurrent OLTP reads. The OLTP latency (normally <5ms) can spike to >100ms during heavy scans.

The production solution at Google was to use two separate Bigtable clusters for the same data: one OLTP cluster (small, fast, high-cache-hit-rate) for online serving and one OLAP cluster (large, batch-scan optimized) for analytics workloads. The OLAP cluster receives writes asynchronously (replication lag of minutes to hours is acceptable for analytics). This is the same principle as "read replicas" in relational databases — separate the workloads onto separate infrastructure so they don't interfere with each other. The cost is running two clusters, but the benefit is predictable OLTP latency regardless of OLAP scan load.

---

## Part 4: Tablets — How Tables Are Split and Located

### What is a tablet?

A tablet is a contiguous range of rows within a table. A table with 1 billion rows might be split into 1,000 tablets, each covering 1 million consecutive rows. The split boundaries are determined by the row keys.

```
TABLE: webtable  (sorted by row key)

┌─────────────────────────────────────────┐
│ Tablet A  │ rows: "" → "com.cnn..."     │ → Tablet Server 1
├─────────────────────────────────────────┤
│ Tablet B  │ rows: "com.cnn..." →        │
│           │       "com.google..."       │ → Tablet Server 2
├─────────────────────────────────────────┤
│ Tablet C  │ rows: "com.google..." →     │
│           │       "com.yahoo..."        │ → Tablet Server 1
├─────────────────────────────────────────┤
│ Tablet D  │ rows: "com.yahoo..." → ∞   │ → Tablet Server 3
└─────────────────────────────────────────┘
```

A tablet is the unit of assignment: the Master assigns whole tablets to Tablet Servers. A tablet is also the unit of splitting: when a tablet grows too large (default: 100–200MB per tablet in 2006, larger in modern systems), the Tablet Server splits it into two tablets and reports the split to the Master.

### The three-level tablet location hierarchy

How does a client find which Tablet Server holds the row it wants to read? Bigtable uses a three-level hierarchy:

```
┌─────────────────────────────────────────────────────────────────────┐
│               THREE-LEVEL TABLET LOCATION HIERARCHY                 │
│                                                                     │
│  Level 0: Chubby                                                    │
│  ──────────────────────────────────────────────                     │
│  Chubby stores the location of the "root tablet."                   │
│  This is the only thing stored in Chubby for tablet location.       │
│                                                                     │
│  Level 1: Root Tablet (1 tablet, never split)                       │
│  ─────────────────────────────────────────────                      │
│  The root tablet contains the locations of all METADATA tablets.    │
│  (stored in METADATA table, which is itself a Bigtable table)       │
│                                                                     │
│  Level 2: METADATA Table (potentially many tablets)                 │
│  ──────────────────────────────────────────────────                 │
│  Each METADATA table row stores the location of one user tablet.    │
│  Format: (table_name + tablet_end_key) → Tablet Server address      │
│                                                                     │
│  Level 3: User Tablets (millions of tablets)                        │
│  ────────────────────────────────────────────                       │
│  The actual user data.                                              │
│                                                                     │
│  CLIENT LOOKUP SEQUENCE:                                            │
│  1. Read Chubby → get root tablet location                          │
│  2. Read root tablet → get METADATA tablet location for target table│
│  3. Read METADATA tablet → get user tablet location for target row  │
│  4. Read/write directly to that Tablet Server                       │
│                                                                     │
│  CACHING: Client caches tablet locations at all levels.             │
│  Most reads/writes skip all 3 lookup steps (fully cached).          │
│  Cache miss at level 3 → 1 extra Tablet Server read                 │
│  Cache miss at level 2 → 1 METADATA read + 1 user tablet read       │
│  Cache miss at level 1 → Chubby read + 2 more reads                 │
└─────────────────────────────────────────────────────────────────────┘
```

### Why three levels?

The METADATA table stores one entry per user tablet. Each entry is about 1KB. If the METADATA table itself gets too large for one tablet, it's split into multiple METADATA tablets. The root tablet stores the locations of all METADATA tablets. The root tablet itself is the one tablet that is NEVER split — it's the anchor of the entire hierarchy.

How much user data can this support? Each METADATA tablet is 128MB. At 1KB per entry, one METADATA tablet holds 128,000 user tablet locations. At 128MB per user tablet, one METADATA tablet covers 128,000 × 128MB = 16PB of user data. With multiple METADATA tablets, the system scales to exabytes.

### Tablet splitting and merging

**Splitting**: When a tablet grows beyond its size limit (typically determined by the Tablet Server), the Tablet Server splits it and notifies the Master. The Master updates the METADATA table with the two new tablet locations.

**Merging (compaction)**: When a tablet becomes very small (because data was deleted), adjacent tablets can be merged. The Master initiates this.

### Intern → Staff Progression (Part 4)

| Level | Understanding of tablets |
|-------|--------------------------|
| **Intern** | "The data is split across servers." Cannot explain how clients find their data. |
| **L3** | Knows there are tablets. Cannot explain the three-level hierarchy or how tablets are located. |
| **L4** | Understands the three-level lookup. Understands that client caching skips most lookups. |
| **L5** | Can explain the capacity math (how much data the three levels can address). Understands tablet splitting and when it happens. |
| **L6** | Can design the complete lookup protocol from scratch. Can explain what happens when the METADATA tablet containing a user tablet's location is itself being split. Can reason about the performance implications of the three-level hierarchy under cache miss scenarios. |

### Common Interview Mistakes — Part 4

**Mistake 1: Saying the Master serves tablet location lookups.**
The Master assigns tablets but does NOT serve location lookups to clients. The location lookup goes through the Chubby → root tablet → METADATA tablet → user tablet hierarchy. Once the client has cached the tablet location, it goes directly to the Tablet Server. The Master is never queried for data reads.

**Mistake 2: Not knowing that tablets can be reassigned.**
Tablets move between Tablet Servers for load balancing. The METADATA table always has the current location of every tablet. If a client has a stale cached tablet location (pointing to an old Tablet Server), it will get an error from the Tablet Server ("I don't have that tablet"). The client then re-does the location lookup through the METADATA table to get the current location.

### How Tablet Splitting Works in Practice

Understanding tablet splitting is not just theoretical — knowing WHEN and HOW tablets split helps you reason about write hotspots and performance cliffs in interview scenarios.

```
TABLET SPLIT SEQUENCE:

  BEFORE SPLIT: Tablet T1 holds rows "com.a" → "com.z", size = 195MB
  ┌──────────────────────────────────────┐
  │ Tablet T1 (195MB, approaching limit) │
  │   row range: "com.a" → "com.z"       │
  │   served by: Tablet Server 3          │
  └──────────────────────────────────────┘

  TRIGGER: T1 grows to 200MB (configured split threshold)

  STEP 1: Tablet Server 3 chooses a split key
    Split key = midpoint of the row key distribution
    For uniform distribution: split_key ≈ "com.m" (middle of com.a-com.z)
    For non-uniform: split_key = key that divides data bytes 50/50

  STEP 2: Tablet Server 3 creates two new tablet metadata entries
    T1a: rows "com.a" → "com.m",  size = ~98MB, served by TS-3
    T1b: rows "com.m" → "com.z",  size = ~97MB, served by TS-3

  STEP 3: Tablet Server 3 writes the split to the METADATA table
    METADATA["webtable_com.m"] = {server: "TS-3", ...}  ← T1a
    METADATA["webtable_com.z"] = {server: "TS-3", ...}  ← T1b

  STEP 4: Tablet Server 3 notifies the Master of the split

  STEP 5: Master updates its in-memory tablet map
    Now knows about T1a and T1b separately

  STEP 6 (optional, async): Master may reassign T1b to a less loaded
    Tablet Server for load balancing
    Master → Tablet Server 5: "you now own T1b (com.m → com.z)"
    TS-5 loads T1b SSTable from GFS, begins serving

  CLIENT PERSPECTIVE DURING SPLIT:
    Old cached location: "T1 (com.a → com.z) is on TS-3"
    After split:
    - Request to "com.cnn.www" → still goes to TS-3 (T1a) ✓ (correct)
    - Request to "com.yahoo.com" → still goes to TS-3 (T1a+T1b) ✓
    - After T1b moves to TS-5: request to "com.yahoo.com" → goes to
      TS-3, gets error "not my tablet", client re-reads METADATA,
      discovers T1b is now on TS-5, updates cache, retries → success
    Total extra latency: one METADATA round-trip = 1-5ms
```

### Tablet Location Caching: The Math

Why does the three-level hierarchy work efficiently despite caching being a separate concern from the data itself?

```
CACHE ANALYSIS FOR A LARGE BIGTABLE CLUSTER:

Cluster: 1 exabyte of user data
  1EB / 200MB per tablet = 5 billion tablets
  1 METADATA entry per tablet ≈ 1KB per entry
  Total METADATA size: 5 billion × 1KB = 5TB of metadata
  At 128MB per METADATA tablet: 5TB / 128MB = ~40,000 METADATA tablets
  All METADATA tablet locations stored in the root tablet
  Root tablet size: 40,000 entries × 1KB = ~40MB → fits in one tablet

Client cache analysis (per client process):
  Typical client accesses: 100,000 different rows
  Tablets accessed: ~100 tablets (100,000 rows / ~1000 rows per tablet)
  Cache entries needed: 100 tablet locations ≈ 100 × 100 bytes = 10KB
  This is TINY — every client caches all the locations it ever uses.

Cache hit rate in practice:
  A client serving web traffic accesses a small subset of tablets (locality
  of access — the same users keep coming back). Cache hit rate is typically
  >99% after a few minutes of warmup. The three extra round-trips of a cold
  start are amortized across thousands of subsequent requests.

Cache invalidation:
  Tablets are reassigned during: Tablet Server failure, load rebalancing.
  Frequency: < 1% of tablets reassigned per hour in a healthy cluster.
  99% cache hit rate × <1% reassignment rate = 0.01% of requests hit a
  stale cache entry. Each stale cache entry costs 1-3 extra round-trips.
  Net overhead: negligible.
```

### Brainstorming Questions — Part 4

**Q: Why is the root tablet never split? What would happen if it were?**

The root tablet is the anchor of the entire location hierarchy. If the root tablet were split, you'd have two root tablets — and there'd be no way to find them without another level of indirection above them. You'd need a "root root tablet" stored somewhere, which just pushes the problem up one level. The solution is to designate exactly one tablet as the permanent anchor and store its location in a fixed external system (Chubby). The root tablet is that anchor.

The practical implication: the root tablet must be sized to avoid splitting. It stores one entry per METADATA tablet (not per user tablet), so even if there are thousands of METADATA tablets, the root tablet might be only a few MB. The root tablet is small enough to never need splitting in practice, which validates the design choice of "never split the root tablet."

---

**Q: A client caches tablet locations to avoid the three-level lookup. What happens when a cached location becomes stale (the tablet moved to a different Tablet Server)?**

Stale cache entries are discovered lazily. The client tries to read/write a row using its cached Tablet Server address. The Tablet Server responds with an error: "I don't serve this tablet anymore." This error is the signal that the cache is stale.

At this point, the client invalidates the stale cache entry and retries the lookup by reading the METADATA table to get the current tablet location. If the METADATA tablet location is also stale (which would be unusual — it would mean two cascading reassignments happened between the client's last lookup and now), the client goes one level higher, reading the root tablet. In the worst case, the client re-does the entire three-level lookup from Chubby.

This lazy staleness detection means that tablet reassignment (due to Tablet Server failure or load rebalancing) causes a brief spike in METADATA reads as clients discover and correct their stale caches. After clients refresh their caches, the system returns to steady state. The three-level hierarchy is designed so that the "cache miss all the way up" case requires at most 3 extra round-trips, not proportional to the number of tablets.

---

**Q: Why does Bigtable use a three-level hierarchy (Chubby → root tablet → METADATA tablet → user tablet) instead of a two-level hierarchy (Chubby → METADATA tablet → user tablet) or a flat lookup stored entirely in Chubby?**

The design must handle the full range of Bigtable cluster sizes — from small clusters with thousands of tablets to Google-scale clusters with billions of tablets. Storing all tablet locations directly in Chubby would fail: Chubby is designed for a small number of coarse-grained locks and a few MB of data, not terabytes of tablet location metadata. Even a "flat" two-level design (one giant METADATA table, no root tablet) would fail because the METADATA table itself would become too large to fit in a single tablet, requiring it to be split — at which point you need a way to locate the METADATA tablets themselves, which brings you back to needing a root level.

The three-level design sizes each level appropriately: Chubby stores exactly ONE entry (the root tablet location), the root tablet stores one entry per METADATA tablet (tens of KB to a few MB), the METADATA tablets store one entry per user tablet (up to hundreds of GB total for a large cluster). Each level is sized to fit comfortably in its storage tier. This cascading fanout (1 → tens of METADATA tablets → millions of user tablets) is a logarithmic hierarchy — two levels of fanout support a billion tablets with manageable metadata sizes at each level.

The specific numbers: one METADATA tablet at 128MB holds 128K user tablet locations (at 1KB each). With 100 METADATA tablets, you address 12.8 million user tablets — that's roughly 1.3PB of user data at 100MB per tablet. The root tablet holds 100 entries for the 100 METADATA tablets — well under 1MB. This three-level structure scales from tens of tablets to billions without any design changes, which is the hallmark of a well-chosen hierarchy.

---

## Part 5: The LSM Tree

### Why not use a B-tree?

Most traditional databases use B-trees as their storage data structure: a balanced tree of nodes on disk, where each lookup traverses from the root to a leaf in O(log N) disk seeks. B-trees are good for random reads AND random writes — each write modifies one node in the tree in place.

The problem: random disk writes are slow. At thousands of writes per second, each write requiring a random disk seek (5–10ms per seek), a single disk can handle only 100–200 writes per second. B-trees can be optimized with caching, but at Bigtable's write scale, in-place updates on spinning disks don't work.

Bigtable uses an **LSM tree** (Log-Structured Merge tree) instead. The key insight: **always write sequentially, never write randomly.** Sequential writes are 10–100x faster than random writes on spinning disks (and faster on SSDs too).

### How the LSM tree works

The LSM tree has two stages: an in-memory buffer (the MemTable) and a sequence of on-disk sorted files (SSTables).

```
┌─────────────────────────────────────────────────────────────────────┐
│                    LSM TREE STRUCTURE                               │
│                                                                     │
│  MEMORY                                                             │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  MemTable (sorted in memory, newest writes here)            │   │
│  │                                                             │   │
│  │  com.cnn.www  → content:html="<html>CNN v3"  t=300         │   │
│  │  com.espn.com → content:html="<html>ESPN"    t=280         │   │
│  │  com.fox.com  → content:html="<html>Fox"     t=270         │   │
│  │  (sorted by row key)                                        │   │
│  └─────────────────────────────────────────────────────────────┘   │
│           │ when MemTable is full (~64MB)                           │
│           │ → flush to disk as new SSTable (minor compaction)       │
│           ▼                                                         │
│  DISK (in GFS)                                                      │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  SSTable-5 (newest, sorted, immutable)                      │   │
│  │  com.abc.com  → content:html="<html>ABC"  t=250            │   │
│  │  com.cbs.com  → content:html="<html>CBS"  t=240            │   │
│  ├─────────────────────────────────────────────────────────────┤   │
│  │  SSTable-4                                                  │   │
│  │  com.cnn.www  → content:html="<html>CNN v2" t=200          │   │  ← older version
│  │  com.nbc.com  → content:html="<html>NBC"   t=195           │   │
│  ├─────────────────────────────────────────────────────────────┤   │
│  │  SSTable-3                                                  │   │
│  │  com.cnn.www  → content:html="<html>CNN v1" t=100          │   │  ← oldest version
│  │  com.fox.com  → content:html="<html>Fox v1" t=90           │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  To read com.cnn.www: check MemTable first, then SSTable-5,        │
│  then SSTable-4, etc. The first hit with the right timestamp wins.  │
│  To avoid reading all SSTables: Bloom filters (see Part 7).        │
└─────────────────────────────────────────────────────────────────────┘
```

### SSTables: sorted, static tables

An SSTable (Sorted String Table) is a file on GFS containing a sorted set of key-value entries. Once written, an SSTable is **immutable** — it is never modified in place. This is the key property that enables sequential writes (you always write a new SSTable, never modify an existing one).

An SSTable has an index at the end of the file (or in a separate file): a list of (key → byte offset in file) entries that allows binary search to find any key without reading the whole file. Reading a key requires at most 2 disk reads: one to read the index, one to read the value.

### Compaction: merging SSTables

Over time, many SSTables accumulate on disk. More SSTables = slower reads (you have to check more files for each read). Bigtable solves this with **compaction**: periodically merging multiple SSTables into a single larger SSTable.

There are two types of compaction:

**Minor compaction (memtable flush):** When the MemTable reaches its size limit (~64MB), it is flushed to disk as a new SSTable. This happens frequently (every time the MemTable fills up).

**Major compaction (merging all SSTables):** All SSTables for a tablet are merged into a single SSTable. During this merge, deleted cells are actually removed (in non-major compaction, deleted cells are marked with a "tombstone" but not physically removed). Major compaction is expensive (reads all SSTables + writes one large SSTable) but leaves the tablet with exactly one SSTable — fastest possible reads.

```
COMPACTION LEVELS (simplified)

  Write→MemTable → [64MB] → flush to SSTable-L0
  
  Many L0 SSTables → compacted to L1 SSTable (larger, fewer)
  Many L1 SSTables → compacted to L2 SSTable (even larger, fewer)
  
  At each level: SSTables are larger and there are fewer of them.
  Major compaction: all levels → single SSTable
```

### Intern → Staff Progression (Part 5)

| Level | Understanding of the LSM tree |
|-------|-------------------------------|
| **Intern** | "Data is stored on disk." No understanding of how. |
| **L3** | Knows there's a MemTable and SSTables. Cannot explain WHY (the sequential write optimization). |
| **L4** | Understands the sequential write optimization. Understands that reads must check MemTable + multiple SSTables. |
| **L5** | Can explain minor vs major compaction. Understands tombstones. Understands the read amplification vs write amplification trade-off. |
| **L6** | Can explain the Bloom filter optimization for reads (Part 7). Can reason about the trade-offs of compaction frequency (fewer SSTables → faster reads but more write amplification). Can explain how LSM-tree-based writes avoid the write bottleneck of B-trees. Can identify other systems that use LSM trees (RocksDB, Cassandra, LevelDB). |

### Common Interview Mistakes — Part 5

**Mistake 1: Saying "Bigtable uses B-trees."**
Bigtable explicitly does NOT use B-trees for its primary storage. B-trees require random writes. Bigtable uses an LSM tree to achieve sequential writes. B-trees are used inside SSTables for the index (fast lookup within a single file), but the overall storage architecture is LSM.

**Mistake 2: Not understanding immutability of SSTables.**
SSTables are never modified once written. Updates to a row don't modify the old SSTable — they create a new entry in the MemTable, which is eventually flushed to a new SSTable. Old versions of the data remain in old SSTables until they're compacted away. This immutability is what makes compaction safe (you can read old SSTables while writing new ones).

**Mistake 3: Saying reads are always fast.**
LSM tree reads can be slow: you have to check the MemTable + every SSTable in descending age order until you find the key. With many SSTables (before compaction), this is many disk reads. This is the "read amplification" cost of LSM trees. The Bloom filter optimization (Part 7) mitigates this by letting you skip SSTables that provably don't contain the key.

### Compaction Lifecycle: A Detailed Example

The following diagram shows one tablet's complete compaction history over a period of active use. Track the SSTable count and approximate disk usage at each stage.

```
COMPACTION LIFECYCLE FOR ONE TABLET
(Tablet receives ~50K writes/hour. MemTable threshold = 64MB.)

STAGE 0: Fresh tablet
  SSTables: none
  Disk: 0 MB
  MemTable: filling up...

  [writes accumulate in MemTable]

STAGE 1: After 5 minor compactions (MemTable flushes)
  +------+   +------+   +------+   +------+   +------+
  | L0-1 |   | L0-2 |   | L0-3 |   | L0-4 |   | L0-5 |
  | 64MB |   | 64MB |   | 64MB |   | 64MB |   | 64MB |
  +------+   +------+   +------+   +------+   +------+
  SSTables: 5 (all L0 = direct MemTable flushes)
  Disk: ~320MB
  Note: L0 SSTables may have overlapping key ranges!
        (each flush includes whatever was in MemTable at that moment)

  Read cost: must check MemTable + up to 5 L0 SSTables per key
  Bloom filters help, but this is getting expensive.

STAGE 2: After merge compaction of the 5 L0 SSTables → one L1 SSTable
  +------------------+
  |        L1        |
  |     ~250MB       |   (smaller than 5 × 64MB because duplicates removed)
  |  (sorted, no     |
  |   overlaps)      |
  +------------------+
  SSTables: 1 (one clean L1)
  Disk: ~250MB
  Note: deduplication during merge removed old versions of overwritten rows
        this is why disk decreased from 320MB to 250MB

  Read cost: check MemTable + 1 L1 SSTable (fast — one Bloom filter, one file)

STAGE 3: After 5 more minor compactions (another wave of writes)
  +------+   +------+   +------+   +------+   +------+
  | L0-6 |   | L0-7 |   | L0-8 |   | L0-9 |   |L0-10 |
  | 64MB |   | 64MB |   | 64MB |   | 64MB |   | 64MB |
  +------+   +------+   +------+   +------+   +------+
  +------------------+
  |        L1        |
  |     ~250MB       |
  +------------------+
  SSTables: 6 (5 new L0 + 1 L1)
  Disk: ~570MB
  Read cost: check MemTable + up to 5 L0 + 1 L1 = 7 sources per key

STAGE 4: Major compaction — ALL SSTables merged into one
  +--------------------------------------------+
  |              MAJOR SSTable                  |
  |              ~400MB                         |
  |   (all data, deduplicated, old versions     |
  |    garbage collected, tombstones removed)   |
  +--------------------------------------------+
  SSTables: 1 (single clean file)
  Disk: ~400MB
  Note: went from ~570MB → 400MB because:
        - old versions of overwritten rows removed
        - deleted rows (tombstones) physically removed
        - only one copy of each (row, col, timestamp) survives

  Read cost: check MemTable + 1 SSTable (optimal)
  Write cost: EXPENSIVE — read all 570MB, write 400MB back to GFS

TABLET SIZE MONITORING:
  Target tablet size: 100-200MB
  If major SSTable > 200MB → tablet split into two tablets
  If tablet < 10MB → candidate for merge with adjacent tablet

COMPACTION TRIGGER THRESHOLDS (typical Bigtable config):
  Minor compaction:  MemTable reaches 64MB
  Merge compaction:  10 L0 SSTables accumulated
  Major compaction:  30 total SSTables, OR scheduled (once/day), OR
                     operator-triggered before major write burst
```

### Concrete Compaction Numbers

These numbers are from the original Bigtable paper and subsequent engineering blog posts from the Bigtable team. Knowing specific numbers separates memorization from understanding.

```
┌────────────────────────────────────────────────────────────────────┐
│              BIGTABLE COMPACTION: CONCRETE NUMBERS                  │
│                                                                     │
│  Typical tablet size:        100–200 MB (target, before splitting)  │
│  MemTable flush threshold:   ~64 MB (when MemTable → new L0 SSTable)│
│  Minor compaction trigger:   MemTable reaches 64MB                  │
│  Merge compaction trigger:   ~10 L0 SSTables accumulated            │
│  Major compaction trigger:   ~30 total SSTables, OR scheduled run   │
│                                                                     │
│  Read impact by SSTable count:                                      │
│   1 SSTable:    ~1ms random read  (Bloom filter + 1 file)           │
│   5 SSTables:   ~3ms random read  (likely 1-2 files after BF)       │
│  10 SSTables:  ~8ms random read  (3-4 files even with BF)           │
│  30 SSTables:  ~50ms random read (many false positives accumulate)  │
│ 100 SSTables:  >200ms (pathological — compaction severely lagging)  │
│ 200 SSTables:  >500ms (tablet is unusable for latency-sensitive ops) │
│                                                                     │
│  Write amplification factors:                                       │
│   WAL write:       1x the data (every write goes to WAL)            │
│   MemTable flush:  1x more (flush MemTable → L0 SSTable)            │
│   Each compaction: ~1x more (each merge rewrites all data in range)  │
│   Total typical:   ~10-30x write amplification across all levels    │
│                                                                     │
│  Major compaction duration (per 200MB tablet):                      │
│   I/O limited: read 200MB + write 200MB = ~400MB GFS I/O            │
│   At 100MB/s GFS throughput: ~4 seconds per tablet                  │
│   For 1000 tablets in parallel: cluster can compact 250 tablets/s   │
│   (Major compaction is CPU and I/O intensive — scheduled off-peak)  │
└────────────────────────────────────────────────────────────────────┘
```

### Real Incident (Part 5): The Disabled Compaction Bug

At a Google property using Bigtable (reported internally, similar incidents also documented in the HBase community as HBase shares the same architecture), major compaction was inadvertently disabled on a tablet due to a configuration bug. The specific trigger was a misconfigured maintenance window setting that told the Tablet Server "never run major compaction" — intended as a temporary bypass during a read-heavy traffic spike, but never reverted.

Over the next 3 months, the tablet continued receiving writes. Each flush created a new L0 SSTable. Merge compactions ran occasionally (triggered by the 10-SSTable threshold) but only merged the newest L0 files without eliminating older ones. The SSTable count grew steadily: from the healthy 3-5 SSTables to 20, then 50, then by month 3, over 200 SSTables.

The symptom: read latency on that specific tablet climbed from a baseline of under 10ms to consistently above 500ms. The Bloom filter false positive rate increased as more SSTables accumulated, causing more disk reads per key lookup. Engineers noticed the tablet was anomalous in latency dashboards but initially attributed it to a "hot" workload rather than a storage pathology.

When the root cause was identified (SSTable count = 200+), the tablet had to be taken offline for 2 hours while major compaction ran. During that time, all reads and writes to that tablet's row range returned errors. The rows recovered fully after compaction, with read latency returning to under 10ms within minutes of the compaction completing.

The fixes implemented after this incident: (1) add an SSTable count metric to the Tablet Server monitoring dashboard, with an alert threshold at 25 SSTables (well before the pathological range); (2) add a hard override that forces major compaction when SSTable count exceeds 50, regardless of the maintenance window configuration; (3) require a time-limited TTL on all compaction disable overrides, so "disable compaction" can only be set for a maximum of 6 hours before it auto-expires.

The lesson for engineers: in an LSM tree system, SSTable count is a critical health metric. It's not enough to monitor read latency alone — you need to also monitor SSTable count per tablet to catch compaction lag before it causes latency degradation. By the time latency spikes, the SSTable count is already in the danger zone.

### Brainstorming Questions — Part 5

**Q: Deleting a row in Bigtable doesn't immediately free disk space. How do deletions work in an LSM tree?**

Deletions in an LSM tree use tombstones. A tombstone is a special marker written to the MemTable saying "this cell/row has been deleted." The tombstone is just another write — it follows the normal write path (MemTable → flush → SSTable). The actual data (in older SSTables) is NOT immediately deleted.

During a read, if the most recent entry for a key is a tombstone, the system returns "not found" even though older SSTables still contain the key. The deletion appears immediately to readers even though the storage isn't freed. The old data is physically removed during compaction: when a major compaction merges all SSTables, it sees the tombstone and drops both the tombstone and all older versions of the deleted key. After major compaction, the storage is freed.

This means a Bigtable "delete" followed by a "check disk usage" may not show immediate space savings. Space is reclaimed asynchronously at compaction time. This surprises engineers used to filesystems where `rm` immediately frees space. For operational purposes, if you need to urgently reclaim space (e.g., a cluster is near full and you deleted a large table), you can trigger manual compaction. Otherwise, compaction happens automatically in the background.

---

**Q: What is write amplification and how does it affect Bigtable?**

Write amplification is the ratio of bytes written to storage per byte of actual user data written. In a simple write path (write once, never move), write amplification is 1x. In an LSM tree, write amplification is higher because each byte of data is written multiple times: once to the write-ahead log, once to the MemTable (in memory), once when flushed to an L0 SSTable, and potentially again during each compaction level.

In a typical Bigtable/LevelDB configuration, write amplification is 10-30x. This means for every 1GB of user data written, 10-30GB is actually written to disk across all compaction levels. This sounds bad, but the critical point is that ALL of these writes are sequential. Sequential writes to disk are 100-1000x faster than random writes. Even at 20x write amplification, sequential writes beat in-place (B-tree) random writes for high-throughput workloads.

The write amplification trade-off also has SSD implications: SSDs have a limited number of write cycles (terabytes written before wear). High write amplification burns through SSD life faster. Systems like Cassandra and RocksDB have tunable compaction strategies that let operators trade read performance for lower write amplification, depending on whether the workload is read-heavy or write-heavy. This tuning is an advanced topic but knowing that write amplification is a real operational concern separates L5 from L6 understanding.

---

**Q: RocksDB (used in TiKV, MyRocks, CockroachDB, and many other systems) also uses an LSM tree. How does RocksDB's approach differ from Bigtable's LSM tree design?**

Bigtable's LSM tree was designed in the early 2000s, and its compaction strategy is relatively simple: separate L0 (direct MemTable flushes), occasional merge compaction (combining several L0 SSTables), and periodic major compaction (one big file per tablet). This works well when the tablet is small (100-200MB) and the write rate is moderate. The simplicity is a virtue — fewer compaction decisions to make, and the tablet boundary naturally limits the scope of any single compaction.

RocksDB uses a leveled compaction strategy (LevelDB's approach, also designed by Google engineers but generalized). In leveled compaction: L0 SSTables are generated by MemTable flushes (same as Bigtable). L1 has a fixed size limit (say, 256MB). L2 is 10x larger (2.5GB). L3 is 10x again (25GB). And so on. When an L0 SSTable is ready, it's merged into L1. When L1 exceeds its size limit, SSTables are merged into L2. This cascading merge maintains the property that SSTables within each level (L2 and above) have non-overlapping key ranges — making point lookups require at most one SSTable read per level. The read amplification is bounded by the number of levels (typically 5-7) regardless of write volume, which is better than Bigtable's variable SSTable count.

The trade-off: RocksDB's leveled compaction has higher write amplification (each byte gets merged more times across more levels) but much more predictable read performance. Bigtable's simpler compaction has lower average write amplification but can have spikes of high read latency if major compaction falls behind. For a system where you need predictable read latency SLAs (sub-10ms P99 at all times), RocksDB's leveled compaction is generally preferable. For a system with very high write throughput where you're willing to accept occasional read latency spikes (controlled by scheduled major compaction), Bigtable's approach works well. This is exactly the design choice made by the teams that built TiKV (uses RocksDB) vs. Bigtable (custom LSM) — both are correct, just optimized for different trade-offs.

---

## Part 6: The Write Path

### Step-by-step: how a write flows through Bigtable

Let's trace a client writing one row to Bigtable. The row key is `com.cnn.www`, column is `content:html`, value is `<html>CNN latest</html>`.

```
┌─────────────────────────────────────────────────────────────────────┐
│                   BIGTABLE WRITE PATH                               │
│                                                                     │
│  Step 1: Client finds the Tablet Server                             │
│  ──────────────────────────────────────                             │
│  Client looks up tablet for "com.cnn.www" in its cache.            │
│  Cache says: Tablet Server 2 (TS-2) serves rows com.a → com.f.     │
│  Client → TS-2: WRITE request                                       │
│                                                                     │
│  Step 2: Tablet Server validates the request                        │
│  ────────────────────────────────────────────                       │
│  TS-2 checks access control (ACL in Chubby — cached locally).      │
│  TS-2 confirms it is still the tablet server for "com.cnn.www"      │
│  (Checks its in-memory tablet assignment list).                     │
│                                                                     │
│  Step 3: Write to the Write-Ahead Log (WAL)                         │
│  ──────────────────────────────────────────                         │
│  TS-2 appends the mutation to its WAL (a file in GFS).             │
│  WAL entry: {row: "com.cnn.www", col: "content:html",              │
│              ts: 1705312000, value: "<html>CNN latest</html>"}      │
│  TS-2 calls fsync (or GFS's equivalent) to ensure the WAL          │
│  entry is durably committed to GFS.                                 │
│  [IMPORTANT: data is now DURABLE even if TS-2 crashes after this]  │
│                                                                     │
│  Step 4: Apply to MemTable                                          │
│  ──────────────────────────                                         │
│  TS-2 inserts the mutation into its in-memory MemTable.            │
│  MemTable is a sorted data structure (usually a skip list or       │
│  balanced BST) keyed by (row_key, col_family, col_qualifier, ts).  │
│                                                                     │
│  Step 5: Return SUCCESS to client                                   │
│  ─────────────────────────────────                                  │
│  TS-2 → Client: "Write successful."                                 │
│                                                                     │
│  [The value is now in the WAL (durable) and the MemTable           │
│   (in memory). It is NOT yet in any SSTable on disk.]              │
│                                                                     │
│  Step 6: Eventually — Minor Compaction (async, background)          │
│  ──────────────────────────────────────────────────────────         │
│  When the MemTable reaches its size limit (~64MB):                  │
│  TS-2 creates a new SSTable from the MemTable contents.            │
│  TS-2 writes the SSTable to GFS (sequential write → fast).         │
│  TS-2 clears the MemTable (in-memory).                             │
│  TS-2 truncates the WAL (WAL entries covered by the new SSTable    │
│  are no longer needed for recovery).                                │
└─────────────────────────────────────────────────────────────────────┘
```

### Why the WAL before the MemTable?

The WAL (Write-Ahead Log) is the durability guarantee. The sequence is:

1. Write to WAL (durable, in GFS) → now the write survives any crash
2. Write to MemTable (in memory) → now the write is queryable
3. Return success to client

If the Tablet Server crashes after step 1 but before step 2, the data is safe in the WAL. When another Tablet Server takes over the tablet, it replays the WAL to reconstruct the MemTable. No data is lost.

If the Tablet Server crashes before step 1, the write is lost — but the client never received a success response, so it will retry. This is the correct behavior.

### Shared WAL across tablets

One Tablet Server handles many tablets. Each tablet conceptually has its own write-ahead log. But writing to many WAL files simultaneously (one per tablet) is inefficient — it causes many random writes. Bigtable instead uses ONE shared WAL file per Tablet Server, and all writes from all tablets go to this shared log.

The tradeoff: when a Tablet Server fails, the shared WAL contains entries for many tablets that will be reassigned to different Tablet Servers. Each new Tablet Server must read through the entire shared WAL and pick out only the entries for its specific tablets. This adds recovery time — the recovery process must "sort" the shared WAL by tablet. Bigtable handles this by having the recovering servers sort the WAL entries in parallel before replaying.

### Intern → Staff Progression (Part 6)

| Level | Understanding of the write path |
|-------|--------------------------------|
| **Intern** | "The client writes to the server and it's saved." |
| **L3** | Knows writes go to the WAL and MemTable. Cannot explain why WAL comes first. |
| **L4** | Understands WAL-before-MemTable for durability. Understands minor compaction (MemTable → SSTable). |
| **L5** | Understands the shared WAL optimization and its trade-off (faster writes, slower tablet recovery). Can explain what happens when a Tablet Server crashes mid-write. |
| **L6** | Can design the complete write path for a new storage system. Can reason about WAL sharing vs. per-tablet WAL under different failure recovery time requirements. Can explain write amplification in the context of compaction. |

### Common Interview Mistakes — Part 6

**Mistake 1: Saying "writes are committed when they reach the MemTable."**
A write is NOT committed (durable) when it reaches the MemTable. The MemTable is in memory — a crash loses it. A write is committed (durable) when it is written to the WAL in GFS. The MemTable is just the fast-access index of recent writes. This is one of the most commonly messed-up facts about Bigtable's write path — the WAL is the durability guarantee, not the MemTable.

**Mistake 2: Confusing the WAL with an SSTable.**
Both the WAL and SSTables are stored in GFS, both contain write data, but they are completely different structures. The WAL is an append-only log of mutations in arrival order — not sorted, not indexed, not efficient for lookups. It exists only for crash recovery. An SSTable is a sorted, indexed, immutable file optimized for efficient key lookups and range scans. The WAL is written FIRST (for durability) and the SSTable is written LATER (via compaction, for query efficiency). Calling them the same thing or conflating their roles signals a fundamental misunderstanding of the write path.

**Mistake 3: Not knowing that the WAL is shared across tablets on one Tablet Server.**
A key operational detail: one Tablet Server uses ONE shared WAL file for ALL tablets it manages, not one WAL per tablet. This makes writes faster (one sequential write to one file vs. many concurrent writes to many files), but complicates recovery. When a Tablet Server fails, the shared WAL must be sorted/partitioned by tablet ID before different Tablet Servers can replay the entries for the specific tablets they're inheriting. Candidates who say "each tablet has its own WAL" are wrong about the implementation.

**Mistake 4: Not knowing that the MemTable is lost on crash without the WAL.**
If a Tablet Server crashes with 50MB of data in the MemTable that hasn't been flushed to an SSTable yet, is that data lost? The answer is NO — because the WAL already has those mutations (they were written to the WAL before the MemTable was updated). The recovering Tablet Server replays the WAL to reconstruct the MemTable state. But if the WAL were missing or truncated (e.g., a bug deleted it), those 50MB of writes would be permanently lost. This is why the WAL write MUST complete (with fsync) before the MemTable is updated and before success is returned to the client. The ordering WAL-then-MemTable is not arbitrary — it is the invariant that makes crash recovery correct.

### The Write Path Under Load: Throughput vs Latency Trade-offs

A critical concept that separates L5 from L6 understanding is knowing HOW the write path degrades under high load — not just that it degrades, but the specific sequence.

```
WRITE PATH DEGRADATION SEQUENCE:

Normal operation (healthy tablet):
  WAL append: ~1ms (sequential GFS write, fast)
  MemTable insert: <0.1ms (in-memory sorted structure)
  Total write latency: ~1-2ms

Stage 1: MemTable pressure (MemTable nearly full)
  New writes still fast (MemTable has space)
  BUT: minor compaction running in background
  GFS bandwidth split between WAL writes AND SSTable writes
  If GFS is the bottleneck: WAL appends slow to 3-5ms
  Total write latency: ~3-6ms (2-3x slower)

Stage 2: Too many L0 SSTables (merge compaction lagging)
  MemTable flushes are fast, but L0 accumulates (10+ SSTables)
  Reads now slow down (check 10+ SSTables per key)
  Tablet Server spends more CPU on merge compaction
  CPU contention slows MemTable inserts
  Total write latency: ~5-10ms (5x slower)

Stage 3: SSTable count extreme (major compaction needed)
  20+ SSTables: Bloom filters have increasing false positive rates
  Reads >50ms for random keys (many SSTable lookups)
  Read load consumes GFS bandwidth that compaction needs
  Compaction falls further behind, SSTable count grows
  Write latency: 10-50ms (10-50x normal) due to GFS I/O saturation

Stage 4: GFS I/O saturation (compaction + writes contending)
  Major compaction reads all SSTables WHILE new writes arrive
  GFS bandwidth completely saturated
  Write acknowledgments stall (GFS WAL append queue fills)
  Clients experience write timeouts
  Some writes retry → adds MORE load → further degrades

Recovery path from Stage 4:
  1. Throttle incoming writes (rate limit at application level)
  2. Let major compaction complete (reduces SSTable count)
  3. After compaction: SSTable count drops, reads fast again
  4. GFS I/O contention reduces, WAL appends return to normal
  5. Gradually un-throttle writes
  Total recovery time: 15-60 minutes depending on tablet size
```

This degradation sequence is why SSTable count monitoring is essential. By the time you notice write latency doubling, you're already in Stage 2. You want to catch Stage 1 early by alerting on SSTable count, not on write latency.

### Real Incident (Part 6): The Gmail Write Storm

In early Gmail deployments, certain user actions caused "write storms" — a sudden burst of writes for a single user (e.g., bulk label changes on thousands of emails). These bursts caused the MemTable for the user's tablet to fill up rapidly, triggering frequent minor compactions. Each compaction wrote a new SSTable to GFS. When too many SSTables accumulated, read performance degraded significantly (too many SSTables to check per read).

The root cause was a mismatch between Gmail's access pattern (bursty per-user writes) and Bigtable's assumption of relatively steady write rates. The fix was twofold: Gmail implemented write rate limiting and batching (coalescing multiple small writes into fewer large ones), and Bigtable improved its compaction triggering logic to begin compaction earlier instead of waiting until the SSTable count reached a very high threshold. This incident is a good example of how even a well-designed storage system can be overwhelmed by access patterns it wasn't optimized for.

### Brainstorming Questions — Part 6

**Q: What happens if a Tablet Server's local disk fills up while writing the WAL?**

First, a clarification of the architecture: Bigtable's WAL is NOT written to the Tablet Server's local disk. It is written to GFS. GFS is a distributed file system that spreads data across many machines. The Tablet Server itself is intentionally stateless — it holds data in memory (MemTable) and uses GFS for all durable storage (WAL and SSTables). So the premise of "local disk fills up" doesn't directly apply to the WAL — GFS manages its own disk space across its chunkservers.

However, the spirit of the question — what happens when the WAL write fails — is worth answering in depth. If a GFS write to the WAL fails (for any reason: GFS chunkserver error, quota exceeded on the GFS namespace, network partition between the Tablet Server and GFS), the Tablet Server cannot safely commit the write. The WAL write must succeed before the MemTable is updated. If the WAL write fails, the Tablet Server returns an error to the client — the write is rejected. The client is responsible for retrying. This is the correct behavior: it's better to return an error to the client than to silently accept a write that might not survive a crash.

The practical concern this question is probing is: what happens when the GFS cluster used for WAL storage runs out of space? The answer is that writes to ALL tablets on ALL Tablet Servers in that cluster would start failing. This is a true cluster-level emergency — equivalent to running out of disk space in any storage system. The operational response is: (1) delete old WAL files and SSTables (trigger compaction to create smaller SSTables, then garbage collect old ones); (2) expand GFS storage by adding more chunkservers; (3) if neither is possible fast enough, shed write load temporarily. This is why GFS disk usage monitoring with early alerts (at 80% full, 90% full) is a critical operational practice for any Bigtable deployment.

**Q: Two clients write to the same row simultaneously. What does Bigtable guarantee?**

Bigtable guarantees row-level atomicity: all mutations to a single row either all succeed or all fail. This means a single write operation that modifies multiple cells in the same row is atomic — readers either see all the modifications or none of them. There is no partial row visibility.

However, Bigtable provides no cross-row transaction guarantees (in the original design — Spanner added this later). Two clients writing to different rows concurrently: both writes succeed independently, with no ordering guarantee between them. Two clients writing to the SAME row concurrently: both writes succeed, but the final state depends on the order in which the Tablet Server serialized them. The last write wins for each individual cell (highest timestamp wins within a cell, or the write that arrived later if using auto-timestamps).

For applications that need cross-row transactions (e.g., "debit from row A, credit to row B atomically"), Bigtable's original design doesn't support it. The application must implement its own optimistic locking or use a higher-level system (like Percolator, which implements distributed transactions on top of Bigtable using timestamp-based locking).

---

## Part 7: The Read Path

### Step-by-step: how a read flows through Bigtable

Reading from Bigtable requires merging data from multiple sources: the MemTable (newest data, in memory) and potentially many SSTables (older data, on disk). The answer is the most recent version of the requested cell.

```
┌─────────────────────────────────────────────────────────────────────┐
│                   BIGTABLE READ PATH                                │
│                                                                     │
│  Client wants: table["com.cnn.www"]["content:html"][latest]         │
│                                                                     │
│  Step 1: Find the Tablet Server                                     │
│  ─────────────────────────────                                      │
│  Client looks up tablet for "com.cnn.www" → TS-2 (from cache)      │
│  Client → TS-2: READ request                                        │
│                                                                     │
│  Step 2: Tablet Server checks MemTable first                        │
│  ───────────────────────────────────────────                        │
│  TS-2 searches its MemTable for ("com.cnn.www", "content:html").    │
│  FOUND: timestamp=1705399200, value="<html>CNN latest v3</html>"    │
│                                                                     │
│  → Return this value immediately. No disk I/O.                     │
│                                                                     │
│  [If NOT found in MemTable, continue to Step 3]                     │
│                                                                     │
│  Step 3: Check Bloom filters for each SSTable                       │
│  ─────────────────────────────────────────────                      │
│  TS-2 has 4 SSTables (SST-1 through SST-4).                        │
│  For each SSTable, check its Bloom filter:                          │
│  SST-4 Bloom filter: "does it contain com.cnn.www?" → YES (maybe)  │
│  SST-3 Bloom filter: "does it contain com.cnn.www?" → YES (maybe)  │
│  SST-2 Bloom filter: "does it contain com.cnn.www?" → NO (certain) │
│  SST-1 Bloom filter: "does it contain com.cnn.www?" → NO (certain) │
│                                                                     │
│  → Only need to check SST-4 and SST-3. Skip SST-2 and SST-1.      │
│                                                                     │
│  Step 4: Read from relevant SSTables (newest first)                 │
│  ──────────────────────────────────────────────────                 │
│  Read SST-4 (newer): FOUND com.cnn.www / content:html at t=1705312000│
│  (This is an older version than what we're looking for, but we'd   │
│   check if we needed an older version. For "latest", MemTable win.) │
│                                                                     │
│  [Actually in step 2 we already found the latest in MemTable,      │
│   so we returned immediately. This step only runs if MemTable miss] │
│                                                                     │
│  Step 5: Return the merged result                                   │
│  ──────────────────────────────                                      │
│  Return the cell with the highest timestamp (most recent version).  │
│  If multiple versions requested: merge MemTable + SSTable results,  │
│  sorted by timestamp descending, return the top N.                  │
└─────────────────────────────────────────────────────────────────────┘
```

### Bloom filters: skipping irrelevant SSTables

A Bloom filter is a space-efficient data structure that answers "does this SSTable contain this key?" with two possible answers:
- **"Definitely NO"** (100% certain) → skip this SSTable, save a disk read
- **"Maybe YES"** (false positive possible) → read this SSTable to check

A Bloom filter uses a tiny amount of memory (a few bytes per key) to provide the "definitely NO" guarantee. Without Bloom filters, reading a key that doesn't exist requires reading ALL SSTables. With Bloom filters, a non-existent key requires reading only the SSTables that returned "maybe YES" — in practice, only 1-2 SSTables even with false positives.

The false positive rate is tunable: a larger Bloom filter → lower false positive rate → fewer unnecessary SSTable reads, but more memory. A typical Bloom filter at 10 bits per key has a ~1% false positive rate — well worth the memory cost.

### Read amplification

Even with Bloom filters, reads in an LSM tree are more expensive than writes. The worst case for a read:
1. MemTable miss (key not in MemTable)
2. Bloom filter says "maybe" for all SSTables
3. Must read N SSTable index blocks + N SSTable data blocks

The more SSTables exist (because compaction hasn't run), the worse reads get. This is the fundamental LSM tree read-write trade-off:
- **More compaction** → fewer SSTables → faster reads, but more write amplification (each byte gets rewritten at each compaction level)
- **Less compaction** → more SSTables → slower reads, but less write amplification

### Intern → Staff Progression (Part 7)

| Level | Understanding of the read path |
|-------|-------------------------------|
| **Intern** | "The client reads from the server." |
| **L3** | Knows reads check MemTable first, then disk. Cannot explain Bloom filters. |
| **L4** | Understands MemTable → SSTable lookup order. Understands that the most recent version wins. |
| **L5** | Can explain Bloom filters and their role in skipping SSTables. Understands read amplification. |
| **L6** | Can explain the read/write amplification trade-off and how to tune it. Can explain how multi-version reads (returning the last N versions) work across MemTable + multiple SSTables. Can explain how a range scan works (more complex than a point lookup — must merge sorted iterators from MemTable + all SSTables). |

### Common Interview Mistakes — Part 7

**Mistake 1: Saying "Bloom filters guarantee the key is in the SSTable."**
Bloom filters can say "definitely NOT here" (zero false negatives) but NOT "definitely here." A positive answer from a Bloom filter means "maybe" — you still have to read the SSTable to confirm. A negative answer is certain — you can skip the SSTable entirely. A candidate who says "Bloom filters tell you if a key is in an SSTable" has the semantics backwards. Bloom filters tell you if a key is DEFINITELY NOT in an SSTable — that's the useful direction.

**Mistake 2: Forgetting that range scans must merge multiple sorted iterators.**
A point lookup (read one specific row key) is relatively simple. A range scan ("give me all rows from `com.cnn.www` to `com.google.www`") requires creating a sorted merge of the MemTable iterator and all SSTable iterators for that row range — a k-way merge. This is why compaction (reducing the number of SSTables) improves not just point lookup performance but also range scan performance. Candidates who understand point lookups but haven't thought about range scans are missing a significant part of the read path.

**Mistake 3: Not knowing that Bloom filters are per-SSTable, stored in memory.**
Bloom filters are loaded into memory when a Tablet Server takes over a tablet. They are NOT on the critical read path on disk — they are pre-loaded into RAM. A typical Bloom filter at 10 bits per key requires only 10 bits × (number of keys in SSTable) of RAM. For an SSTable with 1 million keys, that's 10 million bits = ~1.2MB of RAM. With hundreds of SSTables per Tablet Server, the total Bloom filter RAM footprint is tens to hundreds of MB — substantial but manageable. Candidates who say "checking Bloom filters requires disk I/O" are wrong. The whole point is that they're in RAM.

**Mistake 4: Assuming that "newest first" means the MemTable always wins.**
The MemTable contains the MOST RECENTLY WRITTEN data, but that doesn't mean it always contains the data for every key you read. A key that was last written 3 weeks ago and hasn't been touched since might be in SSTable-1 (the oldest SSTable), not in the MemTable at all. The MemTable only wins when the key was written recently (in the current MemTable flush cycle, typically the last few minutes to hours depending on write rate). For historical data, you must check the SSTables.

### Worked Example: Range Scan With K-Way Merge

Let's trace a range scan in concrete detail. The client requests: all rows from `user_1000` to `user_1999` in a tablet that has 1 MemTable + 4 SSTables.

```
TABLET STATE BEFORE SCAN:
  MemTable (in memory):
    user_1003 → col:email = "alice@example.com"
    user_1005 → col:email = "bob@example.com"
    user_1500 → col:email = "carol@example.com"

  SSTable-4 (newest on disk):
    user_1001 → col:email = "zara_v2@example.com"  (updated)
    user_1003 → col:email = "alice_old@example.com" (OLDER, MemTable version supersedes)
    user_1050 → col:email = "dave@example.com"

  SSTable-3:
    user_1001 → col:email = "zara_v1@example.com"  (oldest version, superseded by SSTable-4)
    user_1200 → col:email = "eve@example.com"
    user_1700 → col:email = "frank@example.com"

  SSTable-2:
    user_1400 → col:email = "grace@example.com"
    user_1800 → col:email = "henry@example.com"

  SSTable-1 (oldest):
    user_1000 → col:email = "ivan@example.com"
    user_1999 → col:email = "judy@example.com"

BLOOM FILTER CHECK:
  All 4 SSTables have keys in the user_1000-user_1999 range, so all
  4 must be included in the scan (no SSTables can be skipped).
  Bloom filters help for point lookups but not for range scans —
  a range scan must check all SSTables whose key range overlaps the query range.

K-WAY MERGE SETUP:
  Create 5 iterators (1 per source), each positioned at "user_1000":
  Iterator-MEM:  → user_1003
  Iterator-SST4: → user_1001
  Iterator-SST3: → user_1001
  Iterator-SST2: → user_1400
  Iterator-SST1: → user_1000

  Priority queue ordered by (row_key ASC, timestamp DESC):
  Initial queue: [user_1000/SST1, user_1001/SST4, user_1001/SST3,
                  user_1003/MEM, user_1003/SST4, user_1400/SST2, ...]

MERGE ITERATION (output order):

  Step 1: Pop user_1000 from SST1
    Output: user_1000 → "ivan@example.com"  ✓
    Advance SST1 iterator → user_1999

  Step 2: Pop user_1001 from SST4 (higher timestamp than SST3's user_1001)
    Output: user_1001 → "zara_v2@example.com"  ✓
    Advance SST4 iterator → user_1050

  Step 3: Pop user_1001 from SST3
    SAME ROW as output in Step 2, OLDER timestamp → DISCARD (deduplicate)
    Advance SST3 iterator → user_1200

  Step 4: Pop user_1003 from MemTable (highest timestamp — it's the newest write)
    Output: user_1003 → "alice@example.com"  ✓
    Advance MemTable iterator → user_1005

  Step 5: Pop user_1003 from SST4 (older version of same row)
    SAME ROW as Step 4, OLDER timestamp → DISCARD
    Advance SST4 iterator → (beyond user_1999, done)

  Step 6: Pop user_1005 from MemTable
    Output: user_1005 → "bob@example.com"  ✓
    Advance MemTable iterator → user_1500

  ... [continue for user_1050, user_1200, user_1400, user_1500, ...]

  Final Output (in row key order, deduplicated):
    user_1000 → "ivan@example.com"
    user_1001 → "zara_v2@example.com"    (SST4 version, not the older SST3 version)
    user_1003 → "alice@example.com"      (MemTable version, not the older SST4 version)
    user_1005 → "bob@example.com"
    user_1050 → "dave@example.com"
    user_1200 → "eve@example.com"
    user_1400 → "grace@example.com"
    user_1500 → "carol@example.com"
    user_1700 → "frank@example.com"
    user_1800 → "henry@example.com"
    user_1999 → "judy@example.com"

KEY INSIGHT: The merge reads each SSTable SEQUENTIALLY within the range.
No random I/O — sequential disk reads within each SSTable, all merge-sorted
in memory. For 10,000 rows across 4 SSTables, this is roughly:
  4 sequential reads × (range fraction of SSTable) ≈ very fast
Compare to a SQL B-tree scan: might require random I/O to follow B-tree
node pointers, especially if the table is fragmented after many updates.
```

### Brainstorming Questions — Part 7

**Q: Reading a row that has 5 versions across 3 SSTables and the MemTable — what does the read path look like?**

The Tablet Server creates a merge iterator: one iterator for the MemTable and one iterator for each SSTable. Each iterator is positioned at the first entry for the target row key. The iterators are merged in a priority queue, ordered by timestamp descending (newest first). The Tablet Server advances through the merged result, collecting versions until it has either found the requested number of versions or exhausted all sources.

Concretely for 5 versions: the MemTable has the latest version (timestamp 5). SSTable-3 (newest on disk) has version 4. SSTable-2 has versions 3 and 2. SSTable-1 (oldest) has version 1. The merge iterator sees them in order: [5, 4, 3, 2, 1]. If the client requested "latest version only," the Tablet Server returns the MemTable's entry immediately after confirming no newer version exists in another source. If the client requested "last 3 versions," it returns [5, 4, 3] — stopping after version 3.

The key performance observation: this multi-source merge is proportional to the number of SSTables, not the total number of entries. With Bloom filters eliminating SSTables that don't contain the key, and with compaction reducing the SSTable count, the merge is typically over just 2-4 sources for a well-maintained tablet.

---

**Q: What makes a Bigtable scan much faster than a SQL table scan?**

The fundamental difference is I/O pattern. A SQL table stored in a B-tree on spinning disk (or SSD) may require random I/O during a scan because B-tree pages can be scattered across disk as the tree grows and pages split. Each time the B-tree scan follows a pointer from one page to another, that's a random seek on a spinning disk. At 5-10ms per random seek, scanning a million-row SQL table with a non-clustered index can require millions of random reads — taking minutes.

Bigtable (LSM tree) scans read SSTables sequentially. An SSTable is a sorted, sequential file on disk. A range scan within an SSTable reads a contiguous block of data — the disk head moves in one direction without backtracking. Sequential I/O on spinning disk is 100-500 MB/s; random I/O on the same disk is 0.5-5 MB/s. For the same 1 million rows stored in a Bigtable SSTable vs. a B-tree, the SSTable scan is 100-1000x faster for sequential read throughput. On SSDs, the advantage narrows (SSDs have much better random I/O than spinning disks), but sequential reads are still faster than random reads on SSDs due to prefetching and larger read granularity.

The second advantage is column-family storage isolation. A SQL full-table scan reads ALL columns for ALL rows, even if the query only needs 2 of 20 columns. Bigtable's column family model stores each column family in separate SSTable files. A scan that reads only the `content` column family does not read any bytes from the `anchor` or `metadata` column families — the I/O is proportional to the data requested, not the total table width. This "column-family pruning" is the wide-column store's equivalent of columnar storage (like Parquet or ORC) — you only read what you need. For tables with many sparse columns (most Bigtable tables), this is a substantial I/O reduction.

---

## Part 8: Row Key Design

### Why this is the most important skill

Row key design is the skill that defines L5 vs L6 in Bigtable discussions. The data model, architecture, LSM tree — all of that is learnable by reading the paper. But row key design is applied knowledge that comes from understanding the relationship between the key and performance.

The rule: **what you want to scan efficiently, put first in the row key.**

Because rows are sorted lexicographically by row key, a prefix scan (give me all rows where the key starts with "prefix") reads a contiguous block of storage. If "who uses this system" (users, organizations, geographic tiles) should be the dominant access pattern, their identifier should be the first element of the row key.

### Pattern 1: Reversed domain names

**Problem:** Store web crawl data where you often query "all pages from a specific domain."

**Naive row key:** `www.google.com/search?q=bigtable`

**Problem with naive approach:** All `google.com` URLs are NOT adjacent. `www.google.com` sorts near other `www.` entries from many domains, not near `news.google.com` or `mail.google.com`.

**Bigtable row key:** `com.google.www/search?q=bigtable`

**Why it works:** By reversing the domain components, all google.com subdomains sort together: `com.google.`, `com.google.mail.`, `com.google.news.`, `com.google.www.`. A scan for "all google.com pages" is a prefix scan on `com.google.` — a single contiguous read.

### Pattern 2: User + timestamp for time-series data

**Problem:** Store Gmail messages where you need to show a user's most recent emails first.

**Naive row key:** `user_id + message_id`

**Problem with naive approach:** Messages sort by message_id (chronological order). To show the newest emails, you'd need to scan all of a user's messages and pick the newest — or scan the entire table in reverse.

**Bigtable row key:** `user_id + (MAX_INT - timestamp)`

**Why it works:** By using `MAX_INT - timestamp`, older timestamps have LARGER row keys and sort LATER. The newest messages sort first within a user's prefix. A scan for "user_id's recent emails" starts at `user_id + 0` (which represents the current time) and reads forward — giving you the newest emails first.

```
ROW KEY EXAMPLES FOR GMAIL

  user_id=u001, timestamp=1705399200 (Jan 16 2024 10:00am):
  Row key = "u001" + (9999999999 - 1705399200) = "u001-8294600799"

  user_id=u001, timestamp=1705312000 (Jan 15 2024 10:00am):
  Row key = "u001" + (9999999999 - 1705312000) = "u001-8294687999"

  SORTED ORDER (lexicographic):
  u001-8294600799  (Jan 16, newest)
  u001-8294687999  (Jan 15, older)
  ...
  u001-9999999999  (oldest possible)

  Scan from "u001-" to "u001z" gives u001's emails, newest first.
```

### Pattern 3: Avoiding hotspots with salting

**Problem:** Storing sensor data where all sensors write to a "current" timestamp, causing all writes to land on the same tablet (the "latest" end of the sorted table).

**Problem:** A time-ordered row key (`timestamp + sensor_id`) means all current writes go to the highest timestamp — the same tablet. One tablet server handles 100% of writes. This is a hotspot.

**Solution:** Prefix the row key with a hash of the sensor ID, modulo a bucket count (say 100):

```
Row key = (sensor_id % 100) + "_" + timestamp + "_" + sensor_id

Examples:
  Sensor 347: (347 % 100) = 47 → "47_1705399200_sensor347"
  Sensor 892: (892 % 100) = 92 → "92_1705399200_sensor892"

Now writes are spread across 100 different prefixes → 100 different
tablet ranges → distributed across many tablet servers.

Trade-off: to scan ALL sensors for a time range, you must scan 100
separate row ranges (one per bucket) instead of one. For write
scalability, this is acceptable.
```

### Pattern 4: Geographic tiles for Google Earth

**Problem:** Store satellite imagery tiles where queries are for "tiles near geographic location X at zoom level Z."

**Bigtable row key:** S2 cell encoding (a space-filling curve that converts 2D lat/lng coordinates into 1D cell IDs such that nearby locations have similar cell IDs).

**Why it works:** S2 cell IDs preserve spatial locality in 1D — tiles near each other geographically have row keys that are close together. A range scan on an S2 cell range gives all tiles in a geographic area. This is the same principle as domain name reversal: map the natural query structure onto contiguous row key ranges.

### Pattern 5: Composite Row Keys for Multi-Dimensional Access

**Problem:** You're building an e-commerce order system. You need to query efficiently by:
1. All orders for a given user in a date range (`user_id + date`)
2. All orders for a given product in a date range (`product_id + date`)

These two access patterns are fundamentally incompatible with a single row key — you can't sort by both `user_id` and `product_id` simultaneously.

**Solution: Two index tables, each with a different composite row key.**

```
TABLE 1: orders_by_user
  Row key: user_id + inverted_date + order_id
  Example:
    "u001_99999998_ord1001"  → user u001, date 2024-01-16 (newest first)
    "u001_99999099_ord2005"  → user u001, date 2021-01-01 (older)
    "u002_99999998_ord1002"  → user u002, date 2024-01-16

  Efficient query: "all orders for u001 in January 2024"
    → prefix scan from "u001_9999X" to "u001_9999Y" (contiguous range)

  NOT efficient: "all orders for product_id p500"
    → full scan of the entire table (product_id not in row key)

TABLE 2: orders_by_product
  Row key: product_id + inverted_date + order_id
  Example:
    "p500_99999998_ord1001"  → product p500, date 2024-01-16 (newest first)
    "p500_99999099_ord2005"  → product p500, date 2021-01-01 (older)
    "p501_99999998_ord1002"  → product p501, date 2024-01-16

  Efficient query: "all orders for p500 in the last 30 days"
    → prefix scan from "p500_9999X" to "p500_9999Y" (contiguous range)

  NOT efficient: "all orders for user u001"
    → full scan required (user_id not in row key)

TABLE 3 (optional): orders_canonical (source of truth)
  Row key: order_id (globally unique)
  Stores: complete order record (all fields)
  Tables 1 and 2 store only the fields needed to answer the query,
  plus the order_id to look up the full record in Table 3.

WRITE PATH:
  When order ord1001 is placed by user u001 for product p500:
  1. Write to orders_by_user: "u001_99999998_ord1001"
  2. Write to orders_by_product: "p500_99999998_ord1001"
  3. Write to orders_canonical: "ord1001"
  All 3 writes happen atomically (or via a transactional queue).

KEY INSIGHT: Two conflicting access patterns = two index tables.
This is the standard Bigtable multi-dimensional indexing pattern.
The cost is write amplification (write N tables instead of 1).
The benefit is O(range_size) query instead of O(table_size) full scan.
```

### Additional Common Interview Mistakes — Part 8 (Extended)

**Mistake 1: Using a UUID or random ID as the row key.**
UUIDs (like `550e8400-e29b-41d4-a716-446655440000`) are randomly distributed by design — they're designed to avoid collisions, not to provide locality. In Bigtable, random row keys mean that writes are uniformly distributed across all tablets (good for write distribution) but ALL scans become full-table scans (there's no locality, no prefix-based filtering). If your most common query is "give me all records for user X," a UUID row key is catastrophically bad — you'd have to scan the entire table and filter in the application. The auto-increment problem (all writes hit one tablet) is bad, but at least scans can use timestamp ranges. UUID row keys cause bad scans with no benefit for any range query. Use UUIDs only as secondary identifiers (stored in a value or a column qualifier), never as row keys for tables with range query patterns.

**Mistake 2: Not accounting for lexicographic sort order in numeric keys.**
The string `"2"` sorts AFTER `"10"`, `"11"`, ..., `"199"`, `"200"` — because lexicographic sort compares byte-by-byte from left to right, and `'2'` (ASCII 50) > `'1'` (ASCII 49). Numeric strings must be zero-padded to the maximum expected length to sort correctly. For user IDs up to 1 billion: `"0000000001"` through `"0999999999"` (10 digits). For Unix timestamps up to year 2100: use 10-digit zero-padded. Not doing this causes subtle ordering bugs where row scans return results in the wrong order — a bug that often only manifests at scale when the numeric values span multiple orders of magnitude.

**Mistake 3: Designing the row key for writes without thinking about reads.**
A common interview mistake is to design a row key that distributes writes evenly across tablets (good!) but makes every read a full-table scan (catastrophic). For example, using `hash(entity_id) + entity_id` spreads writes perfectly but makes "give me all records for entity X" impossible without a full scan — because the hash prefix spreads the entity's records across different tablets. Always ask: "what are the top 3 query patterns?" BEFORE deciding the row key. The row key is an optimization for reads, not just a way to distribute writes.

**Mistake 4: Designing multi-tenant schemas with the tenant ID anywhere except first.**
For a multi-tenant system (one Bigtable table serving many customers), the tenant ID MUST be first in the row key — before the resource type, timestamp, or any other field. If it's not first, then a scan for "all records for tenant X" requires reading records from all tenants and filtering — a full-table scan that leaks one tenant's workload into another tenant's query latency. With tenant ID first, each tenant's data occupies a contiguous row key range and can be isolated to specific tablets — enabling per-tenant performance guarantees and clean data isolation.

### Brainstorming Questions — Part 8

**Q: How do you handle the case where your row key design is optimal for reads but creates write hotspots?**

This is one of the most common real-world Bigtable design dilemmas. The example: you've designed `user_id + inverted_timestamp` as the row key for a messaging system. This is perfect for "show me this user's most recent messages" — the most common read. But now you have a celebrity user with 10 million followers who sends 1,000 messages per day. All 1,000 writes per day go to ONE tablet (the one covering that user_id prefix). That tablet server is saturated while all others are idle.

The core techniques for resolving this are salting, write-time fan-out, and read-time merge. Salting means adding a hash prefix to the row key: instead of `celebrity_id + inverted_timestamp`, you use `(hash(celebrity_id) % N) + celebrity_id + inverted_timestamp`. This spreads the celebrity's writes across N tablets. The trade-off: reads now must scan N different row key ranges to get all of the celebrity's messages and merge them. N is typically a small number (4, 8, or 16) — you choose N based on the expected peak write rate for the hottest entity. At 1,000 messages/day and a tablet throughput of 100 writes/second, N=2 would be sufficient, but N=8 gives headroom for bursts.

Write-time fan-out is a different approach: write the celebrity's messages to multiple "shard" rows simultaneously at write time. Row key `celebrity_id_shard0 + inverted_timestamp`, `celebrity_id_shard1 + inverted_timestamp`, etc., where the shard is chosen randomly or round-robin. At read time, the system reads all N shards and merge-sorts the results before returning to the user. This is essentially the same as salting but makes the fan-out explicit in the schema rather than implicit in the prefix. Read-time merge adds latency to reads proportional to N (N parallel range scans instead of 1), but spreads writes evenly. For a read-heavy system where the celebrity's timeline is read 10M times per day but written to only 1K times per day, this trade-off is excellent — the write cost is distributed, and the read merge cost is minimal per fan-in.

The trade-off space is: how hot is your hottest entity? Is the hotspot temporary (a viral event) or permanent (a permanently popular entity)? For temporary hotspots, dynamic tablet splitting (Bigtable splits hot tablets automatically) often self-heals without manual intervention. For permanent structural hotspots (a celebrity user who will always have high write traffic), you need a deliberate schema change like salting. The L6 answer is to recognize which category the hotspot falls into and apply the right solution — not to apply salting everywhere regardless of whether there's actually a hotspot.

---

**Q: Design the Bigtable schema for a system that stores click events from a mobile app. Requirements: write 1M clicks/second, query click history for any user, query all clicks in the last hour across all users.**
|-------|--------------------------|
| **Intern** | Uses primary keys as row keys without thinking about scan patterns. |
| **L3** | Knows row keys should be meaningful. Cannot explain what "meaningful" means in terms of query patterns. |
| **L4** | Understands that common query prefixes should be the start of the row key. Can design simple schemas (user_id prefix for per-user data). |
| **L5** | Can apply the reversed domain pattern, the inverted timestamp pattern, and the hotspot problem. Can reason about scan efficiency for a given schema. |
| **L6** | Can design the row key schema from first principles given a set of query requirements. Can identify when a schema will cause hotspots and propose salting. Can explain the trade-off between write distribution (salting) and scan efficiency (range queries). Can design multi-table schemas where one Bigtable table serves as an index for another. |

### Common Interview Mistakes — Part 8

**Mistake 1: Using a sequential integer or auto-increment as the row key.**
Auto-increment keys (`1, 2, 3, 4, ...`) always append to the end of the sorted table — all writes go to one tablet, creating a write hotspot. The most recent tablet is always the hottest. This is the most common Bigtable design error in interviews. If you use an auto-increment key, expect the interviewer to ask "what happens when your table has 10 billion rows and 1 million writes per second?" — all going to one tablet.

**Mistake 2: Not thinking about scan patterns.**
The question to ask first: "what are the most common queries?" then design the row key to make those queries contiguous range scans. If you design the row key for writes without thinking about reads, you'll end up with a schema that requires full-table scans for common queries.

**Mistake 3: Not thinking about hotspots.**
Even a well-designed row key can cause hotspots if all writes have the same prefix. If you're storing events by `user_id + timestamp`, and one user is extremely active (a celebrity, a batch job), that user's tablet becomes a hotspot. The fix is either sharding (split the user's data across multiple artificial row key prefixes) or rate limiting at the application level.

### Brainstorming Questions — Part 8

**Q: How would you design a Bigtable schema for a multi-tenant SaaS application serving 10,000 customers, where each customer has its own data that must never be visible to other customers?**

The core constraint is data isolation — row key design must ensure that no range scan for one customer can accidentally return another customer's data. The solution is to make the tenant_id the FIRST component of every row key. With tenant_id as the prefix, all rows for a given tenant are adjacent in the sorted table — contained within a contiguous row key range. A scan with prefix `tenant_001_` will never return rows with prefix `tenant_002_` because `tenant_001_` < `tenant_002_` lexicographically, and the scan stops at the end of the `tenant_001_` prefix range.

Access control adds a second layer: even if the row key design were imperfect, Bigtable's ACL system (stored in Chubby) can be configured per-table or per-row-prefix to restrict which service accounts can read which ranges. However, ACL enforcement is coarser than per-tenant; the row key is the primary isolation mechanism. For very strict isolation requirements (e.g., regulatory requirements that customer data is physically separated), each tenant should have its own Bigtable table, not just a row key prefix — this provides physical SSTable separation and allows per-table encryption keys.

The operational challenge for multi-tenant schemas: one "loud neighbor" tenant who generates high write traffic can impact read latency for all tenants on the same tablet server. Monitor per-tenant write rates and consider setting per-tenant write rate limits at the application layer. If a single tenant needs more throughput than one tablet can handle, the salting pattern applies: shard the tenant's data across `tenant_id_shard0_`, `tenant_id_shard1_`, etc., and merge shards at query time. This shard-per-overactive-tenant pattern is the standard solution for multi-tenant wide-column stores at scale.

**Q: Design the Bigtable schema for a system that stores click events from a mobile app. Requirements: write 1M clicks/second, query click history for any user, query all clicks in the last hour across all users.**

The challenge: two conflicting query patterns. Per-user queries need a user_id prefix. Time-range queries across all users need a timestamp prefix. No single row key schema can make both queries equally efficient.

The solution is to use TWO tables: one for per-user queries and one for time-range queries. The per-user table uses row key `user_id + inverted_timestamp` — per-user queries are fast prefix scans. The time-range table uses row key `bucket + timestamp + user_id` (with salting for write distribution) — time-range queries scan multiple buckets but cover a compact row range within each bucket. Writes go to both tables (dual-write from the application). This is a classic "write to multiple views" pattern in Bigtable design.

A Staff-level answer will also address: write ordering (are clicks exactly-once? If a write to one table succeeds but the other fails, you have inconsistency — need idempotent writes or a queue-based fan-out). Write latency budget (dual-writes add latency — are you writing synchronously or via a background job?). And eventually: at 1M clicks/second with 3x replication, you're writing ~3M operations/second to Bigtable, which requires a cluster of roughly 100+ tablet servers to sustain.

---

**Q: How do you handle a Bigtable schema migration when you need to add a new column family to an existing table with billions of rows?**

Adding a new column family to a Bigtable table is straightforward at the schema level: Bigtable supports adding column families without downtime. Since Bigtable is sparse, the new column family starts empty — existing rows don't have any values in the new family until writes are made. There is no table-level migration or backfill required just to add the family.

The harder problem is BACKFILLING: populating the new column family with computed values for existing rows. For a table with billions of rows, a backfill is a MapReduce job (or Dataflow/Spark job) that scans the entire table and writes the computed values for the new column. This can take hours or days for very large tables, during which:
- The new column is partially backfilled (some rows have it, some don't)
- Application code must handle the absence of the column gracefully (defaulting to a sensible value when the column is absent)
- Write ordering matters: if the application is also writing the new column during backfill, you must ensure the backfill doesn't overwrite newer values (use the actual write timestamp, not a fixed timestamp, for backfill writes)

The L6 insight: schema migrations in Bigtable are much easier than in relational databases (no ALTER TABLE with a full table lock) but backfills are still an engineering project that requires careful design. The column family model is precisely what makes adding columns easy — you don't need to migrate existing rows, only backfill the ones that need the new value.

---

## Part 9: Limitations and What Came After

### What Bigtable cannot do

```
┌─────────────────────────────────────────────────────────────────────┐
│               BIGTABLE'S LIMITATIONS (ORIGINAL DESIGN)             │
│                                                                     │
│  ✗ Cross-row transactions                                          │
│    Single row is atomic. Two rows → no transaction support.        │
│    (Percolator, built on top of Bigtable, added this.)             │
│                                                                     │
│  ✗ Secondary indexes                                               │
│    Only the row key is indexed. To query by a non-key attribute,   │
│    you must scan the entire table or maintain a separate index      │
│    table manually.                                                  │
│                                                                     │
│  ✗ SQL or declarative queries                                      │
│    No SQL, no query optimizer, no joins. All queries require the   │
│    application to know the row key pattern.                        │
│                                                                     │
│  ✗ Strong consistency across rows                                  │
│    Each row is strongly consistent (the Tablet Server serializes   │
│    all reads/writes to a row). But two rows may be on different    │
│    Tablet Servers with no coordination between them.               │
│                                                                     │
│  ✗ Global sorted order across column families                      │
│    Rows are sorted by row key. Columns within a row are NOT        │
│    globally sorted in a way that enables cross-row-key queries.    │
└─────────────────────────────────────────────────────────────────────┘
```

### What came after

**HBase (2007):** The open-source Apache implementation of Bigtable. Uses ZooKeeper instead of Chubby, HDFS instead of GFS. HBase powers many large-scale systems (Facebook Messenger at one point, various analytics platforms). If an interview asks about Bigtable and you're at a non-Google company, HBase is the likely open-source equivalent being discussed.

**Cassandra (2008, Facebook/Apache):** Inspired by Bigtable's data model and Dynamo's distribution model. Key difference: Cassandra uses a peer-to-peer architecture (no master) and eventual consistency instead of Bigtable's strong single-row consistency. More write-optimized and operationally simpler to scale, at the cost of weaker consistency guarantees.

**DynamoDB (2012, Amazon):** Amazon's managed key-value store. The data model is simpler than Bigtable (no column families, no multi-version cells by default), but the operational simplicity (fully managed, auto-scaling, pay-per-use) drove massive adoption. The Bigtable pattern filtered into DynamoDB as the "sort key" — within a partition key, items are sorted by sort key, enabling efficient range scans within a partition.

**Spanner (2012, Google):** Bigtable with cross-row transactions and SQL queries. Google built Spanner to solve the limitations of Bigtable — specifically the lack of cross-row transactions. Spanner uses a distributed consensus protocol (Paxos) per tablet group and TrueTime for external consistency. It provides full SQL with cross-row, cross-table transactions at global scale. Spanner is what Google uses for AdWords and other applications that need ACID transactions at petabyte scale.

**Cloud Bigtable (2015, Google):** The publicly available managed version of Bigtable. No need to run your own Tablet Servers or Chubby — Google operates all of it. API-compatible with HBase.

```
┌─────────────────────────────────────────────────────────────────────┐
│             BIGTABLE FAMILY TREE                                    │
│                                                                     │
│  Bigtable (2004, Google) ──────────────────────────────────────┐   │
│        │                                                        │   │
│        ├── HBase (2007, Apache) ← HDFS + ZooKeeper             │   │
│        │       │                                               │   │
│        │       └── Phoenix (SQL layer on HBase)                │   │
│        │                                                        │   │
│        ├── Hypertable (2008, open source — largely defunct)     │   │
│        │                                                        │   │
│        └── Spanner (2012, Google) ← added SQL + transactions   │   │
│                │                                               │   │
│                └── CockroachDB, YugabyteDB (open-source        │   │
│                    Spanner-like systems)                        │   │
│                                                                 │   │
│  Bigtable (data model) + Dynamo (distribution) =               │   │
│        └── Cassandra (2008, Facebook)                           │   │
│                │                                               │   │
│                └── DataStax, ScyllaDB                           │   │
│                                                                 │   │
│  Cloud Bigtable (2015) ─────────────────────────────────────────┘  │
│  (managed GCP service, same API as Bigtable/HBase)                 │
└─────────────────────────────────────────────────────────────────────┘
```

### System Comparison: Bigtable vs HBase vs Cassandra vs DynamoDB vs Spanner

```
┌──────────────────┬──────────────┬──────────────┬──────────────┬──────────────┬──────────────┐
│   DIMENSION      │  BIGTABLE    │    HBASE     │  CASSANDRA   │  DYNAMODB    │   SPANNER    │
│                  │  (Google)    │  (Apache)    │  (Apache)    │  (Amazon)    │  (Google)    │
├──────────────────┼──────────────┼──────────────┼──────────────┼──────────────┼──────────────┤
│ Consistency      │ Strong per   │ Strong per   │ Tunable:     │ Eventually   │ External     │
│ Model            │ row (tablet  │ row (region  │ ONE/QUORUM/  │ consistent   │ consistency  │
│                  │ server owns  │ server owns  │ ALL. Default │ by default.  │ (TrueTime).  │
│                  │ the row)     │ the row)     │ = eventual.  │ Strong opt.  │ Linearizable.│
├──────────────────┼──────────────┼──────────────┼──────────────┼──────────────┼──────────────┤
│ Transaction      │ Single-row   │ Single-row   │ Single-row   │ Single-item  │ Full ACID    │
│ Support          │ atomic only. │ atomic only. │ lightweight  │ atomic.      │ cross-row,   │
│                  │ No cross-row.│ No cross-row.│ transactions │ Transactions │ cross-table, │
│                  │ (Percolator  │ (Omid adds   │ via Paxos    │ available    │ global.      │
│                  │ adds it on   │ cross-row    │ (Cassandra   │ at extra     │              │
│                  │ top)         │ on top)      │ 4.x+)        │ cost         │              │
├──────────────────┼──────────────┼──────────────┼──────────────┼──────────────┼──────────────┤
│ Data Model       │ Wide-column: │ Wide-column: │ Wide-column: │ Key-value:   │ Relational:  │
│                  │ (row,        │ Same as      │ (partition   │ (partition   │ Tables,      │
│                  │ col_family,  │ Bigtable     │ key, cluster │ key, sort    │ rows, cols   │
│                  │ col_qual,    │              │ key, col) →  │ key) → item  │ SQL schema.  │
│                  │ timestamp)   │              │ value        │ (map)        │              │
├──────────────────┼──────────────┼──────────────┼──────────────┼──────────────┼──────────────┤
│ Sort Mechanism   │ Lexicographic│ Lexicographic│ Lexicographic│ Lexicographic│ SQL ORDER BY │
│                  │ by row key   │ by row key   │ within       │ within       │ + index-     │
│                  │ globally     │ globally     │ partition    │ partition    │ based        │
│                  │              │              │ only         │ only         │              │
├──────────────────┼──────────────┼──────────────┼──────────────┼──────────────┼──────────────┤
│ Write Path       │ WAL → Mem-   │ WAL → Mem-   │ Commit log   │ WAL →        │ Paxos log →  │
│                  │ Table → SST  │ Store → HFile│ → Mem table  │ durable      │ Spanner      │
│                  │ (GFS)        │ (HDFS)       │ → SSTable    │ storage      │ storage      │
├──────────────────┼──────────────┼──────────────┼──────────────┼──────────────┼──────────────┤
│ Read Path        │ MemTable +   │ MemCache +   │ Mem table +  │ In-memory    │ Paxos read   │
│                  │ Bloom filter │ Bloom filter │ Bloom filter │ cache +      │ at chosen    │
│                  │ + SSTables   │ + HFiles     │ + SSTables   │ B-tree index │ timestamp    │
├──────────────────┼──────────────┼──────────────┼──────────────┼──────────────┼──────────────┤
│ Coordination     │ Chubby       │ ZooKeeper    │ Peer-to-peer │ Fully        │ Paxos per    │
│ Mechanism        │ (lock svc) + │ (coord) +    │ gossip. No   │ managed by   │ tablet group │
│                  │ single Master│ single Master│ master.      │ Amazon.      │ + TrueTime   │
├──────────────────┼──────────────┼──────────────┼──────────────┼──────────────┼──────────────┤
│ When to          │ Google-scale │ Open-source  │ Multi-DC,    │ Serverless,  │ Global ACID  │
│ Choose It        │ wide-column  │ Bigtable     │ high avail., │ auto-scale,  │ transactions │
│                  │ needs at GCP │ on your own  │ eventual     │ managed,     │ at global    │
│                  │              │ infra        │ consistency  │ AWS          │ scale        │
│                  │              │              │ is OK        │              │              │
└──────────────────┴──────────────┴──────────────┴──────────────┴──────────────┴──────────────┘

WHEN TO CHOOSE EACH:
  Bigtable:  You're at GCP, you need wide-column at petabyte scale, strong single-row
             consistency, and sorted scans. Time-series, user data, search indexes.
  HBase:     Same as Bigtable but you're NOT at GCP and want to run your own infra on HDFS.
             Popular in Hadoop ecosystems (Cloudera, Hortonworks).
  Cassandra: Multi-datacenter deployment where you need active-active replication.
             Acceptable to have eventual consistency (social media feeds, IoT telemetry).
             No master = simpler operations at the cost of consistency.
  DynamoDB:  AWS deployment, you want zero operational overhead, pay-per-request pricing.
             Simpler data model than Bigtable (no multi-version cells by default, no col families).
  Spanner:   You need cross-row, cross-table ACID transactions at global scale. Financial
             systems, inventory, anything where "debit account A, credit account B" must be
             atomic. More expensive (Paxos overhead) but the strongest consistency available.
```

### Intern → Staff Progression (Part 9)

| Level | Knowledge of the Bigtable ecosystem |
|-------|-------------------------------------|
| **Intern** | "I've heard of HBase and Cassandra." Cannot explain the relationship to Bigtable. |
| **L3** | Knows HBase is "open-source Bigtable." Cannot explain the key differences or why Cassandra was built differently. |
| **L4** | Can compare Bigtable vs HBase (same model, different infrastructure). Understands that Cassandra sacrifices consistency for availability and peer-to-peer simplicity. |
| **L5** | Can explain why each system exists: what Bigtable limitation each successor addressed. Knows that Spanner = Bigtable + transactions + SQL. |
| **L6** | Can choose between Bigtable, Cassandra, DynamoDB, and Spanner for a given problem and justify the choice in terms of: consistency requirements, transaction needs, access patterns, operational complexity, and cost. Can design the migration path from one to another. |

### Common Interview Mistakes — Part 9

**Mistake 1: Saying "use Cassandra instead of Bigtable" without explaining why.**
Cassandra is appropriate when you need eventual consistency (not strong row consistency), peer-to-peer topology (no master, simpler operations), and multi-datacenter replication with tunable consistency (CL=ONE vs. CL=QUORUM). Bigtable (or HBase) is appropriate when you need strong single-row consistency, sorted scans, and multi-version cells. Saying "just use Cassandra" without this reasoning signals you're pattern-matching, not reasoning.

**Mistake 2: Thinking Spanner is just "Bigtable with SQL."**
Spanner is a complete redesign. The distributed consensus mechanism (Paxos per tablet group, TrueTime for commit ordering) is fundamentally different from Bigtable's single-master-per-tablet model. The transaction model (two-phase commit across Paxos groups) adds significant complexity. Spanner achieves external consistency (the gold standard — if transaction T1 commits before T2 starts, T2 always sees T1's writes) using TrueTime's bounded clock uncertainty. This is not "Bigtable plus SQL" — it's a new system that happens to use a Bigtable-like storage layer underneath.

**Mistake 3: Saying DynamoDB is "Amazon's Bigtable."**
DynamoDB's data model was inspired by both Bigtable AND Dynamo (Amazon's key-value paper). But DynamoDB is simpler than Bigtable in significant ways: no column families (just a flat attribute map per item), no multi-version cells by default, and a simpler (partition key + optional sort key) key structure compared to Bigtable's (row key + column family + column qualifier + timestamp). DynamoDB's operational model is also radically different: fully managed, auto-scaling, serverless pricing. Calling it "Amazon's Bigtable" misrepresents both systems. The correct framing is: DynamoDB is a simpler, managed key-value store that adopted some ideas from both Bigtable (sorted order within a partition) and Dynamo (eventual consistency, distributed ring).

**Mistake 4: Not knowing when Bigtable is the WRONG choice.**
Bigtable is the wrong choice when you need: (a) cross-row ACID transactions — use Spanner or a relational database; (b) SQL queries with joins — use Spanner, BigQuery, or PostgreSQL; (c) a secondary index by a non-key attribute — Bigtable has no built-in secondary indexes, you must build your own index table manually; (d) very small datasets — Bigtable's operational complexity (Chubby, Master, GFS dependency) is overkill for datasets under a few terabytes; (e) sub-millisecond latency for simple key-value lookups — Redis or Memcached are more appropriate for in-memory speed.

### Brainstorming Questions — Part 9

**Q: A company is migrating from HBase to Cloud Bigtable. What are the key things they need to verify before the migration?**

The first thing to verify is API compatibility. Cloud Bigtable is API-compatible with HBase via the HBase client library — most HBase reads and writes work without code changes. But there are differences: Cloud Bigtable does not support the HBase coprocessor API (server-side plugins that run code inside the region server), which some HBase users rely on for server-side filtering and aggregation. If your HBase application uses coprocessors, you'll need to rewrite those operations as client-side logic or as server-side filtering via Cloud Bigtable's native filter API.

The second area is performance characterization. HBase on HDFS and Cloud Bigtable have different performance profiles. HBase performance depends heavily on your HDFS configuration (namenode capacity, data locality, compaction settings). Cloud Bigtable is a managed service — you don't tune compaction, and tablet splitting is automatic. But the node count drives throughput: Cloud Bigtable recommends starting with enough nodes for 1-2TB per node, with each node serving ~10K reads/second or ~10K writes/second (rough estimates, varies by row size and access pattern). Run a load test on Cloud Bigtable with production-representative traffic before cutting over.

The third area is cost modeling. HBase on your own hardware has capital costs and operational costs (engineers managing the cluster). Cloud Bigtable has per-node-per-hour costs plus per-GB storage costs. For small clusters (5-10 nodes), Cloud Bigtable is often cheaper once you count engineer time. For large clusters (100+ nodes), the comparison depends on your hardware costs and operational efficiency. Run a 30-day cost estimate on Cloud Bigtable before committing to migration — the main cost drivers are node count (proportional to throughput) and storage (proportional to data volume × replication factor).

---

## Part 10: Interview Application

### The one-sentence summary

> "Bigtable is a sorted map where YOU control the sort key. Design the row key well — based on your most common access pattern — and Bigtable is blazing fast. Design it poorly, and no amount of hardware will fix the hotspots."

### When to reference Bigtable in an interview

**You're designing a system that stores user-specific data at scale.** Reference Bigtable when: (1) the data is semi-structured or sparse (not every user has the same fields), (2) you need to scan within a user's data efficiently (per-user sorted access), (3) scale is petabyte-level with millions of writes per second. Say: "This is a natural fit for a wide-column store like Bigtable. Row key is `user_id + inverted_timestamp` to enable efficient per-user time-ordered scans."

**You're designing a web crawl or search index backend.** Bigtable was literally built for this. Reference the reversed domain row key pattern. Explain why: all pages from the same domain scan contiguously.

**Someone asks about distributed storage systems.** Name-dropping Bigtable is table stakes. But the L6 move is to connect Bigtable to GFS (Bigtable runs on top of GFS) and Chubby (Bigtable uses Chubby for coordination) — showing you understand the dependency graph of Google's infrastructure.

**You're asked about NoSQL databases.** Distinguish: Bigtable is a wide-column store (sorted rows, column families, multi-version cells). DynamoDB is a key-value store (simpler model, no inherent sort). MongoDB is a document store (JSON-like, flexible schema but slower at scale). Redis is an in-memory store (speed, not storage). These are NOT interchangeable.

### L5 vs L6 calibration

**L5 says:** "I'd use Bigtable (or HBase) because it handles high write throughput and stores semi-structured data at scale. The row key would be the user ID."

**L6 says:** "The dominant query pattern here is per-user sorted by recency — that dictates a row key of `user_id + (MAX_INT - timestamp)` so the most recent entries sort first within a user's prefix. Write throughput at 1M/s across 10M users is 100 writes/user/s at peak — that's well within Bigtable's capacity. The hotspot risk is if a single user generates far more writes than average; we mitigate that by monitoring per-tablet write rates and optionally splitting hot users across synthetic row key prefixes. For the cross-user time-range query, we need a secondary index table with `timestamp_bucket + user_id` as the row key — that's a dual-write architecture."

### The "GFS + Bigtable + MapReduce" combo

In a Google Staff interview, knowing that GFS, Bigtable, and MapReduce are a stack — not independent choices — is important:
- GFS stores raw data (web crawls, logs)
- Bigtable stores indexed/structured data built from GFS data (the web index, user data)
- MapReduce processes GFS data to build Bigtable tables
- Bigtable serves online reads (search serving, Gmail inbox)

An L6 answer shows you can reason about this stack end-to-end, not just describe each component in isolation.

### How to Structure a Bigtable Answer in an Interview

Most candidates who know Bigtable fail interviews not because they lack knowledge but because they don't structure the answer to match what the interviewer is trying to evaluate. Here is the recommended structure for any system design question where Bigtable is the right answer:

**Step 1: State the access pattern first, not the technology.**
Don't open with "I'll use Bigtable." Open with "The dominant access pattern is X — we need to do Y queries efficiently." This demonstrates you're reasoning from requirements, not from a fixed technology preference. THEN say "That access pattern is best served by a wide-column store with sorted rows — Bigtable or HBase."

**Step 2: Design the row key out loud, with reasoning.**
Walk through your row key design step-by-step. Say: "The most common query is [X]. That means I want [X] to be a prefix of the row key, so the query is a range scan. The second most common query is [Y], which I'll handle with a secondary index table." This is the L6 move — showing your reasoning, not just the answer.

**Step 3: Identify the hotspot risks proactively.**
Before the interviewer asks, identify any row key design choices that could create hotspots. Say: "This design could create a hotspot if [condition] — to mitigate that, I'd add a [salt/shard] prefix." This shows you're thinking about failure modes, not just happy paths.

**Step 4: Acknowledge limitations and propose the next system.**
Close with: "Bigtable handles the core read/write pattern well. The limitation is [X] — if we need [X], we'd add [complementary system]." This shows you understand where Bigtable's boundaries are.

```
INTERVIEW ANSWER TEMPLATE FOR BIGTABLE PROBLEMS:

  "Given the requirement to [access pattern], I'd use a wide-column
   store. Bigtable (or HBase on-prem) is the natural choice because:

   1. Data model: [what row key maps to what entity]
   2. Row key design: [key + reasoning + scan efficiency]
      Row key = [first element] + [second element] + [third element]
      This makes [query A] a prefix scan (efficient).
      [Query B] requires a secondary table — here's how:
      Secondary row key = [...]

   3. Write path: [expected writes/second] × [row size] =
      [MB/s]. That's [N] tablets at [X] writes/tablet/s.
      Hotspot risk: [yes/no, and why]. Mitigation: [salting/sharding].

   4. Read path: [describe what's fast, what requires a scan]

   5. Limitations: No [cross-row transactions / secondary indexes / SQL].
      For [use case X], we'd need [Spanner / application-layer index /
      read-through cache]."
```

### Real Interview Scenarios and Model Answers

**Scenario A: "Design Instagram's photo metadata storage."**

L5 answer: "Use Bigtable with user_id as the row key. Store photo metadata in column qualifiers under a `photos` column family."

L6 answer: "The two dominant queries are: (1) show a user's photos sorted by recency — that needs `user_id + inverted_timestamp` as the row key. (2) Show photos by hashtag — that's a secondary index table with `hashtag + inverted_timestamp + photo_id` as the row key. The primary table handles per-user queries; the hashtag table handles per-tag queries. Both are dual-written on each photo upload. Write rate is [estimate] — let me check for hotspots: celebrity users with millions of followers posting frequently could create hotspots on their user_id prefix. I'd add a shard suffix if per-user write rate exceeds the Tablet Server's single-tablet write capacity (~10K writes/second). The limitation is that 'show all photos liked by a user' requires yet another index table — at some point we're maintaining N index tables, which suggests we also need an offline consistency check that verifies all index tables are in sync with the primary."

**Scenario B: "Design the storage for Google Search autocomplete."**

L5 answer: "Use Bigtable with query prefix as the row key. Store the top completions as column qualifiers."

L6 answer: "Autocomplete queries are prefix lookups: 'g' → suggest 'google', 'gmail', 'games'. The row key should be the prefix itself, sorted lexicographically — so all completions for 'g' are adjacent to completions for 'ga', 'gm', etc. But we don't store one entry per prefix (that would be exponential — 'g', 'go', 'goo', 'goog'... for every query). Instead we store one entry per FULL query, with the row key as the full query. Then a prefix scan for 'g' returns all rows in [g, h), giving us all queries starting with 'g'. The Tablet Server returns the first K results, which are the most popular completions (because row key is the query, and we pre-sort by popularity within the prefix — using a popularity rank inverted into the second element of the row key). Read latency target is <10ms end-to-end — Bigtable with cached tablet locations and a hot MemTable for popular prefixes should achieve this."

### Common Interview Mistakes — Part 10

**Mistake 1: Jumping to Bigtable before understanding the access pattern.**
The most common failure mode: the candidate hears "large scale, many writes, structured data" and immediately says "Bigtable." The interviewer follows up with "what's the primary access pattern?" and the candidate hasn't thought about it. Always establish access patterns FIRST. "What queries need to be fast?" determines the row key, which determines whether Bigtable is even the right choice.

**Mistake 2: Designing a schema without quantitative reasoning.**
An L6 answer includes numbers. "Expected 1M writes/second at 200 bytes each = 200MB/s. At 100 tablets per Tablet Server and 10K writes/second per tablet, I need roughly 100 Tablet Servers." Saying "it's high scale, so Bigtable will handle it" without any arithmetic is an L4 answer. The arithmetic doesn't need to be exact — it needs to demonstrate you can size a system.

**Mistake 3: Forgetting to address what Bigtable cannot do for the problem.**
Every system design problem has requirements that Bigtable doesn't handle well. An L6 proactively identifies these and proposes solutions: secondary indexes (build a separate index table), cross-row transactions (use Percolator or Spanner), aggregate queries (use BigQuery or Dataflow for offline analytics). Saying "Bigtable handles everything" is the wrong answer — it doesn't, and the interviewer knows it.

**Mistake 4: Not connecting Bigtable to the full data pipeline.**
In a Google interview, an isolated Bigtable discussion is a missed opportunity. The L6 answer connects: "The data pipeline writes to GFS (via a queue or streaming system), MapReduce/Dataflow transforms and indexes the data into Bigtable, and the online service reads from Bigtable. The offline and online worlds share GFS as the storage substrate." This end-to-end thinking is what Staff-level system design looks like.

---

## Part 11: Staff-Level Q&A Drill

The following 10 questions are the type an L6 interviewer asks to separate L5 "knows the architecture" from L6 "can reason about edge cases and trade-offs." Each model answer is 2-3 sentences, specific and precise. Practice answering these out loud before your interview.

---

**Q1: What happens if the Master crashes?**

The Master holds a Chubby lock. When it crashes, the lock is released after the session timeout, and another machine waiting to become Master acquires the lock. Existing reads and writes to all tablets continue unaffected — the Master is not in the data path — but new tablet assignments, load rebalancing, table creation/deletion, and Tablet Server failure recovery are blocked until the new Master finishes its startup scan of the METADATA table (which can take a few minutes for a large cluster).

---

**Q2: Why is the row key sorted lexicographically, not numerically?**

Row keys in Bigtable are opaque byte strings — the system has no way to know whether the bytes represent a UTF-8 string, a reversed domain name, a zero-padded integer, or arbitrary binary data. Lexicographic sort is the only correct general-purpose ordering for byte strings without type information. The responsibility for making numeric keys sort correctly (by zero-padding them) falls on the application — this is a deliberate design choice that keeps Bigtable generic and allows any byte sequence as a row key.

---

**Q3: A query for all rows where column X > 5 — is this fast in Bigtable?**

No. Bigtable has no secondary indexes and no way to filter by column value without reading the column value for every row. A query like "column X > 5" requires a full table scan: read every row, decode the value of column X, filter in the application. For this access pattern, you would need to maintain a separate "index table" where the row key encodes the column value (e.g., `(MAX_INT - column_X_value) + original_row_key`), enabling a range scan on the index table to find matching rows. This manual index maintenance is the operational cost of Bigtable's schema flexibility.

---

**Q4: How do you handle a celebrity user with 10M followers in a Bigtable-backed social graph?**

The celebrity's follower list is a single row with up to 10M column qualifiers (one per follower) or 10M separate rows prefixed by the celebrity's user ID. Either way, a single tablet gets all the writes when follower counts change (new follows, unfollows). The solution is salting: shard the celebrity's data across N virtual row keys — `celebrity_id_shard0`, `celebrity_id_shard1`, ..., `celebrity_id_shardN-1` — distributing writes across N tablets. Reads must query all N shards and merge the results, which adds a fan-in step but keeps any single tablet from becoming a bottleneck.

---

**Q5: Bigtable or Cassandra for a real-time leaderboard?**

Cassandra is generally better for a real-time leaderboard with frequent updates across many entries, because Cassandra's tunable consistency (CL=ONE) with peer-to-peer replication handles high write rates with low latency and no single master bottleneck. Bigtable's strong single-row consistency is not needed for a leaderboard where eventual consistency is acceptable (the score is accurate within seconds). However, if the leaderboard requires an exact sorted view of all scores (not just per-user queries), neither Bigtable nor Cassandra is ideal — you'd add a sorted index service (like Redis sorted sets) in front of either as the sorted score store.

---

**Q6: What does "atomic row operation" mean in Bigtable?**

Atomic row operation means that a single mutation touching multiple cells in the same row either fully succeeds or fully fails — there is no state where a reader sees some cells updated and others not. The Tablet Server serializes all reads and writes for a row: no two operations on the same row execute concurrently. This is per-row atomicity; Bigtable makes no atomicity guarantees for operations that span multiple rows (unless you use an external transaction layer like Percolator).

---

**Q7: How does Bigtable handle disk failure on a Tablet Server?**

Tablet Servers store NO data locally — all data (SSTables and WALs) is in GFS, which itself replicates each chunk across 3+ machines. A Tablet Server disk failure (or complete machine failure) is indistinguishable from a crash: the Tablet Server's Chubby session expires, the Master detects it, and the Master reassigns all of the failed server's tablets to healthy Tablet Servers. The healthy servers read the SSTable files from GFS (still intact across other GFS chunkservers) and replay the WAL to recover in-memory state. No data loss occurs because Bigtable's durability is entirely delegated to GFS.

---

**Q8: Is Bigtable a good fit for storing ML model weights?**

No, for most cases. ML model weights are large binary blobs (a single model can be gigabytes to hundreds of gigabytes), accessed as a unit (you always read the entire model, not a subset of weights), and updated infrequently (once per training run, not millions of times per second). Bigtable is optimized for many small reads and writes across millions of narrow rows — the opposite of one giant blob updated rarely. GCS (Google Cloud Storage) or a distributed object store (S3) is a better fit for model weights: optimized for large sequential reads, cheap for large objects, and no overhead of Bigtable's row/column/timestamp indexing machinery.

---

**Q9: How do you do a COUNT(*) in Bigtable?**

Bigtable has no built-in aggregation functions — no COUNT, SUM, AVG. A COUNT(*) requires either a full table scan (read every row and count in the application, extremely slow for large tables), a pre-computed counter stored in a separate Bigtable cell (updated on every write via read-modify-write with Bigtable's CheckAndMutate operation), or an offline MapReduce/Dataflow job that scans the table and produces the count. For large tables where you need real-time count, the recommended approach is to maintain a separate counter row that you increment atomically (Bigtable's single-row compare-and-set) on each insert. Counting in a wide-column store is a design problem to solve at schema time, not at query time.

---

**Q10: Can Bigtable be used as a message queue?**

Technically yes, but it's a poor fit. A message queue requires: guaranteed ordering (Bigtable has sorted row keys, so ordering is achievable), visibility timeouts and re-delivery on failure (Bigtable has no built-in concept of message leasing or visibility), and at-most-once or at-least-once delivery semantics (Bigtable is a storage system, not a delivery system). You would have to implement queue mechanics (leasing, acknowledgment, dead-letter handling) in application code on top of Bigtable, which is significant work. Use Pub/Sub, Kafka, or SQS instead — systems built for queue semantics. Bigtable excels at persistent structured data with sorted access patterns, not at the state machine logic required for reliable message delivery.

---

## Real Life Product Incidents

### Incident 1: Google Ads Hotspot (2007)

Google's advertising system used Bigtable to store ad click and impression data. When a major product launch (say, the first iPhone announcement in 2007) drove enormous traffic to Google search, the click data for ads related to the announcement concentrated on a small number of row key ranges — because ads were grouped by advertiser ID, and large advertisers had entire tablets to themselves. One large advertiser's tablet received 10x the normal write rate, overwhelming the Tablet Server.

The fix was a two-part schema change: (1) add a write-time hash prefix to the row key to spread writes across multiple synthetic key ranges, and (2) add a secondary "time-bucketed" index for the queries that previously needed the advertiser-grouped schema. This incident drove the development of explicit hotspot monitoring tools at Google that alert when a single tablet's write rate exceeds a threshold. The lesson: schema design that works at normal load can fail catastrophically at peak load if it creates hotspots.

### Incident 2: Google Earth Tile Compaction Slowdown

Google Earth stores satellite imagery tiles in Bigtable, keyed by S2 cell ID (geographic space-filling curve). Each zoom level produces a different resolution tile. The tiles are large (hundreds of KB each). When a new satellite image covering a large geographic area was ingested, millions of tiles were written in a short window — all landing on the same tablet ranges (because the geographic area mapped to contiguous S2 cell IDs).

The sudden write burst caused the MemTable to fill rapidly, triggering frequent minor compactions. The accumulating SSTables caused read latency to spike — users viewing Google Earth saw tiles loading slowly. The root cause: major compaction hadn't run recently, so SSTable count was already high before the write burst.

The fix: proactively trigger compaction before a large image ingestion, and stagger the ingestion to spread writes over time. This incident shaped how Google Earth's ingestion pipeline schedules batch writes: never write an entire geographic area at once; break it into chunks and insert with delays between chunks. The lesson: LSM tree performance degrades under write bursts if compaction lags behind — burst writes need to be rate-limited or pre-planned.

### Incident 3: The Google Analytics Write Fan-Out Bug

Google Analytics (at the time, called Urchin analytics after the company Google acquired) used Bigtable to store per-website, per-day, per-metric aggregated counts. Row key: `website_id + date + metric_type`. Column: `count`. On each page view, Analytics would increment the row's count column.

The problem: a read-modify-write is not atomic in Bigtable without using the CheckAndMutate (compare-and-swap) operation. The original implementation was: (1) read the current count from Bigtable, (2) add the new page view to the count in application memory, (3) write the new count back to Bigtable. This is a classic non-atomic read-modify-write — concurrent writes from multiple application servers would overwrite each other's increments.

At low traffic, this was acceptable (the count was "approximately correct"). But when a viral article caused one website's count to be updated 100,000 times per second across 100 application servers, the race conditions became severe. Each server would read count=500,000, add its increment (say, +1), and write 500,001 — but 100 servers doing this simultaneously means only one increment would "win" the final write. The actual count should have been 500,100, but it ended up as 500,001. The undercount was proportional to the concurrency.

The fix was two-part: (1) use Bigtable's CheckAndMutate for atomic increments — "write new_value only if current value is old_value" — which forces all servers to serialize their updates through the Tablet Server. (2) For very high traffic metrics, switch to a counter aggregation layer: instead of updating Bigtable directly, write increments to a distributed counter service (like a Redis hash), and flush aggregated counts to Bigtable every 60 seconds. This trades real-time accuracy for write scalability — for analytics dashboards, 60-second-delayed counts are acceptable. This incident drove the development of Bigtable's native `ReadModifyWriteRow` operation, which allows atomic increment operations without application-level compare-and-swap.

### Incident 3: METADATA Tablet Hotspot

Bigtable's METADATA table stores the location of every user tablet. For a large Bigtable cluster with millions of tablets, the METADATA table itself becomes large. If many clients simultaneously experience cache misses (e.g., after a large-scale Tablet Server restart that invalidated all cached locations), they all rush to read the METADATA tablet simultaneously.

This happened at Google after a datacenter maintenance event where hundreds of Tablet Servers restarted simultaneously. Millions of client processes — all with stale tablet location caches — simultaneously queried the METADATA table. The METADATA tablet servers were overwhelmed. This caused a cascade: slow METADATA reads → clients timeout → clients retry → more METADATA load → even slower reads.

The fix was a combination of: adding METADATA server replicas (more read capacity), implementing exponential backoff in the client library for METADATA lookup retries, and staggering Tablet Server restart schedules to avoid simultaneous mass-restart events. This incident taught the industry that the metadata tier itself needs the same hotspot protection as the data tier. HDFS learned this lesson and added NameNode read replicas for similar reasons.

---

## Exercises

**Exercise 1: Design a Bigtable schema for a social media platform**
A social media platform needs to store: (1) posts made by users, sorted by recency, (2) comments on each post, (3) likes on each post. For each: design the row key, column families, and column qualifiers. Explain what queries are efficient with your schema and what queries require a full scan.

**Exercise 2: Trace the write path**
A client writes: `table["com.google.www"]["metadata:pagerank"] = "0.921"` at timestamp 1705399200. Trace every step: which component validates the request, where does the WAL entry get written, what does the MemTable entry look like, and when does data first appear on disk as an SSTable?

**Exercise 3: Trace the read path with Bloom filters**
A tablet has 1 MemTable and 5 SSTables. The client reads `table["com.cnn.www"]["content:html"]`. The MemTable contains no entry for `com.cnn.www`. SSTables 5 and 3 have Bloom filter "maybe YES" for `com.cnn.www`. SSTables 4, 2, and 1 have Bloom filter "definitely NO." Trace exactly which SSTables are read and in what order. What is returned?

**Exercise 4: Row key hotspot analysis**
Evaluate these row key designs for a system that stores sensor readings (1M sensors, each writing once per second):
a) `sensor_id` (no timestamp in key)
b) `timestamp + sensor_id`
c) `sensor_id + timestamp`
d) `(sensor_id % 100) + "_" + timestamp + "_" + sensor_id`
For each, explain: (a) what happens during writes, (b) what scans are efficient, (c) what scans require full table scan, (d) are there hotspots?

**Exercise 5: Compare with DynamoDB**
For each of the following requirements, decide whether Bigtable or DynamoDB is more appropriate and explain why:
a) Storing IoT sensor data at 10M writes/second with time-range queries
b) Storing user profiles where each user may have different attributes
c) Storing financial transaction records with cross-row atomicity requirements
d) Storing an inverted search index for a document corpus

**Exercise 6: Design for multi-version cells**
A healthcare system stores patient vitals (heart rate, blood pressure, oxygen saturation) using Bigtable's multi-version cells. They need to: (1) read the latest vitals for a patient, (2) read vitals for a patient in the past 24 hours, (3) delete vitals older than 1 year. Design the Bigtable configuration: row key, column families, column qualifiers, version retention policy, and how each of the three queries maps to Bigtable operations.

**Exercise 7: Interview practice — 5-minute answer**
The interviewer says: "We're building a URL shortener that serves 100K reads/second and 10K writes/second. Short URLs map to long URLs. We also need analytics: for each short URL, how many clicks per day for the last 30 days." Design the Bigtable schema (or justify a different storage choice) and explain the row key design for both the mapping table and the analytics table.

**Exercise 8: Compaction Schedule Under Load**
A tablet receives 10,000 writes per minute at a steady rate. Assume: each write is 100 bytes of user data, MemTable flush threshold is 64MB, minor compaction (MemTable → L0 SSTable) takes 30 seconds, and merge compaction triggers at 10 L0 SSTables.

Calculate:
(a) How many bytes of new data arrive per hour? How many minor compactions occur per hour?
(b) After 1 hour with no merge compaction, how many L0 SSTables exist?
(c) At 10 SSTables per read check (Bloom filter miss rate 10%), what is the approximate read latency for a random key not in the MemTable? Assume each SSTable lookup is 2ms.
(d) What compaction should be triggered? Minor, merge, or major? Justify your answer.
(Hint: 10,000 writes/min × 100 bytes = 1MB/min. 64MB MemTable / 1MB/min = 64 minutes per flush. In 1 hour, fewer than 1 full flush occurs — so this scenario actually doesn't produce 10 SSTables in 1 hour. What does this tell you about the compaction schedule needed?)

**Exercise 9: The Hot Config Row**
A system reads the same "config" row from Bigtable 1 million times per second. This row is small (1KB) and changes only once per hour. The row key is `config:global_settings`.

Describe:
(a) What performance problems does this create for the Tablet Server holding this row?
(b) What happens to the Tablet Server's CPU utilization and network bandwidth?
(c) What happens to other rows on the same Tablet Server (collateral damage)?
(d) Propose two specific fixes. For each fix, explain the trade-off (e.g., what consistency you sacrifice, what operational complexity you add).
(Expected direction: 1M reads/second of 1KB = 1GB/second network load on one Tablet Server — completely unscalable. Fix 1: cache the config outside Bigtable entirely (in-process cache or Memcached with 60-second TTL). Fix 2: replicate the config row to a separate "config table" with multiple tablet replicas. The key insight: Bigtable is not designed for hot singleton reads — it's designed for wide read distribution across many different rows.)

**Exercise 10: Cold Client Write — Complete Message Flow**
Draw the complete message flow for a write to Bigtable starting from a cold client (no cached tablet locations anywhere). The client wants to write: `table["user_500"]["profile:name"] = "Alice"`.

Include in your diagram:
(a) The Chubby lookup to find the root tablet location.
(b) The root tablet read to find the METADATA tablet location.
(c) The METADATA tablet read to find the user tablet's Tablet Server.
(d) The actual write to the Tablet Server: the WAL write to GFS, the MemTable insert, and the client acknowledgment.
(e) Label each message with direction (→ or ←), the sender, the receiver, and what information is carried.
(f) After the write completes, how many entries does the client cache? What are they?
(g) How many round trips did the cold write require? How many would the NEXT write to `user_500` require if done immediately? How many would a write to `user_700` (different tablet) require?

---

## Homework

**Homework 1: Read the original paper.**
Read the Bigtable paper (Chang et al., 2006 — available free online). Focus on Sections 2 (Data Model), 4 (Building Blocks), 5 (Implementation), and 7 (Performance Evaluation). For each section, write one paragraph: what was the key design decision, what trade-off was made, and what modern system uses the same or a different approach.

**Homework 2: HBase vs Bigtable comparison.**
Read the HBase architecture documentation (Apache HBase Reference Guide, Chapter 2). List 5 architectural differences between HBase and Bigtable. For each difference, explain why the difference exists (HDFS vs GFS, ZooKeeper vs Chubby, open-source vs proprietary) and what the operational implications are.

**Homework 3: Row key design exercise.**
Design Bigtable schemas for THREE of the following systems. For each, specify: row key, column families, column qualifiers, version retention, and the top 3 query patterns supported efficiently:
a) A time-series database for server metrics (CPU, memory, disk for millions of servers)
b) A product catalog for an e-commerce site (10M products, searchable by category, price, rating)
c) A social graph (followers, following, mutual connections for 1B users)
d) A ride-sharing booking system (bookings, driver locations, fare estimates)

**Homework 4: Mock interview drill.**
Ask a friend to say: "Design a system to store and serve Google's web search index. You need to store per-URL metadata (crawl date, PageRank, language) and per-query inverted index entries (which URLs contain each search term). Scale: 50B URLs, 100B search terms, 1M queries/second." Practice a 15-minute answer that: (1) identifies this as a Bigtable-appropriate problem, (2) designs the table schema with row keys, (3) handles the read/write path, (4) identifies limitations and next steps.

**Homework 5: LSM tree deep dive.**
LevelDB is an open-source LSM tree implementation (written by the same engineers as Bigtable). Read the LevelDB documentation and source code overview. Answer: (1) what are the compaction levels in LevelDB and how do they differ from Bigtable's approach? (2) How does LevelDB implement Bloom filters? (3) What are the performance trade-offs of tuning the MemTable size?

**Homework 6: Trace a real failure mode end-to-end.**
Design a scenario where a Bigtable cluster degrades slowly over 3 days, with no single catastrophic failure. Example starting condition: compaction is running correctly, but write rate increases by 30% every day (a growing application). For each day, calculate: MemTable flush frequency, L0 SSTable count, estimated read latency for a random key, and estimated SSTable count if major compaction runs weekly. At what point does the cluster need intervention? What is the intervention? This exercise develops intuition for how performance cliffs emerge from operational drift rather than sudden failures.

**Homework 7: Design a Bigtable-backed analytics system.**
A product analytics company needs to store: (1) per-user event streams (1B users, 100 events/user/day), (2) funnel analysis (what fraction of users who did event A also did event B within 1 hour?), (3) cohort analysis (users who signed up in week X — how many returned in week X+1?). Design the complete storage architecture. Which parts are served by Bigtable? Which require a separate offline computation layer? How does data flow from the write path (event ingestion) to the query path (funnel and cohort queries)? Estimate the storage and throughput requirements.

---

## Advanced Concepts for L6 Interviews

This section covers concepts that are rarely covered in introductory material but frequently come up in Staff-level interviews at companies using Bigtable or HBase. You don't need to have memorized every detail, but knowing these topics exist and being able to reason about them signals the difference between "I read the paper" and "I've thought deeply about this system."

### Locality Groups: Column Family Physical Isolation

A **locality group** is a configuration in Bigtable that maps one or more column families to a single set of SSTable files on disk. By default, all column families are in the same locality group (they're stored together). But you can create separate locality groups to physically isolate column families.

Why does this matter? Imagine you have a table with two column families:
- `content`: stores large HTML blobs, ~100KB per cell
- `metadata`: stores small fields (language, pagerank, crawl date), ~100 bytes per cell

If both families are in the same locality group, reading `metadata` also loads `content` blocks from disk (because they're interleaved in the same SSTable files). For a workload that reads only `metadata` (the common case for serving search results), this is 1000x unnecessary I/O.

With separate locality groups:
- `metadata` → locality group 1 (small, fast, frequently cached)
- `content` → locality group 2 (large, rarely accessed, not cached)

A read of `metadata` touches ONLY locality group 1's SSTable files. No content blocks are loaded. This is essentially the column-family version of column-store pruning — you only pay for the I/O you need.

```
WITHOUT LOCALITY GROUPS:
  SSTable block: [content:html][metadata:lang][content:html(row2)][metadata:pagerank]
  Reading metadata:lang requires loading the entire block, including
  the 100KB content:html entries around it.
  I/O per metadata read: ~128KB (one SSTable block)

WITH LOCALITY GROUPS:
  Locality Group 1 SSTable: [metadata:lang][metadata:pagerank][metadata:crawl_date]
  Locality Group 2 SSTable: [content:html][content:images]
  Reading metadata:lang loads ONLY the metadata SSTable blocks.
  I/O per metadata read: ~1KB (just the metadata entries)
  Speedup: ~128x less I/O per read
```

### Compression: Per-Column-Family Tuning

Bigtable (and HBase) support configurable compression per column family or per locality group. The two common options:

**No compression**: fast reads/writes, larger storage footprint. Best for pre-compressed data (JPEG images, already-gzipped HTML) where re-compressing would make the data larger.

**Snappy compression**: moderate compression ratio (~2-3x for HTML text), extremely fast decompression (multi-GB/second). Best for text data like HTML, JSON, logs. Bigtable uses Snappy by default for most column families.

**ZSTD or LZ4**: higher compression ratio at higher CPU cost. Best for cold data that is rarely read (archival use cases) where storage cost savings justify the decompression overhead.

The compression decision interacts with the access pattern. For the web crawl table where `content:html` is read infrequently but stored for billions of URLs, ZSTD makes sense (3-5x compression saves enormous storage at the cost of slower decompression for rare reads). For `metadata` columns that are read for every search result, Snappy or no compression makes sense (fast decompression matters more than storage savings).

### Read-Your-Writes Consistency

A common operational question: if a client writes to a Bigtable cell and immediately reads the same cell, is the write guaranteed to be visible?

Yes, for the same process talking to the same Tablet Server. The Tablet Server serializes all reads and writes for a given row — the write is applied to the MemTable before success is returned, and the subsequent read checks the MemTable first. The MemTable hit returns the just-written value. This is read-your-writes consistency within a single row.

However, if the client process is a different process (or the same process after a restart), there is a subtle case: if the write completed but the MemTable hasn't been flushed to an SSTable yet, and the Tablet Server crashed and was replaced by a new Tablet Server, the new Tablet Server replays the WAL to reconstruct the MemTable. Until WAL replay is complete, reads to that tablet may be temporarily unavailable or may return pre-crash state. After WAL replay (typically seconds), the write is visible. This is a very narrow availability window, not a consistency window — the data is in the WAL and will not be lost.

### Percolator: Distributed Transactions on Top of Bigtable

The Bigtable paper (2006) describes single-row atomicity. Google's Percolator paper (2010) describes how to build distributed transactions (spanning multiple rows and multiple tablets) on top of Bigtable's single-row atomicity.

The key insight: Percolator uses Bigtable's multi-version cells and single-row compare-and-swap operations to implement a two-phase locking protocol. Each row has a "lock" column (a Bigtable cell). To update rows A and B atomically:
1. Write a lock entry to row A's lock column (using Bigtable's compare-and-swap: only write if lock is absent)
2. Write a lock entry to row B's lock column
3. Write the actual data to both rows under a new timestamp
4. Delete the lock entries (commit)

If the process crashes between steps 2 and 3, the lock entries remain. A "cleaner" process periodically scans for stale locks and rolls them back. This is a simplified description — the actual Percolator protocol handles many edge cases — but the key point for an interview: cross-row transactions on Bigtable are possible but require an external coordination layer that uses Bigtable's single-row primitives. This is why Google built Spanner (which has built-in cross-row transactions) for applications that need ACID at scale — Percolator works but adds operational complexity.

### Backup and Restore in Bigtable

Bigtable does not have a built-in "point-in-time backup" in the traditional sense. Because all data is stored in GFS (immutable SSTables), the backup strategy is different from traditional databases:

**Snapshot export**: Bigtable's export operation reads all SSTables for a table and copies them to a separate GCS/GFS bucket, along with the table schema. This is effectively a "cold backup" — a consistent snapshot at the time of the export. Export is performed using a MapReduce job that reads the table and writes Avro/CSV/SequenceFile to GCS.

**Import**: The reverse — read files from GCS and bulk-load them into Bigtable using the SSTable bulk-load mechanism (bypasses the WAL and MemTable for high-throughput initial data load).

**Point-in-time recovery**: True point-in-time recovery (restore to any arbitrary past moment) is not natively supported. You'd need to maintain a change log (by streaming all mutations through a Pub/Sub system) and replay the log up to the desired restore point. This is complex and rarely implemented in practice — most teams rely on periodic exports and accept that "restore to last export" is the recovery target.

### Intern → Staff Progression: Full Picture

Looking back at all 10 parts of this chapter, here is how the complete progression appears across the entire Bigtable competency:

```
┌───────────┬────────────────────────────────────────────────────────────────┐
│   Level   │  What they can do in a Bigtable interview                       │
├───────────┼────────────────────────────────────────────────────────────────┤
│  Intern   │  Knows Bigtable is a NoSQL database. Cannot explain data model, │
│           │  architecture, or row key design. Cannot trace write/read path.  │
├───────────┼────────────────────────────────────────────────────────────────┤
│    L3     │  Knows row keys and column families. Knows writes go to WAL then │
│           │  MemTable. Cannot explain WHY. Cannot design a row key schema.   │
│           │  Cannot explain what happens when a Tablet Server fails.         │
├───────────┼────────────────────────────────────────────────────────────────┤
│    L4     │  Can explain the full data model (4 coordinates of a cell).      │
│           │  Understands the three-level tablet lookup hierarchy.             │
│           │  Understands WAL → MemTable → SSTable write path.               │
│           │  Can design a simple row key (user_id prefix for per-user data). │
│           │  Cannot explain compaction types or Bloom filters in depth.      │
├───────────┼────────────────────────────────────────────────────────────────┤
│    L5     │  Can explain all architecture components and their roles.        │
│           │  Understands minor vs. major compaction and when each triggers.  │
│           │  Understands Bloom filters and read amplification.               │
│           │  Can design non-trivial row keys (reversed domain, inverted      │
│           │  timestamp, salting for hotspot avoidance).                       │
│           │  Knows HBase, Cassandra, Spanner, and when to choose each.      │
│           │  Cannot yet reason about edge cases (Chubby outage, WAL         │
│           │  sharing, Percolator) or quantify performance at scale.          │
├───────────┼────────────────────────────────────────────────────────────────┤
│    L6     │  Can design the full row key schema from first principles.       │
│           │  Quantifies performance: writes/second, tablet count, SSTable    │
│           │  count thresholds, Bloom filter memory usage.                    │
│           │  Handles edge cases: Chubby outage impact, WAL sharing recovery, │
│           │  compaction lag detection, proto versioning in column qualifiers. │
│           │  Knows when Bigtable is the WRONG choice.                        │
│           │  Can design cross-row transactions using Percolator concepts.    │
│           │  Can reason about the GFS + Bigtable + MapReduce stack holistically│
│           │  and connect storage design to pipeline design.                  │
└───────────┴────────────────────────────────────────────────────────────────┘
```

## Bigtable Operational Playbook: What to Monitor and What to Do

This section is for candidates interviewing for Staff-level SRE, infrastructure, or backend roles where operational depth is expected in addition to design knowledge. Even for pure design interviews, knowing WHAT to monitor demonstrates you've thought past "design the schema" to "operate the schema in production."

### Key Metrics Every Bigtable Operator Monitors

```
┌─────────────────────────────────────────────────────────────────────┐
│              BIGTABLE MONITORING: WHAT MATTERS AND WHY              │
│                                                                     │
│  Per-Tablet Metrics:                                                │
│  ─────────────────                                                  │
│  SSTable count per tablet                                           │
│    Alert: > 15 SSTables on any tablet                               │
│    Action: trigger compaction                                        │
│    Why: direct driver of read latency (each SSTable = more I/O)     │
│                                                                     │
│  Tablet size (MB)                                                   │
│    Alert: > 180MB (approaching 200MB split threshold)               │
│    Action: investigate if tablet will split soon, plan for it        │
│    Why: splits cause brief client cache staleness                    │
│                                                                     │
│  Tablet write rate (writes/second)                                  │
│    Alert: > 20K writes/second sustained on one tablet               │
│    Action: investigate row key design for hotspot                    │
│    Why: 20K/s often exceeds a single tablet's sustainable rate       │
│                                                                     │
│  Per-Tablet Server Metrics:                                         │
│  ─────────────────────────                                          │
│  CPU utilization                                                    │
│    Alert: > 80% sustained                                           │
│    Action: rebalance tablets or add Tablet Servers                  │
│                                                                     │
│  MemTable memory usage                                              │
│    Alert: total MemTable memory > 60% of available RAM              │
│    Action: lower MemTable flush threshold, increase compaction rate  │
│                                                                     │
│  WAL lag (bytes written to WAL vs. GFS acknowledged)               │
│    Alert: WAL append P99 > 10ms                                     │
│    Action: check GFS chunkserver load on WAL namespace              │
│                                                                     │
│  Cluster-Level Metrics:                                             │
│  ──────────────────────                                             │
│  METADATA tablet read latency                                       │
│    Alert: METADATA read P99 > 50ms                                  │
│    Action: check for METADATA tablet hotspot, add replicas          │
│    Why: high METADATA latency slows ALL cache-miss client lookups   │
│                                                                     │
│  GFS disk usage for Bigtable namespace                              │
│    Alert: > 80% full                                                 │
│    Action: trigger major compaction, add GFS storage                 │
│    Why: at 90% full, GFS chunkservers start failing writes          │
│                                                                     │
│  Master tablet assignment queue depth                               │
│    Alert: > 100 tablets waiting for assignment                       │
│    Action: check for Tablet Server failures, add servers             │
│    Why: assignment backlog means some tablets are unavailable        │
└─────────────────────────────────────────────────────────────────────┘
```

### Operational Runbook: Common Failure Modes

**Scenario 1: Read latency spikes on one tablet, others fine.**
Root cause: almost certainly SSTable count. Check SSTable count metric for the hot tablet. If > 15, trigger major compaction. If compaction doesn't help, check if there's an unusually high MemTable write rate on the tablet (which prevents compaction from keeping up). Rate-limit writes to that tablet temporarily while compaction runs.

**Scenario 2: Write latency spikes cluster-wide, reads fine.**
Root cause: GFS WAL write slowness. Check GFS chunkserver health for the WAL namespace — are any chunkservers overloaded or failing? Check disk usage — is the WAL namespace near capacity? Check network — is there a physical network event affecting GFS chunk replication? If GFS WAL chunkservers are unhealthy, writes will slow or timeout cluster-wide. This is a GFS-level incident, not a Bigtable-level incident.

**Scenario 3: METADATA lookups slow for new clients, existing clients fine.**
Root cause: METADATA tablet hotspot. This happens after a mass cache invalidation (Tablet Server restart wave, Chubby outage recovery). The fix is to add METADATA tablet replicas to spread the read load and to implement client-side exponential backoff so new clients don't all hammer METADATA at the same time.

**Scenario 4: One Tablet Server serving 5x more traffic than others.**
Root cause: skewed tablet assignment. Either the Tablet Server got unlucky (it happened to be assigned all the hot tablets), or there's a row key hotspot causing all writes to go to a small set of tablets (which happen to be on this server). Check tablet-level write rates. If all tablets on the server are hot, it's a load imbalance — trigger rebalancing. If only 1-2 tablets are hot, it's a row key design problem — redesign the schema.

## Quick Reference Card

```
┌─────────────────────────────────────────────────────────────────────┐
│                   BIGTABLE QUICK REFERENCE                          │
│                                                                     │
│  Data model:      sorted map: (row_key, col_family, col_qualifier,  │
│                   timestamp) → value (bytes)                        │
│                                                                     │
│  Row sort order:  lexicographic (alphabetical byte order)           │
│  Storage:         GFS (SSTables + WAL)                              │
│  Coordination:    Chubby (master election, tablet server registry)  │
│                                                                     │
│  Key components:                                                    │
│  • Master:        assigns tablets, NOT in data path                 │
│  • Tablet Server: serves reads/writes, holds ~10-1000 tablets       │
│  • Client library:caches tablet locations, talks directly to TS     │
│  • Chubby:        distributed lock, stores root tablet location     │
│                                                                     │
│  Write path:      WAL (GFS, durable) → MemTable (memory)           │
│  Read path:       MemTable → Bloom filter → SSTables (newest first) │
│  Compaction:      MemTable→SSTable (minor), SSTable merge (major)   │
│                                                                     │
│  Row key design rules:                                              │
│  1. Put most common scan prefix FIRST                              │
│  2. Reverse domain names for URL data (com.google.www)             │
│  3. Invert timestamps for recency-first (MAX_INT - timestamp)       │
│  4. Add hash prefix for hotspot avoidance (user_id % N)            │
│  5. Never use auto-increment (all writes hit one tablet)            │
│                                                                     │
│  Open-source equivalents:                                           │
│  Bigtable → HBase (HDFS + ZooKeeper)                               │
│  Bigtable + stronger consistency → Spanner (CockroachDB)            │
│  Bigtable data model + eventual consistency → Cassandra             │
│  Bigtable managed cloud service → Cloud Bigtable (GCP)             │
└─────────────────────────────────────────────────────────────────────┘
```

---

## The Ten Things That Separate L5 From L6 in a Bigtable Interview

This is a direct, practical list. If you can speak to each of these in an interview, you are operating at L6 Bigtable fluency.

**1. Row key design from access patterns, not intuition.**
L5 knows the rules (prefix-first, invert timestamps, don't use auto-increment). L6 derives the rules from first principles during the interview: "the most common query is X, so X must be the prefix, because that's the only way to make X a range scan rather than a full table scan."

**2. Quantitative sizing before choosing the schema.**
L6 always says "at 1M writes/second × 200 bytes = 200MB/s total. At 128MB tablet size and 10K writes/second per tablet, I need at least 100 Tablet Servers." Numbers anchor the design to reality.

**3. Hotspot identification and mitigation without being prompted.**
Before the interviewer asks "but what about hotspots?", L6 says "this design might create a hotspot when X happens — here's the mitigation."

**4. Knowing which query patterns are impossible without additional infrastructure.**
Secondary index queries, aggregate functions, cross-row transactions — L6 names these limitations before being asked and proposes solutions (secondary index tables, Dataflow for aggregates, Percolator or Spanner for transactions).

**5. The compaction-performance link.**
L6 can explain exactly how SSTable count drives read latency, and can estimate at what SSTable count the latency becomes unacceptable for the system's SLA.

**6. The shared WAL trade-off.**
L6 knows that Tablet Servers use one WAL per server (not one per tablet), and can explain why this helps write performance but complicates recovery.

**7. The Chubby dependency envelope.**
L6 can articulate exactly which operations succeed vs. fail during a Chubby outage: existing reads/writes continue, new client startups fail, Master failover is blocked.

**8. The GFS dependency and what it means for durability.**
L6 knows that all Bigtable durability is delegated to GFS, that Tablet Servers are stateless, and that a Tablet Server crash with a full MemTable is safe because the WAL in GFS captures everything.

**9. When NOT to use Bigtable.**
L6 proactively identifies when the problem doesn't fit Bigtable: small datasets, cross-row transaction requirements, secondary index needs, sub-millisecond latency requirements (use Redis instead).

**10. The full stack: GFS → Bigtable → MapReduce.**
L6 places Bigtable in context. It's not a standalone database — it's the online serving layer for structured data that was bulk-loaded from GFS via MapReduce. Design that ignores the batch pipeline is incomplete.

## Chapter Summary

```
┌─────────────────────────────────────────────────────────────────────┐
│                    CHAPTER 84: KEY TAKEAWAYS                        │
│                                                                     │
│  1. Bigtable is a sorted map. Rows are sorted lexicographically    │
│     by row key. Everything about performance follows from this.    │
│                                                                     │
│  2. Data model: (row_key, column_family:column_qualifier,           │
│     timestamp) → value. Sparse. Multi-version. Schema-flexible      │
│     within column families.                                         │
│                                                                     │
│  3. Architecture: Chubby (coordination) + Master (tablet           │
│     assignment) + Tablet Servers (data) + GFS (storage).           │
│     Master and Chubby are NOT in the data path.                    │
│                                                                     │
│  4. Storage: LSM tree. Writes: WAL (durable) → MemTable (fast).   │
│     Reads: MemTable → Bloom filter → SSTables (newest first).      │
│     Compaction merges SSTables to reduce read amplification.       │
│                                                                     │
│  5. Row key design is the critical skill. Rules: common scan       │
│     prefix first; reverse domains; invert timestamps for recency;  │
│     salt with hash for hotspot avoidance. Never auto-increment.    │
│                                                                     │
│  6. Bigtable lacks: cross-row transactions, secondary indexes,     │
│     SQL queries. Spanner (Bigtable++), HBase (open-source clone),  │
│     Cassandra (eventual consistency variant) are the alternatives. │
│                                                                     │
│  7. Interview one-liner: "Design your row key for your most        │
│     important scan pattern. Everything else in Bigtable follows    │
│     from that choice."                                             │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Bigtable Glossary: Terminology to Know Cold

If an interviewer uses any of these terms, you should know them without hesitation. This list covers the terms from the original paper and from common engineering discussions about Bigtable and its ecosystem.

| Term | Definition |
|------|------------|
| **Tablet** | A contiguous range of rows in a table; the unit of assignment, splitting, and serving. |
| **Tablet Server** | A server process that manages and serves a set of tablets. Stateless w.r.t. data. |
| **Master** | The administrative server: assigns tablets, detects failures. Not in data path. |
| **Chubby** | Google's distributed lock service (Paxos-based). Bigtable's coordination backbone. |
| **SSTable** | Sorted String Table. An immutable, sorted, indexed file on GFS. The on-disk format. |
| **MemTable** | The in-memory sorted write buffer. The first destination of new writes (after WAL). |
| **WAL** | Write-Ahead Log. The sequential mutation log in GFS. Provides durability. |
| **Minor Compaction** | Flushing the MemTable to a new SSTable on disk (frequent, small). |
| **Major Compaction** | Merging all SSTables into one, removing tombstones and old versions (infrequent, large). |
| **Merge Compaction** | An intermediate compaction: merging a few SSTables without reaching full major. |
| **Bloom Filter** | A memory-resident probabilistic structure that answers "definitely NOT in this SSTable" for any key. |
| **Locality Group** | A configuration that maps column families to separate SSTable files for I/O isolation. |
| **METADATA Table** | A special Bigtable table that maps tablet key ranges to Tablet Server addresses. |
| **Root Tablet** | The one tablet that is never split; stores locations of all METADATA tablets. |
| **Column Family** | A logical + physical grouping of columns; must be declared at table creation. |
| **Column Qualifier** | The dynamic column name within a column family; can be any byte string. |
| **Tombstone** | A special delete marker written to the MemTable; the deleted data is physically removed during major compaction. |
| **Read Amplification** | The ratio of storage reads required per logical read; higher SSTable count = higher read amplification. |
| **Write Amplification** | The ratio of storage writes per logical write; compaction increases this. |
| **Percolator** | Google's framework for distributed transactions on top of Bigtable (2010 paper). |
| **TrueTime** | Google's clock API that provides bounded uncertainty — used in Spanner, not Bigtable. |
| **Hotspot** | A single tablet or Tablet Server receiving disproportionate traffic relative to others. |
| **Salting** | Adding a hash prefix to a row key to distribute writes across multiple tablets. |

## Appendix: Bigtable Paper Summary — Key Numbers

These numbers appear in the original Bigtable paper (Chang et al., OSDI 2006) and are frequently cited in Staff-level discussions. Knowing specific benchmarks grounds your design reasoning in data, not guesswork.

```
BIGTABLE PERFORMANCE BENCHMARKS (from the 2006 paper):

Experimental setup: 1 Tablet Server, 100 client machines
  Tablet Server: 1 Xeon dual-core, 8GB RAM, RAID-10 array
  Values: 1000-byte random values per cell

Random writes (single-row, sequential clients):
  ~10,000 writes/second to one Tablet Server
  Latency: 6.1ms median

Random reads (single-row, sequential clients):
  ~57,000 reads/second to one Tablet Server
  BUT: 80% cache hit rate assumption in this benchmark
  Without cache: much lower (SSTable disk reads required)

Sequential reads (range scans):
  ~580,000 read operations/second
  Sequential reads are 10x faster than random reads
  because of GFS sequential I/O optimization

Sequential writes (bulk load via SSTable import):
  > 1 million operations/second
  Bulk SSTable import bypasses WAL and MemTable entirely

Scalability (benchmark with 500 Tablet Servers):
  Reads: 612,000 random reads/second (roughly linear scaling)
  Writes: 168,000 random writes/second
  Scans: not bottlenecked by Bigtable; bottlenecked by client network

Key takeaways for interviews:
  • Single tablet server: ~10K random writes/s, ~57K random reads/s
  • Sequential (scan) throughput: 10x random throughput
  • Scaling is roughly linear — double the tablet servers, double throughput
  • Cache hit rate is critical: 80% cache = mostly memory, no GFS reads
  • Bulk SSTable import is 100x faster than individual writes for initial load
```

These numbers are from 2006 hardware. Modern Bigtable on modern hardware with SSD storage is significantly faster (single-server random write throughput is now ~100K-500K operations/second depending on value size and instance type). But the RATIOS remain instructive: sequential reads are ~10x faster than random reads, Tablet Server throughput scales linearly, and cache hit rate is the dominant factor in read performance.

## The Five-Minute Pre-Interview Review

If you have 5 minutes before a system design interview where Bigtable is likely to come up, read only this section. It has the most high-leverage facts that are easiest to forget under interview pressure.

1. **Row key is lexicographically sorted.** What you put FIRST determines what scan is fast. Always design the row key for the most common query first.

2. **Write path: WAL first, then MemTable, then SSTable (async).** Durability comes from the WAL. The MemTable is for speed, not safety.

3. **Read path: MemTable → Bloom filter (skip SSTables?) → SSTables newest to oldest.** More SSTables = slower reads. Bloom filter says "definitely NOT here" — it skips SSTables, it doesn't confirm presence.

4. **Master is NOT in the read/write path.** Clients talk directly to Tablet Servers after a one-time (and cached) lookup. Master is for admin only.

5. **Bigtable limitations to name proactively:** no cross-row transactions, no secondary indexes, no SQL queries. Know the successor for each: Percolator/Spanner for transactions, application-built index tables for secondary indexes, Spanner or BigQuery for SQL.

6. **Common interview mistake to avoid:** Using auto-increment or UUID as row key. Auto-increment means all writes go to one tablet (hotspot at the "latest" end of the table). UUID means random distribution (good for writes) but no locality for any scan query (every query is a full table scan). Always use a prefix that distributes writes AND matches your primary scan pattern — or accept that you need two tables (one per access pattern) if writes and reads are in fundamental conflict.

7. **Compaction is the heartbeat of a healthy tablet.** If you hear "read latency is high on one tablet," your first question is "how many SSTables?" High SSTable count is the root cause of high read latency in an LSM tree. The fix is always compaction. Alerting on SSTable count (threshold: 15-20) catches this before latency spikes.

8. **The one-sentence L6 summary:** "Bigtable is a sorted map where YOU control the sort key — design the row key for your most common scan, and Bigtable is fast; design it poorly, and no hardware will fix it."

---

**Related chapters in this series:** Chapter 83 (GFS — the storage substrate Bigtable runs on), Chapter 82 (Chubby — the lock service Bigtable depends on for coordination), Chapter 85 (MapReduce — the batch processing framework that writes to Bigtable), Chapter 42 (Spanner — Bigtable's successor with full ACID transactions), and Chapter 28 (databases in general — the conceptual framework that places Bigtable in the broader storage landscape).

**Recommended reading order:** If you haven't read the original Bigtable paper, read it after finishing this chapter — the paper is 14 pages and takes about 2 hours. Focus on Sections 2 (data model), 4 (building blocks — this is where GFS and Chubby are described), 5 (implementation — the write path, compaction, and tablet location hierarchy), and 7 (performance evaluation — the concrete benchmark numbers). The rest of the paper (Section 6, refinements; Section 8, real-world lessons) is valuable but secondary. The paper pairs directly with Chapter 83 (GFS) and Chapter 82 (Chubby), which cover the infrastructure Bigtable depends on. Reading all three together builds the complete picture of how Google's distributed storage stack is assembled from composable pieces.

*Chapter 84 complete. Next in the Google Foundational Systems series: Chapter 85 — MapReduce.*

*Pairs with: Ch41b (overview of all Google systems), Ch35 (batch processing and data pipelines), Ch28 (databases), Ch83 (GFS), and Ch82 (Chubby).*

---

## Interview Simulation — Bigtable

*45-minute deep-dive interview on Google's Bigtable paper (Chang et al., OSDI 2006). Interviewers expect you to understand the tablet→SSTable→GFS layering, row key design for scan locality, and why Bigtable needs Chubby despite running on GFS.*

### Phase 1: System Overview and Motivation (10 min)

> **Interviewer:** What problem does Bigtable solve that GFS doesn't?

**Candidate:** GFS stores flat files with no understanding of the data inside them. If you want to look up a specific user's data in a GFS file, you read the entire file. Bigtable adds a structured layer: a sorted, sparse map from (row key, column key, timestamp) to bytes. The sort order enables range scans — "give me all rows from user_100 to user_200" — which maps naturally to many Google workloads: web crawl data (sorted by URL), search index (sorted by term), analytics (sorted by time + user). GFS provides the durable storage underneath; Bigtable provides the structured access pattern.

The other key gap: GFS has relaxed consistency. GFS can't be the source of truth for "does this row exist" without application-level coordination. Bigtable provides tablet-level sequential consistency: within a tablet (a contiguous row range), operations are serialized through the tablet server holding that tablet. This is weaker than distributed ACID transactions (Bigtable has no cross-row transactions in the original paper) but strong enough for most Google use cases.

> **Interviewer:** Describe the Bigtable data model precisely.

**Candidate:** The data model is a sparse, distributed, persistent, sorted map with the key: (row, column family:qualifier, timestamp) → byte array. Row is an arbitrary string up to 64KB; all data for a row is stored together and accessed atomically within a single row. Column family groups related columns and must be declared upfront — it determines physical co-location and compression settings. Qualifier is the sub-column name, arbitrary, created dynamically. Timestamp is a 64-bit integer (usually microseconds since epoch); multiple versions of the same (row, column) can coexist, distinguished by timestamp. The newest version is returned by default.

*(Cross-question: why is the column family declared upfront but the qualifier is dynamic?)* Physical locality. All columns within a family are stored together on disk (same SSTable). This enables efficient column-family-level reads ("give me all 'anchor:' columns for this row") without reading columns from other families. But if you had to declare every qualifier at schema time, you couldn't do dynamic schemas like "store all anchor text for all URLs that link to this page" — the set of qualifying columns is data-dependent.

---

### Phase 2: Key Design Decisions (15 min)

> **Interviewer:** Walk me through a write path in Bigtable from client to durable storage.

**Candidate:** The write path has three phases and four components.

```
Bigtable Write Path
===================

Client
  |
  |--[1. locate tablet via 3-level lookup]-->
  |       Root tablet (in Chubby)
  |         └─ METADATA table (in Bigtable)
  |               └─ user table tablets
  |
  |--[2. write request]-->  Tablet Server (owns tablet for row key)
                              |
                              |--[3. WAL append]-->  GFS (commit log file)
                              |   (must succeed before ACK)
                              |
                              |--[4. memtable insert] (in-memory sorted buffer)
                              |   (no GFS write for memtable)
  |<--[5. ACK]--

Background:
  memtable full → minor compaction → SSTable written to GFS
  N SSTables → merging compaction → fewer SSTables
  All SSTables → major compaction → one clean SSTable (no tombstones)
```

The WAL write to GFS must succeed before the client gets an ACK — that's the durability guarantee. The memtable is purely in-memory and would be lost on crash, but the WAL allows replay. A minor compaction freezes the current memtable and writes it to a new SSTable in GFS asynchronously — no blocking on the client write path.

*(Cross-question: what happens if a tablet server crashes before flushing the memtable?)* The master detects the crash via Chubby session expiration. It reassigns the tablet to another tablet server. The new tablet server replays the WAL from GFS — WAL entries for this tablet are mixed with entries for other tablets in the same log file, so the new server must sort through to find relevant entries. The paper notes this as a recovery optimization opportunity: splitting the commit log by tablet reduces recovery scan time.

> **Interviewer:** Why does Bigtable use three levels of tablet location metadata?

**Candidate:** The three-level hierarchy — Chubby file → root tablet → METADATA tablets → user tablets — is designed to support very large tables without overwhelming any single metadata server. The root tablet location is stored in a Chubby file (the lock service), which clients read first. The root tablet itself is a special Bigtable tablet containing locations of all METADATA tablets. METADATA tablets contain the locations of all user tablets. Each METADATA row is about 1KB; one METADATA tablet (100-200MB) can hold locations for ~128 million user tablets. At 100-200MB per user tablet, that's ~12.8PB of user data indexed by a single METADATA tablet. The three-level hierarchy is designed so that even at enormous scale, the depth never exceeds three hops. Clients cache all three levels — a cache miss only requires one, two, or three RPCs to refill, not a full re-scan.

---

### Phase 3: Trade-offs and Alternatives (10 min)

> **Interviewer:** Why does Bigtable use an LSM tree (memtable + SSTable) rather than a B-tree for on-disk storage?

**Candidate:** The LSM tree converts random writes into sequential writes, which maps perfectly to GFS's strengths. GFS is optimized for sequential access — random small writes to GFS would require seeking within large chunks, fighting the append-optimized design. With an LSM tree, every write to durable storage (whether WAL or SSTable flush) is a sequential append. B-trees require random in-place updates: to update a leaf node, you seek to that location on disk. On spinning disks (the hardware era of the original Bigtable), sequential writes are 100x faster than random writes. On SSDs, the gap is smaller but sequential writes still win for write amplification reasons.

The LSM tradeoff: reads can be slower because you may need to search multiple SSTables and the memtable. Bigtable mitigates this with Bloom filters (per SSTable, to skip SSTables that don't contain the requested row key) and block caches (recently read SSTable blocks stay in memory). Read-heavy workloads with cold data benefit less from LSM; that's why MySQL (B-tree) still dominates for OLTP.

> **Interviewer:** What are the limits of Bigtable's consistency model?

**Candidate:** Bigtable provides single-row atomicity: a read-modify-write on a single row is atomic. But there are no multi-row transactions. If you need to atomically update two rows (e.g., debit one account and credit another), you can't do it with native Bigtable operations. Applications had to implement their own two-phase commit (using Chubby locks) for cross-row consistency, which is complex and error-prone.

This is exactly the gap Spanner was built to fill. Spanner adds distributed transactions with external consistency across arbitrary rows and tables, built on top of Paxos rather than Bigtable's single-master tablet model. The cost is higher latency (multi-phase commit across replicas) vs Bigtable's single-tablet operations.

*(Cross-question: Bigtable has no cross-row transactions — how did Gmail work?)* Gmail's data model was designed to fit in single-row operations. A mailbox was one very wide row (all messages as columns). Operations on a single mailbox (mark read, move to folder) were single-row atomic operations. Cross-row operations (rare in Gmail's case) were handled with application-level idempotency and retry.

---

### Phase 4: Modern Application (10 min)

> **Interviewer:** How would you use Bigtable (or an equivalent) to store time-series metrics for a monitoring system?

**Candidate:** The row key design is everything. For time-series data, the naive key is `metric_name#timestamp`, but that creates a write hotspot: all writes for the most recent timestamp go to the last region/tablet as time advances. The fix: reverse the timestamp in the key — `metric_name#(MAX_LONG - timestamp)`. Now the most recent data is at the start of the keyspace and doesn't create a hotspot at the end.

For high-cardinality metrics (millions of distinct metric series), you also want to hash-distribute the metric name prefix to prevent hot tablets. A common pattern: `hash(metric_name)[0:4]#metric_name#reversed_timestamp`. The hash prefix distributes writes across tablets while the metric name and timestamp preserve scan locality for "give me the last 1 hour of metric X." Column families: one for the raw metric value, one for computed rollups (5m average, 1h average), one for metadata (labels). Set TTL at the column family level — raw data expires in 7 days, rollups expire in 2 years.

> **Interviewer:** HBase is the open-source implementation of Bigtable. What would you need to change in HBase for a production deployment at Google scale?

**Candidate:** Three major things. First, the master: HBase's master is a single JVM process. Google's Bigtable master is also single but runs on dedicated hardware with Chubby-backed HA. For production you'd want automated master failover with a standby, ideally multi-AZ. Second, the WAL: HBase writes WAL to HDFS synchronously (like Bigtable to GFS), but HDFS write latency spikes at GC pauses in the DataNode JVMs. Google used native C++ GFS clients. For HBase in production, tune HDFS DataNode GC aggressively or consider HDFS over SSDs. Third, compaction scheduling: uncontrolled compactions can spike read latency. Google's Bigtable throttled compactions during peak traffic. HBase's compaction throughput controls (`hbase.hstore.compaction.throughput.higher.bound`) need explicit tuning — the defaults are conservative.

---

### Common Cross-Questions and Strong Answers

**Q: Why does Bigtable need Chubby? Can't it self-coordinate?**

A: Chubby serves two roles that Bigtable can't provide for itself. First, it stores the root tablet location — you can't store Bigtable's root in Bigtable (chicken-and-egg: where do you look up the location of the place that stores locations?). Chubby is an external, always-available storage for this bootstrapping metadata. Second, Chubby provides master election: when the Bigtable master dies, a candidate master acquires a Chubby lock before taking over. Without this external consensus service, you'd need Bigtable itself to be a distributed consensus system — circular dependency. The design lesson: distributed systems often need an external coordination service at the bottom of the dependency stack.

**Q: What is a tablet split and how does it work?**

A: When a tablet grows past ~200MB, the tablet server splits it at the median row key. It writes two new tablet metadata entries to the METADATA table and notifies the master. The split is cheap: since tablet data is SSTables on GFS, the split only requires updating metadata to point two tablets at different keyspace ranges; the physical files don't move. The master then assigns the two new tablets to tablet servers (possibly different ones for load balancing). This is why GFS's file-sharing semantics matter: multiple tablet servers can read the same SSTable file (with different keyspace filters) during and after a split.

**Q: How does Bigtable handle tablet server failure during a write?**

A: The client detects the failure (RPC timeout or Chubby session expiry). The master detects the failure when the tablet server's Chubby session expires (within a few seconds). The master reassigns the tablet to another tablet server. The new tablet server loads the tablet's SSTable files from GFS and replays the commit log to recover in-flight writes. The client retries after getting the new tablet server address from METADATA. The total failover time is a few seconds to tens of seconds — acceptable for batch workloads, high for interactive applications, which is why Spanner added synchronous cross-replica replication.

---

*Chapter 84 complete. Next in the Google Foundational Systems series: Chapter 85 — MapReduce.*

*Pairs with: Ch41b (overview of all Google systems), Ch35 (batch processing and data pipelines), Ch28 (databases), Ch83 (GFS), and Ch82 (Chubby).*
