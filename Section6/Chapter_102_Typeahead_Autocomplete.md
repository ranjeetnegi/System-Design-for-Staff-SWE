# Chapter 88: Typeahead / Autocomplete — Google Search / Twitter / Amazon

> Typeahead looks simple: user types "appl", system suggests "apple", "application",
> "apple stock". The hidden complexity is everything underneath: sub-50ms latency,
> personalized ranking, trending queries, typo tolerance, and 100,000 queries per
> second — all simultaneously, all invisible to the user.

---

## Why This Chapter Matters

Autocomplete appears in almost every modern product. Google shows suggestions after
two keystrokes. Amazon populates product titles before you finish typing. Twitter
surfaces hashtags and user handles in real time. LinkedIn completes job titles and
company names. The feature feels instant and magical, and that magic is the result
of serious engineering decisions made years before any user types a single character.

This chapter is asked constantly in system design interviews at Google, Amazon,
Twitter, Microsoft, and LinkedIn — both because the feature is genuinely hard and
because it tests a very specific skill: the ability to separate the offline data
preparation work from the online serving path. Almost every candidate who fails this
question conflates the two. They draw a system that computes suggestions live, from
raw logs, on every keystroke. That system would be 10,000x too slow.

By the end of this chapter you will understand:
- Why a trie is the right data structure to teach in a classroom and the wrong one
  to draw first in an interview
- How billions of search queries get transformed into a lookup table that returns
  answers in under 5 milliseconds
- How Google Instant was built, why it was shut down, and what that tells you about
  the real cost of this feature
- What Amazon had to do after their autocomplete surfaced racist and offensive
  suggestions, and how a content filter fits into the pipeline
- How to run a 45-minute typeahead interview as an L6 candidate

Pairs with Chapter 48 (Search Indexing) and Chapter 63 (Search Ranking). This
chapter focuses on the prefix-matching layer specifically, which is distinct from
both full-text search and ranking.

---

## The One-Sentence Mental Model

> Typeahead = offline pipeline (aggregate query logs → rank top-K per prefix →
> store in prefix hash) + serving layer (prefix cache in Redis, < 5ms lookup) +
> real-time layer (Kafka stream → update trending queries every 30 seconds) +
> personalization (global candidates → per-user re-rank).

Hold that structure in your head. Every part of this chapter is an elaboration
of one piece of it.

---

## Part 1: Requirements — What Are We Actually Building?

### 1.1 The Functional Requirements

Before drawing anything, you need to know exactly what "autocomplete" means in
the context of the interview. Autocomplete is not one thing. Here are the three
distinct variants you will encounter:

**Query autocomplete (Google-style):** User types a search query prefix. System
returns the top N most-searched queries that start with that prefix. The suggestions
are ranked by global query frequency, possibly personalized by user history.

**Entity autocomplete (Twitter-style):** User types "@jan" and sees real Twitter
usernames like "@janedoe", "@janet_jackson". Or types "#mls" and sees hashtag
suggestions. Here the index is a closed set (the set of all users or all hashtags),
not an open set of arbitrary query strings.

**Product autocomplete (Amazon-style):** User types "wire" and sees product titles
and categories. The ranking includes not just frequency but purchase probability,
margin, and personalized purchase history.

For this chapter we focus primarily on query autocomplete because it is the most
complex and most commonly asked variant. The techniques generalize.

**The core functional requirements for query autocomplete:**

1. Given a prefix string P typed by the user, return the top-K query strings that
   begin with P, ranked by relevance (typically: frequency + recency + CTR).
2. Latency must be under 50ms end-to-end (browser to server and back). Many
   implementations target under 20ms at the 99th percentile. Google Instant
   famously targeted under 100ms total page load, with suggestions at under 20ms.
3. Results must be fresh enough that a query that trended in the last hour appears
   in suggestions (not just queries from last month's batch job).
4. K is typically 5-10 suggestions. The UI can only show so many.
5. The system must handle all languages the product supports.

**What does NOT belong in the autocomplete system (clarify this in interviews):**
- Full-text search (that is a different system; this chapter is about prefix matching)
- Spell-checking on completed queries (different from typo tolerance in suggestions)
- Search result ranking (happens after the user submits a query)

### 1.2 The Non-Functional Requirements

Now the numbers. These numbers define every architecture decision.

**Scale:**
- Google processes roughly 8.5 billion searches per day, which is about 100,000
  queries per second (QPS). Because autocomplete fires on every keystroke and the
  average query is 5-7 characters, the autocomplete service sees roughly 5-7x the
  QPS of the search service itself. That is 500,000 to 700,000 requests per second
  for Google-scale autocomplete.
- For a startup product, 1,000 QPS is a reasonable starting assumption. For a
  large consumer product: 100,000 QPS.
- For this chapter we target: 100,000 QPS, sub-50ms P99 latency.

**Data volume:**
- Google logs roughly 5 billion unique queries per day (many are one-off queries;
  many more are repeats). Over a year, the corpus of meaningful queries (those
  with frequency above 1) is in the billions.
- Each query can have up to 10 prefixes of interest (for a 10-character query).
  At 1 billion distinct query strings, that is up to 10 billion prefix-to-suggestion
  mappings. This does not fit in one machine's RAM.

**Freshness:**
- Batch-only systems update suggestions every 24 hours. Acceptable for most use cases.
- News-adjacent products (Twitter, Google during breaking news) need trending queries
  to appear in suggestions within 5-10 minutes of the trend emerging.
- The real-time layer (Part 4) handles this specifically.

**Personalization:**
- Returning users should see their recent searches in suggestions.
- Users with a history of cooking searches should see "apple pie recipe" ranked
  higher for the prefix "apple" than "apple stock".
- This introduces a per-user re-ranking layer (Part 6).

### 1.3 Clarifying Questions You Must Ask in the Interview

An L6 candidate does not start drawing a trie. They ask:

1. "Are we building query autocomplete, entity autocomplete, or product autocomplete?"
   (Determines whether the suggestion set is open or closed.)
2. "What is our target QPS and latency SLA?"
   (Drives the decision to use a pre-computed prefix cache rather than a live trie.)
3. "Do we need real-time trending, or is a daily batch update acceptable?"
   (Determines whether you need a Kafka real-time layer.)
4. "Do we need personalization, or is global ranking sufficient?"
   (Personalization adds a second serving tier.)
5. "What languages do we support?"
   (Multi-language changes how you build the index.)

If an interviewer says "let's simplify and skip personalization and real-time
trending" — that is fine. But you should name those as things you are consciously
scoping out, not things you forgot.

---

**Brainstorming Q&A — Part 1**

**Q: Why does the latency requirement of under 50ms drive so many design decisions?
Couldn't we just make the servers faster?**

A: The 50ms number is not arbitrary. Research on user interface latency (including
Google's own studies) shows that users notice and abandon typeahead suggestions when
they appear more than 100ms after the keystroke. Below 100ms, suggestions feel
instantaneous. Above 100ms, they feel laggy enough to be distracting. The 50ms
server-side budget assumes roughly 30-40ms of network round-trip time for a user
on a typical broadband connection, leaving 10-20ms for actual server computation.
That is a tight budget.

That budget cannot be met by doing any significant computation on the critical path.
You cannot traverse a trie of millions of nodes in 10ms while also handling 100,000
concurrent requests per second. The math does not work out. This is the fundamental
reason the entire design splits into an offline pipeline (which does the expensive
work ahead of time) and a serving layer (which does almost nothing except a hash
table lookup). Making servers faster does not help if the algorithm is O(n) where n
is billions.

**Q: What is the difference between autocomplete and autosuggest? Interviewers
sometimes use these terms differently.**

A: The terms are often used interchangeably, but there is a useful distinction.
Autocomplete in the strict sense means "completing a prefix the user has started
typing" — the suggestions all start with the characters the user has typed.
Autosuggest or query suggestion is broader — it may include queries that are
semantically related but do not share the same prefix. Google's "related searches"
at the bottom of a results page is autosuggest. The dropdown that appears while
typing is autocomplete. In this chapter we focus on the narrower prefix-matching
definition. If an interviewer wants semantic suggestions (embedding similarity), that
is a different system entirely and you should clarify before starting.

**Q: Why does Google fire autocomplete on every keystroke rather than waiting for
the user to pause? Wouldn't waiting save server load?**

A: Google experimented with debouncing (waiting 100-200ms after the last keystroke
before firing a request) and found that even small delays made the feature feel
broken. The reason is perceptual: users have internalized that autocomplete is
"live" and any delay feels like the system is slow rather than the system being
clever. The engineering cost of handling 5-7x QPS amplification from per-keystroke
firing is simply absorbed as the cost of a competitive feature. That said, mobile
clients often implement client-side debouncing of 50-100ms to reduce battery usage,
and many implementations batch keystrokes when the user types very fast. The serving
layer needs to handle peak burst QPS regardless.

---

## Part 2: Data Structures Deep Dive — Trie, Prefix Hash, and More

This is the part of the interview where candidates either shine or sink. Most
candidates know what a trie is. Far fewer can explain when a trie is the wrong
answer and why, and what to use instead.

### 2.1 The Trie — The Textbook Answer

A trie (pronounced "try" or "tree" — both are used) is a tree-shaped data structure
where each node represents one character, and the path from the root to a node
spells out a prefix. The word "trie" comes from "retrieval."

Here is a trie containing the words "apple", "app", "apply", "apt", and "banana":

```
ASCII DIAGRAM 1: Trie Structure

                    [root]
                   /      \
                  a        b
                  |        |
                  p        a
                 / \       |
                p   t      n
               /|   |      |
              l e   [apt]  a
             /  |          |
            e   [app]      n
            |              |
           [apple]         a
            |              |
            [apply]       [banana]
            (ly branch)

Each node stores:
  - character (the edge label)
  - children (map from char → child node)
  - isEndOfWord (boolean)
  - topSuggestions (for autocomplete: pre-stored top-K suggestions)

Traversal for prefix "app":
  root → 'a' → 'p' → 'p' → node at "app"
  From that node, collect all descendants.
  With topSuggestions stored: O(1) result retrieval after O(len(prefix)) traversal.
```

**How you use a trie for autocomplete:**

When the user types "app", you traverse the trie: root → 'a' → 'p' → 'p'. You
arrive at the node for the prefix "app". From that node, you collect all words
reachable by following any path downward. The suggestions for "app" are all words
that start with "app".

The naive approach is to do a breadth-first or depth-first search from the "app"
node to collect all descendants. But that is too slow — a popular prefix like "a"
might have millions of descendants. The optimization is to pre-store the top-K
suggestions at every node. When you arrive at the "app" node, you just read
the pre-stored list: ["application", "apple", "app store", "apply", "appointment"].

**Why the trie fails at Google scale:**

Imagine 1 billion unique query strings in your trie. The average query is 6
characters. That is 6 billion nodes minimum (each character is a node). Each node
stores a character, a children map, and a top-K list. A node naively takes ~100-200
bytes depending on implementation. Six billion nodes × 150 bytes = 900 GB. That
does not fit on one machine.

Even with compression and careful implementation you are looking at hundreds of
gigabytes for a trie of this size. You can shard it (Part 5 discusses this), but
sharding a trie is complex: query prefixes do not distribute uniformly across shards,
and a prefix traversal might need to touch nodes on multiple shards.

**The trie is still used in practice — just not as the primary serving structure.**
It appears in the offline aggregation pipeline (Part 3) as a data structure for
counting prefix frequencies, and in smaller-scale systems like mobile autocomplete
where the dictionary is bounded (a few hundred thousand words).

### 2.2 The Compressed Trie (Patricia Trie / Radix Trie)

A regular trie wastes space on long chains of single-child nodes. "banana" creates
six nodes in a row: b → a → n → a → n → a. If "banana" is the only word under 'b',
all six of those nodes are just a linear chain.

A compressed trie (also called a Patricia trie or radix trie) collapses these
chains. Instead of one node per character, a node can store a whole substring when
it has only one child.

```
ASCII DIAGRAM 2: Compressed Trie (Radix Trie)

Regular trie for "apple", "application", "apt":
  a → p → p → l → e          (apple)
            |   i → c → a → t → i → o → n   (application)
        t   (apt)

Compressed (radix) trie for same words:
  [a]
  ├── [p]
  │    ├── [p] → [l]
  │    │          ├── [e]          = "apple"
  │    │          └── [ication]    = "application"
  │    └── [t]                     = "apt"

Further compressed (single-path collapses):
  [a]
  ├── [pp]                    (shared prefix "pp")
  │    ├── [le]               = "apple"
  │    └── [lication]         = "application"
  └── [pt]                    = "apt"

Savings: instead of 20 nodes for 3 words, we have 5 nodes.
At scale (1B queries), a compressed trie can cut memory by 70-80%.
```

The trade-off: compressed tries are more complex to update. When a new word arrives
that shares only part of a compressed node's string, you must split the node. For
a system with a static or slowly-changing dictionary, this is acceptable. For a
live autocomplete with real-time updates, it adds complexity.

### 2.3 The Prefix Hash Table — The Production Answer

Here is what most production autocomplete systems actually use: a hash table that
maps every possible prefix to the pre-computed list of top-K suggestions for that
prefix.

The idea is blunt but effective:

```
PREFIX HASH TABLE (conceptual):

  Key (prefix string)  →  Value (top-K suggestion list)
  ─────────────────────────────────────────────────────
  "a"                  →  ["apple", "amazon", "airbnb", "airpods", "aol"]
  "ap"                 →  ["apple", "app store", "apple tv", "apples", "aps"]
  "app"                →  ["apple", "app store", "apple tv", "application", "applebee's"]
  "appl"               →  ["apple", "apple tv", "apple watch", "applebee's", "apple cider"]
  "apple"              →  ["apple", "apple tv", "apple watch", "apple store", "apple cider"]
  "g"                  →  ["google", "gmail", "google maps", "games", "google translate"]
  "go"                 →  ["google", "google maps", "google translate", "goodreads", "golf"]
  ...

Total entries = sum of all prefixes of all indexed queries.
For a query "apple" (5 chars), we store keys: "a", "ap", "app", "appl", "apple"
Each mapped to the top-K list that includes "apple" for that prefix.
```

**Why this is better than a live trie traversal:**

Lookup is O(1). You hash the prefix string, look up the bucket, return the list.
No tree traversal. No collecting descendants. Just a single hash table lookup.
At 100,000 QPS with a median prefix length of 4 characters, this system can handle
the load on a few Redis nodes with room to spare.

**The storage cost:**

If you have 1 billion unique query strings and each averages 6 characters, you have
up to 6 billion prefix-to-suggestion mappings (one for each character position in
each query). At roughly 200 bytes per entry (prefix string + compressed suggestion
list), that is 1.2 TB of data. That does not fit in one machine's RAM, but it fits
easily across a cluster of Redis nodes with sharding by prefix.

**The optimization — prefix length limit:**

In practice, you only store prefixes up to length L (typically L = 10 or 12). Queries
longer than L characters are rare enough that you can fall back to a trie or secondary
lookup. This cuts the storage by 50-70% at the cost of slightly higher latency for
long-prefix queries (which are rare).

**When to choose which:**

```
DATA STRUCTURE COMPARISON:

              Trie              Compressed Trie    Prefix Hash Table
──────────────────────────────────────────────────────────────────────
Lookup        O(len(prefix))    O(len(prefix))     O(1)
Storage       High (nodes)      Medium             High (precomputed)
Update        Easy              Moderate           Moderate (regen)
Scalability   Hard to shard     Hard to shard      Easy (shard by prefix)
Fuzzy match   No                No                 No (needs extra layer)
Best for      Small dict        Medium dict        Large scale production
              (<1M entries)     (<100M entries)    (100M+ entries)
──────────────────────────────────────────────────────────────────────
```

**The interview answer:** Lead with prefix hash table as your primary serving
structure. Mention trie as the textbook answer and explain why it does not scale.
Describe compressed trie as a middle ground. This is the L6 calibration.

### 2.4 N-grams and Inverted Indexes

Two more data structures come up, especially for fuzzy matching (Part 7).

**N-grams:** An n-gram is a contiguous sequence of n characters from a string.
Bigrams are 2-character sequences; trigrams are 3-character sequences.

The word "apple" broken into trigrams: "app", "ppl", "ple".
The word "apply" broken into trigrams: "app", "ppl", "ply".

Both words share the trigrams "app" and "ppl". This overlap is how you find
near-misses: if a user types "aple" (one character dropped), the trigrams "apl",
"ple" overlap significantly with "apple"'s trigrams. Trigram-based fuzzy matching
is much faster than computing full edit distance (explained in Part 7).

**Inverted index on n-grams:** Store a mapping from each trigram to all queries
that contain it. Then, for a fuzzy prefix, compute its trigrams, look up each
trigram in the inverted index, and find queries that appear in many of those lists.
High overlap = high similarity.

```
TRIGRAM INVERTED INDEX (partial):

  Trigram  →  Queries containing it
  ────────────────────────────────────────────────────────
  "app"    →  {"apple", "application", "app store", "apple tv", ...}
  "ppl"    →  {"apple", "application", "supply", ...}
  "ple"    →  {"apple", "simple", "people", ...}
  "aly"    →  {"analysis", "Italy", "ally", ...}
```

For the prefix "aple" (typo for "apple"): trigrams "apl", "ple". Looking up "ple"
in the index returns {"apple", "simple", "people"}. "apple" is a plausible
suggestion. This is how typo-tolerant suggestions work without running Levenshtein
distance on every candidate.

---

**Brainstorming Q&A — Part 2**

**Q: In the prefix hash table, you said "storage explodes" because every prefix of
every query is stored. Can you put an actual number on this for a system like Google?**

A: Let us estimate carefully. Google indexes roughly 5 billion unique query strings
that are meaningful (high enough frequency to suggest). The average query is about
6 characters. If we store all prefixes up to length 10 (beyond that, we fall back),
then for each unique query of length n, we store min(n, 10) prefix entries. At an
average of 6, that is about 6 entries per query. Five billion queries × 6 = 30 billion
entries in the prefix hash. Each entry is roughly 200 bytes (prefix string as key,
compressed top-K list as value). 30 billion × 200 bytes = 6 terabytes.

That is not RAM — that is disk. You would store this in a distributed key-value store
like Redis Cluster or a custom sharded hash map. Redis Cluster can handle petabytes
of data distributed across thousands of nodes. In practice Google does not use Redis;
they use custom in-house storage. But the scale is the right answer: low single-digit
terabytes for the prefix index, distributed across many machines.

**Q: You said the prefix hash table has O(1) lookup. But hashing is not free —
you still have to compute a hash of the prefix string. Is this really faster than
trie traversal?**

A: Yes, significantly faster. Hashing a 4-character string takes on the order of
50-100 nanoseconds on modern hardware — it is just a few arithmetic operations.
Trie traversal for a 4-character prefix takes 4 pointer dereferences (root →
child → child → child → child). At each step you must look up the character in a
children map (itself a hash map or array). So trie traversal is actually multiple
hash lookups chained together, plus the overhead of pointer-chasing through memory
which causes cache misses. The prefix hash table does one hash lookup on the full
prefix string. It is faster in practice, not just in Big-O notation.

**Q: When would you actually choose a trie over a prefix hash table in production?**

A: Three scenarios. First: when your dictionary is small enough to fit in a single
machine's RAM (under ~1 million entries) and you need to support arbitrary-length
prefix queries without pre-knowing the max prefix length. A spell-checker in a word
processor is a good example — the dictionary is ~300,000 words, memory is fine,
and you want exact prefix matching down to arbitrary depth. Second: when you need to
support prefix range scans — "give me all queries that start with 'ap' through 'ar'"
— a trie naturally supports this, while a hash table requires knowing all prefixes
explicitly. Third: when memory is severely constrained and you can accept the
traversal latency — embedded devices, mobile offline dictionaries. For a web-scale
autocomplete system, you almost always want the prefix hash table or a custom variant.

---

## Part 3: The Offline Aggregation Pipeline

This is the part that most candidates draw wrong. They imagine computing suggestions
live, from raw logs, on every user request. That would be impossibly slow. The real
system pre-computes everything in a massive offline job.

### 3.1 The Raw Input: Query Logs

Every time a user performs a search, the search system writes a log entry:

```
LOG ENTRY FORMAT:
  {
    "timestamp": "2024-01-15T14:32:01Z",
    "user_id": "u_a8f3b2c1",          // hashed/anonymized
    "session_id": "s_9d2e1f4a",
    "query": "apple iphone 15 review",
    "language": "en",
    "country": "US",
    "result_clicked": "techradar.com/reviews/apple-iphone-15",
    "click_rank": 2,
    "device": "mobile"
  }
```

At Google scale, this is hundreds of billions of log entries per day. Even at a
mid-size product (1 million daily active users, 10 searches each), you have 10
million log entries per day. These logs flow into a data lake (typically HDFS or
S3) and are processed by batch jobs.

### 3.2 The MapReduce/Spark Pipeline

The offline pipeline runs periodically — hourly, every 4 hours, or daily depending
on freshness requirements. Here is what it does:

```
ASCII DIAGRAM 3: Offline Aggregation Pipeline

  ┌─────────────────────────────────────────────────────────────────┐
  │                     OFFLINE PIPELINE                            │
  │                                                                 │
  │  Raw Query Logs (S3/HDFS)                                       │
  │  ─────────────────────                                          │
  │  billions of log entries per day                                │
  │         │                                                       │
  │         ▼                                                       │
  │  [STEP 1: Clean & Normalize]                                    │
  │  - Lowercase all queries                                        │
  │  - Remove PII (email addresses, phone numbers in queries)       │
  │  - Remove 1-char queries (too noisy)                            │
  │  - Deduplicate within same session (user typed "appl" then      │
  │    "apple" — only count the final submitted query once)         │
  │         │                                                       │
  │         ▼                                                       │
  │  [STEP 2: Map — emit (prefix, query) pairs]                     │
  │  For query "apple iphone":                                      │
  │    emit("a",      "apple iphone")                               │
  │    emit("ap",     "apple iphone")                               │
  │    emit("app",    "apple iphone")                               │
  │    emit("appl",   "apple iphone")                               │
  │    emit("apple",  "apple iphone")                               │
  │    emit("apple ", "apple iphone")    ← space is a valid char    │
  │    ... up to prefix length limit (10)                           │
  │         │                                                       │
  │         ▼                                                       │
  │  [STEP 3: Reduce — count frequency per (prefix, query)]         │
  │  ("app", "apple iphone") → count: 18,392,000                   │
  │  ("app", "application")  → count: 12,847,000                   │
  │  ("app", "apple store")  → count:  9,284,000                   │
  │         │                                                       │
  │         ▼                                                       │
  │  [STEP 4: Rank — compute score per (prefix, query)]             │
  │  Score = w1*frequency + w2*recency_boost + w3*CTR               │
  │  - recency_boost: queries from last 7 days get multiplier       │
  │  - CTR: fraction of times this suggestion was clicked           │
  │         │                                                       │
  │         ▼                                                       │
  │  [STEP 5: Top-K selection per prefix]                           │
  │  For each prefix, keep only top K=100 (prefix, query, score)    │
  │  (K=100 because personalization layer will re-rank to top 10)   │
  │         │                                                       │
  │         ▼                                                       │
  │  [STEP 6: Write to prefix store]                                │
  │  prefix_store.set("app", [                                      │
  │    {query: "apple iphone", score: 18392000},                    │
  │    {query: "application",  score: 12847000},                    │
  │    {query: "apple store",  score:  9284000},                    │
  │    ... (up to 100 entries)                                      │
  │  ])                                                             │
  │                                                                 │
  └─────────────────────────────────────────────────────────────────┘
```

**How Spark implements this at scale:**

In Apache Spark, Step 2 and Step 3 are a single `flatMap` followed by a `reduceByKey`:

```python
# Pseudocode — not production code
query_log = spark.read.parquet("s3://logs/queries/date=2024-01-15/")

def emit_prefixes(row):
    query = row.query.lower().strip()
    prefixes = []
    for i in range(1, min(len(query) + 1, MAX_PREFIX_LEN + 1)):
        prefix = query[:i]
        prefixes.append((prefix, query, row.timestamp))
    return prefixes

prefix_pairs = query_log.flatMap(emit_prefixes)
# Now we have (prefix, query, timestamp) tuples

# Count frequency and compute recency score
def score(timestamp):
    age_days = (TODAY - timestamp).days
    return 1.0 / (1.0 + 0.1 * age_days)  # decay over time

prefix_query_scores = (
    prefix_pairs
    .map(lambda x: ((x.prefix, x.query), score(x.timestamp)))
    .reduceByKey(lambda a, b: a + b)  # sum scores
)

# Top-K per prefix
prefix_to_topK = (
    prefix_query_scores
    .map(lambda x: (x[0][0], (x[0][1], x[1])))  # (prefix, (query, score))
    .groupByKey()
    .map(lambda x: (x[0], sorted(x[1], key=lambda y: -y[1])[:K]))
)
```

This job runs on a cluster of hundreds of machines and takes on the order of 1-4
hours for a full day's logs at Google scale.

### 3.3 Ranking Signals in the Offline Pipeline

Raw frequency alone is a bad ranking signal. Here is why and what to use instead:

**Problem with raw frequency:** A query that was extremely popular two years ago
("Gangnam style") still has high raw frequency, but users do not need that suggestion
today. More recent queries should rank higher.

**Recency decay:** Apply an exponential decay to query counts based on age. A query
from today counts fully; a query from 30 days ago counts at 70%; a query from a year
ago counts at 20%. This causes trending content to rise naturally.

**Click-through rate (CTR):** When the suggestion "apple iphone 15 review" is shown
for the prefix "appl" and the user clicks it, that is a positive signal. When the
suggestion is shown and the user ignores it (types more characters, picks a different
suggestion, or just submits something else), that is a negative signal. CTR requires
a separate log of suggestion impressions and clicks, processed similarly.

**Safe search filtering:** Queries containing offensive, illegal, or harmful terms
must be filtered from suggestions. This is a critical step. Amazon's failure to do
this properly led to a serious incident (covered in Part 10).

**Diversity:** You should not have the top 10 suggestions for "apple" be ten
variations of "apple iphone" — that wastes suggestions. Some systems apply a
diversity penalty to reduce near-duplicate suggestions.

### 3.4 Intern → Staff Progression: Offline Pipeline

**Intern:** "Run a word count MapReduce on the query logs and use frequency as score.
Store the top K queries for each prefix in a database."

**Junior Engineer (L3):** Adds recency decay. Realizes the frequency count over all
time is not the right signal. Implements a windowed count over last 30 days. Adds
basic content filtering (blocklist of offensive terms).

**Mid-level Engineer (L4):** Separates the scoring pipeline into a separate job
that joins frequency data with CTR data from a separate click log. Implements
A/B testing framework to compare different scoring formulas. Adds monitoring to
catch when the pipeline fails and the prefix store goes stale.

**Senior Engineer (L5):** Designs the pipeline as a multi-stage DAG (directed
acyclic graph) with clear SLAs for each stage. Adds backfill capability (re-running
the pipeline for historical dates). Handles edge cases: what happens if a prefix
has no qualified suggestions (too much filtering)? What is the fallback? Implements
a "safe mode" that falls back to a conservative global list if the primary pipeline
fails.

**Staff Engineer (L6):** Designs the pipeline to be incremental — instead of
reprocessing all logs from scratch, only process the delta since the last run. This
reduces job runtime from 4 hours to 20 minutes. Introduces a separate "trending
boost" layer (covered in Part 4) that runs continuously on a stream rather than
waiting for the batch job. Thinks about the pipeline's total cost (compute hours,
storage, network egress) and proposes optimizations that reduce cost by 40% without
sacrificing quality. Designs the monitoring so that degradation in suggestion quality
is detected automatically, not by user complaints.

---

**Brainstorming Q&A — Part 3**

**Q: You said the offline pipeline runs hourly or daily. What happens during a
breaking news event? "Earthquake in Tokyo" might go from zero to 1 million searches
in 10 minutes. Would users not see it as a suggestion for hours?**

A: That is exactly the right concern, and it is why production autocomplete systems
have two layers: the batch layer and the real-time layer (Part 4). The batch layer
(what we just described) handles the stable, slow-moving suggestions — queries that
have been popular for days or weeks. The real-time layer runs continuously on a
stream of current queries and can detect a trend within minutes. When "earthquake in
tokyo" surges in the real-time layer, the real-time system injects it as a trending
suggestion for the relevant prefixes ("ear", "eart", "earth", "earthq", etc.) even
before the next batch job runs. The two layers are merged at serving time. This
two-layer design (Lambda Architecture style) is the correct answer for breaking-news
sensitivity.

**Q: How do you handle the step where you "emit a (prefix, query) pair for every
prefix of every query"? For a corpus of 5 billion queries averaging 6 characters
each, you are emitting 30 billion intermediate pairs. That is a massive shuffle.
How do you make that manageable?**

A: Several techniques. First, you do the emission and reduction in the same pass where
possible — Spark's `flatMap` + `reduceByKey` will combine pairs locally on each
executor before shuffling, so the full 30 billion pairs never all cross the network
at once. This is called the combiner optimization. Second, you limit prefix length
to 10-12 characters, which caps the fan-out per query. Third, you run the pipeline
on a cluster sized to handle the throughput — at Google, this is on the order of
thousands of machines. Fourth, you partition the input so that each task processes
a manageable chunk (say 100 million log entries per task). The shuffle is still
massive, but distributed systems are built for exactly this kind of work. A modern
Spark cluster can process 30 billion records in 1-2 hours with enough hardware.

**Q: How do you handle privacy in the offline pipeline? The query logs contain
user IDs — doesn't that mean you are building a system on top of private data?**

A: Privacy is a critical concern. Several protections are applied. First, the
query logs used for autocomplete aggregation are anonymized — user IDs are stripped
or hashed before the logs enter the pipeline. The pipeline only cares about aggregate
frequency across all users, not which user made which query. Second, queries that
appear only once (or fewer than a minimum threshold, e.g., five times) are excluded
from suggestions entirely. This prevents autocomplete from surfacing highly personal
queries that only one user made. Third, in many jurisdictions privacy law requires
that data used for autocomplete must respect opt-out choices. Users who opt out of
having their searches used to personalize features should have their queries excluded
from the input data. Implementing these protections correctly is an engineering
challenge that is often underestimated.

---

## Part 4: Real-Time Trending — The Stream Processing Layer

The batch pipeline is great for stable, slow-moving signals. But "trending" is a
real-time phenomenon. This part explains how you detect and surface trending queries
within minutes of them emerging.

### 4.1 The Architecture

```
ASCII DIAGRAM 4: Real-Time Trending Pipeline

  User makes a search query
          │
          ▼
  ┌──────────────────┐
  │  Search Service  │  ←── user gets search results
  └────────┬─────────┘
           │ publishes query event to
           ▼
  ┌──────────────────────────────────────────────────────────────────┐
  │                    Kafka Topic: "query_events"                   │
  │  msg: {user_id_hash, query, timestamp, country, language}        │
  └──────────────┬───────────────────────────────────────────────────┘
                 │
        partitioned by query string hash
                 │
                 ▼
  ┌──────────────────────────────────────────────────────────────────┐
  │             Stream Processor (Flink / Spark Streaming)           │
  │                                                                  │
  │  Sliding window: 5 minutes, evaluated every 30 seconds           │
  │                                                                  │
  │  For each prefix:                                                │
  │    count queries in current window                               │
  │    compare to historical baseline (from batch layer)             │
  │    if count > baseline * TRENDING_THRESHOLD:                     │
  │        mark as trending                                          │
  │                                                                  │
  │  TRENDING_THRESHOLD = 3x baseline (tunable)                      │
  └──────────────────────┬───────────────────────────────────────────┘
                         │
                         ▼
  ┌──────────────────────────────────────────────────────────────────┐
  │                  Trending Query Store (Redis)                    │
  │                                                                  │
  │  "trending:ear"  → ["earthquake tokyo", "early voting results"]  │
  │  "trending:elec" → ["election results", "election day"]          │
  │  TTL: 1 hour (trending queries auto-expire)                      │
  └──────────────────────┬───────────────────────────────────────────┘
                         │
                         ▼
                 Serving Layer (Part 5)
                 merges trending store with batch prefix store
```

### 4.2 The Sliding Window

The key mechanism in the real-time layer is the sliding window count. Instead of
counting all queries since the beginning of time, you count only queries in a
recent time window — say, the last 5 minutes. Every 30 seconds, you slide the
window forward.

A query that gets 1,000 searches in a 5-minute window when the historical baseline
for that query is 10 searches in 5 minutes has a 100x surge. That is a strong
trending signal.

**Why a sliding window instead of a tumbling window?**
A tumbling window resets every 5 minutes. A sliding window overlaps — it always
shows the last 5 minutes regardless of when you look. Sliding windows give smoother
trend detection because a sudden surge in minute 3 is visible for the full next 5
minutes, not just until the window resets.

**Implementation with Flink:**

Apache Flink has built-in sliding window support. You define the window size (5
minutes), the slide interval (30 seconds), and the aggregation function (count by
query string). Flink handles the state management — tracking which events are still
within the window and expiring old ones.

### 4.3 Injecting Trending Into the Prefix Store

The batch prefix store has pre-computed top-K lists per prefix. The trending store
has a separate list of currently-trending queries per prefix. At serving time, the
serving layer merges the two:

```
For prefix "earth":
  Batch store:    ["earth", "earthquake facts", "earth day", "earth science", ...]
  Trending store: ["earthquake in tokyo", "early voting today"]

Merged result (trending queries get a boost):
  ["earthquake in tokyo",    ← trending, boosted to top
   "early voting today",     ← trending
   "earth",
   "earthquake facts",
   "earth day",
   ...]
```

The merge is done at query time in the serving layer. It is fast because both lists
are small (top-K entries, not raw data) and the merge is just a priority queue
operation.

### 4.4 Trending Without Re-running the Full Batch Job

The key insight is that the real-time layer does NOT replace the batch layer. It only
handles the delta — the short-term trending signal. The batch layer handles the
long-term, stable frequency signal. The two layers have different update cycles and
different data, and they are merged at serving time.

This is called a Lambda Architecture (offline batch layer + real-time streaming
layer). Some systems use a Kappa Architecture instead (everything through streaming),
but for autocomplete the Lambda approach works well because the two signals genuinely
are different: you want "apple iphone" in suggestions because it has been popular for
years (batch signal), and you want "earthquake in tokyo" because it is popular right
now (streaming signal). These are different phenomena that warrant different treatment.

### 4.5 Intern → Staff Progression: Real-Time Trending

**Intern:** "Run a batch job every 10 minutes on recent logs to update trending."
This works but is expensive (re-running full Spark jobs every 10 minutes) and still
has 10-minute lag.

**Junior (L3):** Introduces Kafka to capture query events in real time. Writes a
consumer that aggregates counts in a Redis sorted set, using ZINCRBY to increment
query counts and ZRANGE to get top-K. Updates Redis every 30 seconds. This works but
does not handle window expiry (old counts accumulate forever).

**Mid-level (L4):** Implements proper sliding window using Redis with scored sets
where the score is the timestamp. Periodically removes entries outside the window.
Detects trending by comparing current count to a baseline loaded from the batch
layer. Adds a trending label UI element to differentiate trending from regular
suggestions.

**Senior (L5):** Moves from Redis-based sliding window to a proper stream processing
framework (Flink or Spark Streaming) for correctness guarantees (exactly-once
processing, proper watermarks for late-arriving events). Handles the thundering
herd problem: when a major event breaks, thousands of similar queries surge
simultaneously and the trending detector must not emit thousands of trending
suggestions simultaneously.

**Staff (L6):** Designs the trending system to be resilient to manipulation. Bad
actors can artificially boost a query's trending score by flooding with fake searches.
The L6 engineer adds bot detection at the Kafka consumer level: queries from IPs or
user agents exhibiting robot-like behavior are discounted. Also designs the system
to separate trending detection (is this query surging?) from trending promotion (should
this query appear as a suggestion?) — a query might trend but be offensive or
dangerous, and the promotion decision requires a policy check.

---

**Brainstorming Q&A — Part 4**

**Q: You mentioned that trending queries expire after 1 hour. What if a trend lasts
longer than 1 hour — like an all-day election? Won't the suggestion disappear?**

A: Good catch. The TTL of 1 hour on trending suggestions is not about when the query
stops being a valid suggestion — it is about when the real-time signal is retired.
Once a query has been trending continuously for more than 1-2 hours, it has accumulated
enough data to be incorporated into the batch layer on its next run (hourly pipelines
run frequently enough to pick this up). So a query like "election results 2024" that
trends all day will be picked up by the hourly batch job, boosted by recency, and
remain in the primary prefix store even without the trending label. The trending layer
is specifically for the window between "query just started surging" and "batch pipeline
has incorporated the surge." Once the batch layer has it, the real-time layer's job
is done.

**Q: How do you prevent trending manipulation? For example, a political actor
could flood the search system with a specific query to make it appear in trending
suggestions.**

A: This is a real and actively exploited attack vector. Twitter has dealt with
hashtag trending manipulation extensively. Several defenses apply. First, rate
limiting per IP and per user account — no single source can contribute more than N
queries per minute to the trending count. Second, device fingerprinting — bots tend
to have identical user agents, similar request timing patterns, and no associated
real session data; queries from likely bots are down-weighted. Third, velocity
detection — a legitimate trend grows organically from many diverse sources; a
manipulated trend spikes suddenly from a small number of sources. A trend originating
from > X% of its queries from the same IP range is flagged for human review before
promotion. Fourth, the trending threshold (requiring 3x baseline) filters out many
small-scale manipulation attempts. Fifth, for politically sensitive topics some
platforms have additional human review gates before surfacing a trending suggestion.
None of these are perfect; sophisticated manipulation at scale (e.g., a botnet of
millions of IPs) remains difficult to fully prevent.

**Q: What is the difference between a trending query in autocomplete and a trending
topic on Twitter? They seem like the same problem.**

A: They are related but different. Twitter's trending topics are a publicly visible
list — they are the output, shown directly to users as a feature in their own right.
Autocomplete trending is an internal signal that influences which queries appear
in a dropdown — it is a means to an end (better suggestions) not an end in itself.
Twitter trending topics involve additional ranking signals like the network effect
(who you follow is trending vs. global trends), geographic scoping (trending in New
York vs. globally), and curation by human editors in some markets. Autocomplete
trending is typically simpler: detect queries with surge rates above a threshold,
inject them into suggestions. The detection algorithms share a lot of DNA (sliding
window counts, deviation from baseline), but the downstream use of the signal is
quite different.

---

## Part 5: Serving Layer Architecture

You have the offline pipeline writing a prefix store, and the real-time layer writing
a trending store. Now a user types "appl" and needs a response in under 50ms. This
part describes the serving layer.

### 5.1 The Request Flow

```
ASCII DIAGRAM 5: Serving Layer Architecture

  User types "appl" in browser
          │
          │  HTTP GET /autocomplete?q=appl&uid=u123&lang=en
          ▼
  ┌──────────────────────────────────────────────────────────────────┐
  │                    Load Balancer / CDN                           │
  │  Client-side debounce: 50ms (mobile) to 0ms (desktop)           │
  │  TLS termination, rate limiting                                  │
  └──────────────────────┬───────────────────────────────────────────┘
                         │
                         ▼
  ┌──────────────────────────────────────────────────────────────────┐
  │                  Autocomplete Service Cluster                    │
  │                  (stateless application servers)                 │
  │                                                                  │
  │  1. Normalize prefix: lowercase, trim, unicode normalize         │
  │  2. Look up in prefix cache (Redis)  ←─── PRIMARY PATH          │
  │     Cache hit (>99% of requests):                                │
  │       - Retrieve batch top-K for prefix "appl"                   │
  │       - Retrieve trending queries for prefix "appl"              │
  │       - Merge and return                                         │
  │     Cache miss (<1% of requests):                                │
  │       - Forward to Trie Service (fallback)                       │
  │       - Populate cache with result                               │
  │  3. If personalization enabled: call Personalization Service     │
  │  4. Apply content filters (blocklist check)                      │
  │  5. Return top-K suggestions as JSON                             │
  └──────────────────────┬───────────────────────────────────────────┘
                         │ (async, if personalization enabled)
              ┌──────────┴──────────┐
              │                     │
              ▼                     ▼
  ┌────────────────────┐  ┌───────────────────────────┐
  │   Redis Cluster    │  │   Personalization Service  │
  │   (Prefix Cache)   │  │   (covered in Part 6)      │
  │                    │  └───────────────────────────┘
  │  Key: "appl"       │
  │  Value: {          │
  │   batch: [top-100],│
  │   ttl: 3600s       │
  │  }                 │
  └────────────────────┘

  Response time budget:
    Redis lookup:           ~1ms
    Trending merge:         ~0.5ms
    Personalization:        ~5-10ms (parallel call)
    Network + serialization:~5ms
    Total:                  ~7-12ms (well within 50ms budget)
```

### 5.2 Sharding the Prefix Cache

The prefix cache does not fit on one Redis node. You need to shard it. The sharding
key is the prefix string itself.

**Option A: Hash-based sharding**
hash("appl") mod N_shards → shard index. Simple and uniform, but a single prefix
always goes to the same shard, so if one prefix is astronomically popular (e.g., "a")
it can hot-spot a single shard.

**Option B: Range-based sharding**
Prefixes starting with a-f go to shard 1; g-m to shard 2; n-r to shard 3; s-z to
shard 4. This is more predictable and allows you to manually redistribute hot
shards, but the distribution is uneven (there are far more queries starting with
"s" than "x").

**Option C: Consistent hashing with virtual nodes**
Standard consistent hashing with virtual nodes distributes load more evenly and
makes rebalancing easier when adding or removing shard nodes.

**Production choice:** Most systems use consistent hashing. The hot prefix problem
(prefix "a" getting enormous traffic) is handled separately: the most popular
short prefixes are replicated across multiple nodes, and requests to them are
load-balanced round-robin.

### 5.3 Cache Hit Ratios and the Zipf Distribution

A key property of query autocomplete traffic is that it follows a Zipf distribution.
This means a small number of prefixes get an enormously disproportionate share of
traffic.

The prefix "g" (for Google, Gmail, Google Maps) is typed far more often than "q"
(for quora, quiz, queen). The prefix "go" gets 100x the traffic of "qi". The
top 1,000 prefixes by traffic might account for 80% of all autocomplete requests.

This is great news for caching. If 80% of traffic hits 1,000 prefixes, those 1,000
entries fit in a tiny amount of memory (a few megabytes) and can be cached in every
application server's local memory cache — not even requiring a Redis round-trip.
The L1 cache (local memory) handles the hottest prefixes with sub-millisecond
latency. The L2 cache (Redis) handles the rest of the long tail.

```
CACHE HIT ANALYSIS (Zipf distribution):

  Cache tier    Coverage        Capacity    Latency     Hit rate
  ──────────────────────────────────────────────────────────────
  L1 (in-proc)  Top 10K prefix  ~50 MB      ~0.1ms      ~70%
  L2 (Redis)    Top 1M prefix   ~5 GB        ~1ms       ~29%
  L3 (fallback) All prefixes    ~5 TB        ~20ms       ~1%
  ──────────────────────────────────────────────────────────────
  Overall: 99% of requests served from L1 or L2 at < 2ms
```

The L3 fallback is the trie service or a database query. It handles the long tail
of unusual prefixes that are never in the Redis cache because they get so little
traffic. Even at 100,000 QPS total, 1% is 1,000 requests per second to L3 — that
service needs to be designed for it.

### 5.4 Cache Invalidation

When the batch pipeline finishes a new run (say, every 4 hours), the prefix cache
needs to be updated. You cannot just delete all cache entries simultaneously — that
would cause a thundering herd where every request hits the L3 fallback while the
cache is empty.

**Strategy: write-through with staggered expiry**

The batch pipeline writes new prefix entries directly to Redis. Each entry has a TTL
that is the batch cycle time plus a random jitter of 0-20 minutes. This means
entries expire naturally at different times, spreading the cache miss load over a
20-minute window rather than all at once.

For the most popular prefixes (top 10K), the pipeline pushes updates proactively
without waiting for TTL expiry.

---

**Brainstorming Q&A — Part 5**

**Q: You said the L1 cache (in-process memory in the application server) holds the
top 10K prefixes. But application servers restart, get deployed, autoscale. When a
new server starts cold, it has an empty L1 cache. Does every new server cause a
thundering herd?**

A: This is called the "cold start" problem for application server caches. The
thundering herd is mitigated by the fact that new servers warm up gradually — they
serve traffic and populate their L1 cache over a few minutes. During warm-up, they
simply fall through to L2 (Redis), which has essentially all the answers. Since L2
adds only ~1ms of latency, users experience a brief period of slightly higher
latency (1ms vs 0.1ms) while the new server warms up — this is imperceptible. The
design goal for L1 is not "never miss" but "serve the 80% of hottest requests with
the fastest possible latency." A few minutes of warm-up is acceptable. For autoscaling
events where many new servers start simultaneously, you can pre-warm by having each
new server fetch the top-10K entries from Redis on startup before it begins serving
traffic. This takes ~10 seconds and the server starts warm.

**Q: With a Redis cluster serving 100,000 QPS at 1ms per request, what is the Redis
cluster size needed? Can you work through the math?**

A: Sure. 100,000 QPS × 1ms per request = 100 concurrent Redis operations at any
moment. Each Redis node can handle roughly 100,000-200,000 simple GET operations
per second. So theoretically a single Redis node could handle the load. However,
you never run at full capacity — you design for 2x-3x headroom. Also, the prefix
store has terabytes of data and Redis is an in-memory store, so you need enough
nodes to hold the working set. If you cache the top 1 million prefixes (covering
99% of traffic) and each entry is ~500 bytes (prefix + top-K list), that is 500 MB
of data — fits on a single Redis node. In practice you use a Redis Cluster of 6-12
nodes for redundancy (3 primaries with 3 replicas each) and shard the prefix space
across them. This gives you both capacity and high availability. Cost: 12 × a
32GB Redis node = manageable.

**Q: What happens if the entire Redis cluster goes down? Does autocomplete break?**

A: Autocomplete degrades gracefully, not catastrophically. The serving layer should
have a circuit breaker on the Redis calls. If Redis is unavailable, requests flow
through to the L3 trie service directly. The trie service has higher latency (20ms
vs 1ms) but handles the load — it was already handling 1% of traffic routinely.
If the trie service is also unavailable (very rare), the serving layer returns an
empty suggestion list, and the autocomplete dropdown simply does not appear. The
user can still type and search normally; they just do not get autocomplete assistance.
This is the correct degraded behavior: autocomplete is a enhancement, not a critical
path. Search itself continues to function.

---

## Part 6: Personalization — Making Suggestions Relevant to Each User

### 6.1 Why Personalization Matters

Two users type "apple". A software engineer who searches tech news daily should see:
- "Apple WWDC", "Apple silicon", "Apple developer news", "Apple vision pro"

A home cook who never searches tech should see:
- "Apple pie recipe", "Apple cider recipe", "Apple crumble", "Apple varieties"

Without personalization, both users see the same list ranked by global frequency.
The global top queries for "apple" are dominated by Apple Inc. content because that
is what the majority of users search. The home cook is poorly served.

### 6.2 The Two-Phase Approach

Personalization has to be fast. You cannot run a full personalization model on every
keystroke. The solution is a two-phase approach:

**Phase 1: Global retrieval (offline, fast)**
The prefix cache returns the top-100 global candidates for the prefix. These are
pre-computed by the batch pipeline and retrieved in ~1ms. 100 candidates is much more
than the 5-10 the user sees — this is a coarse candidate set that gives the
personalization layer room to re-rank.

**Phase 2: Personalized re-ranking (online, per-user)**
The personalization service takes the top-100 global candidates and re-ranks them
based on the user's profile. This step must complete in under 30ms (to stay within
the 50ms budget with room for network overhead).

```
PERSONALIZATION PIPELINE:

  Prefix "apple" → Redis lookup → top-100 global candidates
         │
         ├── ["Apple", "apple pie recipe", "apple stock",
         │    "apple cider", "apple tv", "apple watch",
         │    "Apple music", "applebee's", ... (100 total)]
         │
         ▼
  Personalization Service
         │
         ├── Load user profile for uid=u123:
         │     recent_queries: ["chicken marsala", "pasta carbonara"]
         │     category_affinity: {cooking: 0.9, tech: 0.1}
         │     location: "Seattle, WA"
         │
         ├── Re-rank 100 candidates:
         │     score(candidate) = global_score * (1 + category_match_boost)
         │     "apple pie recipe":  0.85 × (1 + 0.9) = 1.615  → rank #1
         │     "apple cider":       0.80 × (1 + 0.8) = 1.440  → rank #2
         │     "Apple":             0.95 × (1 + 0.1) = 1.045  → rank #4
         │     "apple stock":       0.78 × (1 + 0.0) = 0.780  → rank #8
         │
         ▼
  Return top-5 personalized suggestions:
    1. "apple pie recipe"
    2. "apple cider"
    3. "applebee's"         ← nearby applebee's (location signal)
    4. "Apple"
    5. "apple cider vinegar"
```

### 6.3 User Profile Storage

The user profile needs to be available in under 10ms for the personalization call.
It must be stored in a low-latency store — Redis again, or a dedicated user profile
service backed by Cassandra or DynamoDB.

The profile stores:
- **Recent queries:** last N searches (e.g., last 50 queries), with timestamps.
  These are used for "recent searches" suggestions and for deriving category affinity.
- **Category affinity vector:** a set of topic weights (cooking: 0.9, tech: 0.1,
  sports: 0.3, finance: 0.0, ...). Updated asynchronously from the search history.
- **Location:** current approximate location, derived from IP or explicitly provided.
  Used to boost local business suggestions.
- **Language and locale:** determines which language index to query.
- **Negative signals:** queries the user explicitly dismissed or marked as not relevant.

### 6.4 Showing Recent Searches

A common subtlety: when a user types "appl", they should also see their own recent
queries that match "appl" even if those queries are not globally popular. "apply for
mortgage refinance" is not a top-100 global suggestion, but if this user searched it
yesterday, it should appear.

Implementation: the personalization service checks the user's recent query list first
and injects any recent queries matching the prefix as top candidates (above the global
ranking). These are labeled "Recent" in the UI.

### 6.5 Cold Start Problem

A new user has no search history. Their personalization profile is empty. You fall
back to global ranking — the same experience as an unregistered user. This is fine.

As the user makes more searches, their profile builds up. Personalization kicks in
after roughly 5-10 queries (there is enough signal to detect category affinity).
The transition from global to personalized is gradual: initially personalization
has low weight, and as the profile grows, the personalization weight increases.

### 6.6 Privacy Considerations

Personalization creates privacy risks. The user's search history is sensitive data.
Key considerations:

**Server-side vs. client-side:** Some systems implement personalization entirely
client-side — the recent query history is stored in the browser's localStorage
and the re-ranking happens in JavaScript before sending the request to the server.
The server never sees the user's history. This is the most privacy-preserving
approach but limits the complexity of personalization you can do.

**Data retention limits:** The search history used for personalization should have
a retention limit (e.g., 90 days). Searches older than 90 days drop out of the
personalization profile.

**Opt-out:** Users must be able to opt out of personalization. When opted out, they
receive global suggestions only. Their queries should not be logged in a way that
updates their personalization profile.

**Legal compliance:** GDPR and CCPA have specific requirements about storing and
processing search history. Any implementation must comply with these regulations
in the relevant jurisdictions.

---

**Brainstorming Q&A — Part 6**

**Q: You said personalization must complete in under 30ms. The re-ranking involves
loading a user profile and computing scores for 100 candidates. Is that feasible
in 30ms?**

A: Yes, comfortably. Loading a user profile from Redis takes ~1ms. The profile is
small (~5 KB compressed). Re-ranking 100 candidates involves 100 multiplication
and addition operations to compute personalized scores, then a sort of 100 items.
On modern hardware that takes microseconds, not milliseconds. The bottleneck is not
the computation — it is the I/O (loading the profile and the candidates). If both
are in Redis and the personalization service is co-located in the same data center,
the total time is 2-5ms for the I/O operations plus negligible computation time.
Even with serialization and deserialization overhead, 30ms is a conservative budget.
The trickier constraint is throughput: at 100,000 QPS with personalization enabled,
the personalization service must handle 100,000 re-ranking operations per second.
Vertical scaling (beefy servers with lots of RAM for the user profile cache) and
horizontal scaling (many instances of the personalization service) handle this.

**Q: What about personalization for logged-out users? Anonymous users account for
30-50% of traffic on many consumer products. They have no user ID and no stored
history. What do you do?**

A: Several approaches. First, session-based recent searches: even without a logged-in
user ID, you can store the current session's recent queries in a cookie or
localStorage and use those for "recent searches" injection during the session. Second,
implicit signals: a logged-out user's request includes their IP address, browser user
agent, and sometimes a long-lived anonymous device ID stored in a cookie. You can
derive coarse signals from these: location from IP (to boost local suggestions),
approximate device type, language from browser headers. Third, contextual signals:
within a single session, if the user searched "nfl schedule" and then types "pat",
you can boost "patriots schedule" above "patent office" even without a persistent
profile. This is lightweight in-session context, not long-term personalization.
Fourth, for the majority of anonymous traffic, just use global ranking — it is not
a bad experience, just not a personalized one.

---

## Part 7: Fuzzy Matching and Typo Correction

Users make typos. "Googel" for "Google". "Amazone" for "Amazon". "Iphone 15 rewiev"
for "iPhone 15 review". A typeahead that only matches exact prefixes is frustrating.

### 7.1 Why Exact Prefix Matching Fails for Typos

If a user types "googel" (swapping the 'l' and 'e'), exact prefix matching returns
nothing — there is no query in the index that starts with "googel". The user sees
an empty dropdown and thinks the system is broken.

The solution is fuzzy matching: accept prefixes that are "close to" actual indexed
queries even if they do not match exactly.

### 7.2 Levenshtein Edit Distance — The Textbook Answer (Too Slow)

The Levenshtein distance between two strings is the minimum number of single-character
edits (insertions, deletions, or substitutions) required to transform one string into
the other.

- "googel" to "google": distance = 1 (swap 'el' to 'le' — actually a transposition,
  edit distance 2 with standard Levenshtein: substitute 'e'→'l' and 'l'→'e').
- "aple" to "apple": distance = 1 (insert 'p').
- "amazone" to "amazon": distance = 1 (delete 'e').

A small edit distance (1 or 2) means "close match" and is a good typo correction signal.

**Why it's too slow for autocomplete at scale:**

To find all queries within edit distance 2 of "googel", you would need to compute
the Levenshtein distance between "googel" and every string in your index. At 1 billion
indexed queries, that is 1 billion distance computations, each of which is O(m × n)
where m and n are the lengths of the two strings. Even at 1 billion simple operations
per second, this is impossibly slow for a sub-50ms response.

The edit distance approach works only when the candidate set is small — for example,
a dictionary of 300,000 words on a spell-checker. For autocomplete with billions of
queries, you need a smarter approach.

### 7.3 Trigram Index — The Production Approach

A trigram is a sequence of 3 consecutive characters in a string. The query "google"
broken into trigrams: "goo", "oog", "ogl", "gle".

A trigram index maps each trigram to all queries that contain it. To find queries
similar to the typo "googel", you compute its trigrams ("goo", "oog", "oge", "gel")
and look up each in the trigram index. Any query that appears in multiple of those
lists is a strong candidate for being what the user meant.

```
TRIGRAM SIMILARITY CALCULATION:

  Query "googel" trigrams: {"goo", "oog", "oge", "gel"}
  Query "google" trigrams: {"goo", "oog", "ogl", "gle"}

  Intersection: {"goo", "oog"}
  Union:        {"goo", "oog", "oge", "gel", "ogl", "gle"}

  Jaccard similarity = |intersection| / |union| = 2 / 6 = 0.33

  A similarity of 0.33 is reasonably high — "googel" and "google" are similar.
  A threshold of 0.2-0.3 is typical for accepting a candidate as a fuzzy match.
```

The trigram index lookup is fast: you hash each trigram and look up a precomputed
candidate list. The candidate set is typically small (a few thousand), and computing
similarity across a few thousand candidates is fast even on commodity hardware.

### 7.4 Phonetic Matching — Soundex and Metaphone

Another approach for typo correction is phonetic matching: group words that sound
alike together, and match by sound rather than spelling.

**Soundex** is an old (1918) algorithm that reduces a word to a letter followed by
three digits, based on the consonant sounds. "Smith" and "Smythe" both become S530.
"Robert" and "Rupert" both become R163. Words with the same Soundex code are
phonetically similar.

**Metaphone** and its successor **Double Metaphone** are more sophisticated phonetic
algorithms that handle more linguistic patterns. Double Metaphone returns two phonetic
codes per word to handle ambiguous pronunciations.

**When to use phonetic matching:**

Phonetic matching is useful when the user knows roughly how something sounds but not
how it is spelled. "Gwyneth Paltrow" vs. "Gwyneth Paltroe". "Tchaikovsky" has many
valid spellings. For a general-purpose autocomplete, phonetic matching is most useful
for name searches (entity autocomplete) rather than query autocomplete.

For product autocomplete (Amazon), phonetic matching helps users find brand names
they have heard but not seen spelled: "nuespee" → "Nespresso".

### 7.5 When to Apply Fuzzy Matching

Fuzzy matching is not free — it adds latency and can produce incorrect suggestions.
Apply it only when exact prefix matching produces insufficient results:

```
FUZZY MATCHING DECISION TREE:

  User types prefix P
          │
          ▼
  Exact prefix match in prefix cache
          │
  ┌───────┴────────┐
  │                │
  ≥ K results     < K results (or 0 results)
  │                │
  ▼                ▼
  Return           Apply fuzzy matching:
  exact            1. Compute trigrams of P
  results          2. Look up trigram index
                   3. Compute similarity scores
                   4. Merge with any exact results
                   5. Return merged top-K
```

Most requests (>95%) have sufficient exact matches. Fuzzy matching fires only for
the tail of unusual prefixes and likely-typo prefixes. This keeps the average latency
low while handling typos gracefully.

### 7.6 Intern → Staff Progression: Fuzzy Matching

**Intern:** "If exact match fails, try removing the last character and matching the
shorter prefix." This helps with partial completions but not transpositions or
substitutions.

**Junior (L3):** Implements Levenshtein distance on a small candidate set (e.g., only
the top-10K most popular queries). Handles common typos for popular queries but
misses long-tail typos.

**Mid-level (L4):** Builds a trigram index as a separate service. Implements the
"fuzzy on miss" decision tree. Adds A/B testing to measure whether fuzzy suggestions
actually get clicked (CTR) to validate that they are helping.

**Senior (L5):** Adds phonetic matching layer for name searches. Implements a
learning-to-rank model for re-ranking fuzzy candidates: not just similarity score
but "given this typo, which corrected query is most likely?" Uses historical
(typo → correction) data from user sessions where the user typed a typo and then
corrected it.

**Staff (L6):** Recognizes that the cleanest solution is not a separate fuzzy layer
but a unified embedding-based approach: map both the typed prefix and the indexed
queries into a shared embedding space, and return the nearest neighbors by embedding
distance. This handles typos, phonetic variants, and semantic near-misses in a
unified model. However, embedding lookup (approximate nearest neighbor search) adds
latency and complexity. The L6 engineer evaluates whether the improvement justifies
the cost for the specific product, and may decide to limit embedding-based fuzzy
matching to a specific slice (e.g., brand name searches on Amazon) where it clearly
wins.

---

**Brainstorming Q&A — Part 7**

**Q: You mentioned trigram similarity. For the prefix "googel" you calculated a
Jaccard similarity of 0.33 with "google". What threshold do you use to decide
"this is a typo correction" vs. "this is just a random suggestion"?**

A: In practice the threshold is tuned empirically, not derived theoretically. A
reasonable starting point is 0.3 Jaccard similarity for 3-character n-grams. But
the right threshold depends heavily on the use case. For a short-prefix autocomplete
(3-4 characters), similarity calculation on short trigram sets is noisy — "app" and
"ape" have Jaccard similarity 0.33 despite being very different words. For longer
prefixes (6+ characters), trigram similarity is more reliable. A practical approach:
use a higher threshold (0.5+) for short prefixes and a lower threshold (0.2+) for
long prefixes. Also threshold on the number of shared trigrams as a raw count, not
just as a fraction — two strings sharing 5 trigrams are likely similar; two strings
sharing 1 trigram out of 2 total have a high Jaccard score (0.5) but the raw evidence
is weak. Production systems often combine multiple signals: Jaccard similarity + raw
shared trigram count + final Levenshtein distance check on the small candidate set.

**Q: Is fuzzy matching more important for mobile users? Mobile keyboards have higher
typo rates due to autocorrect interference and smaller touch targets.**

A: Yes, and this actually changes the design. Mobile keyboards often have their own
autocorrect that modifies what gets sent to the server. If the phone corrects "googel"
to "google" before the request is sent, the server never sees the typo. But mobile
autocorrect sometimes over-corrects — changing a correctly-spelled uncommon word to
a more common misspelling. More importantly, voice input on mobile produces a
different error profile: homophones ("their" vs. "there") rather than letter
transpositions. A robust fuzzy matching system for a mobile-first product should
handle homophones, which trigrams do poorly at. Phonetic matching (Metaphone) handles
homophones better than trigrams. So mobile-heavy products benefit from a combined
phonetic + trigram approach.

---

## Part 8: Multi-Language Support

### 8.1 The Complexity of Languages

English autocomplete is straightforward. English uses the Latin alphabet, left-to-right
reading direction, and space-delimited words. Once you leave English, every assumption
breaks.

**Chinese and Japanese:** These languages do not use space-delimited words. A Chinese
sentence is a continuous string of characters with no spaces. Prefix matching works
differently — you must understand morphological boundaries. Also, users often type
in Pinyin (romanized Chinese) and see suggestions in Chinese characters. The prefix
"zhong" should suggest "中国" (China).

**Arabic and Hebrew:** Right-to-left scripts. The concept of a "prefix" is the
beginning of the string, but displayed at the right side of the screen. The autocomplete
dropdown UI needs to be mirrored.

**German:** Compound words are extremely common. "Donaudampfschifffahrtsgesellschaft"
(Danube steamboat company) is one word. Prefix matching on the full compound word
means users must type many characters before getting useful suggestions. Some German
autocomplete systems decompose compound words.

**Hindi and other Devanagari scripts:** Characters have combining forms — a base
consonant plus vowel modifier renders as a single glyph. Prefix matching must work
at the Unicode code point level, not the glyph level.

### 8.2 Unicode Normalization

Before any prefix matching, normalize the input. Unicode defines several normalization
forms. For autocomplete:

**NFC (Canonical Decomposition, Canonical Composition):** The most common form for
storage and comparison. An accented character like "é" can be represented as a single
code point (U+00E9) or as "e" followed by a combining acute accent (U+0065 U+0301).
NFC ensures both representations are stored and matched the same way.

**Case folding:** "Apple", "apple", "APPLE" should all match. Simple lowercasing does
not work for all languages. Turkish has a dotless 'ı' that lowercases differently
than 'i'. Unicode-aware case folding handles these edge cases.

**Accent stripping (for some use cases):** "café" might be stored both as "cafe" and
"café" in the index, so that users who type "cafe" without the accent still get the
suggestion.

### 8.3 Per-Language Indexes

The correct approach is to maintain a separate prefix index per language. When a
user's request comes in with a language parameter (derived from their browser's
Accept-Language header or their explicit settings), route the prefix lookup to the
appropriate language index.

```
MULTI-LANGUAGE ROUTING:

  Request: ?q=appl&lang=en  → English prefix index
  Request: ?q=appl&lang=de  → German prefix index
  Request: ?q=zhong&lang=zh → Chinese prefix index
           (returns Pinyin-to-character suggestions)
  Request: ?q=الس&lang=ar   → Arabic prefix index (RTL)
```

Each language index is built by the same offline pipeline, but seeded with query
logs filtered to that language.

**Mixed-language queries:** Users often type queries in their native language's
script but include English brand names ("iPhone"), numbers, or domain-specific terms.
The index for each language should include these common cross-language terms.

### 8.4 Language Detection

If the user's language setting is unknown, you need to detect it from the typed prefix.
Language detection from a 3-4 character prefix is hard because short prefixes are
ambiguous ("app" appears in English, German, French, and many other languages).

Practical approach: use the user's browser language settings as the primary signal,
fall back to IP-based geographic language inference, and only attempt character-based
language detection if both are missing. Character set detection is easier than
word-based detection: if the user types Arabic script, you know it is Arabic. If they
type Latin script, the ambiguity is higher.

---

**Brainstorming Q&A — Part 8**

**Q: You mentioned maintaining a separate prefix index per language. How many
languages does Google support, and what is the storage overhead of maintaining
separate indexes?**

A: Google Search supports over 150 languages. The storage overhead depends on the
size of the query corpus in each language. English and Chinese have very large corpora
(billions of queries each) and correspondingly large indexes. Many smaller languages
have small corpora and small indexes. The total storage is dominated by the top 5-10
languages by query volume. A rough estimate: English index is ~1 TB, Chinese is
~800 GB, other major languages (Spanish, Arabic, Hindi, French, German, Portuguese,
Japanese) are 100-400 GB each. Smaller languages might be 1-10 GB. The total across
150+ languages might be 5-10 TB — manageable with sharding. The operational overhead
is significant though: each language's pipeline must be maintained separately, with
language-specific normalization, filtering, and quality checks.

**Q: How do you handle queries that mix languages — for example, a user in India
typing "weather in दिल्ली" (mixing English and Hindi)?**

A: This is a real and common scenario called code-switching. Several approaches.
First, hybrid indexing: in the index for each language, include common cross-language
terms (English words, numbers, common brand names) so that "weather in" is understood
in the Hindi index and auto-completes to "weather in दिल्ली" (Delhi). Second, character
set split: detect the language from the character set of each word segment and route
the query to the appropriate index. A query with both Latin and Devanagari characters
routes to a hybrid index. Third, transliteration support: many users in India type
Hindi words in Latin script (Hinglish). "dilli" (phonetic spelling of Delhi in Hindi)
should suggest "दिल्ली". This requires a Hinglish-to-Hindi transliteration layer.
Indian language autocomplete is one of the most complex engineering challenges in the
space, and Google has dedicated teams working on it.

---

## Part 9: 45-Minute Interview Framework

### 9.1 The Danger Zone: Starting Too Narrow

The most common failure mode in a typeahead interview is starting with "let me draw
a trie" before asking a single question about requirements. This signals that you are
pattern-matching to a data structure you remember from a textbook rather than thinking
about the actual problem.

An interviewer at Google or Amazon sees 50+ candidates per year who open with "I'll
use a trie." They are looking for the candidate who opens with a question.

### 9.2 The 45-Minute Breakdown

```
TIME ALLOCATION FOR A TYPEAHEAD INTERVIEW:

  Minutes 0-5:   Requirements and Clarification
  Minutes 5-15:  High-Level Architecture
  Minutes 15-25: Deep Dive #1 (usually offline pipeline or data structure)
  Minutes 25-35: Deep Dive #2 (usually serving layer or real-time trending)
  Minutes 35-40: Scaling and Fault Tolerance
  Minutes 40-45: Open Discussion / Trade-offs / Questions
```

### 9.3 Minutes 0-5: Requirements and Clarification

Ask these questions in this order:

1. "Query autocomplete, entity autocomplete, or product autocomplete?"
2. "What is the target QPS and latency SLA?"
3. "Do we need personalization?"
4. "Do we need real-time trending, or is daily batch sufficient?"
5. "What languages?"
6. "What is K — how many suggestions per prefix?"

After getting answers, restate the requirements to confirm. "So I'm designing query
autocomplete at 100K QPS, 50ms P99 latency, with global ranking but no personalization
for now, English only, and we want trending queries to appear within 10 minutes. Did
I get that right?"

### 9.4 Minutes 5-15: High-Level Architecture

Draw the system in two halves, separated by a clear line:

```
INTERVIEW WHITEBOARD SKETCH:

  ╔══════════════════════════════════════════════════════════════╗
  ║                    OFFLINE (batch layer)                     ║
  ║  Query Logs → Spark Pipeline → Rank Top-K → Prefix Store    ║
  ║  [runs every 4 hours]                                        ║
  ╟──────────────────────────────────────────────────────────────╢
  ║                 REAL-TIME (streaming layer)                  ║
  ║  Query Events → Kafka → Flink → Trending Store              ║
  ║  [continuous, 5-min sliding window]                          ║
  ╟──────────────────────────────────────────────────────────────╢
  ║                    SERVING (online path)                     ║
  ║  Client → LB → App Server → Redis (prefix cache)            ║
  ║                          ↘ Trending Store                   ║
  ║  [< 50ms SLA]              → merge → return top-K           ║
  ╚══════════════════════════════════════════════════════════════╝
```

Explain why you separated the system into these three layers. This alone demonstrates
L5/L6 thinking.

### 9.5 Minutes 15-25: Deep Dive on Data Structures

Walk through the data structure decision:

"Most candidates draw a trie here. Let me explain why I would not use a trie as
the primary serving structure at this scale."

Explain: trie of 1 billion queries → hundreds of GB, hard to shard, live traversal
too slow.

"Instead I would use a pre-computed prefix hash table, stored in Redis. For every
prefix up to length 10, we pre-compute and store the top-K suggestions. Lookup is
O(1). Redis handles the throughput. Sharding is by prefix with consistent hashing."

Then proactively address the storage concern: "The storage is large — roughly 5 TB
for the full index across all prefixes. But this is distributed across a Redis Cluster.
The working set that fits in cache is much smaller — the top 1 million prefixes cover
99% of traffic and fit in a few GB."

If the interviewer asks "but what about memory on a single machine?" — that is your
cue to explain sharding. Draw the shard diagram.

### 9.6 Minutes 25-35: Deep Dive on the Serving Path or Pipeline

If you have not covered the serving path, do it now. Walk through the request flow:
client debounce → load balancer → app server → L1 in-process cache → L2 Redis →
L3 fallback (trie service). Draw the latency budget.

If the interviewer asks about the pipeline, walk through the Spark job step by step:
emit (prefix, query) pairs → count → rank → top-K per prefix → write to prefix store.

### 9.7 Minutes 35-40: Scaling and Fault Tolerance

Proactively address:

1. "What if the Redis cluster goes down?" → Circuit breaker, fall through to trie
   service, degraded mode (no suggestions) rather than error.
2. "What if the batch pipeline produces bad data?" → The pipeline has validation:
   min query frequency threshold, content filter pass, automated quality checks
   comparing each run's output to the previous run (anomaly detection on the
   suggestion distribution). If output looks wrong, the write to the prefix store
   is blocked and an alert fires.
3. "What if a hot prefix saturates a Redis shard?" → Replication: hot prefixes
   (top 1000 by traffic) are replicated across all shards and requests are
   load-balanced across replicas.

### 9.8 L5 vs. L6 Calibration

What distinguishes L6 answers from L5:

**L5 answer:** Correctly explains trie vs. prefix hash, designs a functioning offline
pipeline, knows that Redis is used for the prefix cache, mentions personalization as
a separate layer.

**L6 answer:** Everything at L5, plus:
- Proactively mentions the Zipf distribution and its implications for cache hit ratios
- Designs the real-time trending layer without being prompted
- Discusses the two-phase personalization (global retrieval then re-rank) and explains
  why you need 100 candidates not just 10
- Raises the thundering herd issue for cache warm-up and has a solution
- Discusses pipeline monitoring and the "bad data" protection
- Can calculate back-of-envelope numbers for storage, QPS, and latency at each tier
- Raises content filtering as a production concern (Amazon incident)
- Mentions privacy and GDPR implications of personalization without being asked

The L6 candidate does not wait for the interviewer to probe for depth. They
proactively raise the hard problems and walk through the solutions.

### 9.9 Numbers to Have Ready

Memorize these for the interview:

```
BACK-OF-ENVELOPE NUMBERS:

  QPS:              100,000 requests/second (target)
  Prefix length:    1-10 characters (practical limit)
  K suggestions:    5-10 (UI limit), 100 (internal candidate set)
  Corpus size:      1 billion unique queries (Google scale)
  Prefix entries:   ~10 billion (10 per query average)
  Prefix store size: ~5 TB (at 500 bytes/entry)
  Redis working set: ~5 GB (top 1M prefixes covering 99% of traffic)
  Batch job runtime: 1-4 hours (hourly cycle)
  Streaming lag:    1-5 minutes (trending detection window)
  Serving latency:  < 5ms (Redis lookup + merge)
  End-to-end P99:   < 50ms (with network)
  Cache hit ratio:  > 99% (Zipf distribution)
  L6 checkpoint:    2 separate pipeline layers + serving explained unprompted
```

---

**Brainstorming Q&A — Part 9**

**Q: You recommend spending minutes 5-15 on high-level architecture. But what if
the interviewer wants to go deep on data structures immediately? How do you handle
a pushy interviewer?**

A: Great interviewers follow your lead if your structure is correct. But if an
interviewer pushes you toward data structures before you have established the
requirements, do not resist — accommodate gracefully while planting a flag: "Happy
to go into data structures — I'll plan to come back to the overall architecture after
this. For the data structure, the key question is whether we are storing 10K queries
or 1 billion queries, so let me use 1 billion as our assumption since we said 100K
QPS at Google scale." Then dive in. You have signaled architectural awareness even
while answering the narrow question. When you finish the data structure discussion,
steer back: "Now let me sketch the full serving path, because the data structure
choice changes the serving architecture." Good interviewers will appreciate the
steering. The key failure mode is getting stuck in a 30-minute trie discussion
without ever drawing the offline pipeline or the serving layer — those are the
parts that demonstrate L6 thinking.

**Q: How long should you spend on the drawing? Some candidates draw beautiful
diagrams and run out of time to explain trade-offs.**

A: Keep drawings functional, not beautiful. A whiteboard diagram should communicate
structure (these boxes, these arrows, this flow) without spending time on alignment,
precise sizing, or calligraphy. Aim for 2-3 minutes per diagram. The most important
drawing in this interview is the two-layer split (offline vs. online) — spend 3
minutes on it. The trie vs. prefix hash diagram can be a table or bullet points,
not a literal tree. The serving path is 4-5 boxes connected by arrows — 2 minutes.
The real-time pipeline is a linear flow from Kafka through Flink to Redis — 2 minutes.
Total drawing time: 10-12 minutes. The remaining 30+ minutes is explanation, trade-off
discussion, and responding to questions. Candidates who spend 25 minutes drawing
a beautiful trie have used up their interview on the wrong thing.

**Q: What if the interviewer asks "how would you implement this in code?" Should
you write actual code?**

A: For a system design interview, pseudocode is always appropriate; production-quality
code is never expected. If asked to implement the prefix lookup, write pseudocode
at the level of: "function getSuggestions(prefix): fetch prefix cache from Redis,
if miss fetch from trie service, merge with trending, apply content filter, return
top K." For the offline pipeline, describe the Spark transformations in English or
rough pseudocode — you do not need to write syntactically correct PySpark. If the
interviewer is pushing for specific code (which is unusual in a system design
interview), clarify: "Do you want system design pseudocode, or are you looking for
an algorithmic implementation detail?" Often they just want to see that you know
how the pieces connect, not that you can write production Spark.

---

## Part 10: Real Incidents and Trade-offs

This section covers three real incidents that illuminate the hardest problems in
building autocomplete at scale.

### 10.1 Incident: Google Instant Shuts Down (2017)

**What was Google Instant?**

Google Instant, launched in September 2010, was the most ambitious version of
autocomplete ever shipped. Instead of just showing suggestions in a dropdown, Google
Instant showed full search results in real time as you typed — the entire results
page updated with every keystroke.

If you typed "g", you saw results for "Google." As you continued typing "go", the
page refreshed to show results for "Google." At "goo", still Google. At "goog",
still Google. At "googl", "google" is now clearly the predicted query and the results
page shows Google's results. The user never had to press Enter.

**The engineering challenge:**

Google Instant required not just fast autocomplete suggestions but full search result
pages delivered within 100ms of each keystroke. This was an extraordinary engineering
feat — the entire search stack (crawling, indexing, ranking, ad auction) had to
participate in serving a keystroke response in under 100ms. Google invested heavily
in infrastructure to make this work.

**Why it was shut down in 2017:**

Google announced the shutdown of Google Instant in July 2017. The official reason:
"the feature didn't work as well on mobile." The real reasons, widely discussed in
engineering circles:

1. Mobile usage surpassed desktop around 2016-2017. On mobile, there is no keyboard
   visible during typing — the keyboard takes up 40% of the screen. Showing live
   search results while typing on mobile is not useful; users cannot see them while
   they type.
2. The infrastructure cost was enormous. Serving full result pages at keystroke
   frequency is 5-7x the compute cost of serving a single result page at query
   submission. As Google's infrastructure costs grew and mobile usage made the feature
   less useful on the majority of traffic, the ROI turned negative.
3. Voice search grew. Voice search does not have keystrokes; it has utterances.
   Google Instant was inherently incompatible with voice.

**The lesson for system design:**

A feature that works brilliantly on one device paradigm (desktop typing) can become
technical debt as the device paradigm shifts. When designing autocomplete, think about
the device split. In 2024, 60-70% of Google searches happen on mobile. Any feature
that works only on desktop is serving a minority of traffic. The original Google
Instant served a majority use case; by 2017 it served a minority. The lesson: build
features whose costs scale with usage, and revisit the cost-benefit when the usage
patterns shift.

### 10.2 Incident: Amazon Autocomplete Shows Offensive Suggestions (2018 and ongoing)

**What happened:**

In 2018, journalists discovered that Amazon's autocomplete was completing partial
searches with racist, anti-Semitic, and otherwise deeply offensive suggestions. A
user typing "Jews" would see completions like "Jews control" or other conspiracy
theory phrasings. Users typing other sensitive terms encountered similarly offensive
completions.

This was not a malicious act by Amazon engineers. It was a consequence of how the
autocomplete system works: it surfaces what users actually search for, and enough
users search for offensive queries that these queries accumulate in the frequency
data and surface as suggestions.

**The root cause:**

The offline pipeline at that time had a content filter, but it was insufficient. The
filter operated primarily on exact-match blocklists: known offensive terms were
blocked. But the completions that appeared were not individual offensive words — they
were phrases that combined an acceptable word ("Jews") with an offensive completion.
Phrase-level blocking requires understanding the full suggestion, not just individual
terms.

**The fix:**

Amazon (and other companies that faced similar problems) had to substantially upgrade
their content filtering. The improved approach:

1. **Expand the blocklist to phrases:** Block not just individual terms but known
   offensive phrase patterns. This requires ongoing curation as new offensive patterns
   emerge.
2. **Model-based filtering:** Train a classifier that scores suggestion candidates for
   offensiveness on a spectrum, not just binary. Suggestions above a threshold are
   blocked. The classifier handles novel phrasings that exact-match blocklists miss.
3. **Sensitive prefix detection:** Identify prefixes that are related to protected
   characteristics (race, religion, gender, sexual orientation, disability). For these
   prefixes, apply more conservative filtering — show only suggestions that are clearly
   informational or positive, not suggestions that could be offensive.
4. **Human review for edge cases:** Maintain a team that reviews borderline cases
   flagged by the classifier and updates the blocklist and classifier training data.

**The system design lesson:**

Content filtering is not an afterthought — it belongs in the offline pipeline as a
mandatory step before any suggestion is written to the prefix store. The filter must
operate at the phrase level, not just the word level. And it must be continuously
updated as new offensive patterns emerge. An autocomplete system that launches without
robust content filtering is one news article away from a reputation crisis.

In the interview, mention content filtering proactively. Candidates who only describe
the happy path (fast suggestions for normal queries) and omit content filtering signal
that they are building in a vacuum, disconnected from the real-world consequences
of what gets surfaced.

### 10.3 Incident: Twitter Trending Topic Hijacking

**What happened (multiple incidents, 2016-2022):**

Twitter's trending topics feature has been repeatedly manipulated by coordinated
campaigns. In various incidents, political actors, governments (particularly state-level
actors in elections), and troll communities coordinated mass-tweeting of specific
hashtags to artificially push them into trending topics. Once a hashtag is trending,
it gains visibility to all Twitter users, amplifying the message far beyond the organic
audience.

Notable examples: coordinated campaigns around elections in multiple countries,
manufactured trending topics to make fringe movements appear mainstream, and
commercially motivated trending manipulation by brands.

**How Twitter's autocomplete is related:**

Autocomplete for hashtags on Twitter is directly tied to trending detection. A hashtag
that starts trending will appear as a suggestion when users type "#". If the trending
detection is fooled, the autocomplete is fooled, and users are served manipulated
suggestions.

**The defenses (and their limits):**

Twitter implemented multiple defenses over the years:

1. **Geographic scoping:** Trending topics are shown per country or region. A hashtag
   must trend in a geographically distributed way to be considered globally trending.
   This made it harder (but not impossible) to run coordinated campaigns from a single
   country.
2. **Account quality scoring:** New accounts, accounts without profile photos, accounts
   that have never tweeted organically — all get lower weight in trending calculations.
   Genuine users contribute more to the trending count than likely bots.
3. **Velocity anomaly detection:** A legitimate trend grows from many diverse accounts.
   A manipulated trend spikes suddenly from accounts with similar creation dates,
   similar follower counts, or similar posting patterns. Anomaly detectors flag these
   patterns.
4. **Human review:** For high-profile events (elections, major news), trending topics
   go through human editorial review before appearing in certain markets.

**The lesson for system design:**

Any autocomplete system that surfaces aggregate behavior (what many users are doing)
can be manipulated by coordinated action. Defenses must be layered: algorithmic
detection, account quality signals, velocity anomaly detection, and human review for
high-stakes scenarios. No single defense is sufficient. And the defenses are in an
arms race with attackers who continually evolve their methods.

In a system design interview, mention the manipulation risk and at least one defense
when you discuss the real-time trending layer. This demonstrates awareness of how
autocomplete systems interact with the real world.

### 10.4 Trade-off Matrix

Every autocomplete design decision involves trade-offs. Here are the key ones:

```
TRADE-OFF ANALYSIS:

  Decision                Choice A            Choice B
  ─────────────────────────────────────────────────────────────────
  Primary data struct     Trie                Prefix Hash Table
  Cost of A               Low memory (sparse) Pre-computes all prefixes
  Cost of B               Hard to shard at    High storage, but O(1)
                          scale               lookup and easy sharding
  Choose B for: large-scale production. Choose A for: small scale.
  ─────────────────────────────────────────────────────────────────
  Pipeline freshness      Batch (4 hours)     Streaming (5 minutes)
  Cost of A               Simple, cheap       Cannot capture trends
  Cost of B               Complex Flink job   Handles trending queries
  Choose: Both (Lambda architecture). Batch for stable signals,
          streaming for trending.
  ─────────────────────────────────────────────────────────────────
  Personalization         Global only         Per-user re-ranking
  Cost of A               Simple, fast        Lower suggestion quality
  Cost of B               User profile store, Better CTR for returning
                          extra latency       users
  Choose B for: products with high returning user rate and privacy
  flexibility. Choose A for: anonymous-heavy or privacy-first products.
  ─────────────────────────────────────────────────────────────────
  Fuzzy matching          None                Trigram index
  Cost of A               Fails on typos      Zero extra latency
  Cost of B               Extra index, extra  Handles ~95% of typos
                          latency (~5ms)
  Choose B for: products where query quality matters. Choose A for:
  prototypes or exact-vocabulary entity search.
  ─────────────────────────────────────────────────────────────────
  Update frequency        Daily batch         Hourly batch
  Cost of A               Simple scheduling   Trending 24h stale
  Cost of B               6x pipeline runs    2-4h staleness (better)
  Choose B when streaming is not available.
  ─────────────────────────────────────────────────────────────────
```

---

**Brainstorming Q&A — Part 10**

**Q: The Amazon incident happened despite Amazon having a content filter. How does
a company know when its content filter is failing before a journalist writes about it?**

A: This is a monitoring problem, and it is hard. A content filter that misses specific
patterns will not trigger any obvious error — the system is working correctly by its
own definition (it is returning suggestions that pass the filter). The failures are
"unknown unknowns." Proactive approaches: First, regular red-team exercises —
dedicated teams whose job is to try to surface offensive suggestions using creative
query combinations, similar to penetration testing for security. Second, automated
probes — a set of sensitive prefix tests that run daily and compare the current
suggestions against expected safe outputs. If "Jews" suddenly returns "Jews control"
as a suggestion, an automated test catches it before a journalist does. Third, user
feedback mechanisms — a report button on autocomplete suggestions that feeds into a
rapid review queue. Fourth, monitoring CTR on flagged suggestion categories — if
suggestions in the hate-speech risk category are getting anomalously high click rates,
something has gone wrong with the filter. None of these are perfect, but layering them
substantially reduces the window of a failure going undetected.

**Q: You described the Amazon incident and the Twitter manipulation as failures. But
are these solvable problems? Is it possible to build an autocomplete system that never
surfaces offensive content?**

A: Not with certainty, no. Language is adversarial — new slurs and coded language
emerge constantly. What was considered neutral yesterday can become a hate symbol
overnight through community adoption. A filter built on historical data will always
lag behind emerging harmful language. Additionally, context matters enormously: the
phrase "white power" is offensive as a political statement but neutral in the context
"how to clean white power-washed siding." A keyword filter cannot distinguish context.
Model-based classifiers are better at context but not perfect and are expensive to
run on every suggestion in real time.

The practical answer is: build the best filter you can, monitor aggressively for
failures, maintain a rapid-response process to add blocklist entries when failures are
discovered, and accept that some offensive content will occasionally surface before
being caught. This is not an excuse to build a poor filter — the quality of the filter
determines how often and how severely failures occur. But complete prevention is not
achievable with current technology. Companies that claim otherwise are either deceiving
themselves or operating at a scale where the long tail of edge cases has not yet found
them.

---

## Part 11: Query Understanding — Beyond Prefix Matching

### 11.1 The Limitation of Pure Prefix Matching

Exact prefix matching breaks in one common case: the user types a short abbreviation
that maps to a much longer canonical query. Example:

- User types "nflx" → should suggest "netflix"
- User types "yt" → should suggest "youtube"
- User types "amzn" → should suggest "amazon"
- User types "fb" → should suggest "facebook"

These are not prefix matches — "nflx" does not start with the letters n-e-t-f-l-i-x.
Pure prefix matching returns nothing. Yet these are extremely common search patterns
from power users who have learned abbreviations.

A related case: multi-word reordering.
- User types "pizza delivery" → should also suggest "delivery pizza near me"
- User types "python tutorial" → should also suggest "learn python for beginners"

### 11.2 Alias Mapping (Simple Fix)

The simplest approach: maintain an alias table.

```sql
CREATE TABLE query_aliases (
  alias       VARCHAR(50) NOT NULL PRIMARY KEY,
  canonical   VARCHAR(200) NOT NULL,
  priority    INT NOT NULL DEFAULT 100
);

INSERT INTO query_aliases VALUES ('nflx', 'netflix', 200);
INSERT INTO query_aliases VALUES ('yt', 'youtube', 200);
INSERT INTO query_aliases VALUES ('amzn', 'amazon', 200);
INSERT INTO query_aliases VALUES ('fb', 'facebook', 200);
INSERT INTO query_aliases VALUES ('goog', 'google', 200);
```

The serving layer checks the alias table before the prefix store:
```
function getSuggestions(prefix):
  // Step 1: check alias
  canonical = aliasTable.get(prefix)  // O(1) hash lookup
  if canonical:
    return prefixStore.get(canonical[0:prefix.length]) + [canonical]
  
  // Step 2: normal prefix lookup
  return prefixStore.get(prefix)
```

At L6: the alias table is maintained by a combination of human curation (for major
brand abbreviations) and automated mining (find short strings with high CTR on specific
canonical queries in the click log).

### 11.3 N-gram Overlap for Abbreviation Detection

For a more general approach without manual curation, n-gram overlap detects when a
short query is likely an abbreviation of a longer one:

- "nflx" vs "netflix": 2-gram overlap = {ne, et, tf, fl, li, ix} ∩ {nf, fl, lx} = {fl}
  Low overlap. But the consonant skeleton of "netflix" = "n-t-f-l-x" matches "nflx" exactly.

**Consonant skeleton matching**: strip vowels from the query and from candidate suggestions.
"netflix" → "ntflx". "nflx" → "nflx". Edit distance between "ntflx" and "nflx" = 1.
Close enough to be an alias.

This works best for brand names and product names, not for common words.

### 11.4 Semantic Autocomplete (L6+ Depth)

The most powerful approach: a query embedding model that maps short queries to a
semantic vector space. Semantically similar queries (like an abbreviation and its
full form) cluster near each other in the embedding space.

Offline: embed all popular queries. Build a nearest-neighbor index (FAISS or ScaNN).
Serving: embed the current prefix, find nearest neighbors in the query embedding space,
merge with prefix-match results.

This is deep L6 territory — worth mentioning as a future direction rather than designing
in detail at L5/L6 interviews. The right phrase: "Semantic autocomplete using query
embeddings is a natural extension — it handles abbreviations, synonyms, and cross-language
queries. The trade-off is serving latency (embedding + ANN search) vs. accuracy."

---

## Part 12: Monitoring and Observability

### 12.1 What to Measure

A healthy autocomplete service should have dashboards for:

```
AUTOCOMPLETE MONITORING
========================

  LATENCY:
  ┌─────────────────────────────────────────────────────┐
  │  Server p50 / p95 / p99 (target: p99 < 50ms)       │
  │  Redis lookup p99 (target: < 5ms)                   │
  │  Offline pipeline completion time (daily)           │
  │  Trending update lag (Kafka → Redis, target: <5min) │
  └─────────────────────────────────────────────────────┘

  QUALITY:
  ┌─────────────────────────────────────────────────────┐
  │  Click-through rate (CTR): % of suggestions clicked │
  │    Good baseline: 30-50% of searches accept a       │
  │    suggestion. Drop below 20% → staleness or        │
  │    relevance degradation.                           │
  │  Zero-results rate: % of prefixes with no suggestions│
  │    Should be < 3%. High rate → pipeline failure or  │
  │    unusual query patterns.                          │
  │  Ranking accuracy: % of top-1 suggestions that match│
  │    the query the user actually completed            │
  └─────────────────────────────────────────────────────┘

  SAFETY:
  ┌─────────────────────────────────────────────────────┐
  │  Harmful suggestion rate (from user reports)        │
  │  Blocklist update lag (time to remove after report) │
  │  Trending query review queue depth                  │
  └─────────────────────────────────────────────────────┘

  INFRASTRUCTURE:
  ┌─────────────────────────────────────────────────────┐
  │  Redis memory utilization (alert at > 80%)          │
  │  Batch pipeline success/failure (daily alert)       │
  │  Kafka consumer lag for trending pipeline           │
  └─────────────────────────────────────────────────────┘
```

### 12.2 Canary Deploys for Ranking Changes

Ranking changes (new scoring model, new CTR weights) are risky — a bad ranking
degrades CTR for every search. The standard practice: canary rollout.

Route 1% of traffic to the new ranking model. Compare CTR between control (99%)
and canary (1%) over 24-48 hours. If canary CTR >= control CTR - 2%, full rollout.
If canary CTR drops 5%+, automatic rollback.

The key metric is CTR, not latency (ranking changes rarely affect latency). CTR is
measured per-prefix and aggregated — a ranking change might help some prefixes and
hurt others, so per-prefix CTR reveals regressions the aggregate hides.

### 12.3 SLO Definition

A reasonable SLO for autocomplete at L6:

| SLO | Target | Measurement |
|-----|--------|-------------|
| Availability | 99.9% | % of requests returning 200 (empty array is 200, not an error) |
| Latency p99 | < 50ms server-side | Measured at the load balancer |
| Freshness | < 26 hours | Time since last successful batch pipeline run |
| CTR | > 30% | Weekly average |
| Safety | < 1 harmful suggestion per 10M requests | User reports / automated scanning |

Note: 99.9% availability means 8.7 hours/year of downtime. For autocomplete (non-critical
feature), this is acceptable. The key is that degraded mode (empty suggestions) is not
counted as downtime — users can still search without suggestions.

---

## Part 13: Pre-Interview Drill

### 13.1 What L6 Knows That L5 Doesn't

An L5 candidate designs a correct autocomplete system. An L6 candidate designs the same
system AND demonstrates command over the hard trade-offs, real failure modes, and the
production concerns that only emerge at scale.

The four L6 differentiators:

**1. Content safety is not optional.**
L5: "I'd filter offensive queries." L6: "Content filtering happens at three layers:
offline (blocklist applied during batch build), real-time (trending queries vetted before
injection), and reactive (user report → blocklist update → cache invalidation). The
reactive path must complete in < 30 minutes per the policy SLA. Missing any layer
creates a gap that bad actors exploit."

**2. The Zipf distribution drives your caching strategy.**
L5: "Use a cache." L6: "The top 10,000 prefixes (0.1% of all keys) account for 70%+ of
traffic (Zipf). An in-process LRU of 10K entries covering 5 MB fits in L1-adjacent
memory. This eliminates Redis round-trips for 70% of requests. For the long tail (rare
prefixes), Redis adds 5-10ms. The blended p99 stays well under budget."

**3. Trending is a separate pipeline, not faster batch.**
L5: "Run batch more often." L6: "Batch every hour is 24× the cost for marginal gain.
The right architecture separates concerns: stable base (daily batch, frequency+recency
ranked) + volatile overlay (Flink sliding window, velocity-based, updated every 5 min).
Each component is independently testable and replaceable. Trending queries need velocity
detection, not frequency counting — they're popular because they just became popular,
not because they've always been popular."

**4. Personalization is a re-ranking problem, not a separate index.**
L5: "Build a separate personalized index per user." L6: "Per-user indexes are impossible
at scale (100M users × prefix keys). The correct approach: two-phase. Global ranking
produces top-100 candidates for the prefix. Per-user re-ranking scores those 100
candidates using the user's click history, recency, and behavior signals. The re-ranking
is O(100) scoring operations, not O(all queries matching prefix)."

### 13.2 The Three Diagrams to Draw Cold

**Diagram 1: The two-pipeline architecture**
```
  OFFLINE (daily):
  Query logs → Spark (frequency + CTR + recency) → Prefix hash → Redis

  ONLINE TRENDING (every 5 min):
  Kafka events → Flink (velocity window) → Trending store → Redis

  SERVING:
  Client (debounce) → API server (L1 LRU cache) → Redis (L2) → Merge trending + base → Response
```

**Diagram 2: Two-phase personalization**
```
  Prefix "py" →
  Global lookup → top-100 candidates: [python, python tutorial, pygame, ...]
                ↓
  Per-user re-ranking: user clicked "python 3.12" yesterday
                ↓
  Re-ranked top-5: [python 3.12, python tutorial, python for beginners, ...]
```

**Diagram 3: Fuzzy matching path (triggered on cache miss)**
```
  User types "pytohn" (typo) →
  Prefix lookup "pytohn" → MISS (no such prefix in store)
                ↓
  Trigram index: {pyt, yto, toh, ohn} → find queries sharing 2+ trigrams
                ↓
  Candidates: [python, python 3, python tutorial, ...]
  Edit distance filter: distance("pytohn", "python") = 2 ← acceptable
                ↓
  Return: [python, python 3, ...]
```

### 13.3 Self-Check — L6 Autocomplete

- [ ] Can you explain prefix hash vs. trie trade-off without notes?
- [ ] Can you walk through the full offline pipeline from raw logs to Redis?
- [ ] Do you know what a Count-Min Sketch is and why trending uses it?
- [ ] Can you design the two-phase personalization without per-user indexes?
- [ ] Do you know the Zipf distribution implication for cache sizing?
- [ ] Can you describe trigram-based fuzzy matching and when it fires?
- [ ] Do you know the three real incidents (Google Instant, Amazon, Twitter)?
- [ ] Can you state the serving path latency budget at each tier?
- [ ] Can you explain why content filtering must happen at three layers?
- [ ] Can you describe what metric catches ranking regressions? (CTR, not latency)

---

## Common Interview Mistakes

These are the six mistakes that consistently separate candidates who fail a typeahead
interview from those who pass:

**Mistake 1: Drawing a naive trie for 1 billion queries without questioning scale.**
The trie is the correct answer for a textbook problem about 1,000 words. It is the
wrong answer for 1 billion queries. A candidate who draws a full trie tree and begins
implementing it without asking "how many queries are in our system?" has signaled that
they are solving a homework problem, not a production system. The moment you hear
"autocomplete at Google scale" or "100K QPS", the trie should be mentioned and
immediately set aside in favor of a pre-computed prefix cache.

**Mistake 2: Not separating the offline pipeline from the serving path.**
Many candidates design a system that computes suggestions live from query logs on
every request. This is conceptually clean but physically impossible at scale — query
logs are petabytes of data, and a live join against them for every keystroke at
100K QPS would require an impossibly large compute cluster. The offline/online
separation is the fundamental architectural decision in typeahead design. Candidates
who skip it are missing the core insight of the problem.

**Mistake 3: Forgetting the real-time trending layer.**
A system that only has a batch pipeline produces suggestions from yesterday's data.
For many use cases (Google during breaking news, Twitter during an event), this is
unacceptable. Even if the interviewer has not asked about real-time trending, proactively
raise it: "One thing I want to flag: with a batch-only pipeline, trending queries
from the last few hours won't appear in suggestions. If that's a requirement, we need
a streaming layer on top." This signal of proactivity is an L6 differentiator.

**Mistake 4: Omitting content filtering.**
Autocomplete suggestions are what the system recommends to users. They carry an implicit
endorsement. A system that surfaces offensive, harmful, or legally problematic suggestions
is a liability — not just a PR problem but potentially a legal one (in some jurisdictions,
auto-completing to defamatory suggestions has resulted in lawsuits). Content filtering
belongs in the offline pipeline as a mandatory step, and it deserves explicit mention
in any complete system design.

**Mistake 5: Ignoring the latency budget.**
Candidates sometimes draw a system with multiple synchronous service calls — prefix
cache → personalization service → fuzzy match service → content filter — all chained
sequentially. Each call adds latency. If each service takes 10ms and you have four
sequential calls, you are already at 40ms before network overhead, and you have blown
the 50ms budget. The serving layer must be designed with the latency budget in mind:
parallelize what can be parallelized (prefix cache lookup and personalization call can
happen simultaneously), use in-process caches for hot data, and keep the critical path
as short as possible.

**Mistake 6: Not discussing trade-offs — presenting a design as "the answer."**
Experienced engineers know there is no single right answer. There are answers that
are better or worse given specific constraints. A candidate who presents a design
without discussing why they made each choice, what the alternatives were, and what
the costs of this choice are — is signaling junior thinking. For every major component
(trie vs. prefix hash, batch vs. streaming, global vs. personalized), explicitly
state the trade-off: "I'm using a prefix hash instead of a trie because the prefix
hash gives O(1) lookup at the cost of high storage. For our scale this trade-off is
worth it because Redis Cluster can handle the storage and O(1) lookup is critical for
the latency SLA." That sentence pattern — "I chose X over Y because Z given our
constraints" — is what interviewers want to hear.

---

## Exercises

1. **Prefix count calculation.** You have a query corpus of 500 million unique query
   strings. The average query length is 7 characters. You store all prefixes up to
   length 8 (discarding characters beyond position 8). How many total prefix entries
   are in your prefix hash table? Estimate the storage in gigabytes assuming each
   entry is 300 bytes (prefix key + top-10 suggestion list). Show your work.

2. **Cache sizing.** Your prefix autocomplete serves 50,000 QPS. Measured traffic
   follows a Zipf distribution where the top 5,000 prefixes account for 75% of
   requests and the top 50,000 prefixes account for 90% of requests. Each prefix entry
   in Redis is 500 bytes. What is the minimum Redis cache size (in GB) needed to
   achieve a 90% cache hit rate? What about 75%?

3. **Sliding window implementation.** Design a data structure that supports:
   - `record(query, timestamp)`: record that a query was made at a given time
   - `getCount(query, window_seconds)`: return the count of the query in the last
     window_seconds seconds
   This must handle 100,000 records per second with O(1) average time per operation.
   Hint: consider a ring buffer or Redis ZSET with timestamp as score.

4. **Content filter design.** You are building the content filtering step for the
   offline pipeline. Your input is a list of (prefix, candidate_query) pairs. You
   must filter out offensive completions. Design an approach that:
   - Has high recall (misses very few offensive suggestions)
   - Has acceptable precision (does not over-block legitimate suggestions)
   - Can run efficiently within the Spark pipeline on 1 billion candidate pairs
   What data structures, algorithms, or ML models would you use? What are the
   limitations of your approach?

5. **Two-phase personalization latency.** The global retrieval (phase 1) takes 1ms.
   The personalization re-ranking (phase 2) takes Xms and can run in parallel with
   the global retrieval. Your total latency budget for suggestions is 20ms. If the
   user profile load takes 3ms and the re-ranking computation takes 0.5ms per candidate
   with 100 candidates, does the personalization fit in the budget? Show the latency
   breakdown.

6. **Trie to prefix hash conversion.** You have a trie containing the top 10 million
   queries for English. You want to convert it to a prefix hash table. Write the
   algorithm (pseudocode) to enumerate all prefix-to-top-K mappings from the trie.
   What is the time complexity? What is the space complexity? How would you parallelize
   this conversion using MapReduce?

7. **Multi-language routing.** A user's request includes Accept-Language: zh-CN, en; q=0.8.
   The user types the prefix "中" (a Chinese character). Design the routing logic that
   determines which language index to query, handles fallback if the Chinese index is
   unavailable, and explains how to merge results from multiple language indexes.

8. **Real-time trending threshold.** Your batch pipeline says the query "super bowl"
   gets an average of 50,000 searches per 5-minute window on a typical Sunday.
   During Super Bowl weekend, it gets 2,000,000 searches in a 5-minute window. Your
   trending threshold is "3x the historical baseline." Would "super bowl" be flagged
   as trending? (Yes — 40x baseline.) Now design a dynamic baseline that accounts for
   expected spikes around known events (holidays, sporting events, product launches).
   How would you build and maintain this dynamic baseline?

---

## Homework

1. **Read Google's paper on speller and autocomplete:** Search for "Google's spelling
   correction" and "Google's query suggestions" papers. The query suggestions literature
   discusses the exact ranking signals (frequency, recency, CTR) used in production.
   Note which signals they found most impactful and why.

2. **Build a toy prefix hash table:** Using Python or any language, build a prefix
   hash table for a small corpus (use a list of 10,000 Wikipedia article titles).
   Measure: (a) time to build the table, (b) time per lookup, (c) total memory used.
   Compare to a trie implementation for the same corpus.

3. **Analyze real autocomplete behavior:** Open Google, Amazon, and Twitter on a
   desktop browser. Use browser developer tools to observe the autocomplete requests.
   For each product: what is the URL pattern? What parameters are sent? What is the
   typical response latency? What is the response format (JSON structure)? What is the
   K value (how many suggestions)? Write a brief comparison of the three systems.

4. **Design the content filter:** Take the Amazon offensive autocomplete incident
   as a case study. Design a content filtering system that would have caught the
   specific patterns that appeared. What blocklist entries would you add? What
   classifier features would you use? How would you test your filter's recall and
   precision?

5. **System design practice:** Treat the following as a 45-minute mock interview.
   Do not look at your notes. Draw the full system from scratch on paper:
   "Design autocomplete for a food delivery app. Users type restaurant names and food
   types. 10K QPS, 100ms latency budget, needs to reflect new restaurant openings
   within 1 hour, personalized by past order history." After drawing, compare your
   design to this chapter. What did you miss? What did you do differently and why?

---

## Key Takeaways

```
╔══════════════════════════════════════════════════════════════════════════╗
║                         KEY TAKEAWAYS                                   ║
╠══════════════════════════════════════════════════════════════════════════╣
║                                                                          ║
║  1. THE FUNDAMENTAL SPLIT                                                ║
║     Every production autocomplete system is TWO systems:                 ║
║     (a) An offline pipeline that pre-computes answers                    ║
║     (b) An online serving layer that looks up pre-computed answers       ║
║     Drawing a system that computes suggestions live is wrong.            ║
║                                                                          ║
║  2. TRIE VS. PREFIX HASH                                                 ║
║     - Trie: textbook, correct for small scale, fails at 1B+ queries     ║
║     - Prefix hash: pre-compute top-K per prefix, O(1) lookup,           ║
║       easy to shard — this is the production answer                      ║
║     - Compressed trie: middle ground, reduces memory, still complex      ║
║                                                                          ║
║  3. THE OFFLINE PIPELINE                                                 ║
║     Query logs → MapReduce/Spark → frequency + recency + CTR →          ║
║     top-K per prefix → content filter → write to prefix store            ║
║     Content filtering is mandatory, not optional.                        ║
║                                                                          ║
║  4. REAL-TIME TRENDING                                                   ║
║     Kafka stream → Flink sliding window → trending store in Redis        ║
║     Merged at serving time with batch results.                           ║
║     Trending requires manipulation defenses (account quality, velocity). ║
║                                                                          ║
║  5. THE SERVING PATH                                                     ║
║     Client → LB → App server → L1 cache (in-proc) → L2 (Redis) →       ║
║     L3 fallback (trie service). Zipf means 70% of requests hit L1.      ║
║     Total serving latency: 5-10ms well within 50ms budget.              ║
║                                                                          ║
║  6. PERSONALIZATION                                                      ║
║     Two-phase: global top-100 candidates → per-user re-ranking.         ║
║     User profile in Redis or Cassandra. Cold start = global ranking.    ║
║     Privacy: data retention limits, opt-out, client-side options.       ║
║                                                                          ║
║  7. FUZZY MATCHING                                                       ║
║     Levenshtein: too slow at scale. Trigram index: fast and practical.  ║
║     Apply only on cache miss (rare). Handles 95% of typos.              ║
║                                                                          ║
║  8. MULTI-LANGUAGE                                                       ║
║     Separate index per language. Unicode NFC normalization.              ║
║     Language detection from browser headers + IP + character set.       ║
║                                                                          ║
║  9. THE L6 DIFFERENTIATORS                                               ║
║     - Raises real-time trending without being asked                      ║
║     - Knows the Zipf distribution and its cache implications             ║
║     - Mentions content filtering proactively                             ║
║     - Designs two-phase personalization                                  ║
║     - Has latency budget at every tier                                   ║
║     - Quotes real incidents (Google Instant, Amazon, Twitter)            ║
║                                                                          ║
║  10. THE ONE-LINE SUMMARY                                                ║
║      Offline pipeline produces a prefix hash. Redis serves it at O(1).  ║
║      Kafka/Flink injects trending. Personalization re-ranks per user.   ║
║      The trie teaches you how it works. The prefix hash is how          ║
║      it ships.                                                           ║
║                                                                          ║
╚══════════════════════════════════════════════════════════════════════════╝
```

---

---

## What to Read Next

- **Ch75 — Typeahead / Autocomplete (L5)**: The same system at L5 depth — the foundation
  to read before or after this chapter. L5 covers trie concept, prefix hash, Redis ZSETs,
  offline batch, sub-100ms latency, and basic trending. This chapter adds fuzzy matching,
  multi-language, deep personalization, incident case studies, and semantic autocomplete.

- **Ch33 — Caching at Scale**: Deep dive on Redis internals (ZSET implementation, memory
  management, eviction policies) and CDN caching patterns relevant to the serving layer.

- **Ch35 — Event-Driven Architectures (Kafka)**: The streaming infrastructure behind
  real-time trending. Understanding Kafka consumer groups and partition assignment
  clarifies how the Flink trending pipeline achieves fault tolerance.

- **Ch55 — Search System**: How full-text search works after the query is submitted.
  Autocomplete shapes the query; the search system executes it. Understanding both
  systems shows their interaction and the end-to-end user flow.

---

*Chapter 102 of Section 6. Pairs with Ch75 (Autocomplete L5), Ch55 (Search System),
Ch33 (Caching/Redis internals), Ch35 (Kafka/streaming). Autocomplete is the layer between
the user and the query: it shapes what queries get asked, before search executes them.*
*Last updated: 2026-06-25*

---

## Interview Simulation — Typeahead / Autocomplete (Staff / L6)

*45-minute Staff-level system design interview. Phases follow the Section 2 framework.*

---

### Phase 1: Requirements (8 min)

> **Interviewer:** Design the typeahead autocomplete system for a search engine at Google scale. Where do you start?

**Candidate:** A few questions to scope this. First — are we completing web search queries (like Google's search box), or completing within a product domain (like a music app completing song names)? The data size and personalization model differ. Second — what's the latency SLA? Autocomplete is uniquely latency-sensitive because it fires on every keystroke — even 150 ms feels sluggish. Third — do we need per-user personalization, or are suggestions the same for all users typing the same prefix? Fourth — content safety: can we show any query, or do we need to filter harmful suggestions?

> **Interviewer:** Google-scale web search autocomplete. Latency < 100 ms p99. Per-user personalization required. Content safety required — no harmful or illegal suggestions.

**Candidate:** Functional requirements: (1) Return top-10 query completions for any prefix within 100 ms. (2) Rank suggestions by a blend of global popularity and user's personal history. (3) Surface trending queries (rising in last 1 hour) without over-indexing on viral but harmful content. (4) Filter suggestions through a three-layer content safety pipeline. Non-functional: 100 ms p99, 99.99% availability (users notice immediately if autocomplete disappears), handle 1 billion prefix queries per day globally.

---

### Phase 2: Estimation (4 min)

**Candidate:** 1 billion queries/day ÷ 86,400 s ≈ 11,500 queries/s average. Peak is ~5× → 57,500 queries/s. Each query is a prefix string (avg 5 characters at time of first suggestion) and returns 10 suggestions (~200 bytes total). Storage for the prefix index: Google processes ~8.5 billion searches/day. The prefix trie of all queries with > 10 occurrences/day would cover the top ~100 million distinct queries. A trie node is ~50 bytes → 5 GB for the complete trie — fits in memory on a single large node, but we shard for redundancy. Trending computation: we need to count query velocity over a 1-hour window. With Count-Min Sketch at 1% error, each sketch is ~10 MB. We run one sketch per 5-minute bucket → 12 buckets/hour → 120 MB total for trending state.

---

### Phase 3: API Design (4 min)

**Candidate:** Single endpoint: `GET /v1/autocomplete?q={prefix}&user_id={uid}&limit=10&locale=en-US`. Returns `{suggestions: [{text, score, type}], request_id}`. Type field values: `POPULAR` (globally trending), `PERSONAL` (from user history), `TRENDING` (velocity-based). The `request_id` enables feedback: when the user clicks a suggestion, `POST /v1/feedback` body `{request_id, selected_index, selected_text}` feeds into both the personalization model and the ranking signal. We do NOT pass the full user search history in the request — the user_id is a key into the personalization store, looked up server-side. This keeps the request payload small and prevents client-side exposure of browsing history.

> **Interviewer:** Why return `type` on each suggestion?

**Candidate:** The UI team needs it to render different affordances: a trending query gets a fire icon, a personal history item gets a clock icon. More importantly, for A/B testing and ranking analysis, we need to know which source generated each suggestion. If a user always clicks PERSONAL suggestions and never POPULAR ones, that's a signal to up-weight personal history in the ranking blend. The type field makes the ranking pipeline observable.

---

### Phase 4: Data Model (4 min)

**Candidate:** Three data stores. Global prefix index: a serialized trie stored in Redis (prefix → list of top-100 completions sorted by global score). Key: `ac:prefix:us`, value: sorted list. We precompute top-100 at index build time — at query time we just fetch and re-rank. The trie is rebuilt nightly from the query log. Personalization store: Apache Cassandra, key = user_id, value = serialized `{recent_queries: [...last 100], topic_affinities: {sports: 0.8, finance: 0.3}}`. Topic affinities are updated by a nightly ML job. Trending state: Count-Min Sketch per 5-minute bucket in Redis, plus a pre-computed `trending_queries` sorted set updated every 60 s by the Trend Aggregation Service.

---

### Phase 5: HLD + Deep Dive (20 min)

**Candidate:** Here's the architecture:

```
QUERY PATH (per-keystroke, < 100ms budget)
==========================================

User Keystroke
  │
  ▼
CDN Edge (Cloudflare Workers)
  │ prefix cache: last 2 chars typed → popular prefixes cached
  │ HIT for top-1000 prefixes (80% of traffic): return immediately
  │ MISS: forward to Autocomplete Service
  │
  ▼
Autocomplete Service (stateless, 200 pods)
  │
  ├─1► Global Prefix Lookup (Redis, 5ms)
  │       GET ac:{prefix}:{locale}
  │       → top-100 global completions
  │
  ├─2► Personalization Fetch (Cassandra, 10ms, parallel)
  │       GET user:{user_id}:recent_queries
  │       GET user:{user_id}:topic_affinities
  │
  ├─3► Trending Injection (Redis sorted set, 2ms)
  │       ZREVRANGE trending:{locale} 0 9
  │       → top-10 trending queries right now
  │
  ├─4► Re-ranking (in-process, 5ms)
  │       blend_score = 0.6*global + 0.3*personal_affinity
  │                   + 0.1*trending_boost
  │       filter personal history matches to top
  │       → ranked list of 20 candidates
  │
  ├─5► Content Safety Filter (parallel async, 10ms)
  │       L1: blocklist lookup (Redis hash, <1ms)
  │       L2: ML classifier (distilBERT, 8ms, GPU sidecar)
  │       L3: human review queue (async, NOT on critical path)
  │       → drop any suggestion scoring > 0.7 harmful
  │
  └─► Return top-10 clean, ranked suggestions

TRENDING PIPELINE (near-real-time)
====================================
User Queries → Kafka (query-events topic)
  │
  ▼
Flink Job (sliding 1-hour window, 5-min slide)
  │ Count-Min Sketch per 5-min bucket
  │ velocity = count(last 1hr) / count(prev 1hr)
  │ flag queries where velocity > 3× baseline
  │
  ▼
Trending Aggregator Service
  │ merges velocity signals, applies content safety pre-filter
  │ writes to Redis: ZADD trending:{locale} {score} {query}
  │ update interval: every 60s
  │
  └─► Autocomplete Service reads trending on every request

INDEX BUILD (nightly batch)
============================
BigQuery (query log, 90-day window)
  │ COUNT queries, filter < 10/day, normalize
  ▼
Trie Builder (Spark job)
  │ builds prefix → top-100 completions per locale
  │ scores: log10(count) * freshness_decay
  ▼
Redis Cluster (atomic swap: new index replaces old)
  └─► zero-downtime deploy via key rename + TTL flip
```

**Deep Dive 1: Personalization Without Per-User Index (Re-ranking, Not Separate Index).**

The naive approach — build a separate autocomplete trie per user — is untenable at Google scale (1 billion users × 5 GB trie = 5 exabytes). The staff insight: we don't need a per-user index. We need per-user re-ranking of the global index results. The global index returns 100 candidates per prefix. The re-ranking step fetches the user's topic affinities and recent query history (from Cassandra, 10 ms) and computes a personal score adjustment. If the user frequently searches for "python programming," the topic affinity for `technology.programming` is 0.9. When they type "py," the global candidate "python download" gets a 0.9 × 0.3 = 0.27 affinity boost added to its global score, surfacing it above "pyrite mineral" even if the latter is globally more popular. The recent queries are handled separately: if the user typed "python decorators" 3 days ago, that exact query appears as a PERSONAL suggestion regardless of global rank. This architecture means the index is O(1) per user (no per-user storage for the index), and personalization is an O(1) lookup per request.

> **Interviewer:** How do you handle a prefix with no suggestions in the index — a very rare or new query?

**Candidate:** *(Cross-question: cold-start for rare prefixes)* Three fallbacks. First, backoff to a shorter prefix: if `ac:pytho` has no completions, check `ac:pyth`. We do this recursively up to 3 chars of backoff. Second, spell-correction: run a fast edit-distance check (BK-tree, max distance 1) against the top-100K queries. If "pythn" is 1 edit from "python," surface "python" completions. Third, the index is rebuilt nightly, but we have a real-time index update for breakout new queries: if a query appears > 1000 times in a 5-minute window and is not in the current index, the Trending Service creates a temporary index entry that expires in 24 hours. This handles "Super Bowl 2027 halftime show" the morning after the event.

**Deep Dive 2: Trending via Velocity (Count-Min Sketch).**

The key staff-level distinction: trending is velocity, not frequency. "Taylor Swift" has millions of queries per day but is not trending (it's always popular). "Taylor Swift Coachella" has 50,000 queries in the last hour versus 200 in the same hour last week — that's 250× velocity, clearly trending. We compute velocity = count(last 1 hour) / count(baseline 1 hour 1 week ago). The Zipf distribution of queries means the top 1,000 queries account for ~30% of traffic — exact counters for these are fine. For the long tail (100 million+ distinct queries), exact counting is infeasible. Count-Min Sketch with width 100,000 and depth 5 gives < 1% error with > 99% probability. The sketch is additive: we maintain 12 five-minute sketches, sum them for the 1-hour window, and compare to the same window from last week. Memory: 12 sketches × 100,000 counters × 4 bytes = 4.8 MB — trivially small.

**Deep Dive 3: Content Safety in 3 Layers.**

Layer 1 (< 1 ms): Deterministic blocklist — a Redis hash set of ~500,000 exact-match banned queries. This catches known harmful queries instantly with zero false positives. Updated hourly by the Trust & Safety team. Layer 2 (8 ms): ML classifier (DistilBERT fine-tuned on a human-labeled dataset of 10M queries) running on a GPU sidecar per pod. Returns a harm_score in [0, 1] for each candidate suggestion. Threshold 0.7 → block. This layer catches novel harmful queries not in the blocklist. False positive rate: ~0.5% (occasional legitimate queries incorrectly blocked). Layer 3 (async, NOT on the critical path): suggestions with harm_score in [0.4, 0.7] are queued for human review. Reviewers add confirmed harmful queries to the Layer 1 blocklist, improving future precision. The key architecture decision: Layer 3 does NOT block the suggestion in real time — it has a 24-hour SLA. Blocking on human review would add unbounded latency to the response.

---

### Common Cross-Questions and Strong Answers (Staff Level)

**Q: How do you size the LRU cache for prefix suggestions?**
A: The Zipf distribution does the work here. The top 10,000 most-queried prefixes receive ~50% of all autocomplete requests. Each prefix result set is ~200 bytes → 2 MB for the top-10K prefix cache. Storing the top 1 million prefixes (covering ~95% of traffic) requires 200 MB — easily fits in a CDN edge node's memory. Cache eviction: pure LRU. TTL: 5 minutes for trending-sensitive content (so trending queries propagate within 5 min), 1 hour for stable popular queries. The CDN Cloudflare Worker cache uses this LRU: the top-1M prefix cache means 80%+ of requests never reach the Autocomplete Service origin — significant cost and latency savings.

**Q: How would you handle an autocomplete request that takes 150 ms — above your SLA?**
A: First, check where the time is spent: CDN miss? Redis latency? Cassandra latency? Content safety classifier? The most common culprit is a slow Cassandra read for personalization (cross-datacenter read). Fix: serve the global (non-personalized) result immediately if Cassandra hasn't responded within 15 ms, then update the UI with personalized results when Cassandra responds — a progressive enhancement pattern. The user sees autocomplete at 20 ms (global) and sees it subtly re-rank at 30 ms (personalized). Imperceptible to the user, within SLA.

**Q: A new viral trend generates a harmful query (e.g., drug combination that causes deaths). How quickly can you suppress it?**
A: Layer 1 blocklist update latency is 60 minutes (hourly batch push). To go faster: the Trust & Safety team has an emergency push API that bypasses the batch — blocklist update propagates to all Redis nodes in < 30 s. The ML classifier (Layer 2) already scores new harmful queries in real time, so as long as the harm_score > 0.7, the query is blocked even before the blocklist update. The Layer 3 human review queue has a P0 escalation path: if a human reviewer marks a query as critical, it bypasses the batch and triggers the emergency push immediately. End-to-end: a new harmful query is blocked by the ML classifier within minutes of appearing at volume, and added to the deterministic blocklist within 30 minutes of human confirmation.

---

*Chapter 102 of Section 6. Pairs with Ch75 (Autocomplete L5), Ch55 (Search System),
Ch33 (Caching/Redis internals), Ch35 (Kafka/streaming). Autocomplete is the layer between
the user and the query: it shapes what queries get asked, before search executes them.*
*Last updated: 2026-06-25*

<!-- END OF CHAPTER 102 -->
<!-- Additions: Parts 11-13 (semantic autocomplete, monitoring/observability, pre-interview drill),
     fixed footer chapter numbers, added What to Read Next section. -->
<!-- Key Staff differentiators: Zipf + LRU sizing, trending = velocity not frequency,
     personalization = re-ranking not per-user index, content safety = 3 layers -->
