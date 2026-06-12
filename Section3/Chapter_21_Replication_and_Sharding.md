# Chapter 21: Replication and Sharding — How Big Systems Handle Millions of Users

*(Note to reader: This chapter is about two fundamental tricks that let databases handle millions of users without falling over. Replication means making copies of your data so more people can read it simultaneously. Sharding means splitting your data into pieces so the load is spread across many machines. By the end of this chapter, you will be able to walk into a system design interview and answer "how would you design Instagram's database?" with real confidence and specific reasoning. Every term is explained from scratch. No prior database experience required.)*

---

## Why This Chapter Exists — The One Server Problem

Let me tell you a story. Not a made-up one — a real one that plays out over and over again in Silicon Valley.

You built a photo-sharing app. You spent three months writing the code in your bedroom, deploying it on a single server you rent for $20 a month. You have 100 users — mostly your friends, your roommate, and a few strangers who stumbled across your Twitter announcement. Everything works perfectly. Photos upload in under a second. The search is instant. You're proud.

You go to sleep on a Monday night thinking about which feature to build next.

Then something magical and terrifying happens: TechCrunch writes about you.

The article goes live at 9:00 AM on a Tuesday. By 9:05 AM, your app has 500 new users. By 9:15 AM, it has 5,000. By noon, it has 100,000 people hammering on it simultaneously. The article calls your app "the future of photo sharing." It has been retweeted 40,000 times.

Your single server — the one little machine that was handling everything — is now trying to do ALL of this at the same time:

- Serve every photo view request (called a **read** — when someone looks at data that already exists in the database)
- Accept every new photo upload (called a **write** — when someone creates or changes data in the database)
- Store every photo on its single hard drive
- Run the database software that tracks who posted what
- Serve the HTML, CSS, and JavaScript files for the website itself
- Handle every search query ("find photos tagged #sunset")
- Send every notification ("someone liked your photo")
- Process every login request

One machine. 100,000 users. All at once. What happens?

Here is what actually happens, described as honestly as possible:

**9:00 AM — the article goes live.** Traffic is normal. Your server CPU (the processor — think of it as the server's brain, the thing that runs all calculations) is at 12% utilization. Everything is fast. You wake up and check your phone, see a few hundred new signups, smile.

**9:05 AM — traffic doubles.** CPU climbs to 30%. Still fine. Pages load in under half a second. You don't even notice.

**9:12 AM — you check Twitter and realize the article is viral.** Your heart rate increases. You nervously refresh your monitoring dashboard.

**9:15 AM — traffic is 10× normal.** CPU hits 70%. Database queries start taking 200 milliseconds instead of 20. Users notice a slight slowdown. Pages feel a bit sticky. But it is still usable.

**9:22 AM — you tweet "we're getting some traffic, working on it 😅"** because that is what startup founders do when they are panicking.

**9:25 AM — traffic is 50× normal.** CPU hits 95%. Now every database query is waiting in a queue because the database can only run so many things at once. Think of it like a single checkout lane at a grocery store suddenly getting 50 people in line. Photo uploads start taking 8 seconds instead of 0.3 seconds. People click "Upload" multiple times because they think it didn't work. Each extra click adds more work to the already-overwhelmed queue. The problem is now self-amplifying.

**9:30 AM — the server is effectively dead.** CPU is pegged at 100%. The database is not responding at all — it is backlogged with thousands of queued requests. Your web server is sending "504 Gateway Timeout" errors to everyone who loads a page. This means "I asked the database for data and it never answered me." Users who try to sign up get a blank error page. Users who try to view photos get an error page. Users who try to log in get an error page. Your phone is blowing up — not with congratulations, but with angry tweets: "this app is broken," "can't even sign in," "what a disappointment," "TechCrunch featured a broken product." The TechCrunch article that was your big break is now actively sending people to a broken experience.

**9:45 AM — you restart the server in a panic.** It comes back up for about 90 seconds before the massive backlog of reconnecting users immediately crushes it again.

**10:00 AM — you email TechCrunch begging them to take down the article.** They don't respond until 3 PM.

**10:15 AM — you start frantically googling "how to scale database fast" and "add replica postgres" while the server continues to fall over every few minutes.**

This moment even has a name in the industry. Developers call it the **hug of death** — when getting famous is the thing that kills your app. It is not hypothetical. It happened to:

- **Instagram in 2010:** They were using a single PostgreSQL database when they launched. Within hours of launch, they were scrambling to add read replicas and reconfigure their infrastructure. Co-founder Mike Krieger said in a 2012 talk that their launch day was a genuine infrastructure scramble.
- **Digg in 2010:** Digg was a social news site where a front-page story could send enormous traffic. Engineers coined the term "getting Dugg" — when the sudden traffic spike from a Digg front page completely overwhelmed a site's servers. Dozens of websites would go down every week from being featured on Digg.
- **Twitter in 2008-2009:** Twitter showed a cartoon of a friendly blue whale being lifted by birds — lovingly called the "Fail Whale" — to millions of users every time the site went down, which was multiple times per day. The Fail Whale became so iconic it was printed on t-shirts, coffee mugs, and posters. Twitter engineers were fighting the database scaling problem almost continuously for two years. Their infrastructure at the time was not designed for how fast they grew.
- **Pokémon Go in 2016:** The app launched globally with backend infrastructure sized for maybe 5 million users. 45 million people downloaded and tried to use it in week one. Servers were down or severely degraded for nearly two weeks after launch. The game was a global phenomenon and a global infrastructure disaster simultaneously.

Every successful startup faces some version of this exact moment. The question is not "will my single server become a bottleneck?" — it will, if you succeed. The question is: "what do I do when it does?"

The answer is two ideas. Two tools. Two fundamental techniques that every professional database engineer reaches for, in order, when a system needs to handle more users.

**Replication**: Make copies of your data. Now multiple servers can answer read requests simultaneously. Instead of one cashier serving 100,000 customers, you have ten cashiers serving them simultaneously. The queue disappears.

**Sharding**: Split your data into pieces and put each piece on a different server. Now writes are spread across many machines instead of all going to one machine. Instead of one enormous warehouse where one person manages everything, you have ten smaller warehouses each with their own manager. The manager of Warehouse A handles everything from customers A through D. The manager of Warehouse B handles E through H. And so on.

This chapter explains both — how they work mechanically, when to use each one, what can go wrong, and how senior engineers think about them in system design interviews.

---

## Chapter at a Glance

Before diving deep, here is the whole chapter in one reference box. Do not worry if it does not all make sense yet — every term in this box will be fully explained before you reach the end of Part B. Come back to this box after reading and see how much more you understand.

```
╔══════════════════════════════════════════════════════════════════════════════╗
║             CHAPTER 21: REPLICATION AND SHARDING — QUICK REFERENCE          ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  THE TWO BIG IDEAS                                                           ║
║  ─────────────────────────────────────────────────────────────────────────  ║
║  REPLICATION = Making identical copies of your entire data on other servers  ║
║    → Scales READS  (more copies = more machines answering reads at once)     ║
║    → Improves AVAILABILITY (if one copy dies, others keep working)           ║
║    → Improves DURABILITY (data lives in multiple places — not just one)      ║
║    → Does NOT help with write bottlenecks (all writes still go to leader)    ║
║    → Does NOT help if your data is too large for one machine                 ║
║                                                                              ║
║  SHARDING = Splitting your data across multiple machines (each has a piece)  ║
║    → Scales WRITES  (each machine handles a fraction of write load)          ║
║    → Scales STORAGE (each machine stores a fraction of total data)           ║
║    → Adds massive operational complexity (much harder than replication)      ║
║    → Makes some queries harder (cross-shard joins)                           ║
║                                                                              ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  THE SCALING JOURNEY (in order — do not skip steps)                         ║
║  ─────────────────────────────────────────────────────────────────────────  ║
║                                                                              ║
║  Step 1: OPTIMIZE  → Add indexes, fix slow queries, add caching              ║
║  Step 2: SCALE UP  → Upgrade to a bigger machine (more RAM, more CPU)        ║
║  Step 3: REPLICATE → Add read replicas if reads are the bottleneck           ║
║  Step 4: SHARD     → Split data if writes or storage are the bottleneck      ║
║                                                                              ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  KEY NUMBERS TO KNOW                                                         ║
║  ─────────────────────────────────────────────────────────────────────────  ║
║  Each replica you add: roughly doubles your read capacity                    ║
║  Each shard you add: divides your write load proportionally                  ║
║  Replication lag: typically 5–50ms in same datacenter, 100–200ms cross-region║
║  Automatic failover time: typically 10–30 seconds                            ║
║                                                                              ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  KEY RISKS TO WATCH                                                          ║
║  ─────────────────────────────────────────────────────────────────────────  ║
║  Replicas → Replication Lag (copies fall behind → reads might get stale data)║
║  Shards   → Hot Shards (one piece gets much more traffic than others)        ║
║  Shards   → Cross-shard joins (queries that span multiple machines are hard) ║
║  Shards   → Resharding (changing the split later is brutal)                  ║
║                                                                              ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  THE GOLDEN RULE                                                             ║
║  ─────────────────────────────────────────────────────────────────────────  ║
║  ALWAYS try these FIRST before adding replicas or shards:                    ║
║    1. Add database indexes (like a book index — find data without scanning)  ║
║    2. Optimize slow queries (fix the query, not the hardware)                ║
║    3. Add a caching layer (Redis: store popular answers in fast memory)      ║
║    4. Vertical scaling (upgrade to a bigger machine — simple and immediate)  ║
║    5. Read replicas (if reads are the problem — much simpler than sharding)  ║
║    6. Sharding (last resort — enormous complexity cost, nearly permanent)    ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

Let's unpack this box before diving deeper.

The two big ideas in this chapter — replication and sharding — solve **different problems**. They are not interchangeable. Choosing the wrong one wastes months of engineering effort and often makes things worse.

Replication is your answer when too many people want to **READ** your data at the same time. Think about a news article that goes viral: ten million people are viewing it, but almost nobody is writing to it. Read replicas let you serve all those readers from multiple copies simultaneously, because each copy of the data can independently answer read requests. Replication does NOT help much if your bottleneck is people writing data — if you add 10 copies of the database and all 10 need to be updated every time someone writes, you have multiplied your write work by 10, not reduced it.

Sharding is your answer when the problem is either too many **writes** (thousands of people updating data simultaneously, all trying to write to the same machine) or too much **data** (your database is 50 terabytes and no single machine can store 50 terabytes). Sharding takes your single huge database and splits it into smaller pieces — each piece lives on its own machine. But sharding comes with a permanent complexity cost, which is why the golden rule exists: exhaust every simpler option before considering sharding.

---

## The Best Analogy: Library Books

Analogies are the fastest way to genuinely understand database concepts. They let you build intuition before you learn the mechanics. Here is one that will stick with you through your entire engineering career.

Imagine a school library. The library has exactly **one physical copy** of a popular Harry Potter book. Every student in the school wants to read it. The problem: only one student can physically hold the book at a time. There is a long queue at the librarian's desk. Students sign up for 1-hour slots. Students who have free time after finishing their homework have to wait three days before their turn comes up.

This is your single database server. One copy of the data. Anyone who wants it has to wait their turn. When traffic is low — 100 students — this works fine. When every student simultaneously decides they want Harry Potter — 100,000 students — the queue becomes impossibly long.

### Replication = Making Photocopies of the Book

The librarian has a breakthrough idea: use the photocopier. She makes 10 copies of the Harry Potter book and puts them all on the shelf. Now 10 students can read simultaneously. The queue disappears. Students who want to read can walk up and grab a copy immediately.

This is **replication**. You make identical copies of your database and put them on different servers. Readers can go to any copy. The queue of read requests disappears because you now have 10× the capacity.

But here is the catch. What if J.K. Rowling releases an updated edition — she corrects a typo on page 47 and adds a new appendix? The librarian has to update ALL 10 copies. During the time it takes to update them — let us say it takes 5 minutes per copy, and she starts with Copy 1 and works her way to Copy 10 — there is a window where some copies have the new appendix and some still have the old version. A student who grabs Copy 8 at exactly the wrong moment gets the old version. A student who grabs Copy 1 (already updated) gets the new version. Two students reading the "same" book at the same time might see different things.

This brief window where some copies have new data and some copies have old data is called **replication lag**. It is one of the most important concepts in this chapter, and one of the most common sources of strange user-facing bugs in real production systems. We will spend significant time on it.

### Sharding = Splitting the Encyclopedia into Volumes

Now imagine the library also has a 26-volume encyclopedia. Each volume covers a range of letters: Volume 1 covers A–C (thousands of entries about Aardvarks through Czars), Volume 2 covers D–F (Dinosaurs through Frogs), Volume 3 covers G–M, Volume 4 covers N–Z.

The encyclopedia is so large — hundreds of thousands of pages in total — that it simply cannot fit in a single book. So it was published as separate volumes. This is not a flaw in the design; it is a deliberate choice to make the encyclopedia manageable.

When a student needs to look up "Elephant," they do not need to flip through the A–C volume or the G–M volume. They go straight to Volume D–F. Students looking up different topics can use different volumes simultaneously — one student reads about "Antarctica" in Volume A–C, while another reads about "Jupiter" in Volume G–M, while a third reads about "Photography" in Volume N–Z. They do not wait for each other at all. The total "read capacity" of the encyclopedia system is much higher than if it were a single book.

This is **sharding**. Your data is so large, or you have so many writes happening to different parts of it simultaneously, that you split it across multiple machines. Each machine handles its own "volume" of data. Machines handling different data do not interfere with each other.

But here is the catch with sharding: what if you want to do some research that spans multiple volumes? "Find every animal in the encyclopedia that lives in Africa." "Elephant" is in Volume D–F. "Giraffe" is in Volume G–M. "Lion" is in Volume G–M. "Antelope" is in Volume A–C. "Zebra" is in Volume N–Z. To answer this question, you have to look in ALL four volumes. In database terms, this is called a **cross-shard query** — a query that needs to look at data on multiple different machines. These queries are expensive and complicated to execute. They require coordination between machines.

### The Key Insight: You Can Do Both

Here is the part that makes everything click into place: you do not have to choose between replication and sharding. You can use both simultaneously, and most large-scale production databases do exactly that.

Make 3 copies of each encyclopedia volume. Each volume lives on 3 different servers. The volumes give you sharding: write traffic for the A–C section is completely independent from write traffic for the D–F section. The copies within each volume give you replication: 3 students can read the A–C section simultaneously without waiting for each other.

```
WITHOUT REPLICATION OR SHARDING:
─────────────────────────────────────────────────────────────
  ┌─────────────────────────────────┐
  │   ONE GIANT DATABASE (all data) │
  │   Only 1 concurrent write       │
  │   Only so many concurrent reads │
  │   Breaks if this machine fails  │
  └─────────────────────────────────┘
  → Works fine for 100 users. Falls over for 100,000.
─────────────────────────────────────────────────────────────

WITH REPLICATION ONLY (same data on 3 machines):
─────────────────────────────────────────────────────────────
  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
  │  Full Database  │  │  Full Database  │  │  Full Database  │
  │  (Primary)      │  │  (Replica 1)    │  │  (Replica 2)    │
  │                 │  │                 │  │                 │
  │  ✓ Reads        │  │  ✓ Reads        │  │  ✓ Reads        │
  │  ✓ Writes       │  │  ✗ No writes    │  │  ✗ No writes    │
  └─────────────────┘  └─────────────────┘  └─────────────────┘
  → 3 machines can serve reads simultaneously.
  → Write load still on ONE machine — not scaled.
  → If data grows to 10TB, ALL THREE machines need 10TB each.
─────────────────────────────────────────────────────────────

WITH SHARDING ONLY (data split across 4 machines):
─────────────────────────────────────────────────────────────
  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐
  │  Shard 1   │  │  Shard 2   │  │  Shard 3   │  │  Shard 4   │
  │  Users A-D │  │  Users E-H │  │  Users I-M │  │  Users N-Z │
  │            │  │            │  │            │  │            │
  │  ✓ Reads   │  │  ✓ Reads   │  │  ✓ Reads   │  │  ✓ Reads   │
  │  ✓ Writes  │  │  ✓ Writes  │  │  ✓ Writes  │  │  ✓ Writes  │
  └────────────┘  └────────────┘  └────────────┘  └────────────┘
  → Write load split across 4 machines. ✓
  → Storage split — each machine stores only 1/4 of data. ✓
  → BUT: Each shard has only 1 copy — single point of failure. ✗
  → If Shard 1's machine dies, all Users A-D data is GONE. ✗
─────────────────────────────────────────────────────────────

WITH BOTH (replication + sharding — the production standard):
─────────────────────────────────────────────────────────────
  Shard 1 Primary ──replicates──► Shard 1 Replica A  Shard 1 Replica B
  Shard 2 Primary ──replicates──► Shard 2 Replica A  Shard 2 Replica B
  Shard 3 Primary ──replicates──► Shard 3 Replica A  Shard 3 Replica B
  Shard 4 Primary ──replicates──► Shard 4 Replica A  Shard 4 Replica B

  Total machines: 4 shards × 3 copies each = 12 machines
  Write capacity:  4× higher than single machine (4 shard primaries)
  Read capacity:   12× higher than single machine (12 nodes serve reads)
  Fault tolerance: Any 1 machine per shard can die — no data loss
  → This is how Airbnb, Uber, Stripe, and GitHub run their databases.
─────────────────────────────────────────────────────────────
```

When you look at the combined diagram, you are seeing what a real production database cluster looks like. It is not exotic or complicated once you understand the two underlying ideas. It is just "split the data into pieces" plus "make copies of each piece."

Most companies start with just replication (it is simpler and sufficient for a long time) and only add sharding when they genuinely need it (it is far more complex and adds permanent operational cost). The rest of this chapter explains replication in full depth. Part B explains sharding.

When you see the word **replica** in this chapter: think "photocopy of the book, available for reading." When you see the word **shard**: think "one volume of the encyclopedia, handling a specific chunk of data."

---

## Quick Visual: The Scaling Journey — When to Use What

Before jumping into technical mechanics, here is the decision tree every experienced engineer follows when a database starts struggling. Memorize this order. It will save you from over-engineering your system.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                   THE DATABASE SCALING DECISION TREE                        │
│                                                                             │
│                        Is your system slow?                                 │
│                              │                                              │
│                              ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  STEP 1: OPTIMIZE FIRST (try this before changing infrastructure)   │   │
│  │                                                                     │   │
│  │  • Add missing database indexes (can give 10-100× speedup)         │   │
│  │  • Fix poorly written queries (review slow query log)              │   │
│  │  • Add Redis caching for popular read-heavy data                   │   │
│  │  • Profile your app code — is the database even the bottleneck?    │   │
│  │                                                                     │   │
│  │  Result: Often solves the problem. No infrastructure changes.      │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                              │                                              │
│              Still slow after optimization?                                 │
│                              │                                              │
│                              ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  STEP 2: SCALE VERTICALLY (buy a bigger machine)                    │   │
│  │                                                                     │   │
│  │  • Upgrade from 8 CPU cores to 64 cores                           │   │
│  │  • Upgrade from 32 GB RAM to 256 GB RAM                           │   │
│  │  • Upgrade to faster NVMe SSD storage                             │   │
│  │                                                                     │   │
│  │  Result: Simple and fast. Often buys 1-2 years of runway.         │   │
│  │  Limit: Eventually you hit the biggest machine available.         │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                              │                                              │
│              Is it a READ bottleneck? (too many read queries)               │
│                              │                                              │
│                              ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  STEP 3: ADD READ REPLICAS                                          │   │
│  │                                                                     │   │
│  │  • Add 1, 2, or 3 additional database servers                     │   │
│  │  • Route read queries to replicas, write queries to primary       │   │
│  │  • Each replica roughly doubles read capacity                     │   │
│  │                                                                     │   │
│  │  Cost: Moderate. Need to handle replication lag.                  │   │
│  │  Does NOT help: write bottlenecks, storage limits                 │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                              │                                              │
│         Still have a WRITE bottleneck or STORAGE limit?                    │
│                              │                                              │
│                              ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  STEP 4: SHARD YOUR DATA       ⚠  LAST RESORT                      │   │
│  │                                                                     │   │
│  │  • Split your database into multiple independent pieces            │   │
│  │  • Each piece lives on its own machine                            │   │
│  │  • Writes go to the correct shard based on a routing key          │   │
│  │                                                                     │   │
│  │  Cost: High. Nearly permanent decision. Massive complexity.        │   │
│  │  Use only when Steps 1–3 genuinely cannot solve the problem.      │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

That warning label on sharding — "LAST RESORT" — is not dramatic. It is accurate, and experienced engineers agree on this.

**Nine out of ten startups shard their database too early.** Here is why that happens: an engineer sees high database CPU and assumes "we need to shard." But sharding is enormously complex. When you shard, you are permanently committing to:

- A decision about how to split the data (changing this later is brutally hard and requires migrating the entire database)
- Rewriting queries that used to join data naturally to now work across multiple machines
- Handling the case where one query needs data from multiple shards (expensive and requires coordination)
- Dealing with "hot shards" — one piece of the data getting way more traffic than others, making the split unfair
- Managing database migrations across dozens of machines instead of one
- Debugging production incidents that now involve many machines with complex interdependencies

Before you shard, try all of these in order:

**1. Database indexes.** An index is like the index in the back of a textbook. Without the index, finding "photosynthesis" means reading every page. With the index, you look it up and go directly to page 247. Without indexes, your database reads every row in a table to find matching rows. With the right indexes, it jumps directly to the answer. Adding the right index can make a query that takes 10 seconds run in 10 milliseconds — a 1000× speedup — with zero infrastructure changes. This is always the first thing to try.

**2. Query optimization.** Sometimes the query itself is just badly written. An engineer who writes `SELECT * FROM users WHERE name LIKE '%john%'` is asking the database to scan every user in the table looking for "john" anywhere in the name. A better query structure plus the right index can do the same thing 10,000× faster. A senior database engineer reviewing your queries regularly finds major speedup opportunities without touching hardware.

**3. Caching.** A cache (most commonly Redis or Memcached — both are extremely fast in-memory databases) stores the results of popular queries so the database never has to compute them again. If 80% of your read traffic is for the same 1,000 most-popular items, you store those 1,000 results in the cache and serve them from there. The actual database never sees those requests. Netflix serves millions of simultaneous streams largely because the metadata for popular shows is cached — it never hits the main database on most requests.

**4. Vertical scaling.** Upgrade to a bigger machine. If your database server has 32 GB of RAM and 8 CPU cores, upgrade to a server with 256 GB of RAM and 64 CPU cores. This is expensive but requires zero code changes and zero architectural changes. It buys you significant runway — often 1 to 2 years — while you figure out longer-term solutions.

**5. Read replicas.** If the bottleneck is definitely reads (people viewing data, not writing data), add read replicas. One or two replicas often eliminate a read bottleneck completely. This is covered in depth in this chapter. It is far simpler than sharding.

**6. Sharding.** Only if ALL of the above have been genuinely tried and proven insufficient, or if you have a storage problem that no single machine can solve, consider sharding.

---

## L5 vs L6: How Senior Engineers Think About the Scaling Decision

One of the clearest observable differences between a mid-level engineer (roughly L5 at Google/Meta/Amazon) and a senior engineer (L6) is the diagnostic process before reaching for a solution. L5 engineers see symptoms and reach for architectural changes. L6 engineers investigate what is actually wrong before touching anything.

| Scenario | L5 Response | L6 Response |
|----------|------------|-------------|
| "Database CPU is hitting 80% sustained" | "We need to shard — at this rate we'll hit 100% in 3 weeks." | "Let's look at the slow query log first. What are the top 5 most expensive queries? Are they missing indexes? Is this a read or write pattern? What's the QPS trend — is this a temporary spike or sustained growth?" |
| "We need more write throughput" | "Let's add multi-leader replication to accept writes on multiple nodes simultaneously." | "How many writes per second are we actually doing, and what is our physical limit? Multi-leader doesn't multiply write capacity — both leaders are writing the same data. If we need more write throughput, we need sharding. But first: can we batch writes? Is there a specific hot partition we can isolate?" |
| "Users in Europe have high latency" | "We need a European database leader for EU writes to go local." | "Is the latency on reads or writes? For reads, a CDN or read replica in Europe solves it simply. For writes, multi-leader adds conflict complexity — let's quantify how many EU writes there are per second and whether 150ms is actually causing user complaints, vs. just showing up in metrics." |
| "One user's data is 40% of our database" | "We have a hot shard problem — we need to re-shard." | "First: is this one user a known business account that should be isolated to dedicated infrastructure? Re-sharding affects all users during migration. Can we move just this one user off-cluster to a dedicated database? What's the migration plan if re-sharding is needed? Who owns rollback?" |
| "We need to add more shards" | "Let's go from 4 to 8 shards — double the shards incrementally." | "Going from 4 to 8 means half the data moves to new locations. During migration, writes to moving data must be paused or dual-written. We need a full migration plan with rollback strategy, and we need to test this on staging with production-scale data volume. Who's on-call the night we do this?" |

The pattern in the L6 column: **diagnose before prescribing.** Every architectural change has a permanent cost. Sharding, once done, is extremely difficult to undo. Multi-leader adds conflict resolution logic that must be maintained forever. L6 engineers understand this and make sure the complexity cost is genuinely necessary before committing to it.

---

# Part 1: Replication — Making Copies of Your Data

## What is Replication, Really?

Ask ten engineers why we replicate data and nine will say "so we don't lose it." That is correct but incomplete. Replication solves four distinct problems, and understanding all four gives you much richer vocabulary to use in interviews and technical discussions.

| Purpose | What It Means | Everyday Example |
|---------|--------------|-----------------|
| **Durability** | If one machine dies, your data still exists on other machines. Data is not permanently lost because of a single hardware failure. | You back up your phone photos to iCloud. If your phone is stolen or falls into a lake, your photos are not gone — they still exist in Apple's servers. The loss of one physical device does not mean the loss of your data. |
| **Availability** | If one machine crashes or goes offline for maintenance, other machines immediately take over. Users do not experience an outage. | A hospital has two backup generators. If the main power grid fails, the backup kicks in automatically within seconds. Patients on life support machines do not even notice the power transition. |
| **Read Scaling** | Multiple copies of data means multiple machines can answer read requests simultaneously, multiplying your total read capacity without requiring any single machine to handle more load. | A textbook publisher prints 10,000 copies of a popular book. Ten thousand students can read simultaneously instead of waiting for a single copy. |
| **Latency Reduction** | Putting copies of data physically close to the users who need it reduces the travel time (latency) of each request. | Netflix stores copies of popular movies on servers located in your city. Your movie starts streaming in seconds because the data is 20 miles away rather than 3,000 miles away on a server in another country. |

The first two purposes — durability and availability — are about **surviving disasters.** A server crashes. A data center floods. A hard drive fails. (Hard drives fail constantly in production: in a large data center with 100,000 servers, multiple hard drives fail every single day.) Replication ensures that routine hardware failures do not mean data loss or downtime.

The second two purposes — read scaling and latency reduction — are about **serving more users faster.** These are what matter when TechCrunch writes about you and your traffic spikes overnight. More copies of your data means more machines can answer "show me this user's posts" simultaneously, and copies closer to users mean faster answers.

A well-designed replication strategy does all four simultaneously. You choose where to put your replicas (which data centers, which geographic regions), how many replicas to maintain, and what consistency model to use, based on which of these four goals matter most for your specific system:

- A social media startup cares most about **read scaling** and **availability** (users must be able to view content and the site must never fully go down)
- A financial transaction system cares most about **durability** and **availability** (money must never disappear and transfers must always be processable)
- A global streaming service cares most about **latency reduction** and **read scaling** (videos must start fast from anywhere in the world)
- A healthcare records system cares most about **durability** and specific regulatory requirements about data locality

---

## How Leader-Follower Replication Works

This is the most common type of replication in production systems worldwide. Understanding it deeply will serve you in the vast majority of database design interview questions.

### The Restaurant Kitchen Analogy

Imagine a restaurant with one head chef — let us call her Chef Maria — and three apprentice chefs: Alex, Jordan, and Sam. Chef Maria is the head chef. She is in charge. She creates every new recipe. She is the only one with the authority to write in the official recipe book, which lives in a locked cabinet at her station.

Every morning, after Chef Maria writes new or updated recipes the previous day, she hands copies to her three apprentices. Alex, Jordan, and Sam each carefully copy the new recipes into their own personal notebooks. During dinner service, when a customer asks "how do I cook the pasta?" the server can ask any apprentice — they all have the same recipe information. This means three tables can get recipe answers simultaneously instead of all waiting for Chef Maria to stop cooking and answer questions herself.

But — and this is critically important — when a customer wants to CREATE a brand new dish or modify an existing recipe ("can you make a gluten-free version of the pasta?"), that request ALWAYS goes to Chef Maria. Only she can write in the official recipe book. The apprentices just follow what the official book says. They cannot make up their own recipes.

After Chef Maria writes the new recipe, she passes it to her apprentices, who update their notebooks. If a customer asks an apprentice about the new dish before the apprentice has copied it from Chef Maria, the apprentice will say "I don't have that recipe yet" — this is replication lag.

This analogy maps directly to how **leader-follower database replication** works:

- **Leader** (also called primary or master — like Chef Maria): The ONE node that accepts all write operations. This is the single source of truth for all data.
- **Followers** (also called replicas, secondaries, or slaves — like Alex, Jordan, and Sam): Copies that receive and apply all changes from the leader. They can serve read operations but they NEVER accept writes directly from clients.

```
                         ════════════════════════════════
                              APPLICATION LAYER
                         ════════════════════════════════
                                      │
                         ┌────────────┴───────────────┐
                         │                            │
                   WRITE TRAFFIC               READ TRAFFIC
                   (all writes go here)        (reads go here)
                         │                            │
                         ▼                            ▼
              ┌─────────────────────┐    ┌────────────────────────┐
              │      LEADER         │    │      LOAD BALANCER      │
              │    (Primary)        │    │  (distributes reads     │
              │                     │    │   across all replicas)  │
              │  • Accepts ALL      │    └─────────┬──────────────┘
              │    writes           │              │
              │  • Single source    │     ┌────────┼────────┐
              │    of truth         │     │        │        │
              │  • Replicates all   │     ▼        ▼        ▼
              │    changes to    ───┼──►  Rep1    Rep2    Rep3
              │    followers        │    │        │        │
              └─────────────────────┘    │Read    │Read    │Read
                         │               │only    │only    │only
                         │               └────────┴────────┘
                    Replication
                    Stream (WAL)
```

Here is the exact sequence of events when a user writes data in this setup, explained step by step:

**Step 1: Client sends a write.**
A user clicks "Post" on your app. Your application server sends the write request to the leader database. The application always knows which server is the leader — this is configured in your database connection settings.

**Step 2: Leader writes to the WAL.**
The leader receives the write. Before doing anything else, it writes the change to its **Write-Ahead Log (WAL)**. The WAL is a sequential log file on disk where every change is recorded before it is applied to the actual data. Think of it as a "to-do list" that the database keeps — it writes "I am about to do X" before actually doing X. This means if the server crashes in the middle of an operation, when it restarts, it can look at the WAL and pick up where it left off. Nothing is ever lost because of a mid-operation crash.

In the Chef Maria analogy: before adding a recipe to the official book, Maria writes it in a scratch notepad first. If she gets interrupted, she can pick up where she left off.

**Step 3: Leader applies the change.**
The leader applies the change to its actual database tables. The write is now committed — it is safely on the leader's disk and visible to future reads on the leader.

**Step 4: Leader sends the change to followers.**
The leader takes the log entry from the WAL and sends it to all followers. This sending is called the **replication stream.** The followers receive these log entries and apply them to their own copy of the data, in the exact same order the leader applied them. Ordering is crucial: if the leader ran "create user Alice, then delete user Alice," followers must apply them in that exact order, not reversed.

**Step 5: Leader responds to the client.**
The leader sends a "success" response back to the application. "Your post was saved!"

**Step 6: Followers apply the change (in the background).**
Each follower receives the replication event and applies the change to its own data. This may happen slightly after the leader's success response — this is where replication lag comes from.

```
EVENT SEQUENCE TIMELINE:
─────────────────────────────────────────────────────────────────────────
T=0ms:    Application → Leader:  "INSERT: user=Sarah, post='Hello World'"
T=1ms:    Leader: Writes to WAL (draft log): "I will insert this row"
T=2ms:    Leader: Applies change to actual table
T=3ms:    Leader → Application:  "OK, success!" (response sent to client)
T=4ms:    Leader → Follower 1:   "Replicate: INSERT user=Sarah, post='Hello World'"
T=4ms:    Leader → Follower 2:   "Replicate: INSERT user=Sarah, post='Hello World'"
T=4ms:    Leader → Follower 3:   "Replicate: INSERT user=Sarah, post='Hello World'"
T=10ms:   Follower 1: Applies change. Now has Sarah's post. ✓
T=15ms:   Follower 2: Applies change. Now has Sarah's post. ✓
T=40ms:   Follower 3: Applies change (was briefly busy). Now has Sarah's post. ✓

KEY OBSERVATION:
From T=3ms (when leader said "success") to T=40ms (when all followers caught up):
  → If a client reads from Follower 3, they will NOT see Sarah's post yet.
  → This 37ms window is the replication lag window.
─────────────────────────────────────────────────────────────────────────
```

Why is leader-follower the most common setup in the world? Because it is simple and it eliminates one of the hardest problems in distributed systems: **write conflicts.** When only one machine (the leader) accepts writes, you can never have the situation where two machines simultaneously try to update the same record in different, incompatible ways. There is one source of truth. One chef writing the official recipe. Everything else is just copying. No conflicts. No ambiguity.

MySQL, PostgreSQL, MongoDB, MariaDB, and most widely-used databases support leader-follower replication as their default and most well-tested mode.

---

## The Replication Lag Problem — When Copies Fall Behind

Notice in the event timeline above that followers apply the change "in the background" after the leader has already responded to the client. There is always some delay — even if tiny — between when the leader writes the data and when the followers catch up. This delay is called **replication lag**, and it is the most common source of subtle, hard-to-debug bugs in systems that use read replicas.

### The Stale Newspaper Analogy

Imagine a newspaper. A story breaks at 8:00 AM. The newspaper is printed at midnight and delivered to doorsteps at 6:00 AM the next morning. Your morning newspaper is already 10 to 22 hours old by the time you read it. All the information is real and accurate — it just describes the world as it existed many hours ago.

Database replication lag is measured in milliseconds, not hours. But the principle is identical: the copy (follower) is always slightly behind the original (leader). In a healthy system, this lag is 5–50 milliseconds — so small that it rarely matters. But under certain conditions — network congestion, heavy follower load, large transactions, server restarts — it can grow to seconds or even minutes.

Here is the replication lag window visualized:

```
TIME AXIS ──────────────────────────────────────────────────────────────────►

T=0ms:     Sarah writes her new profile photo to the LEADER.
           Leader committed: Sarah.photo = "birthday_selfie.jpg"

T=1ms:     Leader sends replication event to all followers.

T=5ms:     Network transit begins (packets traveling from leader to followers).

│◄─── REPLICATION LAG WINDOW FOR FOLLOWER 3 ─────────────────────────────►│
│                                                                            │
T=30ms:    Follower 1 receives and applies replication event.               │
           Follower 1: Sarah.photo = "birthday_selfie.jpg"  ✓               │
                                                                            │
T=50ms:    Follower 2 receives and applies replication event.               │
           Follower 2: Sarah.photo = "birthday_selfie.jpg"  ✓               │
                                                                            │
│          (Follower 3 is under heavy read load, disk is busy)              │
T=80ms:    Follower 3 finally receives and applies replication event.       │
           Follower 3: Sarah.photo = "birthday_selfie.jpg"  ✓               │
│◄──────────────────────────────────────────────────────────────────────────│

DURING THE LAG WINDOW (T=1ms to T=80ms):
  • Any read from Follower 3 returns: Sarah.photo = "old_headshot.jpg"  ✗
  • This is STALE DATA — technically a lie being told to the user
  • The user has no way of knowing the data is stale — it looks accurate
```

In the Chef Maria analogy: Chef Maria writes the new pasta recipe at 10:00 AM. She immediately sends a copy to Apprentice Alex. Alex is busy plating three dishes and does not copy it until 10:05 AM. If a customer asks Alex "what is in the pasta?" at 10:03 AM — during that 5-minute lag window — Alex gives them the old recipe. The customer gets stale information. The new recipe definitely exists (in Chef Maria's book) but Alex's copy hasn't caught up yet.

### The Five Causes of Replication Lag

Replication lag is not always 50 milliseconds. In a healthy system it might be tiny. In a struggling system it might be seconds or minutes. Here are the five most common causes:

**1. Network slowness or congestion.**
The replication stream has to travel from the leader to the followers over a network. If the network is congested (like a highway during rush hour), replication packets get stuck in queue. For followers in a different geographic region — say, leader in New York and follower in Singapore — the baseline travel time alone is 150–200 milliseconds. Any congestion on top of that makes it worse.

**2. Disk I/O pressure on the follower.**
When the follower is also serving many read requests, its disk is busy reading data for those queries. The replication stream is WRITING to disk, but the disk can only perform so many operations per second. Heavy read load on a follower can cause it to fall behind on applying replication events — the reads keep interrupting the writes. More traffic → more lag.

**3. Large transactions on the leader.**
If the leader runs a transaction that updates 10 million rows at once — like a data migration, a bulk price update, or a mass delete — the replication event for that transaction is enormous. The follower has to apply all 10 million row changes sequentially. During this time, the follower falls significantly behind. A large migration that takes 5 minutes on the leader might cause followers to lag by 5–10 minutes.

**4. Schema migrations.**
Adding a column to a table with 500 million rows can take many hours on the leader. During this operation, the follower is continuously receiving and applying changes — but these changes include the migration itself, which touches every row. Followers can fall many minutes behind during large schema changes. This is one reason why "online schema changes" (tools like pt-online-schema-change) were invented.

**5. Follower restarts and catch-up.**
When a follower is restarted — for a software update, to fix a hardware issue, or any other reason — it must catch up on all the replication events it missed while it was down. If it was down for 1 hour, it has 1 hour's worth of changes to apply. During catch-up, the follower's data is very stale. Depending on write volume, catch-up could take minutes to hours.

### The Ghost Profile Bug — A Real User Scenario

Here is a specific bug that is so common it has acquired a name. Understanding this bug will help you understand WHY replication lag matters in practice, not just in theory.

**The setup:** Sarah opens your social media app on her phone. She just got back from her birthday party and is excited to update her profile photo to a fun birthday selfie. She goes to Settings → Profile → Change Photo. She taps "Choose from Gallery," selects the birthday selfie, and taps "Save."

The app responds: "Profile updated successfully!" with a little green checkmark.

Sarah, beaming, turns to her friend standing next to her: "Check out my new profile pic!" She opens her profile page to show her friend.

Her old headshot appears. The birthday selfie is nowhere to be seen.

**Pause.** Think about how Sarah feels in this moment. She just saw a success message. She just saw a green checkmark. Now the app is showing her the old photo. Did it save or not? Is the app lying to her? Is her phone broken? She stares at it, confused and a little embarrassed because her friend is watching.

She taps "Change Photo" again and re-uploads the birthday selfie. This time, the selfie appears immediately on her profile. She is relieved but baffled — what happened the first time?

**What actually happened technically:**

```
T=0:      Sarah's WRITE (upload birthday selfie) → goes to LEADER
          Leader commits: Sarah.photo_url = "birthday_selfie.jpg"
          Leader responds: "Success!" ✓

T=3ms:    Leader sends replication event to all followers.

T=8ms:    Sarah's app immediately navigates to "View Profile."
          Load balancer picks a replica to handle this read.
          Load balancer picks Follower 3 (which is currently 75ms behind).
          Follower 3 still has: Sarah.photo_url = "old_headshot.jpg"

T=8ms:    App displays: old_headshot.jpg ← SARAH SEES HER OLD PHOTO
          She thinks: "The upload didn't work."

T=10ms:   Sarah re-uploads the birthday selfie.
          This is a DUPLICATE write. Harmless, but confusing.

T=83ms:   Follower 3 FINALLY applies the original replication event.
          Follower 3 now has: Sarah.photo_url = "birthday_selfie.jpg" ✓

          (The second upload's replication arrives at T=90ms)
```

From Sarah's perspective: the app showed success, then showed failure, then worked when she tried again. The app appears inconsistent and untrustworthy.

From an engineering perspective: **everything worked correctly.** The write was saved. The follower just had not caught up yet in those 8 milliseconds.

Now multiply this by 100,000 users. Support tickets flood in: "The app doesn't save my profile picture." "The app shows old photos even after updating." "I have to update my photo twice for it to stick." Your engineers investigate, confirm all writes are being correctly saved to the leader, and are baffled. The app IS working. It is just replication lag causing users to read stale data immediately after writing.

This specific problem even has a technical name: **"read-your-own-write" inconsistency** — after you write data, you cannot read your own write back because the read went to a stale replica. It is one of the most common user-visible bugs in systems that use read replicas.

### Solutions to Replication Lag Problems

There are four standard engineering approaches to handle read-your-own-write and other lag-related issues. Each has trade-offs.

| Solution | How It Works | Trade-off |
|----------|-------------|-----------|
| **Sticky sessions after writes** | After a user writes, route ALL of that user's reads to the LEADER for the next N seconds (e.g., 5 seconds). After 5 seconds, followers should have caught up, and we can route to them again. | Adds some read load to the leader, but only temporarily for recently-active users. Usually very manageable. Simple to implement. |
| **Read-from-leader for critical ops** | For operations where stale data is unacceptable (view your own profile, check your own balance), always read from the leader. For non-critical reads (public feeds, trending content), read from followers. | Requires your application to know which operations need freshness guarantees. Leader gets some extra read load. |
| **Replication position tokens** | When a write completes, the leader returns its current replication log position (a number). When the client reads next, it passes this number to the replica. If the replica's current position is behind this number, the replica either waits until it catches up, or the request is re-routed to the leader. | More precise but requires replicas to expose their replication position and requires more coordination. Used by systems like Google's Spanner. |
| **Version/sequence number checks** | Followers advertise their current replication sequence number. The routing layer checks: "is this replica fresh enough for what this client just wrote?" Routes to the freshest available replica above the threshold. Falls back to leader if all replicas are too stale. | Complex routing logic but very precise. Good for systems with heterogeneous workloads. |

The most common production approach is a combination of sticky sessions and operation-based leader routing:

```
function routeReadRequest(userId, operationType, lastWriteTimestamp):
    ────────────────────────────────────────────────────────────────────

    # CHECK 1: Did this user write something recently?
    # If yes, they might be trying to read their own recent write.
    # Route them to the leader to guarantee they see their own data.
    # After 5 seconds, followers should have caught up — safe to use them again.

    secondsSinceLastWrite = currentTime - lastWriteTimestamp

    if secondsSinceLastWrite < 5:
        return LEADER_DATABASE   # ← fresh data guaranteed

    ────────────────────────────────────────────────────────────────────

    # CHECK 2: Is this a "sensitive" operation where stale data is unacceptable?
    # Viewing your own profile: you expect to see what you just updated.
    # Checking your own bank balance: must be accurate.
    # For these: always use the leader regardless of time since last write.

    sensitiveOperations = [
        "view_own_profile",
        "check_own_balance",
        "view_own_order_status",
        "view_own_settings"
    ]

    if operationType in sensitiveOperations:
        return LEADER_DATABASE   # ← stale data here = support ticket

    ────────────────────────────────────────────────────────────────────

    # CHECK 3: Is there a freshness requirement from the caller?
    # Some parts of the code explicitly say "I need data no older than 500ms."
    # Respect that.

    if requiredFreshnessMs is specified:
        freshEnoughReplicas = replicas where currentLagMs <= requiredFreshnessMs
        if freshEnoughReplicas is not empty:
            return leastLoadedReplica(freshEnoughReplicas)
        else:
            return LEADER_DATABASE   # no replica is fresh enough

    ────────────────────────────────────────────────────────────────────

    # DEFAULT: Route to the least loaded follower.
    # For most operations — reading other users' posts, browsing public content,
    # loading trending feeds — a few milliseconds of lag is completely invisible.
    # Use the followers to save the leader for writes.

    return leastLoadedFollower()
```

The insight in this routing logic: you do not need to always read from the leader. That would eliminate the entire benefit of having followers. Instead, you identify the specific cases where stale data genuinely matters — reading your own recently-modified data — and route only those cases to the leader.

---

## Synchronous vs Asynchronous Replication: The Safety Trade-off

When the leader sends a change to its followers, there is a fundamental question that shapes everything: should the leader **wait** for the followers to confirm they have received and stored the change before telling the client "success"? Or should it **immediately** tell the client "success" and update the followers later?

This is the synchronous versus asynchronous replication trade-off. It is one of the most consequential decisions in database architecture because it determines both your performance characteristics and your data loss risk.

### The Paranoid Waiter vs The Trusting Waiter

**Synchronous replication** is like a paranoid waiter at a restaurant. You place your order. The waiter writes it down in the main order book at the front desk. But before walking back to your table to confirm your order, the waiter also walks to the backup order station at the back of the restaurant, writes your order in the backup book there too, and waits for the backup station manager to say "got it, confirmed." Only THEN does the waiter come back to your table and say "your order is confirmed!"

This process takes longer — the waiter had to make two trips before confirming. But if the restaurant burns to the ground right after your order is placed, your order exists in TWO places (front desk AND backup station). Even if the front desk burns, the backup book survives. Your order is not lost.

**Asynchronous replication** is like a trusting waiter. You place your order. The waiter writes it in the main order book and immediately comes back to your table: "your order is confirmed!" Then, when the waiter has a spare moment — maybe 30 seconds later, maybe 2 minutes later — they walk to the backup station and update it.

This is faster — you get your confirmation immediately. But if the restaurant burns down in the 30 seconds between when the waiter confirmed your order and when they got around to updating the backup book, your order exists ONLY in the main book (which burned). The backup book never got it. Your order is lost.

Let's see exactly what this looks like on a timing diagram:

```
SYNCHRONOUS REPLICATION — "wait for all followers before confirming":
─────────────────────────────────────────────────────────────────────────
Client          Leader         Follower 1        Follower 2
  │                │                │                │
  │──── WRITE ────►│                │                │
  │                │                │                │
  │                │──REPLICATE────►│                │
  │                │──REPLICATE────────────────────►│
  │                │                │                │
  │                │◄─── ACK ───────│                │   (follower 1 confirmed)
  │                │◄─── ACK ──────────────────────│    (follower 2 confirmed)
  │                │                │                │
  │◄── SUCCESS ────│                │                │
  │                │                │                │
  Total latency: (leader write) + (network to follower) + (follower write)
                + (network back) = 2× network round-trips
  Guarantee:     Data exists on 3 machines before client gets "success"
─────────────────────────────────────────────────────────────────────────

ASYNCHRONOUS REPLICATION — "confirm immediately, sync later":
─────────────────────────────────────────────────────────────────────────
Client          Leader         Follower 1        Follower 2
  │                │                │                │
  │──── WRITE ────►│                │                │
  │◄── SUCCESS ────│                │                │   ← immediate!
  │                │                │                │
  │                │  (background)  │                │
  │                │──REPLICATE────►│                │
  │                │──REPLICATE────────────────────►│
  │                │                │                │
  Total latency: (leader write) only = 1× network round-trip
  Guarantee:     Data exists on ONLY 1 machine when client gets "success"
                 Followers will get it EVENTUALLY
─────────────────────────────────────────────────────────────────────────
```

The timing difference matters enormously at scale. A synchronous replication round-trip to a follower in the same data center adds 1–5 milliseconds to every write. This sounds tiny, but:

- At 1,000 writes per second (a moderately busy system), 5ms × 1,000 = each second, you're "losing" 5 seconds of capacity waiting for synchronous confirmations
- For a follower in a different city or country, the network round-trip alone adds 50–200 milliseconds per write
- If you have to wait for 3 followers to confirm synchronously, that is 3 network round-trips, potentially 150–600 milliseconds per write

For a social media app handling billions of writes per day, this latency difference is the difference between a fast, responsive system and one that users find slow.

### The Real Risk of Async: Silent Data Loss

Here is the terrifying scenario that async replication creates, stated plainly:

1. User submits a write. Leader writes to disk and responds "success!" to the user.
2. Leader begins sending the replication event to followers in the background.
3. ONE MILLISECOND LATER — before the replication event has been sent — the leader's server crashes. Power outage. Hardware failure. It does not matter why.
4. The followers, which were not yet updated, elect a new leader through a process called **automatic failover**.
5. The new leader does not have the data from step 1. That data was only on the original leader's disk, which is now offline.
6. The user's write is permanently lost.

The user saw "success!" on their screen. They received no error. They have no reason to retry. But the data they submitted does not exist anywhere anymore.

This is not an edge case. In a system with hundreds of servers, servers crash regularly. The probability that a crash happens within milliseconds of a write is low — but the system processes millions of writes, so "low probability" still means it happens. The question is whether it matters.

Most systems use **asynchronous replication for most data,** accepting this risk because the impact is acceptable:

- A social media post: if one post is occasionally lost when a server crashes, the user can re-post. The world does not end.
- A "like" or a view count increment: losing a few hundred likes during a crash is invisible at scale.
- A user preference update (dark mode on/off): losing this occasionally is a minor annoyance, easily rediscovered.

But some systems MUST use synchronous or semi-synchronous replication because the data loss risk is genuinely unacceptable:

- **Bank transactions:** "Transfer $10,000 confirmed" must mean the transfer is permanent. If the leader crashes and the transfer is lost, someone's $10,000 is gone. This is why banks use synchronous replication or database systems with specific durability guarantees.
- **Medical records:** "Patient allergy: penicillin — saved" must be genuinely saved. A lost allergy record could endanger a patient's life.
- **Inventory decrements at checkout:** "Item reserved for your order" must be durable. If the reservation is lost and someone else buys the last item, you have an overselling problem.
- **Legal or regulatory data:** Any data subject to legal requirements (financial audit trails, medical history, identity verification) typically requires guaranteed durability.

### Semi-Synchronous: The Pragmatic Middle Ground

Most production databases offer a third option that tries to capture the best of both extremes. It is called **semi-synchronous replication**, and it is the most common choice in practice for systems that need reasonable durability without sacrificing too much performance.

The rule: **wait for at least ONE follower to confirm before responding to the client.** Other followers sync asynchronously in the background.

```
SEMI-SYNCHRONOUS REPLICATION — "wait for one, then confirm":
─────────────────────────────────────────────────────────────────────────
Client     Leader        Follower 1 (sync)    Follower 2 (async)
  │           │                 │                     │
  │──WRITE───►│                 │                     │
  │           │──REPLICATE─────►│                     │
  │           │◄──ACK ──────────│                     │  ← wait for this one
  │◄─SUCCESS──│                 │                     │  ← then confirm to client
  │           │                 │                     │
  │           │──REPLICATE (background)───────────────►│  ← this one is async
─────────────────────────────────────────────────────────────────────────
```

With semi-synchronous replication:
- Your write exists in at least 2 places (leader + 1 follower) before "success" is returned to the user
- If the leader crashes immediately after confirming, Follower 1 has the data and can be promoted to leader with no data loss
- You only wait for ONE follower, not all of them — so latency is much lower than full synchronous
- The other followers get the data asynchronously — slightly more risk, but they are still receiving it eventually

| Mode | Where Data Is After "Success" | Latency Cost | Data Loss Risk |
|------|------------------------------|--------------|----------------|
| **Fully Synchronous** | All N followers | 2× N network round-trips | None (barring full cluster failure) |
| **Semi-Synchronous** | Leader + 1 follower | 2× 1 network round-trip | Only if both leader AND the synced follower fail simultaneously |
| **Asynchronous** | Leader only (at moment of "success") | 1 network round-trip | Real: leader crash before replication sends = data lost |

Semi-synchronous is the default for MySQL's enhanced semisync plugin, and PostgreSQL's `synchronous_commit = remote_write` setting achieves a similar guarantee. For most production systems — ones that need better-than-async durability but cannot afford full synchronous latency — semi-synchronous is the right default.

The practical rule of thumb:
- **Social media, content platforms, analytics:** Async replication. Fast writes. Occasional data loss is an acceptable business risk.
- **E-commerce, SaaS products, general business apps:** Semi-synchronous. Good durability. Reasonable performance.
- **Banking, healthcare, financial trading, legal records:** Full synchronous. Maximum durability. Performance is secondary.

---

## Multi-Leader Replication: Two Chefs in the Kitchen

Everything covered so far assumes ONE leader — one chef who is the single source of truth for all writes. This is the simplest, safest, and most common setup. But there is a scenario where a single leader creates an unavoidable problem.

**The scenario:** Your product is used by software engineers in San Francisco and Berlin who collaborate in real time on shared technical documents. The only leader database is in San Francisco. Every time a Berlin user types a character in a document, that keystroke has to:

1. Travel from Berlin to San Francisco (150–200 milliseconds)
2. Be processed by the leader database
3. Travel back from San Francisco to Berlin (another 150–200 milliseconds)

Total: 300–400 milliseconds per keystroke. The document editor feels like typing through molasses. Users in Berlin are frustrated, and rightly so. The laws of physics — the speed of light and the distance between cities — are causing this problem.

The instinctive solution: add a second leader in Frankfurt (Germany) for European users. Berlin users write to the Frankfurt leader. San Francisco users write to the US leader. Each leader replicates to the other so both have all the data. Each leader also replicates to its own local followers for read scaling.

This is **multi-leader replication**. And it introduces one of the hardest unsolved problems in distributed systems.

### The Write Conflict Problem

With a single leader, write ordering is simple: writes arrive at the leader one at a time (even if submitted simultaneously, the leader processes them sequentially). There is never ambiguity.

With two leaders, the same data can be updated simultaneously by two different machines in two different continents. They do not know about each other's writes until the replication stream carries the information. By then, a conflict may have already occurred.

```
                US LEADER                          EU LEADER
             (San Francisco)                      (Frankfurt)
          ┌──────────────────┐               ┌──────────────────┐
          │ Alice.manager    │               │ Alice.manager    │
          │                  │               │                  │
          │ T=0: Write       │               │ T=0: Write       │
          │ "Bob" → manager  │               │ "Carol" → manager│
          │                  │               │                  │
          │ Committed: ✓     │               │ Committed: ✓     │
          └────────┬─────────┘               └────────┬─────────┘
                   │                                   │
                   │ ← Replication stream →            │
                   │                                   │
                   ▼                                   ▼
          Receives: "Carol" ← CONFLICT! → Receives: "Bob"

          US Leader had "Bob". Now it hears EU Leader had "Carol" at same time.
          EU Leader had "Carol". Now it hears US Leader had "Bob" at same time.

          BOTH wrote at T=0. NEITHER knew about the other. What is the truth?
```

With single-leader replication, this conflict literally cannot happen because the leader processes writes sequentially. The second write always sees the result of the first write.

With multi-leader, conflict detection is **asynchronous** — you discover the conflict after it has already happened, when the replication streams cross. Both writes were "committed" and both users received "success." Now there is genuine disagreement between the two databases about what the current value is.

### Types of Conflicts — Explained Simply

**Simple value conflict (the most common):** Two leaders update the same field to different values simultaneously. "Alice.manager = Bob" vs "Alice.manager = Carol." The two values directly contradict each other.

**Delete vs Update conflict (the sneaky one):** Leader A deletes a record ("we terminated Bob's employment"). Leader B, not yet knowing about the deletion, simultaneously updates Bob's record ("Bob got a promotion"). Now Leader B is trying to replicate a promotion for an employee that Leader A says no longer exists. What should happen?

**Counter conflict (the mathematically tricky one):** Both leaders increment a shared counter at the same time. US leader: `page_views: 100 → 105` (added 5 US views). EU leader: `page_views: 100 → 103` (added 3 EU views, starting from the same base of 100). Both changes replicate. Which value wins? 105? 103? The correct answer is 108, but simple "take one value" logic cannot get there.

### Conflict Resolution Strategies

When conflicts occur, the system must have a predetermined strategy for resolving them. There is no universally correct answer — the right strategy depends on the data type and business context.

**The pizza order analogy:** You and your roommate share a grocery list app. You both open the list simultaneously (the app is offline, so you each have a local copy). You add "pepperoni pizza" at position 3. Your roommate adds "vegetarian pizza" at position 3. When both devices reconnect and sync — what should the list say?

```
Your version:       Roommate's version:    Resolution options:
─────────────       ─────────────────      ────────────────────────────────
1. Eggs             1. Eggs                LWW (Last Write Wins):
2. Milk             2. Milk                  → "vegetarian pizza" wins if roommate
3. Pepperoni pizza  3. Vegetarian pizza         saved 0.001 seconds later than you
                                              → Your pepperoni silently gone.

                                           First Write Wins:
                                              → "pepperoni pizza" wins (you saved first)
                                              → Roommate's vegetarian silently gone.

                                           Merge (union):
                                              1. Eggs
                                              2. Milk
                                              3. Pepperoni pizza
                                              4. Vegetarian pizza
                                              → Both preserved! But order is ambiguous.

                                           Flag for review:
                                              → App shows both versions and asks user:
                                                "Which version do you want to keep?"
```

| Conflict Resolution Strategy | When It Works Best | Risk |
|-----------------------------|-------------------|------|
| **Last-Write-Wins (LWW):** Take the update with the later timestamp | When conflicts are rare, data is non-critical (social media likes, view counts, analytics). Fast and automatic. | Silently discards data. Users may not know their update was lost. Clocks on different machines are never perfectly synchronized, so "latest timestamp" can be unreliable. |
| **First-Write-Wins:** Take the earlier update, discard the later one | When the first version should be canonical. Seat reservation systems: first to book the seat wins. Prevents double-booking. | Later legitimate updates get discarded. User who was second gets no meaningful error. |
| **Merge / Union:** Keep both changes | When changes are additive and both can coexist. Set operations (add tags, add items to a list), document insertions. | Only works when "both can coexist." Does not work for single-valued fields like "manager name." |
| **Custom Application Logic:** Business-specific rules | When you understand the specific semantics. "For salary data, always use the higher value." "For status fields, use a priority ordering." | Requires writing conflict handlers for every data type. Ongoing maintenance burden. |
| **Flag for Manual Review:** Detect conflict, mark both, surface to human | When correctness is critical and human judgment is needed. Legal documents, medical records, contracts. | Creates operational load. Requires a conflict review UI and process. Does not scale if conflicts are frequent. |

### CRDTs — Data Structures That Cannot Conflict

For certain data types, computer scientists have developed elegant mathematical structures where conflicts are simply impossible by design. These are called **CRDTs — Conflict-free Replicated Data Types.**

The name sounds academic, but the idea is beautifully practical. The key insight: instead of storing a single value (which can conflict), you store a data structure that mathematically encodes "who contributed what." Merging two of these structures is always well-defined, regardless of the order or timing of updates.

**The broken counter problem — and how a CRDT fixes it:**

Your website has a page view counter. You want to track exactly how many people have viewed a page. You have two leaders.

Without a CRDT:
```
Start:  Both leaders have: page_views = 1000

After 1 hour of traffic:
  US Leader: page_views = 1050  (recorded 50 US views)
  EU Leader: page_views = 1030  (recorded 30 EU views, from the same base of 1000)

Replication sync (simple value merge):
  Which value is "correct"? 1050? 1030? Neither!
  Correct answer: 1000 + 50 + 30 = 1080
  Any simple merge strategy loses either 50 or 30 views.
```

With a G-Counter CRDT:
```
Instead of one number, each leader tracks its own contribution:
  counter = { node_id: count_from_this_node }

Start:  Both leaders have: { US: 0, EU: 0 }  →  Total = 0 + 0 = 0

After 1 hour:
  US Leader: { US: 50, EU: 0 }   →  Total = 50
  EU Leader: { US: 0,  EU: 30 }  →  Total = 30

After sync (merge rule: take MAX of each node's value):
  Merged: { US: max(50, 0)=50, EU: max(0, 30)=30 }
  Total = 50 + 30 = 80 ✓

With base count included:
  Merged: { US: 50, EU: 30, base: 1000 }
  Total = 1000 + 50 + 30 = 1080 ✓  CORRECT!
```

The merge rule — take the maximum of each node's contribution — is always correct because each node only ever increments its own slot. The maximum is always the most recent value from that node. This works regardless of the order updates arrive, regardless of network delays, regardless of duplicate messages.

**Why this is mathematically guaranteed to work:**

CRDTs have three properties (you do not need to memorize these names — just understand the concepts they represent):

- **Commutativity:** "US update first, then EU update" gives the same merged result as "EU update first, then US update." Order does not matter. Like addition: 50 + 30 = 30 + 50. This means network message ordering cannot break the system.

- **Associativity:** How you group multiple merges does not matter. "(US + EU) merged with Tokyo" is the same as "US merged with (EU + Tokyo)." This means partial merges and re-merges always produce consistent results.

- **Idempotency:** Applying the same update twice gives the same result as applying it once. If the replication message is accidentally delivered twice (due to a network retry), no harm done. Like "set value to 5": doing it twice is identical to doing it once.

These three properties together mean: CRDTs always converge to the same final state, regardless of message order, timing, or delivery count. No human conflict resolution required. No "last write wins" edge cases. Math handles it.

**The four most common CRDTs in production systems:**

| CRDT Type | What It Stores | Operations | Real-World Use |
|-----------|----------------|------------|----------------|
| **G-Counter** (Grow-only Counter) | A per-node count that only goes up | Increment only | Page views, article likes, download counts, play counts |
| **PN-Counter** (Positive-Negative Counter) | Two G-Counters: one for "adds," one for "removes" | Increment and decrement | Shopping cart quantities, inventory counts, follower counts |
| **G-Set** (Grow-only Set) | A set where items are only ever added | Add only, never remove | Tags on a document, users who viewed a post, upvotes (as a set of voter IDs) |
| **OR-Set** (Observed-Remove Set) | A set with add and remove, where concurrent add+remove is handled correctly | Add and remove | Collaborative document tags (can be added and removed), items in a shared playlist, friend lists |

CRDTs are used in production by: Apple (iCloud Notes uses ORSets for tag collaboration), Redis (several Redis data types are CRDTs), Riak (a database built around CRDTs), and collaborative editing systems like the data layer beneath Google Docs and Figma.

### When Multi-Leader Is the Right Choice — and When It Is Not

Multi-leader replication is one of the most frequently over-used architectural patterns in distributed systems. Engineers reach for it because it sounds powerful ("writes go to multiple leaders!") without fully weighing the operational complexity.

**Multi-leader is the right choice when:**
- You have users in multiple geographic regions who all need to WRITE data with low latency, and that write latency is causing genuine user-facing problems
- The writes in different regions are mostly independent (users mostly edit their own data, not heavily shared data), minimizing conflicts
- You have the engineering capacity to design conflict resolution logic for every data type in your system and maintain it long-term

**Multi-leader is NOT the right choice when:**
- You want to scale your write throughput in a single region. Multi-leader does not multiply your write capacity — both leaders are still writing the same total amount of data. For write throughput scaling, you need sharding.
- Your data has lots of shared mutable state that many users edit simultaneously. Bank balances, inventory counts, anything with heavy contention generates constant conflicts.
- You do not have the engineering capacity to handle conflict resolution. Every multi-leader system needs well-designed conflict handlers for every data type. This is ongoing engineering work, not a one-time setup.
- Your "availability" motivation would be better served by fast automatic failover. A single-leader system with good automatic failover can elect a new leader in 10–30 seconds. For most applications, 30 seconds of write unavailability is acceptable, and it is far simpler than multi-leader.

**The L5/L6 multi-leader conversation:**

An L5 engineer, hearing "we need better database availability," says: "Let's add multi-leader replication. If the primary leader fails, the second leader is already accepting writes. Zero downtime!"

An L6 engineer pauses: "Multi-leader solves geographic write latency, not general availability. What is the specific availability requirement? With automatic leader failover, if the leader goes down, a replica is promoted in 10–30 seconds. Is 30 seconds of write unavailability actually a problem for our use case? If yes — why? What breaks in 30 seconds that cannot handle a retry? And if we go multi-leader: who owns the conflict resolution logic when something breaks at 2am? What is the plan for conflicts in our financial transaction data?"

The L6 insight: most "I want better availability" requests are satisfied by fast failover, not by multi-leader. Multi-leader solves the specific problem of "users in multiple regions need low-latency writes that do not go through a distant central leader." If that is not the actual problem, multi-leader is not the solution — it is just added complexity.

---

## Leaderless Replication: Democracy, Not Monarchy

Both leader-follower and multi-leader replication designate at least one server as a "leader" with special authority. What if we eliminated the concept of leadership entirely?

In **leaderless replication**, every node is equal. Any node can accept write requests directly from clients. Any node can serve read requests. There is no designated primary. There is no failover process because there is no leader to fail over from.

Instead of leadership, leaderless systems use **quorum voting** to ensure that reads always see up-to-date data.

### The Jury Analogy for Understanding Quorums

A jury needs a majority to reach a verdict. Imagine a 12-person jury. The judge requires 7 jurors to agree before rendering a verdict. Why 7? Because 7 is more than half of 12. Any two groups of 7 people, drawn from the same 12, must have at least 2 people in common. This "overlap" property is what makes the system work.

In database terms, quorum conditions use three numbers:
- **N** = the total number of replica nodes (the jury size)
- **W** = the number of nodes that must confirm a write for it to be considered durable (the write quorum)
- **R** = the number of nodes you must read from and compare before trusting a read result (the read quorum)

The quorum rule is: **W + R > N**

When W + R > N, the set of nodes you wrote to and the set of nodes you read from MUST overlap — they must share at least one common node. That shared node participated in the last write and has the freshest data. When you read from R nodes and compare their answers, the node that was in both the write set and read set will return the latest version.

**A concrete walkthrough:**

```
System: N=3 nodes, W=2 (write quorum), R=2 (read quorum)
W + R = 4 > N = 3  ✓  Quorum condition met.

─────────────────────────────────────────────────────────────────────
WRITE "birthday_selfie.jpg":
─────────────────────────────────────────────────────────────────────
Client sends write to ALL 3 nodes simultaneously.

  Node 1: "Written! ✓"  (fast response)
  Node 2: "Written! ✓"  (fast response)
  Node 3: (no response yet — network delay)

W=2 nodes confirmed. Quorum achieved. ✓
Client gets: "Success! Your photo was updated."
(Node 3 will eventually receive the write when its network recovers.)

─────────────────────────────────────────────────────────────────────
READ (moments later):
─────────────────────────────────────────────────────────────────────
Client sends read to ALL 3 nodes simultaneously.

  Node 1: Returns "birthday_selfie.jpg", version=5  ← freshest
  Node 2: Returns "birthday_selfie.jpg", version=5  ← freshest
  Node 3: Returns "old_headshot.jpg", version=4     ← stale (missed the write)

R=2 nodes responded with consistent answer (version 5).
Client uses version 5: "birthday_selfie.jpg" ✓

─────────────────────────────────────────────────────────────────────
WHY THE QUORUM GUARANTEES FRESHNESS:
─────────────────────────────────────────────────────────────────────
  Write set (W=2): {Node 1, Node 2}
  Read set  (R=2): System must query all 3, majority of 2 = {Node 1, Node 2}

  Overlap = {Node 1, Node 2} ∩ {Node 1, Node 2} = {Node 1, Node 2}
  This overlap is NOT empty. ✓

  At least one node in the read set participated in the write.
  Therefore, at least one node returns the fresh data.
  The client takes the highest-version response.
─────────────────────────────────────────────────────────────────────
```

**What about different W and R values?**

Setting W=1, R=1 (when N=3): W + R = 2 ≤ 3 = N. Quorum NOT met. You could write to Node 1 and then read from Node 3 without any overlap. Stale data is possible. This configuration gives maximum speed but no consistency guarantee.

Setting W=3, R=3 (when N=3): W + R = 6 > 3 = N. Strong consistency. BUT now writes require all 3 nodes to confirm — if any node is down, writes fail. Very strong consistency but reduced availability.

Setting W=2, R=2 (when N=3): W + R = 4 > 3. Good balance. Can tolerate 1 node being down for both reads and writes. Still guarantees overlap.

This tunability — being able to dial W and R based on your specific consistency vs. availability needs — is a significant advantage of leaderless systems. Amazon's DynamoDB literally exposes W and R as parameters you configure per request.

### Comparing All Three Replication Styles

| Property | Leader-Follower | Multi-Leader | Leaderless |
|----------|----------------|-------------|-----------|
| **Write conflict risk** | None — leader serializes all writes | High — concurrent writes to different leaders cause conflicts | Low — quorum prevents most, but "sloppy" quorums can have edge cases |
| **Read simplicity** | Simple — read from any follower | Good — read from local followers | Moderate — must read from R nodes and reconcile versions |
| **Write availability** | Limited by leader — leader must be up | High — any leader can accept writes | High — quorum of N nodes must be available, but no single point of failure |
| **Automatic failover** | Yes, with a new leader election (10–30 sec) | Yes, per region (complex) | Not needed — no leaders to fail over |
| **Conflict complexity** | None | High — requires conflict resolution logic for all data | Low — quorum handles most cases; version vectors handle the rest |
| **Operational complexity** | Low | High | Medium |
| **Best for** | Most OLTP, general applications, default choice | Multi-region collaborative apps with independent write workloads | High-availability key-value stores, IoT, always-on write requirements |
| **Production examples** | MySQL, PostgreSQL, MongoDB primary | CockroachDB, Google Spanner | Cassandra, DynamoDB, Riak, Voldemort |

---

## Read Replicas: The Practical Way You Will Use Replication

All of the concepts above — leader-follower, quorums, conflict resolution — are important to understand. But in your daily life as an engineer, replication most commonly shows up in one practical form: **read replicas.**

A read replica is a follower node that you configure your application to route read traffic toward. It is the first and simplest form of database horizontal scaling. If you work at a startup, you will almost certainly add read replicas before you ever touch sharding.

### The More Cashiers at Checkout Analogy

When a grocery store gets unexpectedly busy on a Saturday afternoon, they do not build a new store. They do not redesign their supply chain. They open more checkout lanes — they call more cashiers to come help out. More cashiers serving customers simultaneously. The process is identical for every checkout lane, but now 8 lanes are running in parallel instead of 2. Queue time drops dramatically.

Read replicas are exactly this for your database. Your read process (query data → format result → return to client) is identical on every replica. But now 4 replicas are handling read requests in parallel instead of 1. The queue of waiting read requests disappears.

### Capacity Math: When Read Replicas Actually Help

Working through actual numbers makes this concept concrete. Let us use a realistic scenario.

**Your system today (before growth):**
- Total queries per second: 10,000 QPS
- Your server's maximum capacity: 15,000 QPS before performance degrades
- Breakdown of traffic: 500 QPS are writes, 9,500 QPS are reads
- You have plenty of headroom. CPU at 65%. Life is good.

**After your product goes viral (3× growth in 2 months):**
- Total queries: 30,000 QPS
- Writes: 1,500 QPS (3× growth — users are creating more content)
- Reads: 28,500 QPS (3× growth — users are consuming more content)
- Your single server handles 15,000 QPS. You are at 2× capacity. Pages are loading slowly. Errors are spiking.

**Diagnosing the bottleneck:**
- Write load: 1,500 QPS out of 15,000 max = 10% of your capacity used by writes. Writes are NOT the bottleneck.
- Read load: 28,500 QPS and you only have 15,000 total capacity. Reads ARE the problem.
- Conclusion: This is a read bottleneck. Read replicas will solve it.

**The read replica solution:**
- Add 3 read replicas. Each can handle 10,000 QPS.
- Route all writes to the primary (leader): 1,500 QPS out of 15,000 capacity = 10%. No problem.
- Route all reads to the 3 replicas: 28,500 QPS across 3 replicas = ~9,500 QPS per replica. Well within their 10,000 QPS capacity.

```
                      ════════════════════════════
                           APPLICATION SERVER
                      ════════════════════════════
                                  │
                      ┌───────────┴───────────┐
                      │                       │
               WRITE TRAFFIC             READ TRAFFIC
               (1,500 QPS)               (28,500 QPS)
               5% of traffic             95% of traffic
                      │                       │
                      ▼                       ▼
           ┌─────────────────┐    ┌───────────────────────┐
           │   PRIMARY       │    │    LOAD BALANCER       │
           │   (Leader)      │    └──────────┬────────────┘
           │                 │               │
           │ 1,500 writes/s  │    ┌──────────┼──────────┐
           │ out of 15,000   │    │          │          │
           │ max capacity    │    ▼          ▼          ▼
           │                 │  ┌──────┐  ┌──────┐  ┌──────┐
           │ (10% utilized)  │  │Rep 1 │  │Rep 2 │  │Rep 3 │
           └──────┬──────────┘  │      │  │      │  │      │
                  │             │9,500 │  │9,500 │  │9,500 │
            Replication         │QPS   │  │QPS   │  │QPS   │
            stream ─────────────►      │  │      │  │      │
                                └──────┘  └──────┘  └──────┘
                                  Total read capacity: 30,000 QPS
                                  Your read load:      28,500 QPS
                                  Buffer remaining:     1,500 QPS ✓
```

You have gone from "system is on fire" to "comfortable headroom" by adding three servers and a load balancer. No code changes. No data migration. No architectural redesign. This is why read replicas are the first tool engineers reach for when facing a read bottleneck.

### Three Pitfalls of Read Replicas

Adding read replicas is not as simple as "add more servers and everything just works." There are three specific traps that engineers fall into, especially the first time they add replicas to a production system.

**Pitfall 1: Connection Pool Math**

Every database connection is like a phone call between your application server and your database server. It takes time to establish (the "handshake"), so instead of opening a new connection for every query, applications maintain a "connection pool" — a set of pre-established connections that are reused. Typical connection pool size: 10–100 connections per application server instance.

Before replicas: 1 database server. Each app server maintains 50 connections to it. With 10 app servers: 10 × 50 = 500 total database connections. PostgreSQL default maximum: 100 connections. You would already be over the limit! (This is why connection poolers like PgBouncer exist — but that is a detail for another section.)

After adding 3 replicas: Now each app server needs connection pools for the primary AND each replica. 10 app servers × (50 connections × 4 databases) = 2,000 total connections. Your database servers hit their connection limits quickly.

The analogy: you are a manager who can keep 50 conversations going simultaneously. You hire 3 more managers (replicas). Now YOU have 4 people to coordinate with, and coordination itself takes overhead.

Solutions: Use a connection pooler (like PgBouncer for PostgreSQL) that multiplexes many application connections onto fewer actual database connections. Or reduce connection pool size per database proportionally when adding replicas.

**Pitfall 2: The Slow Replica Trap**

You have 3 replicas. Replica 1 has a fast NVMe SSD. Replicas 2 and 3 have older spinning hard disk drives. Replica 1 answers queries in 5ms. Replicas 2 and 3 take 400–500ms.

Your load balancer uses round-robin routing (send each incoming request to the next server in sequence: 1, 2, 3, 1, 2, 3...). Replicas 2 and 3 look perfectly healthy to the load balancer — they accept connections, they respond to health checks, they return correct data. The load balancer has no way to know they are slow.

Result: 2/3 of your read traffic hits slow replicas. Users experience random 400–500ms latency spikes on 66% of requests. The pattern appears random, which makes it hard to debug. Users complain about "sometimes slow, sometimes fast" performance. Support tickets pile up.

The fix: health checks that measure actual query latency, not just "can I make a TCP connection?" Periodically run a test query against each replica (something like `SELECT 1`) and measure the response time. If a replica is responding in 500ms when others respond in 5ms, remove it from the load balancer rotation or drastically reduce its traffic share.

This is called **latency-aware health checking.** Most modern load balancers support it, but it requires explicit configuration — the default is often just "is the server accepting connections?"

**Pitfall 3: Replication Lag Variance**

Not all replicas fall behind the leader at the same rate. At any given moment:
- Replica 1 might be 10ms behind (very fresh)
- Replica 2 might be 150ms behind (slightly stale)
- Replica 3 might be 2,000ms behind (2 seconds stale — was just restarted and catching up)

If your load balancer uses round-robin, 1/3 of your reads hit Replica 3, which is 2 seconds stale. Users who are unlucky enough to be served by Replica 3 see data that is 2 seconds out of date — unpredictably, apparently randomly.

The fix is **lag-aware routing**: check each replica's current replication lag before routing to it. Skip replicas that are too far behind for the request being made.

```
function findBestReplica(maxAcceptableLagMs):
    ────────────────────────────────────────────────────────────────

    # Get the current replication lag of every replica.
    # Lag = how many milliseconds behind the leader the replica currently is.
    # Most databases expose this as a metric: seconds_behind_master (MySQL)
    # or replay_lag (PostgreSQL).

    eligibleReplicas = []

    for each replica in ALL_REPLICAS:
        currentLag = replica.getCurrentReplicationLagMs()

        if currentLag <= maxAcceptableLagMs:
            # This replica is fresh enough for this request
            eligibleReplicas.append(replica)
        else:
            # This replica is too stale — skip it
            log("Skipping {replica}: lag={currentLag}ms > threshold={maxAcceptableLagMs}ms")

    ────────────────────────────────────────────────────────────────

    # If ALL replicas are too stale, fall back to reading from the leader.
    # This is safe but adds read load to the leader.
    # If this happens frequently, your replicas are chronically lagging
    # and you need to investigate why.

    if eligibleReplicas is empty:
        ALERT("All replicas exceeding lag threshold — falling back to leader")
        return PRIMARY_LEADER

    ────────────────────────────────────────────────────────────────

    # Among the fresh-enough replicas, pick the one with the lightest current load.
    # "Load" can be measured as active connections, CPU utilization, or query queue depth.

    return eligibleReplicas.sortedByCurrentLoad().first()

─── EXAMPLE USAGE ────────────────────────────────────────────────

# For reading a social media feed — 5 seconds of lag is fine, the user
# won't notice if a post is 5 seconds delayed in appearing.
replica = findBestReplica(maxAcceptableLagMs=5000)

# For reading a user's own profile immediately after they updated it —
# maximum acceptable lag is 0ms (read from leader to guarantee freshness)
replica = findBestReplica(maxAcceptableLagMs=0)
# This will always return the primary leader, which is correct.

# For reading a product's current inventory in a checkout flow —
# 500ms lag is acceptable (small window of stale data)
replica = findBestReplica(maxAcceptableLagMs=500)
```

The `maxAcceptableLagMs` threshold should be different for different operations in your application. This is the key insight: there is no one-size-fits-all answer. Your engineering judgment determines what "fresh enough" means for each specific use case.

---

## When to Use Each Replication Style — Decision Guide

After walking through all the detail, here is the simplified decision guide. Print this out. Put it on your wall. Reference it in interviews.

```
┌────────────────────────────────────────────────────────────────────────────┐
│              REPLICATION STYLE DECISION GUIDE                              │
│                                                                            │
│  Q1: Do you need writes to happen in multiple geographic regions           │
│      with low write latency? (users in Tokyo AND London both writing)      │
│               │                                                            │
│     ┌─────────┴────────┐                                                   │
│    YES                 NO                                                  │
│     │                  │                                                   │
│     ▼                  ▼                                                   │
│  MULTI-LEADER       Q2: Do you need maximum write availability —           │
│  (accept the            even if 2 out of 3 nodes go down,                 │
│  conflict              writes must still work?                             │
│  complexity)                    │                                          │
│                      ┌──────────┴──────────┐                              │
│                      YES                   NO                             │
│                       │                    │                               │
│                       ▼                    ▼                               │
│                  LEADERLESS         LEADER-FOLLOWER                        │
│                  (Cassandra/        (default choice —                      │
│                  DynamoDB style)    90% of systems)                        │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘
```

**Leader-follower** is the correct default for the vast majority of systems. Simple. Well-understood. Supported by every major database. No conflict resolution logic needed. Easy to reason about. Add read replicas when read load grows. Handle replication lag with appropriate routing logic. Use semi-synchronous replication for reasonable durability. This is what GitHub, Shopify, Airbnb, Stripe, and thousands of other production systems use.

**Leaderless** (Cassandra or DynamoDB style) is the right choice when your system must continue accepting writes even during significant node failures, or when you need very high write throughput with tunable consistency. Common in IoT systems, event sourcing pipelines, high-throughput analytics ingestion, and always-on applications where any period of write unavailability is unacceptable.

**Multi-leader** is the right choice in the specific case of genuinely independent write workloads in different geographic regions, where write latency to a distant single leader is causing real user-facing problems. This is uncommon, complex, and should be approached with extreme caution.

---

## Chapter Summary: Part A Complete

You have covered the full landscape of database replication — from why we need it, to how each style works mechanically, to when to use each one, to what can go wrong.

**The key ideas in one paragraph:**

Replication means keeping multiple copies of your data on different servers. The most common form — leader-follower — has one server accepting all writes and multiple copies serving reads. Adding read replicas is the first thing you do when your database is getting overwhelmed with read traffic, because each additional replica roughly doubles your read capacity. The main risk is replication lag: copies fall slightly behind the original, causing users to briefly see stale data. You handle this with routing logic that sends fresh-data-critical reads to the leader and lag-tolerant reads to the fastest available replica.

**The five replication concepts and their one-line descriptions:**
- **Leader-follower:** One writer, many readers. Simple. The default for 90% of systems.
- **Synchronous replication:** Wait for followers before confirming success. Safe but slower.
- **Asynchronous replication:** Confirm immediately, sync later. Fast but risks losing recent writes.
- **Multi-leader:** Multiple writers, complex conflicts. Use only for geo-distributed independent write workloads.
- **Leaderless:** No special nodes, quorum voting ensures freshness. Use for maximum write availability.

**The golden rule:**

Always optimize queries, add indexes, add caching, and consider vertical scaling before adding read replicas. Always add read replicas before considering sharding. Sharding is a last resort.

---

*Part B (Chapter 21, Part B) covers sharding in depth: how to split your data across multiple machines, how to choose the right split key, what happens when your split creates "hot spots," how to perform a resharding operation without taking your system down, and how to answer sharding questions in system design interviews with the precision of a senior engineer.*

---

## Deeper Dive: Replication in Practice — Putting It All Together

The sections above taught you the mechanics of each replication style in isolation. Real systems combine these concepts. Let's walk through two real-world scenarios that show how all the pieces fit together.

### Scenario 1: A Growing E-Commerce Site

**Starting situation:**
An online bookstore starts with one PostgreSQL database. It runs fine for two years. Then a major book club recommends the site, and traffic triples in a month.

**Diagnosis:**
The engineering team looks at metrics:
- Database CPU: 85% sustained (too high — leaves no headroom for traffic spikes)
- Read/Write ratio: 94% reads (browsing books, reading reviews), 6% writes (placing orders, writing reviews)
- Query time p95 (the slowest 5% of queries): 2.3 seconds (unacceptable — users are waiting)
- Slow query log: the top 3 slowest queries are all missing indexes on the `books.author` and `books.genre` columns

**Step 1 — Add indexes (do this first, always):**
The team adds indexes on `author` and `genre`. These two changes take 10 minutes to implement and deploy. Results: p95 query time drops from 2.3 seconds to 340ms. CPU drops from 85% to 52%. The immediate crisis is resolved.

**Step 2 — Add caching (do this second):**
The team notices that 70% of all page views are for the same 500 most popular books. Instead of hitting the database every time, they add Redis caching with a 10-minute TTL (time-to-live — after 10 minutes, the cached data expires and the next request re-fetches from the database). This reduces database read traffic by 60%. CPU drops further to 30%.

**Six months later — traffic has grown 5×:**
The caching and indexes bought time, but now the site is growing steadily. CPU is back at 70%. Read queries are again slow during peak hours (evenings, weekends).

**Step 3 — Add read replicas:**
The team adds 2 PostgreSQL read replicas. They configure the application to route all read queries (browsing catalog, searching, viewing reviews) to the replicas, and write queries (placing orders, posting reviews) to the primary.

They implement:
- Sticky read-after-write routing: for 10 seconds after a user posts a review, their reads go to the primary (so they see their own review immediately)
- Lag-aware routing: replicas with >500ms lag are removed from the rotation
- Latency health checks: replicas responding in >100ms are flagged

Results: CPU on the primary drops to 15% (it only handles writes). Each replica handles 40% of their capacity. Plenty of headroom.

**The architectural journey in one diagram:**
```
YEAR 1: Single server
  [PostgreSQL] ← all reads and writes

YEAR 2: Add indexes + caching (no new servers)
  [Redis Cache] → hit for 70% of reads
  [PostgreSQL] ← 30% of reads + all writes
                   + proper indexes now

YEAR 3: Add read replicas
  [Redis Cache] → hit for 70% of reads
  [Load Balancer] → routes remaining reads to replicas
       │
  ┌────┼────┐
  │    │    │
  ▼    ▼    ▼
[Rep1][Rep2][Primary] ← writes only
```

Notice the sequence: each step was triggered by genuine need, not by anticipating future scale. The team did not add replicas on Day 1. They did not add replicas immediately when traffic grew — they added indexes first. They did not add sharding when replicas were added — reads are still the bottleneck, not writes. This is textbook senior engineering judgment.

---

### Scenario 2: The Instagram Moment — When You Have Minutes, Not Days

Sometimes you do not have the luxury of a careful diagnosis. The TechCrunch article scenario from the beginning of this chapter is real. What do you actually DO when your single server is collapsing under traffic and you need to act in the next two hours?

Here is a realistic playbook:

**Minutes 0–5: Stop the bleeding**
- Temporarily enable aggressive caching: set cache TTL to 5 minutes for everything, even user-specific content. Yes, some users will see stale data. This is better than everyone seeing a 504 error.
- Turn off non-essential background jobs (sending notification emails, computing recommendations, generating analytics). Free up database capacity for user-facing requests.
- Scale up the single machine (vertical scaling): most cloud providers let you resize a server in minutes. Double the RAM and CPU cores immediately.

**Minutes 5–30: Spin up a read replica**
Most managed database services (AWS RDS, Google Cloud SQL, Azure Database) let you add a read replica with a few clicks. The replica begins copying data from the primary. This takes 20–60 minutes for a small database. While it is syncing:

- Reconfigure your application to route reads to the replica once it is ready. This usually means changing one configuration variable and redeploying your app.
- Adjust your load balancer to split traffic once the replica is available.

**Hour 1: Replica is live**
Route 80% of reads to the replica. Monitor CPU and query times on both servers. The primary should drop significantly.

**Day 2 and beyond: Proper diagnosis**
Once the fire is out, do the proper work: add missing indexes, implement Redis caching, analyze traffic patterns. You may find that two replicas instead of one is sustainable long-term, or that aggressive caching reduces load enough that the replica can be downsized.

The lesson: in a crisis, the sequence is (1) buy time with caching and vertical scaling, (2) add a read replica as fast as possible, (3) do the real work once you have breathing room.

---

## Automatic Failover: What Happens When the Leader Dies

We have talked about leaders and followers extensively, but there is one important scenario we have not fully covered: what happens when the leader itself dies?

A server can die from:
- A hardware failure (power supply, memory, CPU)
- A software crash (database process terminates unexpectedly)
- A network partition (the server is still running but cannot be reached)
- A disk failure (the data volume becomes corrupted or unreadable)
- A planned shutdown (software upgrade, maintenance)

When the leader dies, followers cannot receive new replication events. Clients trying to write to the leader get connection errors. The system is in a degraded state: reads still work (from followers) but writes are blocked.

**The failover process:**

Step 1 — Detect the leader failure. This is done by a combination of: followers monitoring whether they are still receiving replication events (if not for 30 seconds, something is wrong), a health-check process sending heartbeat requests to the leader, and the leader itself broadcasting a "I am alive" heartbeat.

Step 2 — Elect a new leader. When followers agree the leader is unavailable, they run an election protocol to choose which follower becomes the new leader. The most common approach: the follower that is most up-to-date (the one with the smallest replication lag at the time of failure) is chosen. This minimizes data loss.

Step 3 — Reconfigure clients. The application layer must start sending writes to the new leader. This is typically handled by a configuration update that points the write connection to the new leader's address.

Step 4 — The old leader rejoins (if it recovers). When the original leader comes back online, it must NOT immediately try to be the leader again. The data it has might be slightly ahead of the new leader (if there were writes in-flight when it crashed). The old leader must join as a follower, accept the new leader's replication stream, and catch up. If the old leader's in-flight data conflicts with what the new leader accepted, those writes are discarded — which is why synchronous or semi-synchronous replication is important for write durability.

**The split-brain problem:**

There is a dangerous failure mode called **split-brain**: the leader appears to have failed (due to a network issue), followers elect a new leader, but the original leader is still actually running and accepting writes from some clients. Now there are TWO nodes both acting as leader, both accepting writes to the same data — creating diverging versions.

When the network partition heals, both "leaders" discover each other and have conflicting data. This is extremely difficult to resolve automatically.

Solutions: **STONITH (Shoot The Other Node In The Head)** — a process that, when a new leader is elected, actively terminates the old leader (powers it off remotely) to ensure it cannot continue accepting writes. Also: consensus protocols like **Raft** or **Paxos** that use strict majority voting to ensure only one leader can be elected at a time.

Tools like etcd (used by Kubernetes) and Consul implement Raft consensus and are often used to manage database leader election in production.

```
NORMAL OPERATION:
                [Leader] ──replicates──► [Follower 1]
                    ↑                    [Follower 2]
                    │
                 Clients send
                 writes here

LEADER FAILURE DETECTED:
                [Leader] ✗ (unreachable)
                [Follower 1] ← elected as new leader (most up-to-date)
                [Follower 2] ← becomes follower of Follower 1

                Clients are redirected to Follower 1 for writes.

SPLIT BRAIN (dangerous — avoid with proper consensus):
                [Leader] ← still running! (network partition, not actual crash)
                    ↑
                Some clients still writing here (old config)

                [Follower 1] ← also elected as leader
                    ↑
                Other clients writing here (new config)

                RESULT: Two leaders. Diverging data. Data loss inevitable.
```

Typical automatic failover time in well-configured production systems: 10–30 seconds from failure detection to new leader being available for writes. During this time, write requests fail. In most applications, 30 seconds of write unavailability is tolerable (requests can be retried). In some (financial trading, real-time systems), it is not — which is why those systems use more sophisticated consensus protocols with faster failure detection.

---

## The Full Replication Decision Checklist

Here is the complete decision checklist to work through before making any replication architecture decision. Use this in interviews — it shows systematic thinking.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│         REPLICATION ARCHITECTURE DECISION CHECKLIST                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  STEP 1: UNDERSTAND THE BOTTLENECK                                          │
│  □ What is the actual symptom? (slow reads / slow writes / timeouts /       │
│    high CPU / high storage usage)                                           │
│  □ What is the read:write ratio? (most systems are >90% reads)              │
│  □ What is the current QPS and what is the server's max capacity?           │
│  □ Have you looked at the slow query log? Are there missing indexes?        │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  STEP 2: TRY THE SIMPLE SOLUTIONS FIRST                                     │
│  □ Add missing database indexes on frequently-queried columns               │
│  □ Rewrite the top 5 slowest queries                                        │
│  □ Add Redis/Memcached caching for the most frequently-read data            │
│  □ Vertical scaling: upgrade to a larger instance type                      │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  STEP 3: REPLICATION STYLE SELECTION                                        │
│  □ Single region, mostly reads → Leader-Follower with read replicas         │
│  □ Multi-region, independent geo-specific writes → Multi-Leader             │
│    (confirm: are conflicts acceptable? do you have conflict resolution?)    │
│  □ Maximum write availability, no acceptable downtime → Leaderless          │
│    (confirm: is eventual consistency acceptable for your use case?)         │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  STEP 4: REPLICATION MODE SELECTION                                         │
│  □ Async: social data, analytics, content — occasional data loss OK         │
│  □ Semi-sync: e-commerce, SaaS — reasonable durability without full latency │
│  □ Sync: financial, healthcare, legal — data loss is unacceptable           │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  STEP 5: REPLICATION LAG HANDLING                                           │
│  □ What is the acceptable lag threshold for each operation type?            │
│  □ Does your application need read-your-own-write guarantees?               │
│  □ Which operations require reading from the leader?                        │
│  □ How will you monitor replica lag in production?                          │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  STEP 6: OPERATIONAL READINESS                                              │
│  □ How long does automatic failover take? Is that acceptable?               │
│  □ Is there a process to prevent split-brain during leader election?        │
│  □ How will you handle connection pool sizing with multiple replicas?       │
│  □ What is the runbook when a replica falls too far behind?                 │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

In a system design interview, walking through this checklist — even abbreviated — signals that you are thinking like a senior engineer who has actually operated these systems, not a student who memorized definitions.

---

## Real Numbers to Know for Interviews

System design interviews reward candidates who can reason with real numbers. Saying "replication lag is usually small" is weaker than saying "replication lag is typically 5–50ms in the same data center, and 150–200ms cross-continent." Here are the numbers to internalize:

**Replication lag benchmarks:**
- Same data center, healthy system: 1–50 milliseconds typical
- Cross-region (e.g., US East to US West): 60–100 milliseconds (speed of light over ~3,000 miles)
- Cross-continent (e.g., US to EU): 150–200 milliseconds
- Under heavy write load: can spike to seconds temporarily
- After a follower restart: can lag by minutes while catching up

**Database capacity guidelines (rough order of magnitude):**
- A single PostgreSQL instance: handles roughly 5,000–50,000 QPS depending on query complexity and hardware
- A single MySQL instance: similar range
- With read replicas: roughly N × single-instance capacity for reads (N = number of replicas)
- Write capacity is unchanged with replicas: still limited to the leader's capacity

**Automatic failover timing:**
- Detection: 5–30 seconds (how long before followers notice the leader is gone)
- Election: 1–5 seconds (choosing the new leader among followers)
- Reconfiguration: 5–30 seconds (clients reconnecting to the new leader)
- Total: 10–60 seconds in typical production setups
- With specialized consensus protocols (Raft/etcd): as fast as 3–10 seconds

**Connection pool sizing:**
- Typical pool size per application server per database: 10–50 connections
- PostgreSQL default max connections: 100 (very low — always increase this)
- Practical PostgreSQL max with PgBouncer pooler: 1,000–10,000 concurrent clients

**When to add read replicas:**
- Your database CPU is sustained above 70%
- Read query latency p95 is above your SLA
- Your read:write ratio is above 80:20 (reads dominate)
- Vertical scaling has been maxed out or would be disproportionately expensive

**When NOT to add read replicas (add sharding instead):**
- Your write QPS is exceeding the leader's capacity (replicas cannot help writes)
- Your total data volume exceeds what fits on a single machine
- Your write latency p95 is unacceptable (replicas do not reduce write latency)

Knowing these numbers lets you say things like: "At 3× growth, we go from 10,000 to 30,000 QPS. With our current 15,000 QPS capacity, we need roughly 2 additional replicas to handle the read load. Since our write QPS is only 1,500 — well within the leader's 15,000 QPS capacity — replication is the right tool and sharding is not yet needed."

That is a complete, specific, defensible answer. It is what earns senior-level credit in system design interviews.

---

## Tying It All Together: A Full Worked Example

Let us walk through a complete, realistic scenario from beginning to end. This is the kind of problem that appears in senior engineering interviews, and working through it with the concepts from this chapter shows how everything connects.

**The problem:** Design the database layer for a ride-sharing app (like Uber). The app has two main tables: `trips` (every ride, its route, timestamps, driver ID, rider ID, fare) and `users` (user profiles, payment info, ratings). The app currently has 500,000 users and processes 10,000 trips per day. It is growing at 20% per month.

**Questions to answer:**
1. What replication strategy should we use today?
2. What replication mode (sync/async/semi-sync) for which data?
3. How do we handle the read-your-own-write problem for trip status updates?
4. At what point should we consider sharding (covered in Part B, but worth noting the trigger)?

---

**Answer:**

**Today's access pattern analysis:**

The `trips` table: Riders check their trip status frequently while en route (every 5–10 seconds). This is almost purely reads. Drivers submit location updates every 5 seconds — this is writes. A completed trip generates one final write (updating status to "completed"). At 10,000 trips per day with trips averaging 20 minutes, roughly 700 trips are concurrent at peak. Each active trip generates ~12 reads/minute (rider checking status) and ~12 writes/minute (driver location updates).

Total QPS estimate:
- Reads: 700 concurrent trips × 12 reads/min ÷ 60 sec = ~140 reads/sec during peak
- Writes: 700 concurrent trips × 12 writes/min ÷ 60 sec = ~140 writes/sec during peak

This is well within the capacity of a single PostgreSQL instance (~5,000–15,000 QPS). Today, no scaling infrastructure is needed beyond a well-indexed single server.

**Replication strategy for today (and near future):**

Use leader-follower replication with 2 read replicas. Rationale:
- The app will grow 20% monthly. In 6 months, traffic will be ~3× today. In 12 months, ~6×.
- At 6× growth: reads = 840/sec, writes = 840/sec. Still manageable on a single leader with replicas serving reads.
- The replicas also provide disaster recovery: if the primary fails, a replica is promoted and rides-in-progress can continue.

**Replication mode selection (sync/async/semi-sync):**

Trip status updates (driver location, fare changes): **semi-synchronous.**
- Reason: a rider's app showing "driver is 2 blocks away" when the driver is actually stuck in traffic is a bad user experience. The data should be relatively fresh. Semi-sync ensures at least one replica has the update before responding.
- Acceptable lag: up to 500ms (the app updates location every 5 seconds — 500ms lag is invisible)

Payment data (fare, payment confirmation): **synchronous.**
- Reason: "Your $18.50 fare has been charged" must be a genuine confirmation. If the leader crashes after confirming but before replicating, the charge record could be lost — this is a billing integrity problem. Synchronous replication ensures the payment record exists in two places before the user sees "payment confirmed."

User profiles (name, photo, rating): **asynchronous.**
- Reason: a user's star rating changing from 4.7 to 4.8 does not need to be instantly visible everywhere. If a replication event for a rating update is briefly lost, the user's rating can be recomputed from the trips table on the next read. Low stakes, high volume, async is appropriate.

**Handling the read-your-own-write problem:**

When a driver marks a trip as "completed," the rider's app should immediately show "trip completed — please rate your driver." If the rider's read hits a lagged replica, they still see "in progress" — confusing.

Solution: When the trip status changes to "completed" on the leader, the driver's app receives confirmation, and the trip ID is added to a short-lived "recently completed" list (stored in Redis, with 10-second TTL). When the rider's app next polls trip status:

1. Check Redis: "is this trip ID recently completed?"
2. If yes: route the read to the leader (guaranteed fresh data)
3. If no: route to any available replica

This routes to the leader only for 10 seconds after completion, covering the replication window without putting sustained extra load on the leader.

**When to start thinking about sharding:**

At 20% monthly growth, you will hit these thresholds in roughly:
- 18 months: ~10× growth → trips table will have ~60 million rows. Still manageable on one server with proper indexing.
- 36 months: ~100× growth → trips table will have ~600 million rows. Total trips per day ~1 million. Peak concurrent trips ~70,000. Peak write QPS from driver location updates: ~14,000 writes/sec. This is where a single leader's write capacity becomes the bottleneck.

At that point — roughly 3 years from now at current growth — consider sharding the `trips` table by geographic region (each city or region is its own shard). Driver location updates in New York go to the New York shard. Trips in London go to the London shard. Most queries are naturally geographic: "what is the trip status for ride 12345?" is fully answered by one shard. Cross-shard queries (aggregate statistics, platform-wide analytics) can be served from a separate analytics system that ETLs data from all shards.

The user profiles table (500,000 rows today, maybe 50 million in 3 years) will remain small enough for a single server for much longer. Users are not write-heavy — profile updates are rare.

This full analysis — access pattern breakdown, QPS estimation, replication mode selection per data type, lag handling strategy, and a forward-looking sharding trigger — is what a senior engineer produces when asked "design the database for a ride-sharing app." It is specific, reasoned, and shows awareness of both the technical choices and the operational trade-offs.

---

## The Write-Ahead Log (WAL) — The Backbone of Replication

We mentioned the WAL (Write-Ahead Log) earlier as the mechanism that makes replication work. Because it is so fundamental, it deserves its own careful explanation. Understanding the WAL unlocks not just replication, but also crash recovery, point-in-time restores, and database backups.

### What is a WAL, Really?

The WAL is a sequential log file — think of it like a journal or diary — that the database writes to before making any change to its actual data files.

**Why "write-ahead"?** Because you write to the log AHEAD of (before) changing the actual data. The sequence is always:

1. Write the intended change to the log
2. THEN apply the change to the actual data files

This ordering is critically important. Here is why:

Imagine you are updating a row in a database table. The update involves several steps: read the old row, compute the new values, write the new row, update any related indexes. This takes multiple disk operations. What if the server crashes in the middle — say, after the row is updated but before the indexes are updated? The data is now inconsistent: the row and the index disagree about what exists.

With the WAL, before any of those steps, you first write to the log: "I intend to update row 456 with values X, Y, Z." If the server crashes mid-operation, when it restarts, it reads the WAL and sees the incomplete operation. It can replay the operation from the WAL entry and finish it correctly. The actual data files are always recoverable from the WAL.

```
WITHOUT WAL (dangerous):
─────────────────────────────────────────────────────────────
Step 1: Read old row 456 from disk
Step 2: Compute new values
Step 3: Write new row 456 to disk  ← CRASH HERE
Step 4: Update index for row 456   ← never happens
─────────────────────────────────────────────────────────────
Result: Row 456 has new values, but index points to old location.
        Data is INCONSISTENT. Recovery is complex or impossible.

WITH WAL (safe):
─────────────────────────────────────────────────────────────
Step 0: Write to WAL: "PLAN: Update row 456 to values X,Y,Z"
Step 1: Read old row 456 from disk
Step 2: Compute new values
Step 3: Write new row 456 to disk  ← CRASH HERE
Step 4: Update index for row 456   ← never happens
─────────────────────────────────────────────────────────────
On restart:
  1. Database reads WAL: "found incomplete operation: update row 456"
  2. Database replays steps 3 and 4 from the WAL entry
  3. Data is now consistent
  Result: Zero data loss, full recovery.
```

The chef analogy: Chef Maria always writes in her scratch notepad BEFORE cooking. If she gets pulled away mid-recipe, she can look at the notepad and pick up exactly where she left off. The notepad is her WAL.

### How the WAL Enables Replication

Here is the key insight: the WAL is not just for crash recovery. It is also the perfect replication mechanism. Every change to the database is already recorded in the WAL as a structured log entry. To replicate to a follower, the leader simply streams those WAL entries to the follower.

The follower receives WAL entries and "replays" them — applies them to its own data files in the same order. The follower's data becomes a mirror of the leader's data, because both started from the same initial state and both applied the same sequence of WAL entries.

```
LEADER                          FOLLOWER
──────────                      ────────
WAL file:                       Receives WAL stream:
  entry #1: INSERT user Alice     #1: INSERT user Alice
  entry #2: UPDATE Alice.age=22   #2: UPDATE Alice.age=22
  entry #3: DELETE user Bob       #3: DELETE user Bob
  entry #4: INSERT user Carol     #4: INSERT user Carol

Leader's database after replaying entries 1-4:
  Users table: {Alice(age=22), Carol}

Follower's database after replaying entries 1-4:
  Users table: {Alice(age=22), Carol}

IDENTICAL STATE. ✓
```

PostgreSQL calls this mechanism **WAL streaming replication.** MySQL calls the equivalent mechanism **binary log (binlog) replication** — the binlog is MySQL's version of the WAL. MongoDB uses an **oplog (operations log)** for the same purpose. All three are variations of the same idea: a sequential log of all changes, streamed to followers.

**Replication position:** Each entry in the WAL has a position number (PostgreSQL calls this the LSN — Log Sequence Number). Followers track which position they have applied up to. When you check replication lag, you are comparing the leader's current LSN to each follower's current LSN. The difference tells you how "behind" the follower is.

```
Leader current LSN:       1,847,392
Follower 1 current LSN:   1,847,390  → lag = 2 entries (maybe 5ms)
Follower 2 current LSN:   1,847,100  → lag = 292 entries (maybe 200ms)
Follower 3 current LSN:   1,843,000  → lag = 4,392 entries (follower was restarted, catching up)
```

This is what your monitoring dashboard shows when you look at "replication lag." The LSN difference is converted to an approximate time based on how fast new WAL entries are being generated.

### WAL for Point-in-Time Recovery (PITR)

As a bonus concept: because the WAL is a complete sequential record of every change ever made to the database, you can use it to restore the database to any point in the past. If you take a full backup every night, and keep all WAL files since then, you can:

1. Restore from last night's backup
2. Replay all WAL entries from midnight until exactly 2:47 PM
3. Your database is now in the exact state it was at 2:47 PM

This is called **PITR — Point-in-Time Recovery.** It is how you recover from "someone ran DELETE FROM orders WHERE status='pending' and forgot the WHERE clause and deleted all orders, not just pending ones." You restore from backup and replay WAL up to 1 second before the bad query ran.

---

## Monitoring Replication Health in Production

Understanding replication architecturally is one thing. Operating it in production requires knowing what to monitor and what to do when metrics go out of range. This section bridges the gap between theory and day-to-day engineering.

### The Four Metrics That Matter

**Metric 1: Replication Lag (in milliseconds or seconds)**

This is the single most important metric for a replicated database. It tells you how stale your follower data is.

Healthy range: 0–100ms in the same data center. Alert if it exceeds 1 second. Page someone (wake them up if it's 3am) if it exceeds 30 seconds.

How to check in PostgreSQL:
```
-- On the primary (leader):
SELECT
  application_name,  -- which follower is this?
  state,             -- streaming, catchup, etc.
  sent_lsn,          -- last WAL position sent to follower
  write_lsn,         -- last position follower wrote to its WAL
  flush_lsn,         -- last position follower flushed to disk
  replay_lsn,        -- last position follower applied to data files
  write_lag,         -- time delay for writes
  flush_lag,         -- time delay for flushes
  replay_lag         -- time delay for replay (the one you usually care about)
FROM pg_stat_replication;
```

**Metric 2: Replication Slot Retention (GB)**

Replication slots are a mechanism that ensures the leader keeps WAL files until followers have processed them. If a follower goes offline, the leader must keep accumulating WAL files — because when the follower comes back, it needs all the missed entries.

If a follower is offline for a long time, the leader's disk fills up with retained WAL files. Alert if replication slot retention exceeds 10 GB. Drop the replication slot if the follower has been offline for more than 24 hours (after confirming the follower is genuinely gone, not temporarily).

**Metric 3: Follower Query Latency (p50, p95, p99)**

Are queries on the follower actually fast? A follower can be "up to date" on replication but still be slow for reads due to disk issues, CPU pressure, or poor query planning. Monitor query latency on each follower independently. If one follower is consistently 10× slower than others, investigate disk or CPU issues.

**Metric 4: Failover Readiness**

For each follower: how long would it take to promote this follower to leader right now? What is the data loss risk (how many seconds of WAL would be lost)? Run a failover drill quarterly in staging — actually promote a follower to leader and verify everything works — so you know your process works before you need it in a real crisis.

### The Runbook for Common Replication Problems

**Problem: Replica lag is growing steadily (20ms → 100ms → 500ms over an hour)**

Diagnosis: The follower is falling behind. Why?
- Is the follower's CPU above 80%? If yes: it is processing replications slowly because it is overloaded. Solution: reduce read traffic to this follower, or upgrade its hardware.
- Is there a large transaction running on the leader? If yes: the follower is applying a massive batch operation. Solution: wait for it to complete.
- Is the replication network congested? If yes: investigate network between leader and follower.

**Problem: Replica is offline — lag shows as "unknown" or null**

Diagnosis: The follower has disconnected from the replication stream.
- Check if the follower process is running
- Check follower logs for error messages
- If the follower's disk filled up: clear space, restart replication
- If the leader's WAL files were already cleaned up (leader didn't know follower was offline): follower needs to resync from a full backup

**Problem: After promoting a follower to leader, some recent writes are missing**

Diagnosis: The promoted follower was slightly behind the old leader at the time of the crash.
- If using async replication: expected. The writes in the lag window are lost.
- If using semi-sync: should not happen (1 follower should have been up to date). Investigate why semi-sync was not properly configured.
- Resolution: accept the data loss, notify affected users, restore from backup if the gap is larger than expected.

---

## Common Interview Questions and Strong Answers

Here are the five most common replication questions in system design interviews, with the kind of answers that signal senior-level thinking:

**Q: "How would you scale Instagram's database to handle 100M users?"**

Weak answer: "Add more servers and use replication."

Strong answer: "First I'd characterize the access pattern. Instagram is massively read-heavy — a user scrolling their feed generates dozens of reads per second but maybe one write per minute. So the bottleneck is almost certainly reads. I'd start with leader-follower replication with 3–5 read replicas, route feed reads to replicas, and route writes (post creation, likes, follows) to the primary. I'd implement read-after-write routing to prevent ghost-profile bugs. I'd add Redis caching for the most popular accounts' post lists — the top 1% of accounts generate 50%+ of reads, and caching their data eliminates massive database load. Only if writes become the bottleneck — which would happen if we hit millions of writes per second — would I consider sharding."

**Q: "What is replication lag and how do you handle it?"**

Weak answer: "It is when the replica is behind the leader. You wait for it to catch up."

Strong answer: "Replication lag is the delay between when the leader commits a write and when followers apply it. Typically 5–50ms in the same data center, 150–200ms cross-region. It becomes a problem in two specific scenarios: read-your-own-write (user updates their profile, immediately reads it back, sees the old version) and cross-user coordination (user A writes, user B reads the same data from a lagged replica). The read-your-own-write problem I handle with session-based routing: for 5–10 seconds after a write, route that user's reads to the leader. For most other reads, route to any replica below a configured lag threshold. For operations that always need freshness (balance checks, inventory in checkout), always route to the leader regardless."

**Q: "What is the difference between synchronous and asynchronous replication?"**

Weak answer: "Synchronous waits for confirmation; async doesn't."

Strong answer: "The difference is the durability contract. Async: leader responds 'success' after writing to its own disk, followers sync in background. Fast, but if the leader crashes before syncing, the write is lost — the user saw 'success' but the data is gone. Synchronous: leader waits for at least one follower to confirm before responding. Guarantees the write exists in two places at the moment the client sees 'success.' Adds network round-trip latency — 5ms same-region, 150ms cross-region. Semi-synchronous — waiting for exactly one follower — is the practical middle ground most production systems use. Financial transactions need synchronous. Social media likes can tolerate async."

**Q: "When would you use leaderless replication (like Cassandra) instead of leader-follower?"**

Weak answer: "Cassandra is good for high availability."

Strong answer: "Leaderless replication shines when write availability is the top priority and eventual consistency is acceptable. With a leader, if the leader goes down, writes are blocked for 10–30 seconds during failover. With leaderless quorums — say W=2, R=2, N=3 — you can lose any one node and still accept writes. You need a majority, not a specific node. This is valuable for: IoT data ingestion where you cannot afford to lose events even for 30 seconds, analytics event pipelines, and systems where any write downtime causes data gaps. The trade-off: reads require reading from multiple nodes and reconciling versions, which adds complexity and latency. And eventual consistency means different clients might briefly see different data — acceptable for a sensor reading, not acceptable for a bank balance."

**Q: "Explain what a CRDT is and when you'd use one."**

Weak answer: "It is a data structure that handles conflicts automatically."

Strong answer: "A CRDT — Conflict-free Replicated Data Type — is a data structure designed so that concurrent updates from multiple nodes can always be merged deterministically, without conflicts and without coordination. They achieve this by representing state in a way that encodes 'who contributed what' rather than just the current value. A G-Counter, for example, stores a per-node count instead of a single total: {node_A: 50, node_B: 30}. Merging two G-Counters is just taking the max of each node's value — always correct, always conflict-free. CRDTs are useful when you have multi-leader replication or leaderless replication and need a specific data type to behave correctly under concurrent updates. Real uses: collaborative document editing (character insertions are OR-Sets), distributed counters (G-Counters for page views), and replicated sets (shopping carts that can be modified on multiple devices). They are not a general solution — they only work for specific data types with specific semantics."

---

---

## What You Should Be Able to Do Now

After reading Part A of this chapter, you should be able to do all of the following. If any of these feel unclear, re-read the relevant section before moving to Part B.

**Explain the problem replication solves:**
- Describe the "hug of death" scenario and why a single server fails under viral traffic
- Explain why read replicas solve a read bottleneck but do NOT solve a write bottleneck
- Explain why sharding is needed when replication is not enough

**Explain leader-follower replication step by step:**
- Describe what happens to a write from the moment the client sends it to the moment followers apply it
- Explain what the WAL is and why writes go to the WAL before the actual data files
- Explain why leader-follower eliminates write conflicts while multi-leader does not

**Explain replication lag with a concrete example:**
- Describe the ghost profile bug and explain exactly why it happens
- Name three real causes of replication lag
- Describe two specific strategies for handling read-your-own-write problems

**Compare synchronous, asynchronous, and semi-synchronous replication:**
- Give an example of data that requires synchronous replication (and why)
- Give an example of data where asynchronous replication is acceptable (and why)
- Explain what semi-synchronous buys you over async and what it costs you over sync

**Explain multi-leader replication and conflict resolution:**
- Describe a scenario where multi-leader is the right choice
- Describe what a write conflict is with a concrete example
- Explain last-write-wins and when it is and is not appropriate
- Explain what a CRDT is and give one example (G-Counter)

**Explain leaderless replication:**
- Define N, W, and R and explain the quorum condition W + R > N
- Explain with a 3-node, W=2, R=2 example why the quorum guarantees freshness
- Name one database that uses leaderless replication (Cassandra, DynamoDB, Riak)

**Make replication decisions for a given scenario:**
- Given a system description, identify whether the bottleneck is reads or writes
- Choose between leader-follower, multi-leader, and leaderless for a given use case
- Choose between sync, async, and semi-sync for a given data type
- Describe what monitoring you would set up for a replicated database

---

## Self-Test Questions

Answer these before moving to Part B. Cover your notes and try to answer from memory. Then check.

1. Your social media app has 1,000 QPS of reads and 50 QPS of writes. Your database is hitting 85% CPU. What is the first thing you should investigate before adding replicas?

2. A user updates their email address and immediately clicks "Account Settings" to verify it changed. They see the old email address. Explain exactly what happened and how you would prevent it.

3. You have N=5 nodes with W=3, R=3. Does W + R > N? If a write goes to nodes 1, 2, 3 — what read sets guarantee you see the fresh data?

4. A Berlin engineer and a New York engineer both update the same document field at the same time in a multi-leader system. What is this called? Name two strategies for resolving it.

5. You have 3 read replicas. Replica C has been falling further behind for 20 minutes and is now 8 seconds stale. Your load balancer is still sending it 33% of reads. What should you do and why?

6. What is the WAL and why does the database write to it BEFORE applying changes to actual data files?

7. Your boss says "let's use asynchronous replication for our payment transaction database so writes are faster." What do you say?

8. Name the four purposes of replication (not just "so we don't lose data").

**Answers (do not peek until you have tried each one):**

1. Check the slow query log for missing indexes and inefficient queries. Optimization costs nothing and often gives 10–100× speedup.
2. Replication lag. The write went to the leader. The read went to a lagged follower. Solution: for 5–10 seconds after a write, route that user's reads to the leader.
3. W + R = 6 > 5 = N. ✓ Any read set of 3 from {1,2,3,4,5} that overlaps with write set {1,2,3} — i.e., any read set containing at least one of node 1, 2, or 3.
4. A write conflict. Strategies: Last-Write-Wins (discard one), Merge (combine both if possible), Flag for manual review.
5. Remove Replica C from the load balancer rotation or reduce its weight to near-zero. 8 seconds of lag means users hitting Replica C see data that is 8 seconds old. Investigate why it is lagging (disk pressure? network? heavy load?).
6. The WAL ensures crash recovery. If the server crashes mid-operation, the database replays the WAL on restart and completes any incomplete operations. Without WAL, a crash during a multi-step operation could leave data in an inconsistent state.
7. With async replication, if the leader crashes in the milliseconds after writing to disk but before replicating to followers, the payment record is permanently lost — even though the user received "payment confirmed." Payment data requires synchronous or semi-synchronous replication.
8. Durability (data survives hardware failures), Availability (system stays up when nodes fail), Read Scaling (multiple copies serve reads in parallel), Latency Reduction (copies placed close to users).

---

## A Note on What Comes Next

Part A has covered everything about replication: why we do it, how it works mechanically (WAL, replication streams, follower catch-up), the three replication styles (leader-follower, multi-leader, leaderless), the three replication modes (sync, async, semi-sync), the operational challenges (replication lag, ghost writes, slow replicas, connection pool math), and the engineering judgment required to choose between them.

The chapter established one key boundary: replication scales reads and improves availability. It does NOT help when writes are the bottleneck, or when your data is too large for any single machine.

Part B tackles the second major scaling tool: **sharding** — splitting your data across multiple machines so that both write load and storage scale horizontally. Part B covers:

- How to choose what to shard on (the "shard key" or "partition key" decision — arguably the most consequential choice in sharding)
- Range-based sharding versus hash-based sharding: trade-offs explained with concrete examples
- What a "hot shard" is, why it happens, and how to fix it
- How cross-shard queries work and why they are expensive
- How to rebalance shards when your traffic distribution changes
- How to perform a live resharding operation without downtime
- How Cassandra, DynamoDB, MongoDB, and Vitess each approach sharding
- The full interview answer for "how would you shard Twitter's tweet database?"

If you feel solid on everything in Part A — the self-test questions are a good gauge — you are ready for Part B. If any of the self-test answers felt uncertain, spend 15 minutes re-reading the relevant section. The concepts in Part A are the foundation that Part B builds directly on top of.

One more thought before you move on: the most valuable thing this chapter can give you is not a list of facts. It is a way of thinking. When someone asks "how would you scale this database?", the senior engineer's instinct is to ask:

- What is actually slow right now? (reads or writes?)
- Have we tried the simple things? (indexes, caching, bigger machine)
- What is the read:write ratio? (mostly reads → replicas first)
- What are the durability requirements? (bank data needs sync; social data can be async)
- What happens in the failure cases? (leader dies → how long until failover? what data is lost?)

That sequence of questions, applied systematically, leads to better decisions than any memorized "best practice." Good luck with Part B.

---

*End of Chapter 21, Part A — Replication.*
*Next: Chapter 21, Part B — Sharding.*

---

> **Key Terms Introduced in This Chapter (Part A)**
>
> **Core Concepts**
> - **Read:** Retrieving existing data from the database (viewing a post, loading a profile page)
> - **Write:** Creating or modifying data in the database (posting a photo, updating a bio)
> - **Replication:** Keeping multiple identical copies of your database on different servers
> - **Sharding:** Splitting your database into independent pieces, each stored on a different server
> - **Hug of Death:** When sudden viral traffic overwhelms a system not designed for scale
>
> **Leader-Follower Replication**
> - **Leader (Primary):** The single database node that accepts all write operations
> - **Follower (Replica/Secondary):** A copy of the leader's data that serves read requests
> - **WAL (Write-Ahead Log):** A sequential log file where every database change is recorded before being applied, enabling recovery and replication
> - **Replication Stream:** The continuous flow of change events sent from the leader to its followers
> - **Replication Lag:** The delay between when the leader writes data and when followers apply that change
>
> **Consistency Trade-offs**
> - **Synchronous Replication:** Leader waits for all follower confirmations before responding to client. Maximum durability, higher latency.
> - **Asynchronous Replication:** Leader responds to client immediately; followers sync in the background. Minimum latency, small data loss risk.
> - **Semi-synchronous Replication:** Leader waits for ONE follower to confirm, others sync asynchronously. Pragmatic balance.
> - **Read-your-own-write:** The consistency guarantee that after you write data, your own subsequent reads will see that data (not stale data from a lagged replica)
>
> **Multi-Leader Replication**
> - **Write Conflict:** When two leaders simultaneously modify the same record in incompatible ways
> - **Last-Write-Wins (LWW):** Conflict resolution where the most recent timestamp wins; the other update is discarded
> - **CRDT (Conflict-free Replicated Data Type):** A data structure mathematically designed so concurrent updates can always be merged without conflicts
> - **G-Counter:** A CRDT for counting that only goes up; each node tracks its own contribution separately
> - **PN-Counter:** A CRDT for counting that goes up and down; implemented as two G-Counters
> - **OR-Set:** A CRDT set that supports both add and remove operations with correct handling of concurrent add+remove
>
> **Leaderless Replication**
> - **Leaderless Replication:** Every node is equal; reads and writes use quorum voting instead of a designated leader
> - **Quorum:** A sufficient majority of nodes (defined by W + R > N) that guarantees the read and write node sets overlap
> - **N, W, R:** Total nodes, write quorum size, read quorum size — the three parameters that define consistency in a leaderless system
>
> **Operational Concepts**
> - **Connection Pool:** A set of pre-established database connections maintained by the application to avoid the overhead of opening new connections per query
> - **Lag-aware Routing:** A read routing strategy that avoids sending requests to replicas whose replication lag exceeds an acceptable threshold
> - **Latency-aware Health Checking:** Monitoring replicas not just for "is it alive" but "is it responding within acceptable time"
> - **Automatic Failover:** The process by which a new leader is automatically elected when the current leader becomes unavailable

# Chapter 21 — Replication and Sharding (Simplified)
# Part B: Sharding

---

# Part 2: Sharding — Splitting Your Data When One Database Isn't Enough

---

## Why Replication Doesn't Fix Everything

You just learned about replication. Replication makes COPIES of your database. You have one leader that accepts writes, and several followers that keep identical copies and serve reads. Pretty great, right?

Here is the problem: every single copy has ALL of the data.

Think about what that means:

- If your dataset is 10 terabytes (TB), every replica is also 10 TB. You cannot store 10 TB on an 8 TB disk. Adding more replicas does not help — they all need 10 TB of disk each.
- ALL writes still go to ONE leader. That one leader is the only machine that accepts new data. If your leader can handle 20,000 writes per second and your app now needs 50,000 writes per second — you are stuck. There is no replica you can add that changes this. The leader is the bottleneck.
- Replication scales READS (more copies = more people can read at the same time). It does not scale WRITES or STORAGE.

This is not a flaw in replication. Replication was never designed to solve write scaling or storage problems. It is designed to improve availability and spread read traffic. Once you need to scale writes or storage, you need something different.

That something different is called sharding.

---

### The Moving Truck Analogy

Imagine you are moving out of a 1-bedroom apartment. You have a lot of stuff. You rent three moving trucks to help.

Here is the thing: having three trucks does not help you pack faster. There is still only ONE apartment to empty. Three drivers show up, but there is only one set of boxes to load. The drivers have to take turns — or they trip over each other.

The three trucks help once the boxes are packed, because three drivers can each carry a truckload at the same time. That is read scaling — more people carrying boxes to the destination simultaneously.

But the PACKING (the writes) is still limited by one apartment.

Now imagine a different scenario: instead of one apartment, you have three smaller apartments. Each apartment has one-third of your stuff. You assign one truck to each apartment. All three drivers pack and load simultaneously, completely independently.

Now you are packing three times as fast. That is sharding.

```
REPLICATION (3 trucks, 1 apartment):
                              [REPLICA A]   <- read traffic
                             /    (same 10TB copy)
[LEADER]  ---- copies ----> [REPLICA B]   <- read traffic
(10TB)                       \    (same 10TB copy)
  ^                            [REPLICA C]   <- read traffic
  |                                (same 10TB copy)
ALL WRITES must come here
(still bottlenecked at 1 machine)

Problem: if leader can do 20k writes/sec, you are stuck at 20k.
Problem: if data is 10TB, every machine needs 10TB disk.


SHARDING (3 trucks, 3 apartments):

[SHARD 0]  <- User IDs 0-2.5M    <- writes for users 0-2.5M
(2.5TB)

[SHARD 1]  <- User IDs 2.5M-5M   <- writes for users 2.5M-5M
(2.5TB)

[SHARD 2]  <- User IDs 5M-7.5M   <- writes for users 5M-7.5M
(2.5TB)

[SHARD 3]  <- User IDs 7.5M-10M  <- writes for users 7.5M-10M
(2.5TB)

Each shard only stores 25% of data.
Each shard only handles 25% of writes.
All 4 shards work simultaneously and independently.
```

This is the fundamental difference:

- Replication: one big box of all data, copied three times. Reads can spread out. Writes cannot.
- Sharding: one big box SPLIT into four smaller boxes. Reads AND writes spread across all four. Each machine only knows about its own quarter of the data.

The cost is complexity. With one database, everything is simple. With sharding, your application has to know which shard to talk to. Queries that touch multiple shards become harder. Transactions that span shards become painful. You trade simplicity for scale.

---

## The Evolution: From 1 Database to a Sharded System

Nobody starts with sharding. You start with one database and add complexity only when you are forced to. Here is the typical journey.

---

### Stage 1: The Happy Single Database

Your startup launches. You have 100,000 users. Your database is a single PostgreSQL instance running on a server.

Numbers:
- Writes: 500 per second
- Reads: 5,000 per second
- Storage: 20 GB
- Database machine: 4 CPU cores, 32 GB RAM, 500 GB SSD

Everything fits on one machine with room to spare. Life is WONDERFUL.

Here is what you can do that you will later miss:

- JOIN queries between any two tables. Want to find all orders along with the customer name? One SQL query. Done.
- Transactions. Move money from Account A to Account B. If anything goes wrong, rollback. The database handles all of this for you automatically.
- Foreign keys. The database enforces that every order has a valid user ID. No orphaned data.
- Aggregations. "How many users signed up this month?" One query. Instant answer.
- You can see all your data in one place. You can run complex analytics. You can change your schema without a migration plan that involves 16 machines.

You sleep well at night.

```
Stage 1: Single Database

  [Your App]
      |
      v
 [PostgreSQL]
 Users table
 Orders table
 Products table
 (everything here)

 Writes: 500/sec    <- comfortable
 Reads: 5,000/sec   <- comfortable
 Storage: 20 GB     <- lots of headroom

Life is simple.
```

---

### Stage 2: Read Bottleneck — Add Replicas

Your app gets featured in a popular tech article. Downloads spike. Signups explode. Three months later:

- Writes: still 2,000 per second (people are signing up and posting, but most activity is reading)
- Reads: 50,000 per second (everyone is reading everyone else's posts)
- Storage: 200 GB

Your single database can handle about 15,000 reads per second. You are now at 50,000. Your app is slow. Pages time out. Users are angry.

The fix: read replicas. You add 4 followers. Your leader handles all writes plus its share of reads. Each replica handles a share of the read traffic.

- Leader: 2,000 writes/sec + 2,000 reads/sec (kept a little headroom)
- Each of 4 replicas: 12,000 reads/sec each (48,000 reads total spread across them)
- Total read capacity: ~50,000 reads/sec. Problem solved.

The data is still in ONE logical database. Every machine has a complete copy. You just have four copies instead of one, and you send readers to different copies.

```
Stage 2: Read Replicas Added

  [Your App]
     /    \
   writes  reads (spread across)
     |      \___________
     v                   \
 [LEADER]          [REPLICA 1]
 Writes: 2,000/sec  Reads: 12,000/sec
 Reads:  2,000/sec
                    [REPLICA 2]
                     Reads: 12,000/sec

                    [REPLICA 3]
                     Reads: 12,000/sec

                    [REPLICA 4]
                     Reads: 12,000/sec

Total read capacity: ~50,000/sec. Problem solved!
Data is still 200GB on every machine (5 x 200GB = 1TB total disk used).

This works until... writes grow too.
```

---

### Stage 3: The Uncomfortable Middle (Write Bottleneck)

Two years pass. Your app keeps growing. Now:

- Writes: 18,000 per second (your leader can handle about 20,000)
- Storage: 1.8 TB (your server only has a 2 TB disk — getting close)
- Reads: fine, you added more replicas

You are approaching two walls simultaneously:
1. Your leader is almost maxed out on writes. A traffic spike could push you over 20,000 writes/sec and your system degrades.
2. Your dataset will hit 2 TB within months. When it does, you cannot add data anymore.

Your options:

**Option A: Vertical Scaling**
Buy a bigger machine. A server with 8 CPU cores instead of 4. More RAM. A 4 TB SSD instead of 2 TB. This buys you time. But there are limits — you can only make machines so powerful before they become astronomically expensive. And even a $50,000 machine has limits. This is a temporary fix.

**Option B: Functional Partitioning**
Put different tables on different databases. Users table on Database 1. Orders table on Database 2. Messages table on Database 3. Each database only has a subset of the data.

This works, but it is "cheating" in a sense — you are just organizing your schema into separate databases. Each database still has to handle ALL users' data for whatever tables it owns. If you have 10 million users and the Users table is the bottleneck, moving Orders to a different machine does not help the Users table at all.

**Option C: Sharding**
Split the Users table itself across multiple databases. Each database gets a subset of users. This is true horizontal scaling.

```
Stage 3: The Uncomfortable Middle

  [LEADER]          Status: 18,000 writes/sec
  Users table        Disk: 1.8TB of 2TB used
  Orders table       <- DANGER ZONE
  Messages table

Add more replicas? Won't help. All writes still come here.
Buy bigger machine? Buys time but has limits.
Shard? Yes, but it's complex...
```

---

### Stage 4: Sharding

You make the decision. You are going to shard the Users table.

You have 10 million users. You decide to split them across 4 shards based on user ID:

- Shard 0: User IDs 0 to 2,499,999 (2.5 million users)
- Shard 1: User IDs 2,500,000 to 4,999,999 (2.5 million users)
- Shard 2: User IDs 5,000,000 to 7,499,999 (2.5 million users)
- Shard 3: User IDs 7,500,000 to 9,999,999 (2.5 million users)

Now when user ID 12345 (on Shard 0) logs in, your app goes to Shard 0. When user ID 8,000,000 (on Shard 3) updates their profile, your app goes to Shard 3. These happen simultaneously, on different machines, with no coordination needed.

- Each shard handles roughly 4,500 writes/sec (18,000 / 4)
- Each shard stores roughly 450 GB (1.8 TB / 4)
- You went from ONE machine handling everything to FOUR machines splitting the load

But now consider this query: "Show me all users who signed up between March 1 and March 15."

If user IDs are assigned sequentially (each new user gets the next available ID), then March users might all have IDs around 9,800,000 to 9,850,000. Those are all on Shard 3. Good — one shard.

But if your date-based query crosses shard boundaries, you have to ask ALL 4 shards and combine the results. That is a "cross-shard query." It takes 4× as long and is significantly more complex. This is the main pain of sharding — you trade simplicity for scale.

```
Stage 4: Sharding

Query: "Update profile for User 12345"
  -> App computes: 12345 / 2,500,000 = Shard 0
  -> App talks directly to Shard 0
  -> Fast. Only 1 database involved.

Query: "Update profile for User 8,000,000"
  -> App computes: 8M / 2,500,000 = Shard 3
  -> App talks directly to Shard 3
  -> Fast. Only 1 database involved.

Query: "All users who signed up in March 2024"
  -> Which shard has March 2024 signups?
  -> Could be ANY shard (depends on ID assignment)
  -> Must ask all 4 shards
  -> Combine and sort results in application code
  -> Slower. Complex.

[Shard 0]  [Shard 1]  [Shard 2]  [Shard 3]
  2.5M       2.5M       2.5M       2.5M
  users      users      users      users
  450GB      450GB      450GB      450GB
  4.5K       4.5K       4.5K       4.5K
 writes/s   writes/s   writes/s   writes/s

Total writes: 4 x 4,500 = 18,000/sec. All handled. Problem solved.
Total storage: 4 x 450GB = 1.8TB. Spread across machines. Problem solved.

Life is more complex, but at least it works.
```

---

## The Three Ways to Split Data: Hash, Range, and Directory

Now that you understand WHY sharding exists, you need to understand HOW to split data across shards. There are three main strategies, and each has very different strengths and weaknesses.

Let's start with an analogy that applies to all three.

---

### The Classroom Assignment Analogy

Imagine a principal has 100 students and 4 classrooms. She needs to assign each student to exactly one classroom. How should she do it?

**Method 1 — By student ID number:**
"Take your student ID. Divide it by 4. Whatever the remainder is, that's your classroom number."
Student ID 1247 → 1247 % 4 = 3 → Classroom 3.
Student ID 2068 → 2068 % 4 = 0 → Classroom 0.

This is HASH sharding. Very fair distribution (roughly 25 students per room), but you cannot say "put all honor students together" — they are scattered randomly.

**Method 2 — By last name:**
"Last names A-F go to Room 1. G-M go to Room 2. N-S go to Room 3. T-Z go to Room 4."

This is RANGE sharding. Easy to find someone by last name: "Smith? That's N-S, Room 3." But if 60% of students have last names starting with A-F, Room 1 is overcrowded while Room 4 is nearly empty.

**Method 3 — By a list:**
"Here is a handwritten book: Alice → Room 3. Bob → Room 1. Charlie → Room 2. Diana → Room 4..."

This is DIRECTORY sharding. Completely flexible. You can put whoever you want wherever you want. But someone has to maintain that book, and if the book is lost, nobody can find their classroom.

Let's look at each method in detail.

---

### Strategy 1: Hash-Based Sharding

Take a user's ID. Run it through a hashing function — a mathematical blender that takes any number as input and spits out a (seemingly) random different number. Then take the result modulo the number of shards (the "remainder when divided by" operation).

```
User ID 12345  ->  hash()  ->  9,847,362  ->  % 4  ->  2  ->  Shard 2
User ID 99999  ->  hash()  ->  2,184,597  ->  % 4  ->  1  ->  Shard 1
User ID 55000  ->  hash()  ->  6,723,011  ->  % 4  ->  3  ->  Shard 3
User ID 77777  ->  hash()  ->  1,309,884  ->  % 4  ->  0  ->  Shard 0
```

Because hashing is designed to produce uniformly distributed outputs (the results look random even for similar inputs), the data spreads evenly. Shard 0, 1, 2, and 3 each get roughly 25% of users. No shard ends up stuffed while another is empty.

```
Hash-Based Sharding — Visual

4 Users being assigned to shards:

User 12345 -> [HASH] -> Shard 2   [Shard 0]  [Shard 1]  [Shard 2]  [Shard 3]
User 99999 -> [HASH] -> Shard 1      User       User       User       User
User 55000 -> [HASH] -> Shard 3     77777      99999      12345      55000
User 77777 -> [HASH] -> Shard 0
                                   ~25%       ~25%       ~25%       ~25%
                                   each       each       each       each

Result: Even distribution. No hot spots by default.
```

**Pros of Hash Sharding:**

Even distribution: like shuffling a deck of cards — the data lands fairly randomly across all shards. No single shard hogs all the data.

No lookup table needed: to find user 12345, you just run the same hash function and modulo. The shard number is computed instantly. Your app does not need to ask any external service "where does user 12345 live?" It just knows.

Simple to implement: one function call. That is it.

**Cons of Hash Sharding:**

Range queries are terrible. "Show me all users who signed up in 2023" — users from 2023 are scattered across ALL 4 shards. Their IDs are random-looking because hash sharding destroys any natural ordering. You have to ask all 4 shards, collect all the results, merge them, sort them, and return the combined answer. This is called a "scatter-gather" query. With 4 shards it is 4× the work. With 64 shards it is 64× the work.

And adding new shards is a nightmare. We will explain this separately below because it is important.

---

#### The Modulo Problem: When You Need to Add Shards

Here is the story of why adding shards to a hash-sharded system is painful.

You start with 4 shards. User ID 12345 lands on shard `12345 % 4 = 1`. User ID 20000 lands on shard `20000 % 4 = 0`. Everything is working fine for two years.

Your app grows and now you need a 5th shard to handle the load.

The moment you add Shard 4, your formula changes from `% 4` to `% 5`.

Now: `12345 % 5 = 0`. User 12345 should be on Shard 0. But their actual data is still sitting on Shard 1 from two years ago.

And it is not just User 12345. When you change from `% 4` to `% 5`, approximately 75-80% of all keys map to a DIFFERENT shard than before. If you have 10 million users, ~7.5 million of them are now "in the wrong place." All that data needs to move.

Moving 7.5 million users' data while the system is live is like moving 75% of the books in a library while customers are actively browsing. Books disappear from where they were, but have not arrived at their new location yet. Customers cannot find anything.

This is catastrophic for a live system. It requires:
1. Stopping all writes (or accepting that data will be wrong temporarily)
2. Moving 75% of your data to new locations
3. Verifying everything moved correctly
4. Resuming writes

On a large system, this migration can take weeks.

The solution to this problem is called Consistent Hashing.

---

#### Consistent Hashing — The Fix

Consistent hashing uses a clever trick to minimize how much data moves when you add or remove a shard.

**The Circular Highway Analogy:**

Imagine a circular highway — like a racing track — with mile markers going from 0 to 1000, and then back to 0. Your 4 shards sit at specific mile markers around this circle:

- Shard 0 sits at mile marker 0
- Shard 1 sits at mile marker 250
- Shard 2 sits at mile marker 500
- Shard 3 sits at mile marker 750

When you need to store a piece of data (say, User ID 12345), you hash the user's ID to get a mile marker. Let's say `hash(12345) = 345`. You start at mile 345 and drive clockwise around the ring until you hit the next shard. That is Shard 2 at mile 500. Data goes to Shard 2.

```
Consistent Hashing Ring:

             Shard 1
             (mile 250)
                |
     mile 0/1000|
  Shard 0 ------+------ (going clockwise)
     (mile 0)   |
                |
     User 12345 (mile 345)
       -> drive clockwise
       -> hit Shard 2 at mile 500

                |
             Shard 2
             (mile 500)
                |
                |
             Shard 3
             (mile 750)

Each shard "owns" the arc of the ring before it.
Shard 0 owns: mile 750-1000 and 0-250 (wrapping around)
Shard 1 owns: mile 250-500  (wait, that's wrong - let me clarify)

Actually:
Shard 0 at mile 0   -> owns data hashing to mile 751-999 (coming clockwise to reach it)
Shard 1 at mile 250 -> owns data hashing to mile 1-249
Shard 2 at mile 500 -> owns data hashing to mile 251-499
Shard 3 at mile 750 -> owns data hashing to mile 501-749

Each shard owns roughly 25% of the ring = roughly 25% of the data.
```

Now here is the magic: you add a 5th shard at mile 600.

Shard 5 now sits between Shard 2 (mile 500) and Shard 3 (mile 750). It claims the arc from mile 500 to mile 600 — data that was previously owned by Shard 3.

Only data that hashed to a mile marker between 500 and 600 needs to move. That is only 1/10th of the ring, or about 10% of all data. The other 90% stays exactly where it is.

```
Before Adding Shard 5:

            [Shard 1]
           (mile 250)
          /            \
   [Shard 0]           [Shard 2]
   (mile 0)            (mile 500)
          \            /
           [Shard 3]
           (mile 750)

After Adding Shard 5 at mile 600:

            [Shard 1]
           (mile 250)
          /            \
   [Shard 0]           [Shard 2]
   (mile 0)            (mile 500)
          \            /   \
           [Shard 3]      [Shard 5]  <- NEW!
           (mile 750)     (mile 600)

Only data between mile 500 and 600 moves: ~10% of total data.
Everything else: untouched.
```

Compare:
- Regular hash sharding, adding 1 shard: ~75% of data moves
- Consistent hashing, adding 1 shard: ~1/N of data moves (N = number of shards)

With 4 shards adding a 5th: only ~20% of data moves instead of 75%. With 16 shards adding a 17th: only ~6% of data moves.

This is why consistent hashing is used by almost every large-scale distributed system: Cassandra, Dynamo (Amazon), Chord, Akamai CDN, and many others.

---

#### Virtual Nodes: Making the Distribution Even More Even

There is still one problem with the basic consistent hashing ring. By pure chance, the shards might not be evenly spaced. Shard 0 might be at mile 0, Shard 1 at mile 50, Shard 2 at mile 800, Shard 3 at mile 900. In this case, Shard 2 "owns" the huge arc from mile 50 to mile 800 — that is 75% of the ring. The other 3 shards share the remaining 25%. Very uneven.

The fix is called virtual nodes (vnodes).

Instead of placing each physical shard at ONE position on the ring, you place it at MANY positions.

- Physical Shard 0 → virtual positions at miles 15, 340, 650, 920, 230, 580... (150 positions)
- Physical Shard 1 → virtual positions at miles 75, 280, 490, 810, 155, 440... (150 positions)
- Physical Shard 2 → virtual positions at miles 30, 195, 510, 730, 360, 695... (150 positions)
- Physical Shard 3 → virtual positions at miles 110, 425, 615, 880, 260, 540... (150 positions)

Now instead of 4 positions on the ring, you have 600 positions. Even if the physical shards are unevenly powerful machines, you can give a stronger machine more virtual positions so it handles proportionally more data.

The rule of thumb: 100-200 virtual nodes per physical shard. This creates statistical evenness — no shard ends up accidentally owning a huge chunk of the ring.

---

### Strategy 2: Range-Based Sharding

Range sharding splits data into contiguous ranges. The simplest example: if user IDs go from 0 to 9,999,999, split them evenly:

- Shard 0: IDs 0 — 2,499,999
- Shard 1: IDs 2,500,000 — 4,999,999
- Shard 2: IDs 5,000,000 — 7,499,999
- Shard 3: IDs 7,500,000 — 9,999,999

**The Alphabetical Phone Book Analogy:**

Before smartphones, phone books were enormous. Some cities split them into multiple volumes: A-D in Volume 1, E-K in Volume 2, L-Q in Volume 3, R-Z in Volume 4.

If you wanted to find "Smith, John," you immediately knew: R-Z is Volume 4. You grab Volume 4 and look up Smith. You did NOT have to search all four volumes. One volume, done.

Range sharding works the same way. To find a user in the range 5,000,000 to 7,499,999, you go directly to Shard 2. No calculation, no lookup table. You just check which range the ID falls into and go straight to that shard.

```
Range-Based Sharding:

User ID: 1,200,000
  -> Falls in range 0-2,499,999
  -> Go to Shard 0
  -> One database. Fast.

User ID: 6,800,000
  -> Falls in range 5M-7.49M
  -> Go to Shard 2
  -> One database. Fast.

[Shard 0]    [Shard 1]    [Shard 2]    [Shard 3]
IDs: 0        IDs: 2.5M    IDs: 5M      IDs: 7.5M
  to 2.49M     to 4.99M     to 7.49M     to 9.99M

Query: "All users with ID between 2,400,000 and 2,600,000"
  -> Spans Shard 0 AND Shard 1
  -> Query 2 shards, combine results
  -> Still much better than querying all 4!
```

**The Big Advantage — Range Queries Work Well:**

Range sharding is great when your most common queries are range-based.

Example: an e-commerce site wants to show "all orders from the last 7 days." If orders are sharded by date (January orders on Shard 0, February on Shard 1, etc.), then recent orders are all in the same shard. One query, one shard, fast.

Example: a logging system stores events by timestamp. If you want "all errors from last Tuesday between 2pm and 4pm," you go directly to the shard that holds Tuesday's data. No scatter-gather needed.

This is a HUGE advantage over hash sharding, where that same query would require asking all shards.

---

**The Big Problem — Hot Spots:**

Here is where range sharding gets painful. In most applications, new data is being written RIGHT NOW. New users signing up RIGHT NOW. New orders placed RIGHT NOW. New log events generated RIGHT NOW.

If user IDs are sequential (each new user gets the next available ID), then ALL new users today have the highest IDs. All those writes go to the shard with the highest ID range — Shard 3 in our example.

Meanwhile, Shard 0 (full of users from 3 years ago, most of whom are inactive) barely gets any traffic.

```
Range Sharding Hot Spot Problem:

Time passes. Users are added sequentially.

[Shard 0]       [Shard 1]       [Shard 2]       [Shard 3]
IDs 0-2.49M    IDs 2.5M-4.99M  IDs 5M-7.49M    IDs 7.5M-9.99M
(old users)     (old users)     (old users)     (NEW users today)

Write traffic:
10% ------------> 10% ----------> 15% -----------> 65% (HOT!)

Read traffic (old inactive users barely log in):
5% ------------> 5% -----------> 10% -----------> 80% (HOT!)

Shards 0, 1, 2: sitting idle.
Shard 3: overwhelmed.

Even though you have 4 machines, 3 of them are barely doing anything.
This is called a "hot partition" or "hot shard."
```

This specific problem — where the most recently created keys always pile up on the last shard — is called temporal skew.

**The Time-Range Hot Spot:**

Here is a classic example that many systems fall into:

You shard your application's log events by time:
- January logs → Shard 1
- February logs → Shard 2
- March logs → Shard 3
- April logs → Shard 4

RIGHT NOW it is March 15th. Every single log event your app generates goes to Shard 3. Shard 3 is working hard. Shards 1 and 2 are doing almost nothing (just serving occasional reads from old log data).

This is temporal skew. It is very common whenever the shard key has a time component or a monotonically increasing value (like auto-increment IDs).

The fix: do not use a purely sequential key as your shard key. Either hash the key first (destroying range query ability but fixing hot spots), or add a random component to the key (salting).

---

### Strategy 3: Directory-Based (Lookup Table) Sharding

Sometimes you do not want to compute a shard from a formula, and you do not want strict ranges. You want complete manual control over where each piece of data lives.

**The Receptionist Routing Calls Analogy:**

Imagine a large company with 1,000 employees across 10 departments. When a call comes in and the caller asks for "Smith," the receptionist checks a desk directory:

```
Smith, John      -> Marketing, Ext. 304
Smith, Patricia  -> Engineering, Ext. 817
Jones, Robert    -> Sales, Ext. 201
...
```

The receptionist looks up the name and routes the call to the right extension. If John Smith moves from Marketing to Engineering, you update the directory. The callers do not need to know anything changed — they just ask for Smith and get routed correctly.

Directory sharding works exactly the same way. A separate service (the directory) stores a table that maps keys to shards:

```
customer_id: 1234    -> Shard 5
customer_id: 5678    -> Shard 2
customer_id: 9101    -> Shard 8
customer_id: 1121    -> Shard 2
```

When your app wants to read or write data for customer 1234, it first asks the directory: "Which shard has customer 1234?" The directory answers: "Shard 5." The app then talks to Shard 5.

```
Directory-Based Sharding:

Client
  |
  | (1) "Where does user 1234 live?"
  v
[Directory Service]
  |
  | (2) "Shard 5"
  v
Client
  |
  | (3) Query Shard 5 directly
  v
[Shard 5]
  (user 1234's data)

The directory is a simple lookup table:
+-------------+---------+
| customer_id | shard   |
+-------------+---------+
| 1234        | Shard 5 |
| 5678        | Shard 2 |
| 9101        | Shard 8 |
| 1121        | Shard 2 |
+-------------+---------+
```

**Pros of Directory Sharding:**

Complete control. This is the key advantage. You can put VIP customers on dedicated high-performance hardware. You can rebalance the load by moving a few customers from a busy shard to a quiet one — just update the directory entry. No data movement required (well, you still need to move the actual data, but the directory update is instant).

You can make decisions that no formula could make. "Put all enterprise customers in this specific geographic region on these specific high-memory machines." You literally just type it into the directory.

**Cons of Directory Sharding:**

The directory becomes critical infrastructure. If the directory service goes down, NOBODY can find any data. Your entire application stops. Because every single database query starts with "ask the directory which shard to use," the directory is now in the critical path of every operation.

This means the directory needs to be:
- Highly available (replicated, with failover)
- Fast (probably cached in memory everywhere)
- Consistent (stale directory entries send queries to the wrong shard)

It also adds latency. Every query now has an extra network round-trip to ask the directory before it can ask the actual shard. In practice, the directory response is cached aggressively — your app remembers that customer 1234 is on Shard 5 and does not ask again for a while. But cache invalidation (knowing when to forget a cached entry) is its own problem.

---

**The SaaS Multi-Tenant Example:**

The clearest use case for directory sharding is multi-tenant software-as-a-service (SaaS) systems.

Imagine you run a project management tool like Jira or Asana. You have:
- 500 small startups (each with 5-20 users, 100MB of data)
- 50 medium companies (each with 100-500 users, 5GB of data)
- 5 large enterprises (each with 5,000+ users, 200GB of data)

With hash or range sharding, a large enterprise and a small startup could end up on the same shard. The enterprise's heavy workload slows down the startup.

With directory sharding:
- Small startups share shards (like shared apartment buildings — 50 startups per shard)
- Medium companies get more dedicated space (5 companies per shard)
- Large enterprises each get their own dedicated shard (one enterprise = one shard, or even one dedicated cluster)

The directory maps each customer ID to their assigned shard:

```
+------------------+------------------+------------------+
| Customer         | Type             | Assigned Shard   |
+------------------+------------------+------------------+
| Startup A-Z      | Small            | Shared Shard 1   |
| StartupAA-AZ     | Small            | Shared Shard 2   |
| Medium Corp X    | Medium           | Shard 15         |
| Enterprise Y     | Large            | Dedicated Shard  |
| Enterprise Z     | Large            | Dedicated Shard  |
+------------------+------------------+------------------+

Enterprise customers:
- Get dedicated resources
- Never compete with other customers
- Higher performance guaranteed

Small customers:
- Share resources (cost-efficient)
- Performance may vary slightly
- But they pay less
```

This is how Salesforce, Shopify, and many SaaS platforms handle their infrastructure. Big customers get private infrastructure. Small customers share.

---

## Choosing the Right Sharding Strategy

Here is a comparison table to help you decide which strategy to use:

```
+----------------------------------+-----------+-----------------------------------------------+
| Scenario                         | Strategy  | Why                                           |
+----------------------------------+-----------+-----------------------------------------------+
| User lookups by user ID          | Hash      | Even distribution. You only ever query by ID  |
|                                  |           | (point queries). Range queries not needed.    |
+----------------------------------+-----------+-----------------------------------------------+
| Time-series logs and events      | Range     | "All events in last hour" = one shard.        |
|                                  |           | (But watch for temporal hot spots!)           |
+----------------------------------+-----------+-----------------------------------------------+
| Multi-tenant SaaS platform       | Directory | Flexible per-customer placement.              |
|                                  |           | Enterprise customers need dedicated shards.   |
+----------------------------------+-----------+-----------------------------------------------+
| Social media posts by user       | Hash by   | All posts from one user are on the same       |
|                                  | user ID   | shard. Showing "my posts" = single shard.    |
+----------------------------------+-----------+-----------------------------------------------+
| E-commerce orders (user history) | Hash by   | User's full order history on one shard.       |
|                                  | user ID   | "My orders" = single shard.                  |
+----------------------------------+-----------+-----------------------------------------------+
| Financial transactions by date   | Range +   | Date range queries work. Hash within range    |
|                                  | Hash      | to avoid hot spots on "today's" shard.        |
+----------------------------------+-----------+-----------------------------------------------+
```

**Decision Flowchart:**

```
START: Choosing a sharding strategy

Do you need range queries?
(e.g., "all records from last week")
       |
      YES --> Are keys sequential with hot recent data?
       |      (e.g., auto-increment IDs, timestamps)
       |            |
       |           YES --> Hash sharding (or Hash + Range hybrid)
       |           NO  --> Range sharding
       |
      NO  --> Do some customers need special treatment?
               (VIP, different performance tiers)
                     |
                    YES --> Directory sharding
                    NO  --> Hash sharding (simplest default)
```

---

## Choosing the Shard Key: The Most Important Decision

The shard key is the column (or combination of columns) you use to decide which shard data goes to. It is the most important architectural decision you make when setting up a sharded system.

**The Building a City Analogy:**

When city planners design a new city, they make big decisions about where things go. Residential neighborhoods near schools. Industrial zones near highways (not near homes). Shopping areas where foot traffic is high. Hospitals accessible from major roads.

Once the city is built, you cannot easily move things. If you put the hospital in the wrong place, millions of people are inconvenienced for decades. The planning happens BEFORE construction because changes later are enormously expensive.

The shard key is your city plan. Where you put data determines:
- How fast your most common queries run
- Whether some shards get overloaded while others sit idle
- How hard it is to run cross-shard queries
- Whether you can grow the system cleanly

Once you pick a shard key and data accumulates, changing it is like moving a hospital. Possible, but painful.

---

### The Shard Key Cheat Sheet

```
+------------------+--------------+-----------+-------------------------------+
| Use Case         | Good Key     | Good For  | Bad For                       |
+------------------+--------------+-----------+-------------------------------+
| Social network   | user_id      | Profile   | "All posts in last hour"      |
|                  |              | & post    | (scattered across shards)     |
|                  |              | queries   |                               |
+------------------+--------------+-----------+-------------------------------+
| E-commerce       | user_id      | Order     | "All orders in region X"      |
|                  |              | history   | (scattered across shards)     |
|                  |              | queries   |                               |
+------------------+--------------+-----------+-------------------------------+
| Messaging app    | conversation | Fast msg  | "All msgs from user A across  |
|                  | _id          | load      | all conversations"            |
|                  |              |           | (scattered)                   |
+------------------+--------------+-----------+-------------------------------+
| Ride-sharing     | region_id    | Local     | "All rides for user X across  |
|                  |              | dispatch  | all regions"                  |
|                  |              |           | (scattered)                   |
+------------------+--------------+-----------+-------------------------------+
| Content platform | content_id   | Single    | "All content by creator X"    |
|                  |              | item load | (scattered across shards)     |
+------------------+--------------+-----------+-------------------------------+
| Multi-tenant SaaS| tenant_id    | All data  | Analytics across all tenants  |
|                  |              | for       | (requires querying all shards)|
|                  |              | one tenant|                               |
+------------------+--------------+-----------+-------------------------------+
```

The pattern is clear: the shard key is great for queries that INCLUDE the shard key in their filter. It is bad for queries that do NOT include the shard key and need to scan everything.

---

### The 3 Questions to Ask Before Choosing a Shard Key

**Question 1: What queries do I run most often?**

Your most common queries should hit exactly ONE shard if possible. One shard = fast. Multiple shards = slower and more complex.

If 90% of your queries are "get all orders for user X," shard by user_id. User X's orders all live in one shard. Fast.

If 90% of your queries are "get all events in the last 5 minutes," shard by time. Recent events are all in one shard. Fast.

The goal: your most common queries should be single-shard queries. Save the multi-shard queries for rare analytics that can afford to be slow.

**Question 2: Will some keys have way more data than others?**

This is the celebrity problem.

Instagram user Kylie Jenner has 390 million followers. If you shard Instagram posts by user_id, and Kylie's user_id hashes to Shard 2, then:
- Every one of Kylie's posts goes to Shard 2
- Every one of her 390M followers' READ requests for her posts... all go to Shard 2
- Shard 2 is drowning
- The other 15 shards are barely busy

Meanwhile, a random user with 200 followers — their posts and reads are a tiny drop in the ocean. Their shard is fine.

This is data skew and access skew combined. The shard key (user_id) is "bad" for celebrities because it concentrates hot data on single shards.

The solution: special handling for famous accounts, or a different shard key, or caching (cover this more in the hot partitions section below).

**Question 3: Is the distribution truly even?**

Sequential IDs with range sharding → all new users on the "last" shard. Always bad.

UUIDs are random by design → even distribution with hash sharding. Good.

Timestamp as shard key → temporal hot spot. All writes go to "now." Always bad.

User IDs with consistent hashing → fairly even distribution. Good.

Test this before going live: simulate a million records and check how many land on each shard. If the distribution is 40/30/20/10 instead of 25/25/25/25, your shard key is skewed.

---

## Hot Partitions: When One Shard Gets All the Traffic

Even with a perfectly designed sharding strategy, some shards can become overloaded due to uneven access patterns. This is one of the most common operational problems in sharded systems.

**The Black Friday Checkout Lane Analogy:**

It is Black Friday. A large electronics store has 10 checkout lanes to handle the rush. Management is proud — 10 lanes should handle 10× the customers compared to just one lane.

But then a rumor spreads: Lane 3 has a celebrity cashier who signs autographs. Everyone queues in Lane 3. The line stretches out the door and into the parking lot. The other 9 lanes are completely empty. Staff are standing around with nothing to do while Lane 3 is in chaos.

Your "10 checkout lanes" (10 shards) are effectively useless. You are still bottlenecked on 1 lane.

This is a hot partition. One shard receives disproportionate traffic. The other shards sit idle. The hot shard slows down, queues requests, drops connections, and your users experience the system as "broken" — even though 9 out of 10 shards are perfectly healthy.

```
Hot Partition Example:

Instagram sharded by user_id across 4 shards:

[Shard 0]      [Shard 1]      [Shard 2]         [Shard 3]
                                 ^-- Celebrity
Utilization:   Utilization:   Utilization:      Utilization:
    8%              9%           74%                9%
                              OVERLOADED!
                              Requests timing out.
                              Errors reported.

Shard 0, 1, 3: fine. Nothing to do.
Shard 2: on fire.

Users complain: "Instagram is down!"
Actually: Instagram (3/4 of it) is fine.
Kylie Jenner's shard is not.
```

---

### The 4 Types of Skew (Explained Simply)

**Type 1: Data Skew**

One user (or tenant) has dramatically more data than others.

Example: a cloud storage service (like Dropbox). Most users have 5-50 GB. But one media company has 500 TB of video files. If you shard by user_id, that company's shard has 500 TB while every other shard has maybe 50 GB average. Shard nearly full, others barely used.

**Type 2: Access Skew**

One piece of data gets accessed dramatically more often than others.

Example: a tweet from a celebrity goes viral. Normally that tweet's shard handles 1,000 reads per second (same as every other shard). Suddenly: 2 million reads per second. All going to the same shard.

The data itself is small (one tweet is a few hundred bytes). The RATE of access is the problem. The shard's CPU and network are overwhelmed.

**Type 3: Temporal Skew**

Explained above: recent data is accessed far more than old data. A shard containing recent data gets hammered. Shards with old data sit idle.

Example: any news website. Articles from today get millions of reads. Articles from last year get a handful. If you shard by article_id and IDs are sequential, today's articles are all on one shard.

**Type 4: Popularity Skew**

Certain individual items become disproportionately popular for a period.

Example: a product listing on Amazon. Normally a product gets 100 views per day. Someone posts it on Reddit and it becomes "the deal of the century." 500,000 people look at it in the next hour. That product's shard — and everything else on it — gets hammered.

This is similar to access skew but more transient. Celebrity content is permanently popular. Viral content is temporarily popular (a few hours or days).

---

### Solutions to Hot Partitions

**Solution 1: Salting (Spreading Hot Keys)**

Instead of storing celebrity Kylie Jenner's data in ONE location, spread it across multiple shards using a technique called "salting." You append a random number (the "salt") to the key:

```
WITHOUT SALTING:
All writes for user kylie_jenner:
  hash("kylie_jenner") % 16 = Shard 7
  -> ALL writes -> Shard 7 (overloaded)

WITH SALTING (salt = random number 0-9):
  hash("kylie_jenner_0") % 16 = Shard 2
  hash("kylie_jenner_1") % 16 = Shard 11
  hash("kylie_jenner_2") % 16 = Shard 5
  hash("kylie_jenner_3") % 16 = Shard 9
  hash("kylie_jenner_4") % 16 = Shard 14
  ... (10 different shards)

Writing a new post from Kylie:
  -> Pick random salt 0-9
  -> Write to kylie_jenner_{salt}
  -> Load distributed across 10 shards

Reading all of Kylie's posts:
  -> Read from kylie_jenner_0 through kylie_jenner_9
  -> Combine results in application code
  -> 10 reads instead of 1, but each shard handles only 1/10 of the traffic
```

The trade-off is explicit: writes are fast (spread across 10 shards), but reads are more expensive (need to gather from 10 locations). This trade-off is worth it when WRITE traffic is the bottleneck (as it typically is for a celebrity posting new content and instantly getting millions of reactions).

```
SALTING VISUAL:

Before Salting:
[celebrity writes] -----> [Shard 7] (100% of celebrity traffic)
                          OVERLOADED

After Salting (10 salt values):
[celebrity write 1] -> [Shard 2]   (10% each)
[celebrity write 2] -> [Shard 11]
[celebrity write 3] -> [Shard 5]
[celebrity write 4] -> [Shard 9]
[celebrity write 5] -> [Shard 14]
[celebrity write 6] -> [Shard 0]
[celebrity write 7] -> [Shard 6]
[celebrity write 8] -> [Shard 13]
[celebrity write 9] -> [Shard 3]
[celebrity write 10]-> [Shard 8]

No single shard overwhelmed. 10x improvement in write distribution.
Cost: reads now require gathering from 10 shards.
```

**Solution 2: Caching Hot Keys**

Many hot partition problems involve data that is read frequently but changes infrequently. A celebrity's profile photo. A viral article's content. A product description for a popular item.

Instead of letting 2 million reads per second hammer the database shard, put a cache (like Redis) in front:

```
Without caching:
2,000,000 reads/sec -> [Database Shard 7] -> OVERLOADED

With caching:
2,000,000 reads/sec
     |
     v
[Redis Cache]
  - 1,980,000 reads/sec answered here (cache hit ~99%)
  - 20,000 cache misses -> [Database Shard 7] -> Manageable

Database shard 7: now handles 20,000 reads/sec instead of 2,000,000.
```

This is particularly effective because:
- Cache hits are ~100× faster than database reads
- Popular data (celebrity profiles, viral content) is read in bursts: millions of reads of the same data
- The same data can serve millions of reads without the database being involved at all

Works best for: data that changes rarely (celebrity bio, product description, viral post content). Works poorly for: data that changes frequently (live sports scores, stock prices, comment counts).

**Solution 3: Dedicated Infrastructure**

For truly enormous accounts — users with 100 million+ followers, enterprise customers using 500TB of storage — sometimes the right answer is to give them their own dedicated infrastructure.

Instead of sharing Shard 7 with 50,000 other users, Kylie Jenner gets her own database server (or cluster of servers). Her traffic is completely isolated. Other users never compete with her for resources.

This sounds expensive, but for truly large accounts, the alternative (a perpetually overloaded shared shard causing everyone else to suffer) is worse.

Many platforms have a "VIP tier" of infrastructure for their most demanding users, even if users never know it exists.

**Solution 4: Redesigning the Feature — Pull vs. Push**

Sometimes the hot partition problem is a signal that the system's design needs to change, not just the infrastructure.

Consider Twitter's "fan-out" problem:

Kylie Jenner posts a tweet. She has 190 million followers.

**Fan-out on write (push model):**
When Kylie posts, Twitter immediately writes her tweet to 190 million followers' personal feed databases. Each follower's feed is pre-computed and stored. When followers open the app, their feed loads instantly from THEIR personal database record.

The problem: posting one tweet generates 190 MILLION writes. All of those writes flow through Kylie's shard first (or her followers' shards, which are spread out but still enormous in total). The write storm is massive.

**Fan-out on read (pull model):**
When Kylie posts, Twitter writes her tweet exactly once — to Kylie's own database record. When a follower opens the app, their feed is assembled at that moment by querying: "Give me the latest posts from all 500 people I follow." The feed is computed on the fly.

The write problem disappears — one write per tweet, not 190 million. But now reading the feed is expensive: you query 500 people you follow, get results, sort by time, display. If some of those people have sharded data across 16 shards, that is potentially hundreds of database queries just to load your feed.

Twitter's actual solution: hybrid approach. Regular users: fan-out on write (pre-compute feeds). Celebrities: fan-out on read (too expensive to write to all their followers; instead, inject their posts at read time). When you load your feed, Twitter combines your pre-computed feed (from people you follow who are not celebrities) with real-time queries to the celebrities you follow.

The lesson: hot partition problems sometimes have architectural solutions, not just infrastructure solutions.

---

## Re-Sharding: The Migration Everyone Dreads

Eventually, your sharding setup that worked great at 10 million users needs to be changed. Maybe you need more shards. Maybe your shard key was wrong and you have hot spots. Maybe one shard has grown much larger than others and needs to be split.

This is resharding, and it is one of the most stressful operations in large-scale systems engineering.

**The Moving a Library While It's Open Analogy:**

Imagine a library with 500,000 books that is open 24 hours a day, 7 days a week. You need to reorganize the entire library — different sections, different shelving system, different indexing.

But you cannot close the library. People are checking out books and returning them right now. While you are carrying books from the old location to the new location, someone might try to check out a book you just moved. They go to the old shelf: empty. They cannot find it.

If you return a book to the old shelf (not knowing it has been moved), it ends up in the wrong place. The old system says it is here. The new system says it is there. It is actually somewhere else entirely.

Resharding is exactly this: you are moving data between shards while the system continues accepting reads and writes around the clock. A user might write to a record you are currently copying. Another user might read a record you just moved, from the old location that no longer has it.

**Why Resharding Happens:**

1. Your shard key was wrong. You picked user_id but your celebrity users are causing persistent hot spots. You want to switch to a hash of user_id with salting.

2. You need more shards. You started with 4 shards at 10 million users. You now have 100 million users. 4 shards each hold 25 million users; you need 16 shards of 6.25 million users each.

3. One shard grew disproportionately. Shard 3 ended up with 40% of your data (maybe your shard key was skewed). You need to split Shard 3 into two shards.

4. You want to merge shards. Traffic dropped (maybe a seasonal business, maybe you lost customers). You have 16 shards but only need 8. Consolidate to save infrastructure costs.

---

### Three Strategies for Resharding

**Strategy 1: Double-Write Migration**

The idea: for a period of time, you write every new record to BOTH the old shard layout AND the new shard layout. Meanwhile, you slowly copy all the OLD existing data to the new layout in the background. Once everything is copied and verified, you switch reads to the new layout and stop double-writing.

Analogy: you are moving offices. For two weeks, you send every new email and document to BOTH the old filing system and the new one. Simultaneously, you slowly photocopy everything in the old filing cabinets and put the copies in the new system. Once all old files are copied and you verify nothing is missing, you stop using the old system.

```
Double-Write Migration Timeline:

Week 1: Old system only
  [Write] -> [Old Shards] only
  [Read]  <- [Old Shards] only

Week 2-3: Double-write begins
  [Write] -> [Old Shards] AND [New Shards] simultaneously
  [Read]  <- [Old Shards] only (new shards not ready yet)

Week 4-5: Background data copy
  [Write] -> BOTH systems
  [Old data] being copied to [New Shards] in background
  [Read]  <- [Old Shards] still

Week 6: Verification
  [Write] -> BOTH systems
  Check: does every record in old shards match new shards?
  Run checksums. Compare record counts. Fix discrepancies.

Week 7: Switch reads
  [Write] -> BOTH systems (still)
  [Read]  <- [New Shards] now
  Monitor for errors. If anything wrong, fall back to old.

Week 8: Switch writes
  [Write] -> [New Shards] only
  [Read]  <- [New Shards] only
  Old shards still exist (safety net)

Week 9-10: Monitor, then decommission old shards
```

**Strategy 2: Ghost Tables (Change Data Capture)**

This strategy uses a technique called Change Data Capture (CDC). Every time a record is inserted, updated, or deleted in the old system, the change is captured as an event and replayed on the new system.

Analogy: you hire someone to watch your old office all day. Whenever ANYTHING changes — a new document arrives, an old one is updated, something is thrown away — they write it down in a log. Meanwhile, you are copying all the old files to the new office. Once you are done copying, you replay everything in the log on the new office to bring it up to date. The two offices are now synchronized. You switch.

```
Ghost Table (CDC) Migration:

Phase 1: Set up CDC
  [Old Shards] --> [CDC Log] --> [New Shards]
  Every write to old is captured and replayed on new.
  New shards start empty but immediately receive all changes.

Phase 2: Backfill
  Copy all existing data from old shards to new shards
  (in the background, while CDC keeps things synchronized)

Phase 3: Catch up
  CDC has been running. Replay any backlog of events.
  New shards now have: all old data + all recent changes.

Phase 4: Verify
  Check that old and new shards match.
  Compare record counts, checksums, spot checks.

Phase 5: Cutover (brief pause)
  Pause writes for a few seconds.
  Final sync.
  Switch reads and writes to new shards.
  Resume writes.

Phase 6: Done. Decommission old shards later.

Advantage: minimal downtime (just a few seconds at cutover).
Disadvantage: complex to set up. CDC infrastructure needed.
```

**Strategy 3: Gradual Read-Through Migration**

The laziest approach: new writes go to the new shard layout. Old data stays in the old shards. When someone reads data, if it is in the new system, serve it. If it is in the old system, serve it AND copy it to the new system at the same time (lazy migration).

Over time, data "migrates itself" as it is accessed. Rarely accessed data (old cold data) migrates last, or maybe never (you can forcibly migrate it at the end when there is little left).

Analogy: you are moving to a new house. New mail goes to the new address. Old stuff in the old house: you only move a box when you actually need something from it. You go to the old house, get the box, put it in the new house, and from now on it is there. After a few months, 90% of your stuff has naturally migrated because you needed it. The remaining 10% (stuff you never use) you move in one final weekend.

```
Read-Through Migration:

New writes: -> [New Shards]
Old data:      [Old Shards] (still there)

Read Request comes in:
  -> Check New Shards first
  -> Found? Serve it. Done.
  -> Not found? Check Old Shards.
     -> Found in Old? Serve it.
        AND copy it to New Shards now.
        (next time it will be in New Shards)

Over time:
Month 1: 10% of data migrated (the most active data migrates first)
Month 2: 40% migrated
Month 3: 70% migrated
Month 4: 90% migrated
Month 4, Final Week: force-migrate remaining 10%
Month 5: decommission old shards

Advantage: zero disruption, very simple.
Disadvantage: slow. Old shards run alongside new ones for months.
              Some queries need to check both systems.
```

---

### The Minimum Timeline for a Safe Resharding

If your live system has millions of users, you cannot rush this. Here is a realistic minimum timeline:

```
Safe Resharding Timeline:

Week 1-2: Preparation
  - Set up new shard infrastructure
  - Write and test migration scripts on a copy of production data
  - Test the new sharding logic in staging environment
  - Write rollback plan (what do we do if something goes wrong?)
  - Brief team, set up monitoring dashboards

Week 3-4: Double-write begins
  - Deploy new code that writes to BOTH old and new shards
  - New writes land in both places simultaneously
  - No reads from new shards yet — just getting data there
  - Watch for performance impact of double-writes

Week 5-6: Background backfill
  - Copy all data from old shards to new shards
  - Run during off-peak hours to minimize impact
  - Double-writes still happening (new data is always in both)
  - Progress monitoring: X% of records migrated

Week 7: Verification
  - Pause backfill
  - Run full comparison: every record in old shards vs new shards
  - Check record counts per shard
  - Run checksums on sample data
  - Fix any discrepancies found

Week 8: Switch reads
  - Deploy code that reads from NEW shards
  - STILL double-writing (in case you need to fall back)
  - Monitor error rates intensely (first 48 hours)
  - If error rate spikes: fall back to old shards immediately
  - If stable: continue

Week 9: Switch writes to new only
  - Stop double-writing
  - New shards are now the sole system of record
  - Old shards receiving no new writes

Week 10: Monitor and cleanup
  - Watch for any stale reads from old shards
  - Confirm all systems pointed at new shards
  - Plan decommission of old shards (do not rush this)
  - Old shards: keep as backup for 2-4 more weeks before deleting
```

This is why choosing the right shard key the first time matters so much. Resharding a live system with millions of users is a multi-month project that can go wrong in a dozen ways. Every step has a risk. Double-write bugs can corrupt data. Backfill scripts can have off-by-one errors. Verification can miss subtle differences. Cutover can have race conditions.

An engineer who has gone through a major resharding once will spend a LOT of time thinking carefully about the shard key choice the next time around.

---

## Cross-Shard Operations: The Price You Pay

Sharding splits your data across machines. But your application does not always know in advance which shard has the data it needs. Some queries naturally span multiple shards. These cross-shard operations are the main tax you pay for the scalability that sharding provides.

**The Asking Multiple Classrooms Analogy:**

The school secretary needs to find all students named "Smith." The students are split across 10 classrooms. She cannot just walk into one classroom and ask — Smith could be in any of them.

She writes the same note — "Is there a student named Smith in your class?" — and sends it to all 10 classroom teachers simultaneously. She waits. Teachers reply one by one. She collects all the replies and combines them into one list.

This takes longer than asking one teacher. It takes proportionally longer as you add more classrooms. And if one teacher is slow to reply (maybe they are in the middle of a lesson), the secretary has to wait for them before she can give the final answer. The slowest classroom determines how long the whole operation takes.

Cross-shard queries work exactly the same way. The slowest shard determines the latency of the entire query.

---

### Problem 1: Cross-Shard Joins

Before sharding, this query works perfectly:

```sql
-- Before sharding: ONE database, everything accessible
SELECT orders.order_id, orders.total, users.name, users.email
FROM orders
JOIN users ON orders.user_id = users.id
WHERE orders.created_at > '2024-01-01'
ORDER BY orders.created_at DESC;

-- One database. One query. Returns in 50ms. Simple.
```

After sharding, suppose orders are spread across Shards 0-3 (sharded by order_id), and users are on Shards 4-7 (sharded by user_id). Neither group of shards has BOTH orders AND users. The JOIN is impossible within any single shard.

What happens instead:

```
Cross-Shard Join (the hard way):

Step 1: Query all 4 order shards
  -> "All orders from 2024" (scatter-gather across 4 shards)
  -> Collect: 50,000 orders
  -> Extract: all unique user_ids in those orders (perhaps 30,000 unique users)

Step 2: Query all 4 user shards
  -> "Give me name and email for these 30,000 user IDs" 
  -> (another scatter-gather or targeted queries)
  -> Collect: 30,000 user records

Step 3: Join in application code
  -> Loop through orders
  -> For each order, look up the user record by user_id
  -> Combine into final result

Cost:
  Before sharding: 1 database query, ~50ms
  After sharding: 8 database queries, many seconds, complex app code

Not great.
```

**Solutions to Cross-Shard Joins:**

**Option A: Denormalization**

Copy the user's name into the orders table. Instead of looking it up via a join, it is already there:

```
orders table (denormalized):
+----------+-------+---------+------------+
| order_id | total | user_id | user_name  |  <- user_name copied here
+----------+-------+---------+------------+
| 1001     | 89.99 | 12345   | Alice Chen |
| 1002     | 45.00 | 67890   | Bob Smith  |
```

Now the query does not need the users table at all:

```sql
SELECT order_id, total, user_name
FROM orders
WHERE created_at > '2024-01-01';
-- Single shard query if order_id is the shard key. Fast.
```

The trade-off: if Alice Chen changes her name, you need to update her name in EVERY order she has ever placed. She might have 500 orders across multiple shards. One name change → up to 500 write operations instead of 1. You are trading READ simplicity for WRITE complexity.

For data that changes rarely (names, email addresses), denormalization is often worth it.

**Option B: Application-Level Join**

Fetch the orders first, then look up users by ID:

```
App-level join strategy:
1. Query order shards: "All recent orders" -> get list of orders + user_ids
2. Collect unique user_ids from step 1
3. Query user shards for just those user_ids (targeted, not full scatter-gather)
4. Merge in application code

Benefit: you only fetch EXACTLY the users you need (not all users)
Cost: 2 round trips to database instead of 1. Still more work than before sharding.
```

This is the most common approach in practice. It is more code to write, but manageable.

**Option C: Co-Location (the cleanest solution)**

Shard BOTH orders AND users by user_id. Now user 12345 is on Shard 2, AND their orders are also on Shard 2.

```
Co-location:
User 12345 -> hash(12345) % 4 = Shard 2
Orders for user 12345 -> also hashed by user_id -> Shard 2

Now the JOIN works on a single shard!

SELECT orders.*, users.name
FROM orders JOIN users ON orders.user_id = users.id
WHERE orders.user_id = 12345;
-- Both tables are on Shard 2. One shard. One query. Fast!
```

The limitation: this only works for queries that include the shard key. "All orders from all users in March 2024" still requires a cross-shard scatter-gather, because March 2024 orders span all shards.

---

### Problem 2: Cross-Shard Transactions

Before sharding, moving money between two accounts is straightforward:

```sql
BEGIN TRANSACTION;
  UPDATE accounts SET balance = balance - 100 WHERE account_id = 'A';
  UPDATE accounts SET balance = balance + 100 WHERE account_id = 'B';
COMMIT;
-- If anything fails, ROLLBACK. Atomic. Safe. Either both happen or neither.
```

The database guarantees this is atomic — it either fully succeeds or fully rolls back. No partial states.

After sharding, suppose Account A is on Shard 1 and Account B is on Shard 3. These are different database servers. There is no single transaction that spans both.

```
Cross-Shard Transaction Problem:

Step 1: Debit $100 from Account A (Shard 1)
  -> Shard 1: OK. Balance reduced. Committed.

Step 2: Credit $100 to Account B (Shard 3)
  -> Shard 3: ??? 
     - Shard 3 server crashes
     - Network timeout
     - Disk full
     - Query error

Result: $100 gone from Account A. Nothing added to Account B.
$100 has vanished from the system. This is catastrophic for a bank.
```

**Solutions to Cross-Shard Transactions:**

**Option A: Two-Phase Commit (2PC)**

A coordinator ensures that all participating shards either commit or rollback together.

```
Two-Phase Commit:

Phase 1: Prepare
  Coordinator -> Shard 1: "Prepare to debit $100 from Account A"
  Coordinator -> Shard 3: "Prepare to credit $100 to Account B"

  Shard 1: acquires locks, writes to transaction log, replies "READY"
  Shard 3: acquires locks, writes to transaction log, replies "READY"

Phase 2: Commit (only if ALL shards said READY)
  Coordinator -> Shard 1: "COMMIT"
  Coordinator -> Shard 3: "COMMIT"

  Both shards commit their changes.

If ANY shard says "ABORT" in Phase 1, or doesn't respond:
  Coordinator -> all shards: "ROLLBACK"
  All changes undone.
```

This guarantees atomicity across shards. But it has problems:
- It is slow. Four network round-trips minimum (prepare both shards, commit both shards).
- If the coordinator crashes between Phase 1 and Phase 2, all shards are stuck holding locks waiting for a commit or rollback that never comes. Recovery is complex.
- It cannot tolerate network partitions well. Any communication failure causes a stall.

2PC is used in databases (PostgreSQL's PREPARE TRANSACTION), but avoided in high-throughput systems due to its slowness and fragility.

**Option B: Saga Pattern**

Instead of one atomic transaction, break the operation into a series of smaller operations, each with a compensating operation that undoes it if something later goes wrong.

```
Saga Pattern for money transfer:

Step 1: Debit $100 from Account A (Shard 1)
  Success? -> Continue to Step 2
  Fail?    -> Nothing to undo. Stop.

Step 2: Credit $100 to Account B (Shard 3)
  Success? -> Done! Transaction complete.
  Fail?    -> Run COMPENSATING ACTION:
              -> Credit $100 BACK to Account A (Shard 1)
              -> Undo Step 1

If compensating action also fails:
  -> Add to retry queue, alert on-call engineers
  -> This is a serious but rare failure case
```

The key insight: instead of preventing failure through locks (2PC), the Saga pattern handles failure by reverting previous steps. This is more complex to reason about ("what are all the possible failure states?") but much more scalable and resilient.

Uber uses Sagas for their payment and dispatch systems. Airbnb uses Sagas for booking transactions.

**Option C: Design Away the Problem**

Often the best solution is to redesign so the transaction is single-shard.

For a bank: shard by user_id. A user's checking account, savings account, and transaction history are all on the same shard. Transfers between two accounts by the same user are single-shard. Transfers between two different users across different shards are still cross-shard — but those can be modeled as two separate events (a debit event on one shard, a credit event on another) with eventual consistency rather than a synchronous transaction.

---

### Problem 3: Cross-Shard Aggregations

Before sharding:

```sql
-- "How many users signed up this month?"
SELECT COUNT(*) FROM users WHERE signup_date >= '2024-01-01';
-- One query. Returns: 142,857. Instant.
```

After sharding with 16 shards: this query must run on all 16 shards simultaneously, and the results must be summed.

```
Cross-Shard Aggregation:

Query sent to all 16 shards simultaneously:
SELECT COUNT(*) FROM users WHERE signup_date >= '2024-01-01';

Shard  0: 8,903
Shard  1: 9,241
Shard  2: 8,751
Shard  3: 9,108
... (12 more shards)
Shard 15: 8,880

Sum all results in application code.
Total: 142,857

Problems:
- 16 queries instead of 1
- Must wait for SLOWEST shard (if Shard 7 is busy, everyone waits)
- If any shard is down, result is incomplete
- More expensive as shard count grows
```

For occasional analytics queries, this is fine. For a dashboard that shows real-time signup counts, refreshed every second, this is very expensive.

**Solution: Maintain Aggregate Counters Separately**

Keep running counters in a fast, dedicated store (like Redis) that tracks totals:

```
Counter Architecture:

When a new user signs up:
  1. Insert user record into the correct shard (as normal)
  2. ALSO: INCR redis_counter "signups:2024-01" by 1

When dashboard asks "signups this month?":
  -> Read "signups:2024-01" from Redis
  -> Returns: 142,857
  -> Time: <1ms. No shard queries needed.

Cost: every signup now does 1 extra Redis write.
That is tiny. The savings in read cost are enormous.
```

This pattern works for many aggregate metrics: total posts, active users, items sold, daily revenue. The counter is always slightly approximate (there can be tiny race conditions), but for dashboards and analytics, approximate is usually fine.

---

## Distributed ID Generation: Making Unique IDs Across Shards

Before sharding, your database assigned IDs automatically. Each new user got the next number: 1, 2, 3, 4... Simple. The database handled it with its built-in auto-increment feature.

After sharding, each shard has its own auto-increment counter. Shard 0's first user is "User 1." Shard 1's first user is also "User 1." You now have multiple users all named "User 1." Chaos.

**The Company Employee Number Analogy:**

A small company with 50 employees assigns numbers 1-50. Simple. The HR department keeps track.

The company acquires another company of 50 people. That other company ALSO assigned numbers 1-50 to their employees. Now you have two Employee #1, two Employee #2... all the way to two Employee #50. The merged company has 100 employees but 50 duplicate numbers.

In distributed databases, you need a way to generate IDs that are globally unique — no two shards ever generate the same ID.

---

### Option 1: UUID (Universally Unique ID)

A UUID is a 128-bit number, typically shown as a string like:

```
550e8400-e29b-41d4-a716-446655440000
```

Generated completely randomly on any machine. The probability of two UUIDs ever matching is approximately 1 in 2^122 — a number so large it is practically impossible.

Each shard generates its own UUIDs independently, with zero coordination needed. No shard ever needs to talk to another to get a new ID.

```
UUID Generation:

Shard 0 generates: 550e8400-e29b-41d4-a716-446655440000
Shard 1 generates: f47ac10b-58cc-4372-a567-0e02b2c3d479
Shard 2 generates: 9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d

These will NEVER clash (statistically).
No coordination needed. Super fast.
```

**Pros:** Zero coordination needed. Works on any machine. Globally unique. Simple to implement.

**Cons:** Long (36 characters as a string). Random (not sortable — you cannot say "later UUIDs come after earlier ones"). Bad for database indexes because random insertions cause fragmentation.

---

### Option 2: Snowflake IDs (Twitter's Approach)

Twitter needed a better solution for generating tweet IDs. They invented Snowflake: a 64-bit integer whose bits are carefully divided to encode multiple pieces of information.

```
64-bit Snowflake ID structure:

[1 bit: sign] [41 bits: timestamp] [10 bits: machine ID] [12 bits: sequence]

   0           00000101000010110001011111001001 111     0000001000     000000000001
   ^           ^                                        ^              ^
   |           |                                        |              |
   0           Milliseconds since                       This machine   Sequence
   (always)    custom epoch                             is ID 000001   number
               (Jan 1, 2010)                            (0-1023)       within this
                                                                       millisecond
```

How it works:
- The first bit is always 0 (reserved)
- The next 41 bits encode the current timestamp in milliseconds (relative to a custom start date). This gives ~69 years of IDs before running out
- The next 10 bits encode a machine ID (0-1023). You assign each shard/server a unique ID in this range
- The last 12 bits are a per-machine counter that increments within each millisecond. This allows up to 4,095 IDs per machine per millisecond before the counter rolls over

Result: up to 4,095 × 1,000 = 4,095,000 IDs per machine per second. Twitter generates far fewer tweets than this.

```
Two different machines generating IDs at same millisecond:

Shard 0 (machine ID 001):
  Timestamp: 10000001000 (some millisecond)
  Machine:   0000000001
  Sequence:  000000000001
  ID:        100000010000000000010000000000001  (a big number)

Shard 1 (machine ID 002):
  Timestamp: 10000001000 (same millisecond)
  Machine:   0000000010
  Sequence:  000000000001
  ID:        100000010000000000100000000000001  (a different big number)

They are different because the machine ID bits differ.
They will NEVER clash.
```

**Pros:**
- Roughly time-ordered: later IDs are numerically larger (the timestamp bits are in the most significant positions). This is great for database indexes — new records always go at the "end" of the index, avoiding fragmentation.
- Compact: 64-bit integer (8 bytes). Much smaller than UUID (36-character string = 36 bytes).
- Fast: no network round-trip needed. Each machine generates IDs locally using just its machine ID and a counter.

**Cons:**
- Requires synchronized clocks across machines. If a machine's clock drifts backward (NTP correction or hardware issue), it could generate IDs that are numerically less than IDs it generated before. This could create duplicate IDs if the sequence number has been used in that millisecond.
- Machine ID allocation requires some coordination (you need to ensure no two machines share an ID).

Used by: Twitter (tweets), Instagram (posts), Discord (messages), LinkedIn (posts and comments), and many other large platforms. When you look at a tweet's URL and see a large number like `1845820394837282816`, that is a Snowflake ID.

```
Snowflake ID: 1845820394837282816

In binary:
[0] [00011001100001000011101001000011101] [0000000001] [000000000000]
     ^timestamp (Jan 2024)                ^machine 1   ^seq 0

Decoding it tells you:
- Created in January 2024 (roughly)
- Generated on machine/shard 1
- First ID in that millisecond
```

---

### Option 3: Auto-Increment with Range Reservation

Keep the familiar auto-increment behavior, but pre-allocate non-overlapping ranges to each shard:

```
Range Reservation:

Shard 0 gets range:    1 to 1,000,000
Shard 1 gets range:    1,000,001 to 2,000,000
Shard 2 gets range:    2,000,001 to 3,000,000
Shard 3 gets range:    3,000,001 to 4,000,000

When Shard 0 generates IDs: 1, 2, 3, 4, ... 1,000,000
When Shard 1 generates IDs: 1,000,001, 1,000,002, ... 2,000,000
No overlap. No coordination needed (within a range).

When Shard 0 uses up its range:
  -> Ask a central coordinator: "I need a new range"
  -> Coordinator assigns: 4,000,001 to 5,000,000
  -> Shard 0 continues: 4,000,001, 4,000,002, ...
```

**Pros:** Familiar behavior. IDs are simple integers. Database indexes work well (sequential insertions). Easy to reason about.

**Cons:** Requires a central coordinator for range allocation. If the coordinator is down, shards that have exhausted their range cannot generate new IDs. Range allocation adds a latency hit when a shard needs a new range (though this happens infrequently — a shard with a 1,000,000-ID range might only need a new range once every few days).

```
Comparison of ID Generation Strategies:

+-------------------+------------+----------+-----------+------------+
| Strategy          | Globally   | Sortable | Compact   | Coordination|
|                   | Unique     | by time  |           | needed?    |
+-------------------+------------+----------+-----------+------------+
| UUID              | Yes        | No       | No (large)| None       |
| Snowflake         | Yes        | Yes      | Yes       | Clock sync |
| Range Reservation | Yes        | Roughly  | Yes       | Coordinator|
+-------------------+------------+----------+-----------+------------+

For most systems: Snowflake IDs are the best balance.
For simple systems: UUIDs are easiest.
For legacy systems: Range Reservation can work if you have a reliable coordinator.
```

---

## Putting It All Together: A Sharding Decision Checklist

When you are facing a system design interview question (or a real engineering decision) about sharding, here is the complete checklist to work through:

**Step 1: Do you even need sharding?**

Sharding is complex. Only shard if:
- Your write throughput exceeds what one machine can handle, AND
- Vertical scaling (bigger machine) is not sufficient or cost-effective, AND
- Functional partitioning (different tables on different machines) is not sufficient

If you can avoid sharding, avoid it.

**Step 2: Pick a shard key**

Ask yourself:
- What are my most common queries?
- What field do those queries always filter by?
- Is that field evenly distributed?
- Are there celebrity/hot-key problems with that field?

The shard key should be in the WHERE clause of your most common queries.

**Step 3: Choose a sharding strategy**

- Hash sharding: your queries are almost always point lookups (by ID). Even distribution is critical.
- Range sharding: you need range queries. Watch out for hot spots with sequential keys.
- Directory sharding: you have different tiers of customers with different requirements.

**Step 4: Plan for cross-shard operations**

Identify which queries will need cross-shard access. Decide in advance:
- Will you denormalize to avoid joins?
- How will you handle cross-shard transactions (Saga? 2PC? Redesign)?
- How will you handle aggregations (counters? Batch jobs?)?

**Step 5: Plan for hot partitions**

For any celebrity/popular key problem:
- Will you use salting?
- Will you use caching?
- Will you use dedicated infrastructure?

**Step 6: Plan for future resharding**

You will probably need to reshard eventually. Choose a shard key and strategy that makes resharding as painless as possible:
- Consistent hashing minimizes data movement when adding shards
- Good tooling for online data migration from day one

---

## How Real Systems Talk About Sharding: The Vocabulary You Need

System design is partly a communication exercise. Knowing the concepts is not enough — you need the vocabulary to express them clearly. Here are the key terms used in real engineering discussions and interviews, explained simply.

---

**Shard / Partition**
One slice of the overall dataset. Shard 0 might contain users with IDs 0-2.5M. A shard is an independent database (or database server). Each shard only knows about its own slice.

**Shard Key / Partition Key**
The column (or combination of columns) used to determine which shard a record belongs to. If your shard key is user_id, then user_id 12345 always maps to the same shard (computed by the hashing or range logic).

**Scatter-Gather**
When a query must be sent to ALL shards simultaneously (because you do not know which shard has the answer), results collected from all of them, and then merged together. A cross-shard query pattern. Slow but sometimes unavoidable.

**Hot Shard / Hot Partition**
A shard that receives disproportionately high traffic or stores disproportionately large data. While hot, it becomes a bottleneck even though other shards are underutilized.

**Fan-out**
When one request causes multiple requests to downstream systems. In sharding, a scatter-gather query fans out to N shards. In social networks, fan-out refers to broadcasting a post to all followers.

**Co-location**
Deliberately placing related data on the same shard so that queries that join or aggregate that data can stay within one shard. Example: storing a user's posts, comments, and profile all on the shard determined by user_id.

**Data Skew**
An uneven distribution of data across shards — some shards have much more data than others.

**Access Skew / Workload Skew**
An uneven distribution of queries across shards — some shards receive far more reads or writes than others, even if data size is roughly equal.

**Resharding**
The process of changing the number of shards or the sharding strategy on a live system. Involves migrating data between shards while the system continues running.

**Consistent Hashing**
A hashing scheme where the hash space is arranged as a ring, and adding or removing nodes only affects a small fraction of keys (proportional to 1/N of all keys). Minimizes data movement during resharding.

**Virtual Nodes (Vnodes)**
Multiple logical positions on the consistent hashing ring assigned to each physical shard. Improves evenness of data distribution and makes it easier to assign different capacities to different machines.

**Two-Phase Commit (2PC)**
A protocol for atomic transactions across multiple shards. Phase 1: ask all participants if they can commit (Prepare). Phase 2: if all say yes, tell all to commit. If any say no, tell all to abort. Reliable but slow and fragile under network failures.

**Saga Pattern**
An alternative to 2PC for distributed transactions. Break the transaction into steps. Each step has a compensating action that undoes it if a later step fails. More resilient than 2PC; requires careful design of compensating actions.

**Change Data Capture (CDC)**
A technique for capturing every insert, update, and delete that happens in a database as a stream of events. Used in resharding (replay changes on new shards) and for building derived data systems.

**Denormalization**
Copying data into multiple places to avoid cross-shard joins. Trade-off: eliminates read-time join complexity at the cost of write-time duplication (must update data in multiple places when it changes).

**Salting**
Appending a random value (the "salt") to a hot key to distribute it across multiple shards. Solves write hot spots at the cost of requiring gather-and-merge at read time.

**Snowflake ID**
A 64-bit globally unique ID scheme (created by Twitter) that encodes timestamp + machine ID + sequence number. Time-ordered, compact, requires no coordination beyond clock synchronization.

**UUID (Universally Unique Identifier)**
A 128-bit randomly generated ID. Globally unique with astronomically high probability. Simple to generate, but large (36 characters as string) and not sortable.

---

## A Complete Worked Example: Designing a Sharded Twitter-Like System

Let us put everything together with a realistic example. You are designing a simplified Twitter-like system. Walk through the sharding decisions from scratch.

**System requirements:**
- 100 million users
- Users can post "tweets" (short messages up to 280 characters)
- Users can follow other users
- Each user has a feed: tweets from people they follow, most recent first
- 50,000 tweets written per second at peak
- 500,000 feed reads per second at peak

---

**Step 1: Do we need sharding?**

A well-tuned PostgreSQL instance can handle approximately 10,000-20,000 writes per second. Our peak is 50,000 writes/sec. That exceeds one machine's capacity even with optimization. We need sharding.

Storage: 100 million users × 200 tweets average × 200 bytes per tweet = ~4 TB of tweet data, plus user data, follow relationships, etc. Call it 8 TB total. This exceeds a comfortable single-machine storage. Sharding helps here too.

Conclusion: yes, we need sharding.

---

**Step 2: Pick a shard key**

Most common query: "Give me the latest 20 tweets from user X" — this is asked every time someone visits a profile.

Second most common query: "Load the feed for user Y" — requires tweets from all users Y follows.

For the profile query, sharding by user_id is ideal: all of user X's tweets are on one shard.

For the feed query, we need tweets from many different users. This is inherently cross-shard regardless of shard key. We will handle this with pre-computed feeds (a separate fanout service), not by changing the shard key.

Decision: shard by user_id.

---

**Step 3: Choose sharding strategy**

We are sharding by user_id, a numeric ID. We want even distribution (celebrities should not dominate any one shard). We do NOT need range queries by user_id (we almost never ask "all users with IDs 5M-6M").

Decision: hash sharding with consistent hashing (for future resharding flexibility).

---

**Step 4: Decide shard count**

Starting: 50,000 writes/sec peak. Each shard handles ~15,000 writes/sec comfortably. Need at least 4 shards (50,000 / 15,000 = 3.3, round up to 4).

For safety and room to grow: start with 8 shards. Each handles ~6,250 writes/sec — well below the limit.

Future: if we grow to 200M users and 100,000 writes/sec, we add more shards. With consistent hashing, adding shards only moves ~1/8 of data per shard added.

Decision: 8 shards initially.

---

**Step 5: Handle celebrity hot partitions**

A celebrity with 20 million followers posts a tweet. That tweet immediately gets 500,000 read requests in the first minute — all going to the same shard.

Mitigation plan:
- Cache celebrity tweets in Redis with a short TTL (30 seconds). Cache-hit rate for viral content: ~99%. Shard only handles the 1% cache misses.
- For celebrities with >1M followers: salting. Store their tweets in 10 locations (one per salt value). Reads gather from up to 10 locations.
- Identify "celebrity accounts" at account creation (or when follower count crosses a threshold) and route them to a special high-performance shard tier.

---

**Step 6: Plan cross-shard operations**

The feed is the hardest problem. User Y follows 300 people. To build Y's feed, we need the latest tweets from all 300 — potentially on 8 different shards.

Solution: fanout-on-write for regular users. When user X posts, a "feed fanout service" looks up all of X's followers and writes the tweet ID to each follower's feed cache (stored in Redis sorted by timestamp). When user Y loads their feed, they read from their pre-computed Redis feed. Zero cross-shard queries at read time.

```
Tweet Write Flow:
User X posts tweet
  -> Write tweet to X's shard (hash(X) % 8)
  -> Fanout service: look up X's followers (from follower shard)
     -> For each follower: add tweet ID to follower's Redis feed list
  -> Done.

Feed Read Flow:
User Y opens feed
  -> Read Y's Redis feed list (pre-computed, sorted by time)
  -> Get top 20 tweet IDs
  -> Fetch tweet content for those IDs (batch query, probably 2-3 shards)
  -> Return to user Y
```

For celebrities (fanout-on-read): when Y loads their feed, inject celebrity tweets at read time by querying the celebrity's shard directly (or from Redis cache) — do NOT fanout to all 20M followers.

---

**Step 7: Plan distributed IDs**

Tweet IDs must be globally unique, time-sortable (newer tweets have higher IDs), and compact.

Decision: Snowflake IDs. Each of the 8 shards gets a unique machine ID (0-7). Tweet IDs encode the shard they were created on + timestamp + sequence.

Bonus: because Snowflake IDs are time-ordered, listing "user X's tweets sorted by time" = listing them by ID (descending). No separate sort operation needed.

---

**Final Architecture Summary:**

```
Sharded Twitter-Like System:

8 Shards (hash by user_id, consistent hashing):
  Each shard: 1 leader + 2 read replicas = 3 machines
  Total: 24 database machines

Shard 0 (users hashing to 0): 12.5M users, ~6K writes/sec
Shard 1 (users hashing to 1): 12.5M users, ~6K writes/sec
... (6 more shards)

Celebrity handling:
  - Top 1,000 accounts: dedicated high-perf shard
  - Famous accounts: Redis caching of their tweets

Feed system:
  - Regular users: fanout-on-write to Redis feed lists
  - Celebrities: fanout-on-read at feed load time

ID generation: Snowflake (each shard has a machine ID)

Cross-shard analytics: separate data warehouse
  (not using live shards for analytics queries)

Resharding plan:
  - Consistent hashing: add 8 more shards when we need to double
  - Only ~12.5% of data moves per new shard added
  - Double-write migration strategy, 10-week timeline
```

This is a realistic, production-grade sharding design that you can confidently describe in a system design interview. It addresses: shard key choice, sharding strategy, shard count, hot partition handling, cross-shard operations, distributed IDs, and future resharding.

---

## Common Interview Mistakes About Sharding

Before the summary, here is a list of the most common mistakes students make when discussing sharding in system design interviews. Knowing what NOT to say is just as valuable as knowing what to say.

---

**Mistake 1: "I'll just shard from the beginning to be safe."**

This is premature optimization. Sharding adds enormous operational complexity. You lose transactions, you complicate joins, you need distributed ID generation, you need to worry about hot partitions, you need to plan for resharding. None of this is free.

Start with a single well-tuned database. Add read replicas when reads are the bottleneck. Add vertical scaling when writes start to strain. Only shard when those options are genuinely exhausted.

In an interview, if you propose sharding for a system with 100,000 users, the interviewer will immediately question your judgment. Sharding is a tool for very large systems. Reach for it when the scale demands it, not before.

---

**Mistake 2: "I'll shard by user_id AND timestamp" (compound shard keys without thinking)**

Compound shard keys can work, but they need careful thought. If you shard by (user_id, timestamp), every write for user 12345 goes to a shard determined by hashing both values. But now "all activity for user 12345" is scattered across multiple shards — because the timestamps change the shard assignment.

The rule: a user's data should be co-located. All of it. If you are building a social network, shard by user_id. All a user's posts, comments, profile data, and settings go to the same shard. This maximizes the number of single-shard queries.

---

**Mistake 3: Forgetting about the directory / routing layer**

With sharding, your application needs to know WHERE to send each query. This is called the shard routing layer. Options:

```
Option A: Application-level routing
  - Your application code computes the shard for each query
  - Fastest (no extra network hop)
  - Requires all application servers to know the sharding logic
  - Hard to change (need to redeploy all app servers)

Option B: Proxy-based routing (shard proxy)
  - Queries go to a smart proxy that routes them
  - App does not need to know sharding logic
  - Adds one network hop (small latency cost)
  - Easier to change routing logic (update proxy, not all app servers)

Option C: Database driver routing
  - The database driver (e.g., MongoDB's driver) handles routing automatically
  - Transparent to the application
  - Works only with databases that support it natively
```

Many systems use a combination: application-level routing for common queries (fast path), proxy routing for complex queries (flexibility).

Forgetting to explain the routing layer in an interview leaves a big gap. The interviewer will ask: "How does the app know which shard to talk to?"

---

**Mistake 4: "Sharding is just partitioning."**

These terms are often used interchangeably, but they have a subtle difference worth knowing:

- Partitioning: splitting data within a single database instance. The database manages multiple partition files internally, but from the outside it still looks like one database. You still have one connection string, one set of credentials, one transaction log.
- Sharding: splitting data across multiple separate database instances. Each shard is an independent database server. You literally have 4 separate PostgreSQL servers with different IP addresses.

Partitioning is largely transparent. Sharding is explicit — your application must actively choose which server to talk to.

In practice, many people use "shard" and "partition" to mean the same thing. If your interviewer uses them interchangeably, do not correct them. But knowing the difference helps you understand the complexity boundaries.

---

**Mistake 5: Ignoring replication within shards**

Sharding and replication are not mutually exclusive — they stack.

A production sharded system almost always combines both:
- 4 shards (for write and storage scaling)
- Each shard has 3 replicas (1 leader + 2 followers, for read scaling and high availability)

Total database servers: 4 × 3 = 12 machines.

If you propose "4 shards" in an interview for a high-availability system without mentioning replicas, the interviewer will ask: "What happens if one shard goes down?" The answer: you lose 25% of your data access until that shard recovers. For most production systems, that is unacceptable.

```
Production Sharded System with Replication:

Shard 0 Leader  <- writes for users 0-2.5M
Shard 0 Replica 1 <- reads
Shard 0 Replica 2 <- reads (failover if leader dies)

Shard 1 Leader  <- writes for users 2.5M-5M
Shard 1 Replica 1 <- reads
Shard 1 Replica 2 <- reads

Shard 2 Leader  <- writes for users 5M-7.5M
Shard 2 Replica 1 <- reads
Shard 2 Replica 2 <- reads

Shard 3 Leader  <- writes for users 7.5M-10M
Shard 3 Replica 1 <- reads
Shard 3 Replica 2 <- reads

Total: 12 database servers
Write capacity: 4x a single server
Read capacity: ~12x a single server
Any single machine can fail without data loss
```

In a system design interview, describing this combined architecture shows you understand production-grade design, not just the theoretical concept.

---

**Mistake 6: Not mentioning the cost of cross-shard operations early**

Students often describe sharding enthusiastically ("we split the users across 4 shards, each handling 25% of traffic!") and then forget to mention that certain queries now require asking all 4 shards. When the interviewer asks "how do you handle analytics queries?" they are caught off-guard.

Always pair a sharding proposal with its cross-shard implications:
- "We shard by user_id, which means user profile and activity queries are single-shard and fast."
- "Analytics queries like 'active users in last 30 days' need to hit all 4 shards. We handle these through a separate data pipeline that pre-aggregates counts, so dashboards read from counters, not the live shards."

Proactively addressing this shows maturity.

---

## Chapter 21, Part B — Summary

Here is what you learned about sharding:

**Sharding basics:** Replication makes copies (scales reads). Sharding splits data (scales writes and storage). Each shard has a DIFFERENT subset of data.

**When to shard:** When writes exceed one machine's capacity, OR when data exceeds one machine's storage capacity. Not before.

**Three sharding strategies:**
- Hash sharding: even distribution, great for point queries, bad for range queries, consistent hashing minimizes data movement when scaling
- Range sharding: great for range queries, hot spots are the main danger with sequential keys
- Directory sharding: maximum flexibility, requires maintaining a critical directory service

**Shard key selection:** The most important decision. Match your most common queries. Avoid skewed keys. Avoid hot spots.

**Hot partitions:** One shard overwhelmed while others sit idle. Fix with salting, caching, dedicated infrastructure, or redesigning fan-out behavior.

**Resharding:** Moving data while the system is live. Multi-month projects. Double-write, ghost tables, or read-through migration strategies. This is why you choose carefully the first time.

**Cross-shard operations:** The price you pay for sharding. Joins become scatter-gather operations. Transactions require 2PC or Sagas. Aggregations require pre-computed counters. Co-location (putting related data on the same shard) is the best defense.

**Distributed ID generation:** Use Snowflake IDs (time-ordered, compact, no coordination needed) for most systems. UUIDs work if you do not need sortability.

---

*Part C covers: monitoring sharded systems, shard health, and operational best practices.*

*Part D covers: real-world case studies — how Instagram, Cassandra, and MongoDB handle sharding at scale.*
# Chapter 21 — Part C: Putting It All Together
## Real System Examples, Failure Modes, and Lessons from Actual Incidents

*Parts A and B covered the theory: what replication is, how sharding works, and the concepts behind both. Now we zoom out and ask: how does this stuff actually get used? What does a real growing system look like? And what happens when things go wrong?*

*This part is story-driven. We follow a fictional social network as it grows from zero to 100 million users. We look at failure scenarios with actual timelines. We study real incidents where major companies got their database architecture into trouble — and what they learned from it.*

*Think of this as the "case studies" portion of the chapter. Theory tells you the rules. Real stories teach you why the rules exist.*

---

# PART 3: Putting It All Together — Real System Examples

---

## Applied Scenario 1: How a Social Network's User Database Evolves

Let's follow a fictional social network called **Chirp**. Chirp is basically Twitter — users post short messages called "chirps," follow other users, and browse a feed. We'll watch what happens to their database architecture as they grow from 0 to 100 million users.

This is important because the right architecture at 10,000 users is completely wrong at 10 million users. And the right architecture at 10 million is over-engineered overkill at 10,000. The skill isn't knowing the "best" architecture — it's knowing when to apply which architecture.

---

### Stage 1: 0 to 10,000 Users — The Early Startup

**The situation:**

Chirp just launched. It's three engineers, a stack of ramen, and a dream. They have about 10,000 users after their first few months. Users are posting chirps, following each other, and browsing feeds. Traffic is light — maybe a few hundred requests per second on a good day.

**The architecture:**

```
+------------------+
|   App Server     |
|  (handles all    |
|   web requests)  |
+--------+---------+
         |
         | All reads AND writes
         |
+--------+---------+
|   PostgreSQL     |
|  (single node)   |
|  $100/month      |
|  2 CPU, 2GB RAM  |
|  100GB SSD       |
+------------------+
```

That's it. One app server, one database. Everything goes to the same place.

**Is this okay?**

Completely okay. At 10,000 users, a single PostgreSQL instance on a modest cloud server can handle enormous amounts of traffic — easily 5,000 to 10,000 reads per second. Chirp is nowhere near those limits. The database is barely breaking a sweat.

**What's in the database?**

- `users` table: 10,000 rows. Tiny.
- `chirps` table: maybe 500,000 rows (50 chirps per user on average). Still tiny.
- `follows` table: maybe 200,000 rows. Still tiny.

The whole database probably fits in RAM. Queries are fast. Engineers are happy.

**What the engineers are worried about:**

Honestly, not the database. They're worried about getting more users. Product-market fit. Marketing. Features. The database is not a problem.

**The trap to avoid:**

Some engineers, fresh out of school with their systems design knowledge buzzing in their heads, will look at this and say: "We should add read replicas now so we're ready when we scale." 

This is a mistake. Adding read replicas at 10,000 users adds:
- More servers to pay for (cost goes from $100/month to $300/month)
- More complexity in the codebase (routing reads to replicas, handling replication lag)
- More failure modes (replicas can fall behind, replicas can go down)
- More operational burden (monitoring two more servers)

In exchange, you get: solving a problem you don't have.

> **Staff insight:** "Engineers who add read replicas at 10,000 users are optimizing for a problem they don't have. The best database architecture is the simplest one that works. Every layer of complexity you add without a specific need is a layer of complexity you'll have to debug at 2am during an outage."

The Chirp engineers keep it simple. One server. One database. Move fast.

---

### Stage 2: 10,000 to 100,000 Users — Getting Traction

**The situation:**

Six months later, Chirp has been featured in a tech blog. Users start flooding in. They hit 100,000 users. Traffic has exploded. The database server that was barely breaking a sweat is now struggling. The engineers look at their metrics and see:

- Read queries: **20,000 per second**
- Write queries: **2,000 per second**
- The single PostgreSQL server maxes out at about **15,000 queries per second** total

The database is at 130% capacity. Queries are queuing up. Pages are loading in 8 seconds instead of 0.5 seconds. Users are complaining.

**Diagnosing the problem:**

The engineers look at the ratio: 20,000 reads vs 2,000 writes. Reads are 10× more common than writes. Most database load is from people reading chirps, not posting new ones.

This tells them the solution: handle reads separately. Add read replicas.

**The architecture:**

```
+------------------+
|   App Server     |
+--------+---------+
         |
         v
+------------------+
|   Load Balancer  |
|  (routes traffic)|
+---+----------+---+
    |          |
    |          | 90% of reads go here
    |          |
    v          v
+--------+  +-----------+-----------+
| Leader |  | Replica 1 | Replica 2 |
| (all   |  | (reads    | (reads    |
| writes)|  | only)     | only)     |
| 15K    |  | 15K/sec   | 15K/sec   |
| writes |  | capacity  | capacity  |
| /sec   |  |           |           |
+--------+  +-----------+-----------+

 10% of reads go to Leader
 (for read-your-own-writes consistency)
 
 All writes → Leader only
 90% of reads → Round-robin between Replica 1 and Replica 2
```

**The numbers:**

- Before: 1 server at 130% capacity
- After: 1 leader + 2 replicas. Each replica can handle 15,000 reads/second
- Total read capacity: 30,000 reads/second (15,000 per replica × 2)
- Write capacity: 15,000 writes/second (just the leader, but writes are only 2,000/sec so plenty of headroom)

**Cost:** Three servers instead of one. About $300/month. Still cheap.

**The new problems that appear:**

Replication means the replicas are slightly behind the leader. When a user updates their profile picture, the change hits the leader immediately. But a replica might take 50-500 milliseconds to catch up. If the user refreshes their profile page and that request gets routed to a replica... their old profile picture shows up. The change appears to have been lost. The user hits refresh again. Same thing.

This is called **read-your-own-writes** inconsistency. It's not data loss — the write is safely stored on the leader. It's just that the reads are going to a slightly-behind replica.

**The fix:** For reads immediately after a write (profile page after profile update), route to the leader. For browsing other people's feeds, read from replicas. The app layer needs to know which queries need "fresh" reads vs. which queries can tolerate slight staleness.

**What the code looks like:**

```python
# Reading your own profile — must be fresh
def get_my_profile(user_id):
    return leader_db.query("SELECT * FROM users WHERE id = ?", user_id)

# Reading someone else's feed — stale is okay
def get_chirps_for_feed(user_ids):
    return replica_db.query("SELECT * FROM chirps WHERE user_id IN (?)", user_ids)
```

**Staff insight:** At 100,000 users, the engineers spend more time on application-level routing logic (which queries go to leader vs. replica) than on the database itself. This is normal. The database is now simple again; the complexity has moved to the code.

---

### Stage 3: 100,000 to 1,000,000 Users — Scaling Up

**The situation:**

A year in. A million users. Growth is real. The engineers look at their metrics:

- Reads: 100,000 per second (handled fine by 6 replicas)
- Writes: 5,000 per second (the leader handles this fine)
- BUT: the `chirps` table is now **500GB**. Not rows — gigabytes of data.

The database has a new problem: size, not speed. Queries on a 500GB table are slow even when the CPU has capacity, because PostgreSQL has to scan through huge amounts of data. Taking a backup of a 500GB table takes 4 hours. Restoring from backup takes even longer. Adding an index to a 500GB table locks it for hours.

The writes are fine. The reads are handled. But the sheer size of the data is causing operational pain.

**The solution: functional partitioning**

This is not true sharding yet. It's simpler: split the database by feature area. Put different types of data into completely separate databases.

```
                    +------------------+
                    |   App Server     |
                    +--+------+-----+--+
                       |      |     |
          +------------+      |     +------------+
          |                   |                  |
          v                   v                  v
+------------------+  +------------------+  +------------------+
| Tweet DB         |  | User DB          |  | Follow DB        |
| (all chirps)     |  | (user profiles,  |  | (who follows     |
|                  |  |  auth, settings) |  |  whom)           |
| Leader + 2       |  | Leader + 2       |  | Leader + 2       |
| Replicas         |  | Replicas         |  | Replicas         |
|                  |  |                  |  |                  |
| 500GB data       |  | 50GB data        |  | 100GB data       |
+------------------+  +------------------+  +------------------+
```

Each database now handles its own smaller domain. The Tweet DB is still 500GB, but at least it's not sharing resources with user lookups or follow-graph queries. Each can be scaled, backed up, and maintained independently.

**The new problem that appears:**

Before functional partitioning, a query like "get all chirps from users I follow" was simple:

```sql
SELECT c.* FROM chirps c
JOIN follows f ON c.user_id = f.followed_id
WHERE f.follower_id = 12345
ORDER BY c.created_at DESC
LIMIT 20;
```

One query, one database, done.

After functional partitioning, the chirps and follows are in different databases. You can't JOIN across them. You have to do it in application code:

```python
def get_feed(my_user_id):
    # Step 1: Get the list of users I follow (from Follow DB)
    followed_user_ids = follow_db.query(
        "SELECT followed_id FROM follows WHERE follower_id = ?", my_user_id
    )
    
    # Step 2: Get recent chirps from those users (from Tweet DB)
    chirps = tweet_db.query(
        "SELECT * FROM chirps WHERE user_id IN (?) ORDER BY created_at DESC LIMIT 20",
        followed_user_ids
    )
    
    return chirps
```

Two database calls instead of one. And the `followed_user_ids` list could have thousands of entries. This is getting expensive.

**The fix: add a caching layer**

Pre-compute each user's feed and store it in Redis (an in-memory cache). When new chirps come in, update the feeds in the background. When users request their feed, serve from Redis instead of doing two cross-database queries.

```
+------------------+
|   App Server     |
+--+------+-----+--+
   |      |     |
   |      |     +-------------------------+
   |      |                               |
   v      v                               v
+--------+ +-----------+         +------------------+
| Try    | |  If miss: |         |   Redis Cache    |
| Redis  | |  Query    |         |  (pre-computed   |
| first  | |  Tweet DB |         |   user feeds)    |
|        | |  + Follow |         |  ~1ms response   |
|        | |  DB       |         |                  |
+--------+ +-----------+         +------------------+
```

Feed loads: <1ms from Redis. Cold cache miss (Redis doesn't have the feed yet): ~50ms from two database calls. The vast majority of requests hit the cache.

**At 1 million users, the architecture feels a bit messy.** There are three databases now, plus a Redis cache, plus routing logic in the app. But every component is handling a manageable load. No single component is overwhelmed.

---

### Stage 4: 1,000,000 to 10,000,000 Users — Real Scale

**The situation:**

Three years in. Ten million users. The engineers look at their metrics and find a new problem they haven't seen before:

- Writes to the chirps table: **25,000 per second**
- Maximum write throughput of the Tweet DB leader: ~20,000 per second (even on the most powerful cloud server)

For the first time, **writes are the bottleneck**, not reads. And unlike reads (which you can handle by adding more replicas), you can't solve write overload by adding more read replicas. The writes all have to go to the single leader.

Also:
- The chirps dataset is now **10TB**. That's 10,000 gigabytes. A single PostgreSQL instance has trouble with that much data efficiently.

This is the moment when true sharding becomes necessary.

**The sharding decision:**

The engineers decide to shard the chirps table. The question: what should the shard key be?

Candidate 1: shard by `chirp_id` — randomly distribute chirps across shards
Candidate 2: shard by `user_id` — all chirps from the same user go to the same shard

The most common query is: "Get the 20 most recent chirps from user X" (for displaying a user's profile page). 

If they shard by `chirp_id`, one user's chirps scatter across all 16 shards. To get user X's chirps, you'd have to query all 16 shards and merge the results. Expensive.

If they shard by `user_id`, all of user X's chirps live on the same shard. One query, one shard, done. 

**They choose to shard by `user_id`.**

**The 16-shard architecture:**

```
+---------------------+
|   App Server        |
|                     |
|  Routing: user_id % 16  --> which shard?
+-----+---------------+
      |
      | Route to correct shard
      |
+-----v-----------+
| Shard Router    |
| user 0-624999   --> Shard 0
| user 625000-    --> Shard 1
|    1249999      |
| ...             |
| user 9375000-   --> Shard 15
|    9999999      |
+---------+-------+
          |
  +-------+-------+
  |               |
+-v--------+   +--v-------+        +----------+
| Shard 0  |   | Shard 1  |  ...   | Shard 15 |
| Leader + |   | Leader + |        | Leader + |
| Replicas |   | Replicas |        | Replicas |
|          |   |          |        |          |
| ~625GB   |   | ~625GB   |        | ~625GB   |
| ~1,500   |   | ~1,500   |        | ~1,500   |
| writes/s |   | writes/s |        | writes/s |
+----------+   +----------+        +----------+
```

**The math:**

- Total write load: 25,000 writes/second
- Distributed across 16 shards: ~1,562 writes/second per shard
- Each shard's max capacity: ~20,000 writes/second
- Result: Each shard is running at ~8% capacity. Lots of headroom.

- Total data: 10TB
- Distributed across 16 shards: ~625GB per shard
- Each shard handles a manageable dataset.

**The new problem that appears:**

The shard key is `user_id`. That works great for write distribution (users are fairly evenly distributed) and for "get my chirps" queries.

But Chirp is a social network. There are celebrities. Beyoncé has 40 million followers. When Beyoncé posts a chirp, 40 million people might try to read it at almost the same time. Beyoncé's user_id maps to, say, Shard 3. Suddenly Shard 3 is handling 80% of all read traffic. The other 15 shards are barely doing anything.

This is the **celebrity problem** (also called "hot key" or "hot partition"). The data is distributed evenly (each shard has roughly equal amounts of data), but the access is not distributed evenly.

**The fix: cache celebrity content in Redis**

```
+------------------+
|   App Server     |
+--------+---------+
         |
         | Is this user a celebrity? (follower count > 1M?)
         |
    +----+----+
    |         |
    v         v
+-------+  +------------------+
| Redis |  | Normal shard     |
| Cache |  | lookup (16-shard |
| (hot  |  | database)        |
| user  |  |                  |
| data) |  | For non-celebrity|
|       |  | users            |
+-------+  +------------------+

Celebrity chirps: served from Redis (memory, <1ms)
Normal chirps: served from the appropriate shard (~5ms)
```

The celebrity shards still get writes (when Beyoncé posts), but not the massive read traffic. Redis absorbs the reads. Cold shards + hot cache. 

---

### Stage 5: 10,000,000 to 100,000,000 Users — Hyperscale

**The situation:**

Five years in. One hundred million users. Chirp is a major platform. The engineering team has grown from 3 to 300. The single "database problem" has evolved into dozens of specialized problems, each with its own solution.

**The full architecture:**

```
CHIRP AT 100M USERS — FULL ARCHITECTURE

                    +----------------------------+
                    |       Load Balancers       |
                    +---+--------+--------+------+
                        |        |        |
          +-------------+        |        +-------------+
          |                      |                      |
          v                      v                      v
   +-----------+         +-----------+          +-----------+
   | Feed API  |         | Profile   |          | Search    |
   | servers   |         | API       |          | API       |
   |           |         | servers   |          | servers   |
   +-----+-----+         +-----+-----+          +-----+-----+
         |                     |                      |
         |                     |                      |
   +-----v-----+         +-----v-----+         +------v-----+
   |           |         |           |         |            |
   | Redis     |         | User DB   |         | Search     |
   | Feed      |         | (sharded  |         | Index      |
   | Cache     |         | by        |         | (dedicated |
   | (pre-     |         | user_id,  |         | Elastic-   |
   | computed  |         | 16 shards)|         | search     |
   | feeds)    |         |           |         | cluster)   |
   |           |         +-----------+         |            |
   +-----+-----+                               +------------+
         |
         |
   +-----v-----+
   |           |         +-----------+         +------------+
   | Chirp DB  |         | Follow    |         | Media      |
   | (sharded  |         | Graph DB  |         | Storage    |
   | by        |         | (graph    |         | (S3-like   |
   | user_id,  |         | database, |         | object     |
   | 64 shards)|         | not SQL)  |         | storage,   |
   |           |         |           |         | NOT in DB) |
   +-----------+         +-----------+         +------------+

         +--------------------------------------------------+
         |              Analytics Warehouse                 |
         |  (separate read-only cluster, updated every hour)|
         |  Data analysts query this, NOT production DBs    |
         +--------------------------------------------------+
```

At 100M users, "the database" doesn't exist. There are dozens of specialized data stores:

**1. Chirp Database (64 shards)**
- Purpose: store chirps
- Sharding: by user_id (started at 16 shards, grew to 64 over time as data grew)
- Total data: ~100TB
- Data per shard: ~1.5TB
- Access pattern: "get user X's chirps," "get this specific chirp"

**2. User Database (16 shards)**
- Purpose: store user profiles, authentication, settings
- Sharding: by user_id
- Total data: ~5TB
- Access pattern: "get user X's profile," "update user X's settings"

**3. Follow Graph Database**
- Purpose: store who follows whom
- This is NOT a regular SQL table anymore — it's a **graph database** (specialized for relationships)
- Why? The "who follows whom" data is a network graph. Queries like "who does user X follow?" and "who follows user X?" and "suggest users for X to follow" are graph traversals. Graph databases handle this much more efficiently than SQL.
- Total data: ~50TB (100M users, each following ~500 people on average = 50B edges)

**4. Media Storage (Object Storage, not a database)**
- Purpose: store photos, videos, GIFs in chirps
- This is not a database at all — it's object storage (think: a giant file system in the cloud, like Amazon S3)
- Why? Databases are optimized for structured data with queries. A JPEG image is just a blob of bytes. You don't need to query inside it. You just need to store it cheaply and serve it fast.
- Each photo might be 1-5MB. If 1M photos uploaded per day, that's 1-5TB of raw media per day.
- Storing terabytes of binary blobs in a SQL database is expensive and slow. Object storage is 10-100× cheaper per GB.

**5. Redis Feed Cache**
- Purpose: pre-computed feeds for each user
- When someone you follow posts a chirp, the system "fans out" and pushes that chirp into the feed caches of all their followers
- Your feed loads in <1ms because it's just reading a sorted list from memory
- Trade-off: celebrities with 40M followers can't fan out (would require writing to 40M Redis keys per chirp). Celebrity content is handled differently — pulled and merged at read time.

**6. Search Index (Elasticsearch)**
- Purpose: full-text search of chirps ("find all chirps mentioning 'earthquake'")
- SQL databases are terrible at full-text search. Elasticsearch is specialized for it.
- Data is replicated from the Chirp Database into Elasticsearch in near-real-time.

**7. Analytics Warehouse**
- Purpose: business intelligence, data science, trend analysis
- This is a read-only copy of all the data, updated hourly
- Data analysts can run slow, complex queries against this without impacting production databases
- "How many chirps were posted yesterday?" against the analytics warehouse: takes 10 seconds, fine
- "How many chirps were posted yesterday?" against the production Chirp DB: would lock tables and cause an outage, not fine

> **Staff insight:** "At 100M users, you don't have 'the database.' You have dozens of specialized data stores, each optimized for its specific access pattern. A graph database for social connections, object storage for media, an in-memory cache for feeds, a search engine for text search, a warehouse for analytics — they're all handling different pieces of the same overall problem. The skill is knowing which tool is right for which piece."

---

### The Growth Thresholds — A Quick Reference

Here's the full picture of when to make each architectural change:

```
+------------------+---------------------------+---------------------------+
| User Scale       | Architecture              | Why This Change?          |
+------------------+---------------------------+---------------------------+
| 0 — 10K          | Single database           | Simple, no replication.   |
|                  | (no replication)          | One server handles it all.|
|                  |                           | Don't optimize early.     |
+------------------+---------------------------+---------------------------+
| 10K — 100K       | Add read replicas         | Reads outpace the leader. |
|                  | (1 leader + 2-3 replicas) | 3-5× read capacity boost. |
|                  |                           | Writes still one leader.  |
+------------------+---------------------------+---------------------------+
| 100K — 1M        | Functional partitioning   | Data size becomes         |
|                  | (separate DBs by feature) | unmanageable as a monolith|
|                  |                           | Separate concerns for     |
|                  |                           | independent scaling.      |
|                  |                           | Add caching layer.        |
+------------------+---------------------------+---------------------------+
| 1M — 10M         | Shard high-growth tables  | Write volume exceeds what |
|                  | (16 shards for hot tables)| one server can handle.    |
|                  |                           | Data too big for one node.|
|                  |                           | Requires shard key design.|
+------------------+---------------------------+---------------------------+
| 10M — 100M       | Per-feature specialized   | Different access patterns |
|                  | databases                 | need different tools.     |
|                  | (graph DB, object         | Analytics must be isolated|
|                  |  storage, search,         | from production.          |
|                  |  analytics warehouse)     | Scale each piece          |
|                  |                           | independently.            |
+------------------+---------------------------+---------------------------+
| 100M+            | Same as above, but        | Optimization becomes the  |
|                  | more shards, more         | main work. Performance     |
|                  | specialized, geographically| vs. consistency          |
|                  | distributed               | trade-offs everywhere.    |
+------------------+---------------------------+---------------------------+
```

The key insight: you don't need to build the 100M architecture when you're at 10K. You need to build the architecture that handles your current scale comfortably, with enough room to grow to the next stage before you have to change it again.

Premature optimization is a real cost. Every layer of complexity you add early is a layer your small team has to maintain, debug, and work around while trying to build features.

---

## Applied Scenario 2: How a Rate Limiter Uses Sharding

This scenario is different from the social network story. It's not about storing user content — it's about a specific operational problem: preventing abuse. And it's a great example of how sharding solves a problem you might not expect.

---

### The Problem: You Can't Send Unlimited Emails

Imagine Chirp has a feature: you can email notifications to your followers. But spammers exist. Without a limit, a spammer could create a Chirp account and send 10 million notification emails in a minute.

The rule: **no user can send more than 100 emails per minute**.

For every email a user tries to send, the system has to check: "how many emails has this user sent in the last 60 seconds?" If fewer than 100, allow it. If 100 or more, block it.

---

### Simple with One Database

With one database, this is easy:

```sql
SELECT COUNT(*) 
FROM email_sends 
WHERE user_id = 12345 
  AND sent_at > NOW() - INTERVAL 1 MINUTE;
```

If the result is less than 100, update the count and allow the email. Done.

**But here's the scale problem:**

Chirp has 10 million users. Each of them might be clicking "send notification" simultaneously. That's potentially 10 million count-check queries hitting the database every minute. A single database maxes out at maybe 50,000-100,000 simple queries per second. At 10M checks per minute, that's ~167,000 per second — over capacity.

---

### Sharding the Rate Limiter

Shard the rate-limiting counters by `user_id`. With 16 shards:

- User 12345 → Shard 2 (12345 % 16 = 1, let's say Shard 2 for illustration)
- Each shard handles ~625,000 users' rate limit counters
- 10M users / 16 shards = 625,000 users per shard

Now instead of 167,000 queries per second on one server, each shard handles 167,000/16 = ~10,000 queries per second. Each shard can handle that easily.

**But there's a new problem:**

What if the same user tries to send emails from two different devices at the exact same time? Both requests hit the same shard (correct — same user_id). But if both requests arrive within milliseconds of each other, this can happen:

1. Request A reads counter: "user 12345 has sent 99 emails this minute"
2. Request B reads counter: "user 12345 has sent 99 emails this minute" (reads before A updated it)
3. Request A: counter is 99 < 100, so increment to 100 and allow
4. Request B: counter is 99 < 100, so increment to 100 and allow

Both requests were allowed! But the user should have only gotten 1 more email allowed, not 2. This is a **race condition** — two operations reading and writing the same value at the same time, stepping on each other.

---

### The Fix: Redis with Atomic Increments

Instead of a database with read-then-write operations, use Redis (an in-memory database) with **atomic increment** (INCR).

Atomic means: the read-and-increment happen as one indivisible operation. No other request can squeeze in between. It's like a bank teller who counts your money and stamps your card in one motion without looking up. The person behind you has to wait until that entire motion is complete.

```
+------------------+  +------------------+  +------------------+
|   App Server 1   |  |   App Server 2   |  |   App Server 3   |
+--------+---------+  +--------+---------+  +--------+---------+
         |                     |                     |
         |                     |                     |
         +----------+----------+----------+----------+
                    |
                    v
         +----------+----------+
         | Redis Cluster        |
         | (also sharded by     |
         |  user_id)            |
         |                      |
         | Shard 0: users 0-625K|
         | Shard 1: users 625K-1.25M |
         | ...                  |
         | Shard 15: users 9.375M-10M|
         +----------+-----------+
```

**The pseudocode for the rate check:**

```python
def rate_check(user_id, limit=100):
    # Build a key that's unique per user per minute
    current_minute = datetime.now().strftime("%Y-%m-%d-%H-%M")
    key = f"rate:{user_id}:{current_minute}"
    
    # INCR is atomic — it increments and returns the new value
    # in one operation. No race condition possible.
    count = redis.INCR(key)
    
    # If this is the first increment, set the key to expire after 60 seconds.
    # This means we don't need to manually clean up old counters —
    # Redis auto-deletes them after a minute.
    if count == 1:
        redis.EXPIRE(key, 60)  # Auto-delete after 60 seconds
    
    if count > limit:
        return "RATE_LIMITED"   # Block the email
    
    return "ALLOWED"            # Let the email through
```

Let's trace through the race condition scenario again with Redis INCR:

1. Request A: calls `INCR("rate:12345:2024-01-15-09:30")` → Redis atomically increments from 99 to 100 and returns 100. Count is 100. 100 > 100? No, 100 == 100, not over limit. **ALLOWED.**
2. Request B: calls `INCR("rate:12345:2024-01-15-09:30")` → Redis atomically increments from 100 to 101 and returns 101. Count is 101. 101 > 100? Yes. **RATE_LIMITED.**

No race condition. The atomic increment means only one request can "claim" the 100th slot.

---

### The Beauty of This Design

Let's appreciate how elegant this is:

**No stored emails.** You don't store the actual emails in the rate limiter. You don't store timestamps of individual emails. You just store one counter per user per minute. One Redis key: `rate:12345:2024-01-15-09:30`.

**Auto-cleanup.** The `EXPIRE 60` means Redis automatically deletes the counter after 60 seconds. No background cleanup job needed. No growing table of old timestamps. The database automatically stays small.

**How small?** At any given moment, there's at most one key per active user per minute. If 100,000 users are sending emails simultaneously, that's 100,000 Redis keys, each a few bytes. Maybe 1MB of memory total. Redis can hold billions of small keys in memory.

**Sharding scales it further.** By sharding Redis by user_id, each Redis shard handles 1/N of the keys and 1/N of the traffic. You can add shards as traffic grows.

**Diagram of the full flow:**

```
User clicks "Send Notification"
         |
         v
+-------------------+
| App Server        |
| rate_check(12345) |
+--------+----------+
         |
         | Hash: user 12345 → Redis Shard 2
         |
         v
+-------------------+
| Redis Shard 2     |
| INCR rate:12345:  |
|   2024-01-15-09:30|
|                   |
| Returns: 47       |
+-------------------+
         |
         | 47 < 100? Yes → ALLOWED
         |
         v
+-------------------+
| Email Service     |
| (sends the email) |
+-------------------+
```

This is a real-world use case of sharding that most tutorials skip. Sharding isn't just for "I have too much data." It's also for "I have too many small operations that a single server can't handle."

---

## Applied Scenario 3: The E-Commerce Platform (Staff-Level Design)

The social network was about storing and retrieving content. The rate limiter was about counting and blocking. Now let's tackle something that has to be both fast AND perfectly correct: an e-commerce platform where transactions involve real money.

**The platform specs:**
- 50 million users
- 5 million products
- 100 million orders processed per day (~1,150 per second on average, 10,000+ during peak)
- Need to: look up user orders, browse product catalog, process new orders, search products

---

### Shard Key Design for Each Data Type

The most important decisions at this scale are shard key choices. Let's think through each table independently.

---

**Table 1: Users**

The primary access pattern: "Get me user X." Almost always a point query — fetch one specific user by ID. Nobody queries "get me all users named John Doe" at checkout.

**Shard key: user_id (hash)**

With a hash of user_id:
- User 12345 → Shard 5
- User 98765 → Shard 11
- Users are roughly evenly distributed (hash functions spread values uniformly)

Point queries are perfect for this: routing is instant, and all user data is in exactly one place.

```
Query: "Who is user 12345?"
        |
        | hash(12345) % 16 = 5
        |
        v
      Shard 5 → return user profile
```

---

**Table 2: Orders**

This is the most important and most interesting shard key decision.

The naive choice: shard by `order_id`. Each order gets a unique ID; distribute them across shards.

The problem with that: the most common query is "show me all my orders." A user might have 50 orders over 5 years of shopping. If those 50 orders are distributed across 16 shards (because we sharded by order_id), getting all of them requires querying all 16 shards and merging. Slow. Expensive.

**Shard key: user_id (NOT order_id)**

All of a user's orders land on the same shard as the user. "Show me all my orders" goes to exactly one shard:

```
Query: "Show me all orders for user 12345"
        |
        | hash(12345) % 16 = 5
        |
        v
      Shard 5 → return all orders where user_id = 12345
                 (all co-located, fast scan)
```

What about looking up a specific order by order_id? "What's the status of order 78901?" You need to know which user placed it to find which shard. So the system stores order_id → user_id in a small lookup table (or the order_id is designed to encode the shard number). A small extra step, but worth the efficiency gain on the main query.

---

**Table 3: Products**

5 million products, each about 1KB of data (name, description, price, attributes). That's 5GB of product data. Not enormous.

The naive approach: shard by product_id. 5M products across 16 shards = ~312,500 products per shard, ~300MB per shard.

**But why shard this at all?**

Products are written rarely (new product listings, price updates) and read constantly (every browse page, every checkout). It's a heavily read-dominant dataset that's small enough to fit in memory.

**Better approach: replicate the product catalog to every shard**

Don't shard products. Instead, every shard has a full copy of the product catalog. 5GB × 16 copies = 80GB total storage, which is inexpensive. The benefit: no cross-shard product joins. When an order query on Shard 5 needs product info, it queries the local product replica on Shard 5. Zero cross-shard network calls for product lookups.

```
                    EACH SHARD
+------------------------------------------+
|  Shard N                                 |
|                                          |
|  user_data (1/16 of all users)           |
|  order_data (1/16 of all orders)         |
|  product_catalog (FULL COPY — all 5M)    |
|                                          |
|  "Show me user 12345's order 78901       |
|   with full product details"             |
|   → All data is right here, no hops      |
+------------------------------------------+
```

This is a clever trade-off: you spend 80GB of storage to eliminate cross-shard product lookups entirely.

---

**Table 4: Order_Items**

An order consists of multiple items (you ordered 3 products in one checkout). These are stored in the `order_items` table.

**Shard key: order_id, which maps to user_id**

Since we want "what was in order 78901?" to be a single-shard query, we shard order_items the same way as orders: by the user_id that placed the order. Co-location. An order and all its items live on the same shard.

```
user 12345 → Shard 5
  order 78901 by user 12345 → Shard 5
  order_items for order 78901 → Shard 5

Query: "What was in order 78901?"
  → Shard 5, JOIN orders + order_items
  → Single shard, fast
```

---

### The Checkout Flow — A Cross-Service Transaction

Here's where e-commerce gets genuinely hard. Placing an order isn't just writing a row to a database. It requires multiple steps across multiple systems, all of which have to succeed or fail together:

1. **Check inventory:** Does product X have stock? Reserve 1 unit.
2. **Charge payment:** Deduct from user's payment method.
3. **Create order:** Write the order to the orders shard.
4. **Deduct inventory:** Commit the inventory reduction.

These steps touch different services (inventory service, payment service, order service). Each service might have its own database. They might be on different shards or different database clusters.

The problem: what if step 2 (charge payment) succeeds but step 3 (create order) fails? The user was charged but has no order. That's a real-money bug.

**Why we can't use a simple database transaction:**

A classic SQL transaction (BEGIN; ...; COMMIT;) works when all the operations are in the same database. You either commit everything or roll everything back.

But in a sharded, multi-service system, the steps are in different databases. There's no "global transaction" that spans them.

**The solution: the Saga pattern**

Think of a checkout as a **journey with checkpoints**. Each step is a checkpoint. If any checkpoint fails, you retrace your steps back to the beginning, undoing each completed checkpoint in reverse order.

```
SAGA: CHECKOUT FLOW

Forward journey:
Step 1: Reserve inventory (mark 1 unit of product X as "pending")
           ↓ success
Step 2: Charge payment ($49.99 from user's card)
           ↓ success
Step 3: Create order (write order_id=78901 to orders shard)
           ↓ success
Step 4: Confirm inventory deduction (mark reservation as complete)
           ↓ success
→ CHECKOUT COMPLETE

But what if Step 3 fails?

Backward journey (compensating transactions):
Step 3 FAILS → trigger compensation steps
   ↓
Undo Step 2: Refund the $49.99 charge
   ↓
Undo Step 1: Release the inventory reservation (mark unit as available again)
   ↓
→ CHECKOUT ROLLED BACK. User sees: "Sorry, checkout failed. No charge was made."
```

Each "undo" step is called a **compensating transaction**. Unlike a database rollback (which is instant and guaranteed), compensating transactions involve real API calls that can themselves fail. This makes the Saga pattern more complex but also more flexible — it works across services that don't share a database.

**The four steps and their compensating transactions:**

| Step | Forward Action | Compensating Transaction |
|------|---------------|--------------------------|
| 1 | `inventory.reserve(product_id, qty)` | `inventory.release(reservation_id)` |
| 2 | `payment.charge(user_id, amount)` | `payment.refund(charge_id)` |
| 3 | `orders.create(user_id, items)` | `orders.cancel(order_id)` |
| 4 | `inventory.confirm(reservation_id)` | *(already final — step 3 failed before this)* |

The Saga pattern doesn't make failures disappear. It makes them **manageable**. When something goes wrong, there's a clear, automated path to a consistent state.

---

# PART 4: Failure Modes — What Can Go Wrong (and What to Do)

The previous sections were about building things that work. This section is about what happens when things break — and the honest truth is, in distributed systems, things will break. The question isn't if a failure will happen; it's when, and whether you catch it before your users do.

---

## The Failure Mode Decision Tree

When something goes wrong, you need to diagnose quickly. This table is your first instinct guide — when you see a symptom, this points you at the likely cause and first action:

```
+----------------------------+------------------+------------------------+
| SYMPTOM                    | LIKELY CAUSE     | FIRST ACTION           |
+----------------------------+------------------+------------------------+
| ALL writes failing         | Leader is down   | Check leader health;   |
|                            |                  | promote a replica.     |
+----------------------------+------------------+------------------------+
| SOME reads returning       | Replication lag  | Route critical reads   |
| old/stale data             |                  | to leader temporarily. |
+----------------------------+------------------+------------------------+
| Latency spikes on 1        | Hot partition    | Enable caching for     |
| specific shard only        | (hot key)        | the hot data.          |
+----------------------------+------------------+------------------------+
| Partial users affected     | One shard is     | Trigger shard failover.|
| (a specific subset)        | down             | Other shards are fine. |
+----------------------------+------------------+------------------------+
| Data inconsistent; users   | Split brain      | FENCE THE OLD LEADER   |
| seeing contradictory info  | (two leaders)    | IMMEDIATELY.           |
+----------------------------+------------------+------------------------+
| Everything slow; all       | Network          | Investigate network    |
| operations degraded        | partition or     | infrastructure first.  |
|                            | infrastructure   | Not a DB fix.          |
+----------------------------+------------------+------------------------+
```

**Why the order matters:**

Not all failures are equal. Priority order:

1. **Split brain** — most dangerous. Two leaders accepting writes = data corruption growing by the second. Every second you wait, the divergence grows. Act immediately.

2. **Leader down** — most visible. Every write is failing. Users notice immediately. But the fix is clear: promote a replica.

3. **Shard down** — serious but contained. 1/16 of users are affected. The fix is clear: failover the shard.

4. **Replication lag** — subtle and silent. No errors, just stale data. Users might complain that their changes "aren't saving." Hard to detect without monitoring. Important to fix but not immediately dangerous.

5. **Hot partition** — degrades gradually. Starts as elevated latency on one shard, can cascade into a full outage if not addressed. Fix with caching.

---

## Replication Failure Modes

### Failure Mode 1: The Leader Crashes

**The story:**

It's 2:17am. You're asleep. Your phone lights up. Your monitoring system is screaming. Every write to Chirp's User Database is failing. The error: "connection refused." Your PostgreSQL primary server died — hardware failure, disk failure, power supply, something. It's gone.

Every user trying to log in gets an error. Every user trying to update their profile gets an error. Read replicas are still up and serving reads. But without the leader, nothing can be written.

**What happens next, step by step:**

```
STEP 1: Health checks detect failure (5 to 30 seconds after crash)
   Monitoring systems ping the leader every few seconds.
   No response for 3 consecutive checks? Alert fires.
   
STEP 2: Automatic failover OR human makes the call
   If you have automatic failover (e.g., using Patroni for PostgreSQL,
   or AWS RDS Multi-AZ): the system automatically selects a replica
   to promote. No human needed for this step.
   
   If manual: an on-call engineer gets paged, decides which replica
   to promote, runs the promotion command.

STEP 3: Replica is promoted to new leader
   The chosen replica stops accepting replication from the old leader.
   It now accepts writes directly.
   It becomes the new source of truth.

STEP 4: Application configuration updated
   The app's database config points to the new leader's IP address.
   Either automatically (service discovery) or manually (config change + restart).
   
STEP 5: Other replicas redirect to new leader
   Any remaining replicas now replicate from the new leader, not the old one.

STEP 6: Old leader comes back (maybe)
   Hardware is replaced. Old server comes back up.
   Critical: it must NOT become leader again automatically.
   If it did, you'd have two leaders again — split brain.
   It must come back as a replica, replicating from the new leader.
   The data it "missed" while it was down gets replicated to it.
```

**Diagram of the failover:**

```
BEFORE (normal operation):
+----------+     replication    +----------+
| Leader   | ----------------> | Replica 1|
|          | ----------------> | Replica 2|
|          |                   | Replica 3|
+----------+                   +----------+

FAILURE:
+----------+                   +----------+
| Leader   |  X   CRASHED      | Replica 1|
| (DEAD)   |                   | Replica 2|
|          |                   | Replica 3|
+----------+                   +----------+

FAILOVER (elect Replica 1 as new leader):
+----------+     replication    +----------+
| Old      |  (demoted to      | NEW      |
| Leader   |   replica when    | LEADER   |
| (COMING  |   it returns) --> | (was     |
| BACK AS  |                   | Replica  |
| REPLICA) |                   | 1)       |
+----------+                   +----------+
                                    |
                              replication
                                    |
                               +----+----+
                               |Replica 2|
                               |Replica 3|
                               +---------+
```

**The data loss question:**

Whether you lose data depends on replication mode:

- **Async replication:** The leader acknowledged writes without waiting for replicas to confirm. Any writes in the last few seconds (between the last sync and the crash) exist only on the old leader's disk — which is dead. Those writes are **lost**.
  - Acceptable for: social media posts, likes, non-critical data
  - Unacceptable for: financial transactions, medical records

- **Sync replication:** The leader only acknowledged a write after at least one replica confirmed it. When the leader crashes, the designated replica has everything the leader had. **Zero data loss.**
  - Cost: every write is slower (has to wait for replica to confirm)
  - Acceptable for: financial transactions, anything where data loss is unacceptable

There's no right answer — it's a trade-off between write latency and data loss risk.

---

### Failure Mode 2: Replication Lag Spike

**The story:**

Chirp is running a major marketing campaign. A celebrity endorsement drops at noon and 10 million people sign up in an hour. The write rate to the User Database leader spikes from 2,000 per second to 20,000 per second. The leader is handling it — barely. But the replicas are struggling to keep up.

The leader is writing data faster than the replicas can apply changes. Normally, replication lag is 50ms — by the time a user refreshes their page, their changes are already on the replicas. Now replication lag grows to 5 seconds, then 30 seconds, then 2 minutes.

**What users experience:**

A user signs up and immediately tries to log in. The signup wrote to the leader. But 30 seconds later, the user's login request hits a replica that still doesn't have their account. They get "account not found." They try to sign up again. "Email already taken." 

Their account exists — it's on the leader. The replica is just 30 seconds behind. But from the user's perspective, it looks like the system is broken.

**This is "silent degradation."** There are no database errors. The CPU isn't maxed. Disk isn't full. Every query succeeds. It's just that the answers are stale. Without monitoring specifically for replication lag, you wouldn't know this was happening until users started complaining.

**How to detect it:**

- MySQL: `SHOW SLAVE STATUS;` — look at `Seconds_Behind_Master`
- PostgreSQL: `SELECT * FROM pg_stat_replication;` — look at `write_lag`, `flush_lag`, `replay_lag`
- Alert threshold: 5 seconds of lag → alert. 5 minutes of lag → page the on-call engineer.

**How to fix it when it happens:**

Option A: Throttle writes. If the leader is writing too fast for replicas to keep up, slow down the writes at the application layer. Introduce a brief delay between bulk operations. This is painful — it means slowing down your product during peak time.

Option B: Route critical reads to the leader. If lag is growing, stop sending reads to replicas and send everything to the leader until lag subsides. The leader will be under more load, but users won't see stale data.

Option C: Upgrade replica hardware. If replicas are slower than the leader at applying writes, get faster replicas. More CPU to apply transactions, faster disk to write WAL.

Option D: Add more replicas and shard earlier. Ultimately, if the leader's write volume is too high for replicas to keep pace, you're approaching the point where you need to shard.

---

### Failure Mode 3: Split-Brain (The Scariest One)

**The story:**

It's worth taking time on this one because it's both the most dangerous failure mode and the most common one that engineers don't fully understand until they've seen it.

Imagine Chirp has a two-datacenter setup. Data Center West (DCW) in California, Data Center East (DCE) in Virginia. The PostgreSQL leader lives in DCW. Two read replicas live in DCE.

A fiber optic cable is cut by a construction crew in Kansas City — this literally happens, regularly. The network link between DCW and DCE goes down.

**From DCE's perspective:**

The replicas in DCE can no longer reach the leader in DCW. Is the leader dead? Or just unreachable due to network issues? The replicas don't know. After a configurable timeout (say, 30 seconds), DCE's automatic failover kicks in: it elects one of the DCE replicas as a new leader.

**From DCW's perspective:**

The leader in DCW is fine. Hardware is fine. The network went out, but the server is healthy. It's still accepting writes from users whose traffic happens to be routed to DCW. It doesn't know DCE elected a new leader.

**You now have two leaders:**

```
DCW (California)          DCE (Virginia)
+----------+              +----------+
| ORIGINAL |              | NEW      |
| LEADER   |              | LEADER   |
|          |              |(was rep.)|
| accepting|   NETWORK    | accepting|
| writes   |   X CUT      | writes   |
|          |              |          |
| User A's |              | User B's |
| data     |              | data     |
+----------+              +----------+

User A updates their bio on DCW → bio updated on DCW leader
User B updates their bio on DCE → bio updated on DCE leader

30 minutes later, network cable repaired. Both leaders reconnect.
```

**When the network heals, you have a problem:**

User A's bio was updated on the DCW leader. User B's bio was updated on the DCE leader. But each leader also has data about the other user — just stale, from before the split. Who's right? Which version is the "real" one?

There's no automatic answer. Some changes can be merged (if the same record wasn't touched by both). Some can't (if both leaders tried to update the same user's account balance, you can't just "merge" two different numbers). You might have to manually inspect the diverged data and decide which writes to keep. This takes hours. Sometimes the "losing" data is gone forever.

**This is data corruption caused by two nodes thinking they're in charge.**

**The prevention: FENCING**

Fencing is like a power cut-off switch. When the DCE replicas decide to elect a new leader, before the new leader starts accepting writes, the system must ensure the old leader is physically prevented from writing.

The fencing mechanism sends a message to the DCW leader: "You are no longer the leader. Stop accepting writes." If the DCW leader can't be reached to confirm this (because the network is cut), the system uses a "fence token" — the new leader gets a higher-numbered token. The old leader, if it ever reconnects, is forced to check its token against the current token. If its token is lower, it refuses to accept writes and demotes itself.

Like cutting off access to someone's ID badge before issuing them a new one. The old badge stops working the moment the new one is issued, even if the person with the old badge is somewhere where you can't physically reach them.

**Diagram:**

```
NORMAL OPERATION:
+----------+       +----------+
| Leader   | ----> | Replica  |
|(token=5) |       |(token=5) |
+----------+       +----------+

NETWORK PARTITION:
+----------+   X   +----------+
| Leader   |       | Replica  |
|(token=5) |       | can't    |
|          |       | reach    |
|          |       | leader   |
+----------+       +----------+

FENCING:
+----------+       +----------+
| Old      |       | NEW      |
| Leader   |       | LEADER   |
|(token=5) |       |(token=6) |
|          |       |          |
| If OLD reconnects: token=5 < token=6
| → OLD leader refuses writes, demotes itself
| → Only NEW leader (token=6) accepts writes
+----------+       +----------+

RECONCILIATION (after network heals):
+----------+       +----------+
| Old node |  <----| NEW      |
|(now rep.)|repl.  | LEADER   |
|(gets data|from   |(token=6) |
| it missed)|leader|          |
+----------+       +----------+
```

**The lesson:** In distributed systems, you can't always distinguish "that server is dead" from "that server is unreachable." Fencing ensures that even if a server is alive but unreachable, it stops acting as leader before a new one takes over.

> **Staff insight:** "Split brain can happen in a few seconds. The data divergence it creates can take hours to reconcile. And for financial data, some divergence might never be cleanly reconcilable — you have to pick a winner and write off the loss. Fencing is not optional. It's the one mechanism that prevents the most expensive class of database failure."

---

## Sharding Failure Modes

### Failure Mode 1: A Shard Goes Down

**The story:**

Chirp's tweets database has 16 shards. Shard 7 experiences a disk failure. The leader on Shard 7 is dead. Automatic failover promotes a replica to leader. Failover takes 45 seconds.

During those 45 seconds, users whose user_ids map to Shard 7 can't access their tweets. New tweets fail with errors. Reading old tweets fails with errors.

**The blast radius:**

With 16 shards: 1/16 of users are affected. That's 6.25%. Out of 10 million users, that's 625,000 users who get errors for ~45 seconds. That's real and unpleasant.

But here's the thing — 93.75% of users notice absolutely nothing. They continue scrolling, posting, and using the app normally. A single failure is contained to a predictable fraction of users.

**Compare this to the pre-sharding world (one big database):** That same disk failure takes down the ENTIRE platform. 100% of users get errors. The blast radius is catastrophic instead of contained.

**The blast radius table:**

```
+-------------+-------------------+------------------------+---------------------------+
| # of Shards | % Users Affected  | Users Affected         | Blast Radius Comment      |
|             | per Shard Failure | (at 10M total users)   |                           |
+-------------+-------------------+------------------------+---------------------------+
| 1 (no shard)| 100%              | 10,000,000             | Full outage. All users.   |
+-------------+-------------------+------------------------+---------------------------+
| 4           | 25%               | 2,500,000              | Severe. Major incident.   |
+-------------+-------------------+------------------------+---------------------------+
| 8           | 12.5%             | 1,250,000              | Bad. Significant users.   |
+-------------+-------------------+------------------------+---------------------------+
| 16          | 6.25%             | 625,000                | Moderate. Contained.      |
+-------------+-------------------+------------------------+---------------------------+
| 32          | 3.125%            | 312,500                | Smaller. Acceptable for   |
|             |                   |                        | most companies.           |
+-------------+-------------------+------------------------+---------------------------+
| 64          | 1.5625%           | 156,250                | Small. Minor incident.    |
+-------------+-------------------+------------------------+---------------------------+
| 128         | 0.78%             | 78,125                 | Very small. Background    |
|             |                   |                        | noise.                    |
+-------------+-------------------+------------------------+---------------------------+
```

This is an underappreciated benefit of sharding. Engineers think about sharding to handle scale (more data, more writes). They often don't think about sharding as a way to reduce blast radius. But for very large systems, the blast-radius reduction is often the MORE important reason to have many shards.

**Real-world consequence of a shard going down:**

If you have 1 million users and 16 shards:
- Shard down = 62,500 users can't access their data
- Until failover completes: ~5 to 15 minutes (depends on failover automation)
- During failover: those 62,500 users get errors on every operation
- After failover: they're back to normal. Nobody else noticed.

---

### Failure Mode 2: Hot Partition Cascade

**The story:**

This is one of the most common ways a database architecture fails in production, and it almost always involves something unexpected going viral.

A celebrity tweets something controversial. Within minutes, 10 million people simultaneously try to read tweet_id=99999. That tweet was posted by user_id=88888. user_id 88888 maps to Shard 7.

```
NORMAL (baseline):
Shard 7 CPU: 15%    Latency: 5ms    Queries/sec: 2,000

VIRAL TWEET (t=0):
Shard 7 CPU: 95%    Latency: 200ms  Queries/sec: 50,000

QUEUE BUILDUP (t=30 seconds):
Shard 7 CPU: 100%   Latency: 2,000ms  Queries/sec: 50,000+
(queries are queuing because the shard can't process them fast enough)

TIMEOUTS BEGIN (t=60 seconds):
Users' requests time out after 3 seconds of waiting.
App servers retry. Now there are 2× the outstanding requests.
Shard 7 CPU: 100%   Latency: 5,000ms  Retry storm begins.

CRASH (t=90 seconds):
Shard 7 runs out of connection slots. New connections refused.
Existing connections time out.
All users on Shard 7 get errors.
```

**The retry storm amplifies the failure:**

When your request to Shard 7 times out, what does the app server do? It retries. This is normally sensible behavior. But when the shard is already overloaded, retries from the first wave of failed requests arrive on top of new requests from new users. The load doubles. Then triples. The shard that was barely surviving at 100% CPU is now being asked to do 300% capacity. It collapses completely.

This is called a **retry storm** (also sometimes "thundering herd"). A temporary overload becomes a total outage because of rational retry behavior from clients that don't know the server is already dying.

**The three-part fix:**

Fix 1: **Circuit breaker** — after a shard fails to respond N times in a row, stop sending it requests entirely. Give it a "recovery window" to breathe. This breaks the retry storm. Users get errors, but clean "service unavailable" errors instead of hanging timeouts that cause more retries.

```python
# Circuit breaker pseudocode
if shard_7.failure_count > 10:
    # Open the circuit — don't even try
    raise ServiceUnavailableError("Shard 7 circuit open")

try:
    result = shard_7.query(...)
    shard_7.failure_count = 0  # Reset on success
except TimeoutError:
    shard_7.failure_count += 1
    raise
```

Fix 2: **Caching** — the viral tweet is being read by millions of people who all want the exact same data. Put that tweet in Redis. The first request hits Shard 7 and gets cached. Every subsequent request serves from Redis (memory, <1ms). Shard 7's load drops from 50,000 queries/sec to ~1 query/sec (just cache updates when the tweet is edited).

Fix 3: **Rate limiting at the shard level** — if Shard 7 is getting more than X,000 queries per second, reject excess queries with a backpressure signal ("slow down, try again in 1 second"). This prevents runaway queue buildup.

---

### Failure Mode 3: Resharding Failure Mid-Migration

**The story:**

This is a nightmare scenario that's more common than people think, because resharding is inherently a dangerous operation.

Chirp is growing. They're at 64 shards and need to move to 128 shards. The migration plan: move half the data from each existing shard to a new set of 64 shards. A slow, careful migration.

On Day 60 of the migration, a disk failure occurs on the server running the migration scripts. Some user data was being moved from Shard 3 to the new Shard 67. The migration was 50% done for those users. Those users' data is now:
- Partially on Shard 3 (the rows that haven't been moved yet)
- Partially on Shard 67 (the rows that were moved before the failure)
- But the routing config hasn't been updated yet (users still route to Shard 3)

When users whose data was being migrated try to access their accounts, Shard 3 returns partial data (half their chirps are missing because they were already moved to Shard 67). Users see incomplete timelines. Some users appear to not exist.

**Why this is terrifying:** The migration is supposed to be invisible to users. Instead, it's causing data integrity failures during what should be a routine (if slow) maintenance operation.

**The analogy:** Resharding is like reorganizing a library while people are actively using it. You're trying to move books from section A to section B while people are checking books out, returning books, and asking librarians where things are. At any point, a book might be in transit — not yet on the new shelf, not anymore on the old shelf.

**Prevention: the double-write + verify + cutover pattern**

Step 1: **Double-write (days 1 through 30)**
Route all writes to BOTH old shards and new shards. Every new tweet goes to Shard 3 AND Shard 67. Reads still come from old shards (source of truth). New shards are building up their data in parallel.

```
DOUBLE-WRITE PHASE:
Write → Shard 3 (original, authoritative)
Write → Shard 67 (new, shadow copy)

Read ← Shard 3 (still the source of truth)
```

Step 2: **Backfill (days 31 through 59)**
Copy historical data from old shards to new shards. This is the slow part. Verify checksums: every row on Shard 67 should exactly match the corresponding row on Shard 3.

Step 3: **Verify parity (days 60 through 63)**
Run checksums and row counts. New shards should have exactly the same data as old shards. No missing rows. No corrupted rows. Until parity is verified, don't change any routing.

Step 4: **Cutover (day 64, planned maintenance window)**
At a specific time, atomically switch the routing config. All servers (simultaneously) update their routing table: reads and writes now go to the new shard. This must happen simultaneously — having 50% of app servers on old routing and 50% on new routing creates the mixed-state nightmare.

Step 5: **Keep old shards running for 2 weeks**
Don't delete the old data immediately. If something goes wrong with the new shards, roll back to old shards instantly. Keep them running in parallel. After two weeks of verifying everything is fine, decommission old shards.

**Why the failure happened in the incident above:**

The migration skipped the double-write phase. They tried to do a direct "move" of data (delete from old, insert to new) while live traffic was running. When the migration script crashed mid-move, data was genuinely missing from both shards.

The double-write approach costs more (double the storage during migration), but means data is never in a "being moved" state. It's either in both places or the old place. Rollback is always safe.

> **Staff lesson:** "Resharding is a distributed systems change. All nodes in the system need to agree on the new routing simultaneously, or with proper locking. Blue-green deployment for config changes — not a gradual rollout that creates a mixed state where some servers use old routing and some use new routing."

---

# Real Incidents — When Things Actually Went Wrong

The previous sections described failure modes in theory. Here are real (or realistic composite) incidents where these failures happened at real companies, with real consequences.

---

## Incident 1: GitHub's Database Failover Incident (Replication Lag & Split Brain)

**Context:**

GitHub is one of the largest developer platforms in the world. As of 2018, it hosted hundreds of millions of code repositories and served millions of developers daily. Their database stack used MySQL with leader-follower replication across multiple datacenters.

**The incident:**

On October 21, 2018, GitHub experienced a major outage that lasted most of a day. The root cause was a chain reaction that started with a network partition and ended with split-brain.

**The timeline:**

```
22:52 UTC — Network switch failure
   A network switch in a datacenter fails.
   The link between Data Center A and Data Center B briefly drops.
   Duration of the network partition: approximately 43 seconds.
   Then the network heals itself. The switch is replaced.

22:52 — 22:53 UTC — Failover triggered
   GitHub's high-availability system (Orchestrator) detected
   that the leader (in DC-A) was unreachable from DC-B.
   After the detection timeout, Orchestrator promoted a replica
   in DC-B to be the new leader.

22:52 — 22:53 UTC — Split brain window
   The old leader (in DC-A) was never actually dead.
   It was just partitioned. During the 43 seconds of partition,
   it continued accepting writes from users routed to DC-A.
   The new leader (in DC-B) also accepted writes.
   Both thought they were the leader.

   43 seconds of writes on two separate leaders = diverged data.

22:53 UTC — Partition heals
   DC-A and DC-B can communicate again.
   Orchestrator recognizes there are now two leaders.
   Engineers are paged.
   
   The question: which 43 seconds of data do you keep?
   - Writes on old leader: real user actions (code pushes, PRs, etc.)
   - Writes on new leader: also real user actions
   - Some of the same records were modified on both sides.

The next several hours:
   GitHub engineers must reconcile the diverged data.
   This is not automated — it requires manual inspection.
   For each conflicting record, engineers must decide which version
   is "correct" or how to merge them.
   
   During this time, GitHub operates in degraded mode:
   some features are disabled, some operations fail.
   
Full resolution: approximately 24 hours after the initial incident.
```

**What went wrong (deeper analysis):**

The core problem: GitHub's failover system (Orchestrator) made the decision to promote a new leader based on "the leader seems unreachable" without first confirming the old leader had stopped writing. This is the fencing gap — the new leader was created before the old one was fenced.

Why was the fencing hard? Fencing requires communicating with the old leader: "stop being leader." But the old leader was unreachable (that's why the failover was triggered). If you can't reach it to tell it to stop, how do you fence it? This is the fundamental tension in distributed systems.

**What GitHub learned and changed:**

After this incident, GitHub rewrote significant parts of their database orchestration layer. Key changes:

1. **More conservative failover thresholds.** Wait longer before deciding a leader is truly dead (not just unreachable). A 43-second network partition should not trigger a failover — that's a blip, not a failure.

2. **Better fencing.** Before promoting a new leader, the system must be more confident the old leader has stopped writing. If confidence can't be achieved, don't promote — instead, alert humans to make the call.

3. **Leader lease mechanisms.** The leader periodically renews a "lease" in a highly available system. If the leader can't renew (because it's truly dead), the lease expires, and only then is a new leader allowed to be elected. This prevents premature elections during brief partitions.

> **Staff lesson:** A 43-second split brain can create hours of data reconciliation work and a full day of degraded operations. Fencing isn't optional. The cost of slower failover (waiting longer to be sure) is almost always lower than the cost of even a brief split-brain event.

---

## Incident 2: Instagram's Shard Imbalance (Hot Partition)

**Context:**

When Facebook acquired Instagram in 2012, Instagram was serving tens of millions of users on a relatively lean infrastructure built primarily with PostgreSQL and Python. They used sharded PostgreSQL clusters. Most shards were roughly equal in size and traffic.

But Instagram is a social network, and social networks have celebrities.

**The problem:**

The top 0.01% of users by follower count — celebrities like Beyoncé, Kim Kardashian, major athletes — generated approximately 60% of all read traffic. Their shards ran at 90%+ CPU utilization while other shards ran at 15-20%.

This wasn't obvious from the beginning. As Instagram's user base grew, the celebrities' follower counts grew, and the traffic imbalance grew with them. By the time the problem was acute, a few shards were chronically overloaded while the rest were idle.

**The acute crisis:**

Certain events would create sudden, massive spikes on specific celebrity shards. In 2013, Beyoncé announced her pregnancy on Instagram. The post generated hundreds of millions of likes and comments in hours. The shard containing Beyoncé's account hit 100% CPU. Queries queued up. Response times climbed from milliseconds to seconds. Some requests timed out. The shard's replicas also overloaded, as every read for the viral content hit the same few machines.

At the same time, the vast majority of Instagram's infrastructure was quietly idle.

**The engineering response:**

The Instagram engineering team (now part of Facebook's infrastructure group) took a multi-layer approach:

1. **Identified hot keys by monitoring per-user and per-shard query volume.** Standard shard-level metrics showed "Shard 4 is hot." But that wasn't enough detail. They needed to know WHICH user IDs within Shard 4 were causing the heat. They added per-user-id monitoring to identify the specific hot keys.

2. **Built a pre-warming system.** Before a celebrity's post is distributed to millions of followers' feeds, cache it in Memcached proactively. This is "push caching" — don't wait for someone to request it and then cache it; cache it before the first request arrives.

3. **Added "celebrity mode" routing.** They defined a threshold: if a user has more than 1 million followers, their data is classified as a "high-traffic user." For high-traffic users, all reads are served from the Memcached cache rather than from the database shard. The database shard only handles writes (new posts, profile updates) — not the massive fan-out of reads.

4. **Moved to push-based feed generation.** Originally, Instagram's feed was "pull" based: when you open your feed, the system queries "who do I follow? what did they post recently?" and assembles the feed on demand. At scale, this hits the database hard. They switched to "push" based: when a user posts, the system pre-writes that post into the feeds of all their followers. Opening your feed becomes a simple "fetch pre-computed list" instead of complex real-time computation.

**The result:**

Hot shard incidents dropped dramatically. The celebrity accounts that had caused chronic hotspots now served their massive read traffic from cache, barely touching the database. The database shards normalized to much more even utilization.

> **Staff lesson:** Access skew — not data skew — is often the harder problem to solve. Monitoring at the shard level isn't granular enough to find hot spots early. You need per-key access patterns to identify specific hot user IDs before they cause incidents. And the fix for hot keys is almost always caching: move the hottest data into memory so the database never sees the flood.

---

## Incident 3: A Fintech Company's Resharding Nightmare

**Context (this is a composite/anonymized incident based on real patterns in the fintech industry):**

A payment processing company had built their transaction database on 8 shards when they were processing 10 million transactions per day. Three years later, they were processing 200 million transactions per day and running out of capacity. They needed to reshard from 8 shards to 32 shards — a 4× expansion.

This was a major undertaking. Their transactions table contained 5 billion historical rows. Moving that data safely while continuing to process live payments was like performing open-heart surgery on a patient who insists on jogging during the operation.

**The migration plan:**

```
Phase 1 (Months 1-2):
Build the 32-shard infrastructure.
Begin double-writing: all new transactions go to BOTH 8-shard and 32-shard systems.
Source of truth for reads: 8-shard system (the original).
32-shard system receives writes but isn't used for reads yet.

Phase 2 (Months 2-3):
Backfill historical data from 8-shard to 32-shard system.
5 billion rows × 500 bytes each = 2.5TB of data to copy.
Run in small batches (100K rows at a time) to avoid lock contention.
Verify checksums as you go.

Phase 3 (Day 89, planned cutover):
Verify full parity between 8-shard and 32-shard systems.
At maintenance window (2am Sunday), atomically switch routing.
All app servers update config simultaneously: reads + writes now go to 32-shard.
Keep 8-shard running for 2 weeks as hot standby.
```

**What actually happened on Day 89:**

The cutover was scheduled for 2am Sunday. The engineering team had been awake for 18 hours verifying parity. Parity verified. Config ready.

At 2:03am, the config rollout began. The new routing configuration would be pushed to all 600 app servers simultaneously via their config management system.

Except there was a bug in the config rollout script.

```python
# Intended config logic:
if environment == "production":
    shard_count = 32
    use_new_routing = True

# Actual config logic (had a bug):
if shard_count == 32:   # BUG: checks shard_count before it's set
    use_new_routing = True
else:
    use_new_routing = False
    shard_count = 8
```

The result: approximately 95% of app servers correctly received the new 32-shard routing. But about 5% of app servers (those where the config was applied in a slightly different order) fell back to the old 8-shard routing.

For the next 3 hours, the payment processing system was in a mixed state:

- 95% of app servers wrote new transactions to the 32-shard system
- 5% of app servers wrote new transactions to the 8-shard system
- Both systems accepted the writes (they were still running in double-write mode)
- The two systems were diverging

**How it was discovered:**

At 5:17am, customer support started receiving calls about "double charges." Some users had been charged twice for the same transaction. Investigation found: 1 transaction from a payment, 1 from the corresponding 8-shard system, 1 from the 32-shard system — the same payment, processed twice, once by each routing configuration.

**The response timeline:**

```
05:17am — First "double charge" reports come in to customer support

05:31am — Engineering on-call paged. Starts investigating.

05:49am — Root cause identified: mixed routing state.

05:52am — Decision: ROLLBACK to 8-shard. Push config to all servers: shard_count=8.

06:04am — All servers on 8-shard routing. Writes stabilize to 8-shard only.

06:04am — 07:30am — Count duplicate transactions.
   1,847 duplicate transactions identified.
   Some users charged twice.

07:30am — 09:00am — Issue refunds for all duplicates (automated refund process).

09:00am — Public status: "Earlier this morning, some customers experienced
   duplicate charges. All duplicates have been refunded. We apologize for
   the inconvenience."

Day 89 — Day 95: Manual data reconciliation.
   Identify which transactions in the 32-shard system were legitimate
   new transactions vs. duplicate entries.
   Verify the 8-shard system has all legitimate transactions.

Day 100: File regulatory report with financial regulators.
   (Required by law for payment processing incidents of this type.)
   Report details: 1,847 affected transactions, all refunded, root cause identified.

Month 4: Begin resharding attempt #2 with the bug fixed and much more
   extensive pre-cutover validation.
```

**What went wrong (root cause analysis):**

1. **Config deployment bug.** The routing config had a logic error that went undetected because it was only triggered during the exact deployment sequence of a live migration. Unit tests missed it. Integration tests missed it.

2. **Gradual config rollout instead of atomic.** The config was pushed to 600 servers over about 90 seconds, not instantaneously. During those 90 seconds, the system was in a mixed state. A resharding cutover requires atomic config update — all servers at exactly the same time, or with proper locking to prevent divergence.

3. **No automated mixed-state detection.** There was no monitoring alarm for "are all app servers using the same routing config?" If such an alarm existed, it would have fired immediately when the first 5% of servers stayed on old routing.

4. **No maintenance mode.** During the cutover, writes should have been briefly paused (5-10 seconds) to allow all app servers to switch routing before any new writes arrive. Instead, new transactions were being processed during the config rollout window.

**What the company changed afterward:**

1. **Two-phase cutover:** Phase 1 = stop accepting new transactions (maintenance mode). Phase 2 = switch all routing atomically (takes <1 second since no new traffic). Phase 3 = resume transactions. A 10-second maintenance window beats a 4-hour incident.

2. **Config validation checks:** Before starting any migration, automated tests verify that the config logic is correct by running it against every possible edge case.

3. **Routing consistency monitoring:** A new metric: `config_routing_version` reported by every app server. Alert if any server reports a different version than the rest.

4. **Canary migrations:** For future resharding, migrate 1% of traffic to the new routing, verify no issues for 24 hours, then proceed. If issues are found, roll back the 1% before the damage is widespread.

> **Staff lesson:** Resharding is a distributed systems change requiring all nodes to agree on the new routing simultaneously (or with proper locking). Blue-green deployment for config changes, not gradual rollouts that create a mixed state. And always have a maintenance mode — a brief pause in writes during the atomic cutover is far less costly than a mixed-state incident.

---

## Blast Radius Quantification

Let's put specific numbers on failure impact. This is the kind of thinking that happens during incident planning ("what's our worst case scenario?") and post-incident reviews ("how bad was it?").

```
+------------------+------------+-----------+----------------+------------------------------------+
| Failure Type     | % Users    | Users     | Time to Fix    | Real-World Consequence             |
|                  | Affected   | Affected  | (Typical)      | (at 1M users, 16 shards)           |
|                  |            | (1M users,|                |                                    |
|                  |            | 16 shards)|                |                                    |
+------------------+------------+-----------+----------------+------------------------------------+
| Leader down      | 100%       | 1,000,000 | 5-15 min       | ALL writes fail. Reads still work. |
| (no auto-        |            |           | (manual)       | Users can read but not post.       |
| failover)        |            |           |                |                                    |
+------------------+------------+-----------+----------------+------------------------------------+
| Leader down      | 0-2%       | 0-20,000  | 30-120 sec     | Brief blip during failover. Most   |
| (with auto-      |            | (during   | (auto)         | users notice nothing. Small        |
| failover)        |            | failover  |                | window of write errors.            |
|                  |            | window)   |                |                                    |
+------------------+------------+-----------+----------------+------------------------------------+
| Replication      | 100%       | 1,000,000 | Hours (if      | All reads may be stale. No         |
| lag >30 sec      |            |           | undetected)    | errors — just wrong data.          |
|                  |            |           | or minutes     | Users see old profile pics,        |
|                  |            |           | (if detected)  | missing new posts, "changes lost." |
+------------------+------------+-----------+----------------+------------------------------------+
| Split brain      | 100%       | 1,000,000 | Hours to days  | Data corruption growing every      |
| (two leaders)    |            |           | (data          | second. Financial/integrity risk.  |
|                  |            |           | reconciliation)| Some user data may be permanently  |
|                  |            |           |                | inconsistent.                      |
+------------------+------------+-----------+----------------+------------------------------------+
| One shard down   | 6.25%      | 62,500    | 5-15 min       | 62,500 users get errors. Other     |
| (16 shards)      |            |           | (auto-         | 937,500 users see zero impact.     |
|                  |            |           | failover)      |                                    |
+------------------+------------+-----------+----------------+------------------------------------+
| Hot partition    | 6.25%      | 62,500    | Minutes (if    | One shard's users see slow         |
| (one shard)      |            | directly, | cached), hours | performance or errors. Can cascade |
|                  |            | more if   | (if cascades)  | to full shard failure if retry     |
|                  |            | cascade   |                | storm occurs.                      |
+------------------+------------+-----------+----------------+------------------------------------+
| Network          | 100%       | 1,000,000 | Minutes to     | Everything slow or failing.        |
| partition        |            |           | hours          | May trigger inappropriate          |
|                  |            |           |                | failovers. See GitHub incident.    |
+------------------+------------+-----------+----------------+------------------------------------+
| Resharding       | Variable   | Variable  | Hours to days  | Data in inconsistent state.        |
| migration bug    |            |           | (depends on    | Some users affected until          |
|                  |            |           | detection +    | reconciliation complete.           |
|                  |            |           | reconciliation)|                                    |
+------------------+------------+-----------+----------------+------------------------------------+
```

**What this table teaches you:**

The "safest" failures are those with high automation and low blast radius. Auto-failover on leader down: brief window, then normal. Shard failure with auto-failover: 6.25% of users, 5-15 minutes.

The most dangerous failures are those that are **silent** or have **no clear fix**. Replication lag silently serves stale data for hours before anyone notices. Split brain corrupts data until fenced. Resharding bugs can require days of manual reconciliation.

When you design a system, designing for the failure modes matters as much as designing for the happy path.

---

## Monitoring What You Can't See

The biggest theme in this chapter is **silent failures**. A leader crashing is obvious — your monitoring screams. But replication lag quietly serving 30-second-old data? A single shard slowly warming up? These failures sneak up on you.

Good monitoring doesn't just check "is the database up?" It measures the specific signals that indicate silent degradation.

---

### The Monitoring Dashboard for a Healthy Sharded + Replicated System

Here's what a healthy system looks like on a monitoring dashboard, and what thresholds should trigger alerts:

**Replication Health Metrics:**

```
Metric: replication_lag_seconds (per replica)
  Healthy: < 0.5 seconds
  Warn: > 5 seconds (investigate)
  Alert: > 30 seconds (page the on-call engineer)
  Critical: > 5 minutes (incident declared, route reads to leader)
  
  Why it matters: if replication lag is 30 seconds, users see data 
  from 30 seconds ago. Profile updates appear lost. New posts don't 
  show up. Not a crash, but users notice.

Metric: replication_running (per replica, boolean)
  Healthy: 1 (replication is running)
  Alert: 0 (replication has stopped)
  
  Why it matters: if replication stops, lag will grow without bound.
  Users will increasingly see stale data until it reaches the point 
  of being unusable.

Metric: replica_count (how many replicas are healthy)
  Healthy: expected count (e.g., 2 replicas per shard)
  Alert: < expected count (a replica has failed)
  
  Why it matters: if you have 2 replicas and 1 fails, you have 1 
  left. If that one fails, you have no read capacity and no failover 
  target. You want to be alerted at the first failure, not after the 
  second.
```

**Shard Health Metrics:**

```
Metric: queries_per_second (per shard)
  Healthy: roughly equal across shards (within 2×)
  Alert: one shard is 3× the average (hot partition developing)
  Critical: one shard is 10× the average (hot partition, immediate action)
  
  Why it matters: even distribution is the whole point of sharding.
  If one shard is getting 10× the queries, you have a hot partition 
  that will soon become an incident.

Metric: disk_usage_bytes (per shard)
  Healthy: roughly equal across shards (within 1.5×)
  Alert: one shard is 2× the average (data skew developing)
  
  Why it matters: if one shard has twice as much data as others, 
  it might fill up while others have plenty of room. Needs resharding.

Metric: cpu_utilization (per shard, percentage)
  Healthy: < 50% (lots of headroom)
  Warn: > 70% (starting to get busy)
  Alert: > 85% (degradation likely under any spike)
  Critical: > 95% (active incident, queries are queuing)
  
  Why it matters: a shard at 95% CPU has no capacity to handle 
  any traffic spike. A normal event that causes a 20% increase 
  will push it to 115%, which means queuing, latency explosion, 
  and the beginning of a hot partition cascade.

Metric: query_latency_p99 (per shard, milliseconds)
  Healthy: < 10ms (typical for indexed point queries)
  Warn: > 3× baseline (e.g., > 30ms if baseline is 10ms)
  Alert: > 10× baseline (significant degradation)
  
  P99 means "99th percentile" — the latency that 99% of queries 
  complete within. It catches the slow outliers that P50 (median) 
  misses.
  
  Why it matters: the 1% of slow queries are often the ones that 
  cause problems (they can be symptoms of table locks, missing indexes, 
  or hot key contention).

Metric: connection_pool_utilization (per shard, percentage)
  Healthy: < 60%
  Alert: > 80%
  Critical: > 95%
  
  Why it matters: PostgreSQL and MySQL have a maximum number of 
  simultaneous connections. When the connection pool is full, new 
  requests can't even start — they get "too many connections" errors 
  immediately. High connection pool utilization is a leading indicator 
  of imminent capacity failure.
```

**The "Silent Failure" Problem:**

All of the metrics above measure things that can fail quietly. Consider the contrast:

| Failure Type | Does It Throw Errors? | How You Find Out (without monitoring) |
|---|---|---|
| Leader crash | YES — every write fails | Immediately, users are screaming |
| Shard crash | YES — 6.25% of users get errors | Users notice within minutes |
| Replication lag >30s | NO — queries succeed, just stale | Users complain "my changes aren't saving" 30+ minutes later |
| Hot partition (early) | NO — queries succeed, just slow | P99 latency slowly climbs for hours before it becomes an incident |
| Data skew | NO — queries succeed | You notice when one shard's disk fills up and you get an emergency 2am alert |

Replication lag and hot partitions are the sneaky ones. They don't announce themselves. They quietly degrade user experience. By the time users notice and file support tickets, the degradation might have been going on for an hour.

**The discipline of monitoring silent metrics:** Setting up good monitoring for `replication_lag_seconds` and `queries_per_second per shard` isn't glamorous. It doesn't ship features. But it's the difference between knowing about a problem when it starts (and having 30 minutes to fix it quietly) vs. knowing about it when users have been complaining for an hour (and you're in full incident mode at 2am).

---

## Schema Evolution in a Sharded System

One more failure-adjacent topic that every engineer working with sharded systems encounters: changing the database schema after sharding.

Before sharding, changing a table (adding a column, adding an index, changing a data type) is annoying but manageable. After sharding, it becomes a carefully planned, multi-week operation.

---

### The "Changing the Rules Mid-Game" Problem

**Before sharding:**

```sql
ALTER TABLE users ADD COLUMN loyalty_points INTEGER DEFAULT 0;
```

Run this. Wait 30 seconds (maybe less for small tables). Done. The column exists. Developers can start using it immediately.

For larger tables (say, 50 million rows), this might lock the table for 5-10 minutes, during which reads might be slow and writes might be blocked. Annoying. But one database, one maintenance window, move on.

**After sharding across 16 shards:**

The same command needs to run on 16 separate databases. If you run it on all 16 simultaneously, you get:
- 16 simultaneous table locks, blocking queries across 1/16 of your users each
- If each lock takes 10 minutes, some users are blocked for 10 minutes
- 16 simultaneous heavy operations competing for disk I/O on shared infrastructure

If you run it sequentially (shard 0 first, wait, then shard 1, etc.):
- Total time: 16 shards × 10 minutes each = 160 minutes
- Application code deployed during this window needs to handle both "column exists" and "column doesn't exist" states
- A transaction that spans two shards during the migration window might fail if one shard has the column and the other doesn't

And this is just adding a column. More complex changes (changing a column type, splitting a column, adding a foreign key) are exponentially harder.

---

### The Online Schema Change Approach

For large, sharded production databases, the right approach is never "just run the ALTER TABLE." It's a multi-step migration that takes days or weeks but never causes a table lock.

**Step 1: Add the new column as nullable with no default**

```sql
-- Bad (causes table rewrite on PostgreSQL):
ALTER TABLE users ADD COLUMN loyalty_points INTEGER DEFAULT 0;

-- Good (no rewrite — just metadata change):
ALTER TABLE users ADD COLUMN loyalty_points INTEGER;
```

Why does `DEFAULT 0` cause a table rewrite? Because PostgreSQL has to update every existing row to set the default value. For a table with 100M rows, that's 100M row updates = massive I/O.

Without a DEFAULT, PostgreSQL just adds the column definition. Existing rows have NULL for the new column. Instant. No lock.

**Step 2: Deploy application code that writes to BOTH old and new column**

During the migration window, the application code needs to work whether the new column exists or not (for the shards that haven't been migrated yet) AND whether the new column has data or not (for existing rows that haven't been backfilled yet).

```python
def add_loyalty_points(user_id, points):
    # Always write to the new column (it exists on all shards now)
    db.execute("UPDATE users SET loyalty_points = loyalty_points + ? WHERE id = ?", 
               points, user_id)

def get_loyalty_points(user_id):
    user = db.query("SELECT loyalty_points FROM users WHERE id = ?", user_id)
    # If loyalty_points is NULL (not yet backfilled), treat as 0
    return user.loyalty_points or 0
```

**Step 3: Backfill existing rows in small batches**

```sql
-- DON'T DO THIS:
UPDATE users SET loyalty_points = 0 WHERE loyalty_points IS NULL;
-- This locks the entire table while it updates 100M rows. Full outage.

-- DO THIS INSTEAD:
UPDATE users SET loyalty_points = 0 
WHERE id BETWEEN 0 AND 1000 AND loyalty_points IS NULL;
-- Wait 100ms (let other queries run)

UPDATE users SET loyalty_points = 0 
WHERE id BETWEEN 1001 AND 2000 AND loyalty_points IS NULL;
-- Wait 100ms

-- ... repeat for all rows, 1,000 at a time
-- At 1,000 rows per batch, 100ms sleep between batches:
-- 100M rows / 1,000 rows per batch × 0.1 seconds = 10,000 seconds ≈ 2.8 hours
-- Slow, but the database is fully available throughout
```

**Step 4: Verify backfill is complete on all shards**

```sql
SELECT COUNT(*) FROM users WHERE loyalty_points IS NULL;
-- Should return 0 on all 16 shards before proceeding
```

Run this on every shard. Don't proceed until every shard has zero NULLs.

**Step 5: Deploy application code that reads the new column directly**

Once backfill is verified, remove the "or 0" fallback:

```python
def get_loyalty_points(user_id):
    user = db.query("SELECT loyalty_points FROM users WHERE id = ?", user_id)
    return user.loyalty_points  # No longer nullable, no fallback needed
```

**Step 6: Eventually drop the old column (if applicable)**

Wait a few more weeks to make sure nothing is still reading the old column. Then drop it. Or keep it if dropping is risky.

---

### The Timeline Reality

Let's be honest about what this takes:

```
+------------------+----------------------------------+----------------------------+
| Step             | Duration                         | Risk                       |
+------------------+----------------------------------+----------------------------+
| Add column       | 1 hour (run on all 16 shards,   | Low — just metadata change |
| (nullable, no    | verify each is instant)          |                            |
| default)         |                                  |                            |
+------------------+----------------------------------+----------------------------+
| Deploy code that | 2 days (staging, testing,        | Medium — needs careful     |
| handles nullable | gradual rollout to production)   | testing of NULL handling   |
| column           |                                  |                            |
+------------------+----------------------------------+----------------------------+
| Backfill         | 1-3 days (running in batches     | Low (if batches are small) |
| existing rows    | around the clock, 1K rows at a   |                            |
|                  | time across 16 shards)           |                            |
+------------------+----------------------------------+----------------------------+
| Verify backfill  | 1 day (run verification queries  | Low                        |
| complete         | on all shards, review results)   |                            |
+------------------+----------------------------------+----------------------------+
| Deploy code that | 2 days (staging, test, rollout)  | Low                        |
| uses new column  |                                  |                            |
|                  |                                  |                            |
+------------------+----------------------------------+----------------------------+
| Clean up         | 2 weeks later (safety margin     | Very low                   |
| (optional        | before removing fallback code)   |                            |
| column drop)     |                                  |                            |
+------------------+----------------------------------+----------------------------+
| TOTAL TIME       | 2-3 weeks                        |                            |
| (for a simple    |                                  |                            |
| column add)      |                                  |                            |
+------------------+----------------------------------+----------------------------+
```

Compare: before sharding, a simple column add = 30 seconds. After sharding across 16 shards = 2-3 weeks.

This isn't a story of sharding being bad. It's a story of complexity having real costs. Sharding is the right tool when you need the scale it provides. But it means that operations which were instant become week-long projects. Your team needs to plan for this.

**This is why database schema changes in sharded systems require:**

1. **Migration scripts** written in advance, reviewed by multiple engineers, tested in staging
2. **Multi-week rollout plans** with clear stages and verification checkpoints
3. **Application code that handles both old and new schema** during the transition window
4. **Backfill jobs** that run in small batches to avoid table locks
5. **Verification tools** that check every shard is in the expected state before proceeding

"Just add a column" doesn't exist at sharded scale. "Carefully add a column over 2-3 weeks" does.

---

# Putting It All Together — A Final Reflection

You've just read through a social network growing from 0 to 100 million users, a rate limiter using Redis sharding, an e-commerce platform with careful shard key design, several failure modes with step-by-step diagnosis, three real (or composite) incidents from companies you've heard of, blast radius calculations, monitoring strategies, and the realities of schema changes in sharded systems.

That's a lot. Let's surface the five most important ideas from Part C:

---

**1. The right architecture is the one that fits your current scale.**

At 10,000 users, one database is the right answer. At 10 million users, one database is a liability. Premature sharding creates complexity you'll spend months debugging. Delayed sharding creates incidents you'll spend nights recovering from. The skill is reading the metrics and knowing when to make the next architectural investment.

---

**2. Shard key design is the most important decision in a sharded system.**

Wrong shard key → hot partitions, cross-shard queries, scatter-gather nightmares. Right shard key → uniform distribution, co-located data, fast single-shard queries. The question to ask for every table: "What is the most common query against this table, and which key would let me answer that query with the fewest shard hops?"

---

**3. Silent failures are the hardest ones.**

Leader crashes are loud. Replication lag is quiet. Hot partitions start as whispers. Without monitoring the specific metrics (replication_lag_seconds, queries_per_second per shard, cpu_utilization per shard), you find out about problems when users complain, not when they start.

---

**4. Split brain is the most dangerous failure mode. Always fence.**

Two nodes thinking they're the leader, both accepting writes, for even 43 seconds — can create hours of data reconciliation work and permanent data inconsistency. Fencing (preventing the old leader from writing before the new one starts) is non-negotiable in any system where data correctness matters.

---

**5. Operational complexity is a real, ongoing cost of sharding.**

Adding a database column = 30 seconds (unsharded) vs. 2-3 weeks (16 shards). Migrating to more shards = 3-month engineering project with real data-loss risk if done wrong. Every additional shard is another machine to monitor, fail over, back up, and maintain. These costs are worth paying when you need the scale — but they're real costs that should inform the decision to shard.

---

*End of Part C. Part D will cover: advanced patterns (consistent hashing in depth, virtual nodes, geographic distribution), the CAP theorem applied to real choices, and how to talk about replication and sharding in a system design interview.*

---

*Chapter 21 Part C — Applied Scenarios, Failure Modes, and Real Incidents*
*Section 3 — Distributed Systems Fundamentals (Simplified)*
# Chapter 21: Replication and Sharding — Part D
## Interview Calibration, Staff-Level Reasoning, Brainstorming Questions, Exercises, and Quick Reference

---

> **This is Part D of a 4-part chapter.** Parts A–C covered all the core concepts: what replication is, how sharding works, shard keys, consistency models, failure modes, and real-world patterns. This part is about turning that knowledge into interview performance and deep engineering judgment.

---

# Part 5: Staff-Level Interview Calibration

## How the Interview Actually Tests This Topic

Here is how almost every system design interview involving a database goes:

The interviewer says: "Design Instagram" or "Design a URL shortener" or "Design a payment system." You sketch out the major components — web servers, load balancers, databases, caches. Everything is going fine.

Then the interviewer asks: "How would you scale the database as you grow to 100 million users?"

**That question is the moment they are actually evaluating you.**

Everything up to that point was warm-up. The database scaling answer is where they separate candidates. Here is why: almost every system that serves millions of users hits a database bottleneck. Engineers who understand replication and sharding can talk intelligently about those systems. Engineers who do not understand them can describe architectures but cannot explain why the architectures actually work at scale.

The interviewer is not just looking for a correct answer. They are looking at how you think. Do you jump straight to solutions? Do you ask clarifying questions first? Do you understand trade-offs? Do you know when NOT to use a complex solution?

Here is what the answer looks like at different career levels, for the question "How would you scale this database?":

**Junior Engineer answer:**
"I would use a relational database like PostgreSQL."

This answer reveals the junior engineer is thinking about technology choices, not scale. They are answering a different question than the one asked. They heard "database" and gave a database answer. The question was about scaling, not selection.

**Mid-Level Engineer answer:**
"I would add read replicas to handle the read traffic. The leader handles writes and the replicas handle reads."

This is a real answer. It shows understanding of a genuine scaling technique. It would work for many situations. But it is a template answer — it does not engage with the specifics of the system being designed. It does not ask "is this actually a read bottleneck?" It just applies the read replica pattern reflexively.

**Senior Engineer (L5) answer:**
"I would use read replicas for read scaling since this system is probably read-heavy at 90% reads. For write scaling as we grow, I would shard by user_id — that distributes writes evenly since every action ties to a user. That gives me both read and write scaling."

This is a good answer. It is specific, it shows understanding of the read/write ratio, and it explains why the chosen shard key works. An L5 has the vocabulary and can apply the patterns correctly.

**Staff Engineer (L6) answer:**
"Let me think about what the actual bottleneck is before I propose a solution. Our access patterns are mostly profile reads and feed reads — that is a heavy read workload. Our write QPS is probably around 5,000 based on your numbers — not extreme. Our dataset size is probably 10TB at 100M users. Based on that, our bottleneck right now is almost certainly read throughput, not write capacity and not storage. That means read replicas solve this problem, probably for the next 18 months. I would hold off on sharding until we actually see write throughput become the bottleneck — sharding adds 6 months of migration complexity and I would rather not pay that cost before I have to. Now, when we do eventually need to shard, I would choose user_id as the shard key because..."

See the difference? The L6 answer does not start with a solution. It starts with a diagnosis. It is specific about the bottleneck. It explicitly considers whether the expensive solution is necessary yet. It reasons about cost and timing, not just technical correctness.

This pattern — diagnose before prescribing — is the single most reliable signal that separates L5 from L6.

---

## The Anatomy of an L6 Database Scaling Answer

When you sit in an interview and they ask about database scaling, the L6 answer has five recognizable phases. If you can hit all five, you signal staff-level thinking.

**Phase 1: Establish the access pattern before touching architecture.**
What queries does this system run? Point lookups? Range scans? Aggregations? Graph traversals? The access pattern determines the shard key. You cannot choose a shard key without knowing the access pattern first. Spend 60–90 seconds on this even if the interviewer seems impatient. Say explicitly: "Before I design the sharding strategy, I want to understand the access patterns, because the wrong shard key is very hard to fix later."

**Phase 2: Run the capacity math out loud.**
Pick specific numbers — dataset size, read QPS, write QPS — and show whether your current or proposed architecture handles them. This demonstrates that you live in the world of real systems, not abstract patterns. "At 100M users with 1KB average row, that is 100GB of data. At 10 shards, 10GB each. That fits on a standard SSD." Interviewers reward specific numbers even when the numbers are estimates.

**Phase 3: Name the bottleneck precisely.**
Is the bottleneck read throughput? Write throughput? Disk storage? Query latency? Single-shard hot spot? Network bandwidth? Name it specifically. The solution to "read throughput bottleneck" is very different from the solution to "write throughput bottleneck." If you do not name the bottleneck, you might solve the wrong problem.

**Phase 4: Try the simple solution first.**
Before proposing sharding, ask: would read replicas fix this? Would better indexes fix this? Would caching hot data fix this? Would a bigger machine fix this for another year? Proposing sharding when replicas would suffice is a signal of under-experience, not depth of knowledge. L6 engineers know that simpler solutions are almost always worth exhausting first.

**Phase 5: Address the failure modes of your solution.**
If you propose sharding, immediately address: what happens if a shard goes down? How do you handle hot spots? What is the resharding strategy? What happens to cross-shard queries? Proactively naming the failure modes of your own design — and having mitigations ready — signals that you have thought through the problem deeply, not just pattern-matched to a solution.

---

## The L5 vs L6 Contrast Table

This table shows eight real scenarios. Read each row and notice the pattern in how the approaches differ.

| Scenario | L5 Approach | L6 Approach |
|---|---|---|
| **DB CPU at 80%** | "Add read replicas to distribute the load." | "What queries are driving CPU? Are they reads or writes? If it is a handful of slow queries, better indexes could fix this with zero infrastructure cost. Replicas only solve this if it is genuinely a read volume problem — not a query efficiency problem. Let me look at the slow query log first." |
| **Need 3× write capacity** | "Shard the database across multiple nodes." | "Before sharding: can we batch writes together? Use write-behind caching to absorb bursts? Vertically scale to a bigger machine first? Sharding is the last resort — it adds 6 months of migration risk and permanently increases operational complexity. What is the actual write QPS number and why can the current setup not handle it?" |
| **Global users, high latency** | "Use multi-leader replication so any region can accept writes." | "Which users actually need write locality? Is it all users, or just users in Region X? If 15% of users in one region are driving the latency complaint, we could shard by region for those users and accept cross-region write latency for edge cases. Full multi-leader means conflict resolution everywhere — that is a high complexity price for a problem that might affect a minority of users." |
| **Celebrity user causing a hot spot** | "Add more shards to distribute the load." | "The problem is access skew, not data volume. Adding more shards does not help if all reads are targeting one user_id regardless of how many shards exist. The celebrity's data still lands on one shard. The right fix is to cache celebrity data in Redis with a short TTL. Fix the access pattern, not the shard count." |
| **Cross-shard joins are slow** | "Optimize the query or add indexes." | "Cross-shard joins are an architectural constraint, not a query problem. You cannot index your way out of scatter-gather across 16 shards. The options are: denormalize the frequently-joined data so it lives in one place, or redesign the shard key so that related data is co-located. This is a schema decision, not a tuning decision." |
| **Resharding needed** | "Plan the migration from 8 to 16 shards." | "Before planning the migration: why is resharding needed? If it is wrong shard key choice, can we fix with a new global secondary index on a separate service instead of moving all data? If it is data growth, could we add logical shards without moving data? Resharding is a 2–4 month project with high risk. Let us exhaust other options first." |
| **Replication lag is 30 seconds** | "Investigate the replicas to find what is wrong." | "30-second lag means either replicas are underpowered for the write stream they are receiving, or writes are spiking unexpectedly. Immediate action: route all critical reads to the leader so users are not seeing stale data. Root cause in parallel: profile the write stream. Is there a batch job running? A schema migration? The symptom is lag, but the root cause is almost always a specific workload pattern." |
| **Need 5 nines availability (99.999%)** | "Add more replicas for redundancy." | "Replicas help with availability but they do not protect against split-brain, catastrophic datacenter failure, or network partition from your quorum. What is the actual SLA budget? Replicas plus automated failover gets you to roughly 99.9%. Getting to 99.999% requires multi-region active-active architecture with extremely careful consistency design. Let us talk about what level of availability is actually required." |

**The pattern in every L6 answer:** They always ask "what specifically is the problem?" before proposing a solution. They always ask "what is the cheapest fix?" before proposing the expensive fix. They know that simpler solutions — better indexes, query optimization, caching, vertical scaling, batching — have roughly ten times the benefit at one tenth the cost and risk of sharding.

The other pattern: L6 answers are specific. They use numbers. They talk about QPS, dataset size, migration timelines. Vague answers ("we should probably shard") are L5. Specific answers ("at 50,000 writes per second with a 2TB dataset, here is exactly when sharding becomes necessary") are L6.

---

## Interview Probing Questions — Prepare for These

After you give your sharding and replication design, the interviewer will probe it. These are not trick questions. They are tests of whether your design is real or just surface-level. Here are the eight most common probing questions with notes on what the interviewer is actually checking.

---

**Q: "What happens if the leader crashes in the middle of a write?"**

*What they are testing:* Whether you understand the durability gap in asynchronous replication.

*A weak answer:* "The replica takes over as the new leader." (Technically true but misses the point entirely.)

*A strong answer:* It depends entirely on whether we are using synchronous or asynchronous replication. With async replication, the write was acknowledged to the application before it was replicated. If the leader crashes after acknowledging but before the replica receives it, that write is lost permanently — the new leader does not have it. The application thinks the write succeeded but it is gone. The defense against this: make writes idempotent so the application can safely retry after detecting the crash, accepting that rare writes might need to be replayed. With semi-synchronous replication, at least one replica confirmed receipt before we acknowledged, so we have a surviving copy and can proceed.

*The follow-up they might ask:* "How does the application know the leader crashed? How does it know to retry?" This tests understanding of timeouts, retry logic, and idempotency keys.

---

**Q: "A shard is getting 10× more traffic than the others. What do you do?"**

*What they are testing:* Whether you know the difference between data skew and access skew — two very different problems with very different solutions.

*A weak answer:* "Reshard to distribute the data more evenly." (This is expensive and may not even help.)

*A strong answer:* First, diagnose whether this is data skew or access skew. Data skew: one shard has physically more data than others because the shard key distributes unevenly. Access skew: one shard has normal amounts of data but one hot entity is being requested constantly. If it is access skew (like a celebrity user or a viral post), adding more shards does not help — the hot entity still maps to one shard. The fix is to cache the hot entity in a fast in-memory layer like Redis. If it is genuine data skew, that is when you consider rehashing that portion of the data. Start with cache, check if that resolves it.

---

**Q: "How would you do a zero-downtime reshard?"**

*What they are testing:* Whether you have thought through live migration — it is not just "move the data."

*A strong answer walks through the phases:* First, provision new shards but route no traffic to them yet. Then enter a double-write phase: all new writes go to both old and new shards simultaneously. This builds up new shards while keeping old shards as source of truth. Then backfill: copy historical data from old shards to new shards — data that predates the double-write start. Then verify: run checksums and row counts to confirm new shards match old shards exactly. Then switch reads: route read traffic to new shards. Watch metrics for 15–30 minutes. Be ready to roll back reads if anything looks wrong. Then switch writes: stop double-writing, route writes to new shards only. This is the point of no return. Then decommission old shards once you are confident.

Zero downtime does not mean zero risk. Each phase has failure modes. The verification step is the one most teams rush and later regret.

---

**Q: "User A transfers $100 to User B. They are on different shards. How do you do this safely?"**

*What they are testing:* Distributed transaction knowledge and whether you know real patterns for cross-shard atomicity.

*A strong answer:* This is a distributed transaction problem and there is no perfect solution — only trade-offs. The Saga pattern handles this by breaking the transaction into local steps with compensating transactions for rollbacks. Step 1: debit $100 from User A's account (local transaction on shard A). Hold it in "pending" state. Step 2: credit $100 to User B's account (local transaction on shard B). Step 3: confirm the debit on shard A (remove the "pending" state, finalize the debit). If Step 2 fails, execute the compensating transaction: credit $100 back to User A. For safety, you need idempotency keys on both steps so that if either step is retried due to network timeout, it does not double-apply. Money is never in limbo — it is either pending on the source or finalized on both.

---

**Q: "How do you prevent split-brain when the leader goes down?"**

*What they are testing:* Understanding of consensus mechanisms and fencing. This is a deep question — only engineers who have thought carefully about distributed systems can answer it well.

*A strong answer:* Split-brain happens when two nodes both believe they are the leader and accept writes — now you have two diverging versions of your data that must eventually be reconciled. The protections: fencing tokens (each leader election generates a new monotonically increasing token; any write with an old token is rejected, so the stale leader's writes are automatically blocked even if it has not learned it is no longer the leader), quorum-based elections (you need acknowledgment from a majority of nodes to become leader — mathematically impossible for two nodes to simultaneously get a majority from the same group), and lease timeouts (the leader holds a time-bounded lease; it stops accepting writes if it cannot renew the lease within the lease period, preventing a partitioned leader from continuing to act).

---

**Q: "How does Instagram handle Kylie Jenner's 190 million followers getting her new post?"**

*What they are testing:* Fan-out strategies and the celebrity problem — a canonical design challenge for social media systems.

*A strong answer:* If Instagram used pure push-based fan-out (write the post to every follower's feed table on post creation), Kylie's post would trigger 190 million writes immediately. That is a database-destroying spike — even at 100,000 writes per second, it would take 30 minutes to fan out a single post. Instead, Instagram uses a hybrid approach. For normal users (under roughly 1 million followers), push fan-out works fine: at 1,000 followers, posting creates 1,000 writes, totally manageable. For celebrities, Instagram uses pull-based fan-out: when you open your feed, the system assembles it by fetching recent posts from everyone you follow. Kylie's post is fetched on demand, not pushed to 190M feed tables. The routing logic checks follower count: if you are a celebrity, your posts are not pushed. The trade-off is that celebrity posts are slightly more expensive to read (assembly at read time) but essentially free to write.

---

**Q: "What is the replication lag SLO for a social media feed versus a payment system?"**

*What they are testing:* Understanding that different data has different staleness tolerances — and that you should tune your consistency model to the business requirement, not to a single universal setting.

*A strong answer:* For a social media feed, 5 to 60 seconds of staleness is entirely acceptable. If you see a friend's post 30 seconds after they publish it, you do not notice and you do not care. This means we can route feed reads freely to replicas and accept significant lag. For a payment system, the acceptable staleness is zero milliseconds on balance-checking operations. If a user sends $100 and then checks their balance, they must see the balance change immediately. Showing a pre-payment balance even for 500ms is unacceptable — users think the transaction failed and retry, causing double-sends. Payment reads must go to the leader or use synchronous replication. The business requirement defines the consistency requirement, which defines the replication strategy.

---

**Q: "If you were designing Twitter's database from scratch today, would you use the same shard key?"**

*What they are testing:* Whether you understand the trade-offs of real shard key choices at real scale — specifically, that every shard key that solves one problem creates another problem.

*A strong answer:* Twitter shards tweets by tweet_id hash, which distributes write load evenly — every new tweet goes to a pseudo-random shard. This works well for write throughput at billions of tweets. The problem is the celebrity hot-spot on reads: when a celebrity tweets, millions of people request that tweet. It always lands on the same shard because tweet_id is fixed. The shard handles enormous read load. Twitter's solution is aggressive caching — celebrity tweets are served from cache, not the database. If I were designing from scratch, I would keep tweet_id as the shard key for writes (even distribution of writes is the primary concern), but I would design the caching layer more explicitly from day one rather than retrofitting it. Sharding by user_id would create an even worse problem — the celebrity's shard would receive all writes from that user AND all reads to their timeline, with no escape valve.

---

## The "Design a User Database" — L6 Sample Answer

This is what an 8-minute interview answer sounds like when it is done well. Read it as if you are the candidate speaking out loud to an interviewer. Notice the structure: access patterns first, capacity math second, shard key third, hot spots fourth, failure analysis fifth, consistency model sixth.

---

"Before I choose a sharding strategy, I want to understand the access patterns, because the shard key should come directly from how this data is actually queried.

What queries does this user database serve? I am thinking of four main ones: login — look up a user by email or phone number to authenticate them; profile view — look up a user by user_id to display their profile; user search — find users by name; and feed assembly — find all users that I follow. The first two are point lookups on a single user. The third is a completely different access pattern — it needs a full-text search index, not a shard key. Sharding does not help with text search. The fourth is a graph traversal — it needs a different data structure entirely, probably a separate adjacency list or dedicated graph store.

For the main user table, the dominant access pattern is point lookup by user_id. That makes the shard key obvious: hash by user_id. Every query for user X goes to exactly one shard — no scatter-gather, no fan-out across multiple database nodes.

Let me run the capacity numbers to sanity-check this design. At 100 million users with an average row of 1 kilobyte — name, email, hashed password, profile bio, join date, settings — that is 100 gigabytes of user data. With 10 shards, each shard holds 10 gigabytes, which fits comfortably on any modern SSD with headroom. For writes: user registrations plus profile updates, maybe 1,000 writes per second total at peak. Across 10 shards that is 100 writes per second per shard. Any database handles that trivially. For reads: let us say 500,000 reads per second at peak across the platform. At 10 shards with 3 replicas each, that is 30 database instances. 500,000 divided by 30 is roughly 17,000 reads per second per instance. Manageable with standard hardware.

Hot spots: the real risk here is not data skew — user rows are roughly similar in size, so hash sharding distributes data evenly. The risk is access skew: celebrity users get dramatically more profile reads than normal users. But celebrities typically do not write to their profile frequently — they are read-heavy, not write-heavy. So the fix is not more shards, it is a cache layer. I would put celebrity profiles in Redis with a 30-second TTL. Reads for accounts above, say, 100,000 followers hit Redis instead of the database. That handles maybe 80% of profile reads without a single database query.

For the follow graph — user_id to list of followed user_ids — this has a fundamentally different access pattern from the user table. The follow graph is used for feed assembly, recommendation, and notification routing. I would not put it in the same sharded user table. I would use a dedicated store optimized for graph traversals, or at minimum a separate adjacency table with its own sharding strategy based on follower_id.

For email-based login: users look themselves up by email, not user_id. But I shard by user_id. So how does login work? I maintain a separate lookup table: email → user_id. This table can be a simple key-value store or a small separate database. It maps the email to the user_id, which I then use to look up the actual user record on the correct shard. This adds one extra hop on login but login is not in the hot path for ongoing requests — it happens once per session.

Failure mode: if one of the 10 shards goes down, 10% of users cannot log in for the duration of the failover — roughly 5 to 15 minutes with automated failover. With 3 replicas per shard, we can survive 2 simultaneous failures on any single shard before losing availability. The other 90% of users experience zero impact because their data is on different shards. This is the key operational benefit of sharding — blast radius isolation.

Consistency model: I would use eventual consistency for profile display data — seeing someone's updated bio 3 seconds stale is acceptable. But I would use strong consistency for authentication — a user who just had their session revoked must not be able to log in even for 500 milliseconds. So authentication reads (checking if a session token is valid, checking if an account is banned) go to the leader. Profile display reads can go to replicas. This split consistency model reduces leader load significantly while maintaining the guarantees that actually matter for security."

---

## Common Mistakes — L5-Level Pitfalls to Avoid at L6 Interviews

These are the six mistakes that most reliably signal "L5 thinking, not L6." Each one sounds reasonable when you first hear it — that is why they are traps. If you catch yourself making these arguments in an interview, stop and recalibrate.

---

### Mistake 1: Sharding Before You Need To

**The thinking:** "We are growing fast. We should shard preemptively so we are ready when we need it."

**Why it happens:** Engineers learn about sharding as a scaling technique and want to apply it. Growth feels urgent. Preparing early seems responsible and forward-thinking.

**What goes wrong:** Sharding adds 3 to 6 months of engineering work — designing the shard key, migrating data live, updating application routing, rebuilding cross-shard query patterns, overhauling your deployment and testing pipeline. Cross-shard transactions become painful. Any query that touches multiple users becomes expensive. Your schema is now semi-permanent because resharding is enormously costly. And you spent 6 months engineering for a problem you might not hit for 2 years, while the operational complexity increased permanently.

**The better path:** Profile your actual bottleneck. 80% of "we need to shard" situations can be resolved with read replicas, better indexes, query optimization, caching hot data, and potentially a vertical scale to a larger machine — another 12 to 18 months of runway at a fraction of the cost. When those options are genuinely exhausted and you have measured the bottleneck, then shard. The bottleneck should be measured, not anticipated.

---

### Mistake 2: Using Timestamp as a Shard Key

**The thinking:** "Our data is naturally time-ordered. Events happen in time sequence. It makes sense to organize them by time."

**Why it happens:** Time-series data genuinely is organized by time. It is intuitive. Range queries on time are common for analytics. The design feels clean.

**What goes wrong:** All new data — which is always the highest-traffic data in any active system — goes to the shard for the current time window. "Today's events" shard receives all writes and most reads. Last month's shards are completely idle. This is a guaranteed, unavoidable hot spot that gets worse as your write rate grows. At the worst moment — peak traffic — your system is concentrating all load on one shard.

**The better path:** Hash by entity_id (user_id, device_id, session_id — whatever your primary entity is) for even write distribution. Use time as a secondary sort key within each shard so you can still query "all events for device X in the last hour" efficiently on a single shard. For aggregate time-range queries across all entities, use a separate analytics pipeline — not your primary OLTP database.

---

### Mistake 3: Ignoring Co-location

**The thinking:** "Each table should be independently sharded by its natural primary key. Users by user_id, orders by order_id, payments by payment_id. Uniform rules are easier."

**Why it happens:** It seems principled to shard each table independently. Each table has its own natural primary key and its own natural distribution.

**What goes wrong:** Querying "all orders for user X" now requires scatter-gathering across every order shard, because orders are distributed by order_id — not by user_id. You get the user from shard 3, but their orders could be on any of 16 order shards. Every user-order lookup fans out to all shards, waits for all responses, and assembles the result in the application layer. At high QPS this is extremely expensive — you have turned every user-order lookup into 16 parallel database queries.

**The better path:** Think about which tables are almost always queried together. If you almost always look up a user and their orders at the same time, shard orders by user_id. Now user X's profile is on shard 3 and user X's orders are also on shard 3. One database, one query. The principle: shard key = your primary join key, not each table's own primary key.

---

### Mistake 4: Making the Directory Service a Single Point of Failure

**The thinking:** "We will use a centralized directory service that maps entity IDs to shards. This gives us flexible routing and easy resharding — we just update the directory."

**Why it happens:** Directory-based routing is genuinely more flexible than consistent hashing. It is the right tool for certain situations, particularly for VIP tenants or irregular shard placement.

**What goes wrong:** If the directory service goes down — hardware failure, deployment bug, network partition — no application server can route any request to any shard. The directory service has become more critical than the shards themselves. A system where the routing metadata is unavailable is completely unavailable, even if all 16 shards are healthy and running perfectly.

**The better path:** Cache the routing table in every application server. The directory service is only consulted when the routing table changes — during resharding or rebalancing. Stale cached routing — from a few seconds or even minutes ago — is acceptable for almost all operations because shards almost never move. An application server with a 5-minute-old routing cache can still serve requests correctly in the vast majority of cases. The directory service going down means routing is frozen, not broken.

---

### Mistake 5: Forgetting Replication Lag in Application Design

**The thinking:** "We use a replicated database, so all reads return current data. The replicas are equivalent to the leader."

**Why it happens:** Replication lag is invisible in development environments. You do not have replicas locally. Even in production, replication lag is sub-second most of the time and goes completely unnoticed until it does not.

**What goes wrong:** A user updates their email address. The write goes to the leader. The application immediately redirects the user to their profile page. The profile page reads from a replica — which has 2-second replication lag. The email shows as the old value. The user thinks their update failed. They try again. Now you have a duplicate update request, a confused user, and possibly a support ticket about "the site not saving my changes."

**The better path:** Implement read-your-writes consistency for data that the user just modified. One simple approach: after a write, tag the user's session with a "freshness token" — a timestamp or log sequence number. For the next 30 seconds, route that user's reads to the leader. After 30 seconds, they fall back to replica reads. The user sees their own updates immediately. Everyone else can tolerate replica lag.

---

### Mistake 6: Not Planning for Resharding from Day One

**The thinking:** "Simple is better. We will use modulo hashing — entity_id mod N equals the shard number. Everyone on the team understands it instantly."

**Why it happens:** Modulo hashing is genuinely simple and genuinely correct. It works perfectly — right up until you need to add a shard. And when you start, adding a shard feels like a distant problem.

**What goes wrong:** You start with 4 shards. entity_id mod 4 = 0, 1, 2, or 3. Later you add a 5th shard. Now entity_id mod 5 gives different results for almost every entity. Roughly 80% of all data needs to move to a different shard. On a live production system with millions of users, this is a catastrophe — you cannot just rewrite the shard assignments overnight. This migration takes months and carries enormous risk.

**The better path:** Use consistent hashing from the start. With consistent hashing, adding a new shard only moves approximately 1/N of total data — not 80%. Alternatively, over-provision logical shards: use 64 logical shards on 4 physical machines (16 logical shards per machine). When you add a 5th machine, move 12–13 logical shards to it. No entity changes its logical shard — shards just move between machines. Logical shard count never changes; physical machine count does. This is what most production systems use.

---

## Key Numbers to Remember for Interviews

These numbers will make your answers sound grounded and credible. Do not invent numbers in interviews — use these ballpark figures and note that actual values depend on hardware and query complexity.

| Metric | Typical Value | Why It Matters in Interviews |
|---|---|---|
| Standard read replica capacity | 10,000–50,000 QPS per replica | Lets you calculate how many replicas you need for a given read load |
| Replication lag (healthy system) | Less than 100ms within same datacenter | Baseline for "everything is normal" |
| Replication lag (alert threshold) | Greater than 5 seconds | Signal to investigate — something is wrong |
| Replication lag (page immediately) | Greater than 30 seconds | Operationally severe — users are seeing stale data |
| Leader failover time (automated) | 30 seconds to 5 minutes | Determines your availability window during a leader failure |
| Shard hot spot alert threshold | Greater than 3× average shard utilization | Rule of thumb for when a shard needs intervention |
| Consistent hashing data movement (add 1 shard) | Approximately 1/N of total data | Shows why consistent hashing is worth the added complexity |
| Naive modulo reshard (4 → 5 shards) | Approximately 75–80% of data moves | Shows why naive modulo hashing is dangerous long-term |
| Resharding timeline for live production system | 2–4 months minimum done safely | Sets realistic expectations — not a weekend project |
| Logical shards per physical node (common practice) | 4–16 logical shards per machine | How production systems allow gradual, safe rebalancing |
| Read/write ratio for typical web applications | 80:20 to 95:5 reads to writes | Why read replicas solve most scaling problems before sharding is needed |

---

# Part 6: Brainstorming Questions — 30 Scenarios

These are not textbook questions asking you to "discuss" a topic. Each question is a specific scenario with a specific situation. Work through them as if you are in an interview. No hand-waving — give specific answers with specific numbers.

After each question, "Discussion Notes" indicate what a strong answer covers. Use these to check your own thinking.

---

## Section A: Replication Fundamentals (Questions 1–6)

---

**Q1: The Marketing Campaign**

Your PostgreSQL database serves a social media app with 500,000 daily users. It is currently a single node. Read QPS: 8,000. Write QPS: 2,000. The hardware can handle 15,000 total QPS before performance degrades. A marketing campaign next month will triple all traffic — reads to 24,000 QPS, writes to 6,000 QPS.

**Part A:** Walk through exactly what happens without any changes when 3× traffic hits. Which metric fails first? What do users see?

**Part B:** What is the minimum change to survive the campaign? What is your order of operations — add cache first? Replicas first? Upgrade hardware first?

> **Discussion Notes:** Part A — total QPS becomes 30,000, exceeding the 15,000 limit by 2×. The database slows down first, then connections queue up, then requests time out. Users see very slow page loads followed by errors. Part B — the minimum change depends on whether the traffic is read-heavy or write-heavy. If it is 80% reads (which social media usually is), 2 read replicas could absorb 16,000 reads/sec, bringing the leader's load to just writes (6,000 QPS). But this requires routing changes. A faster option: add a caching layer (Redis or Memcached) for profile reads and feed data. A well-designed cache layer can absorb 60–80% of reads within hours of deployment, no database changes needed. Cache first, replicas second, upgrade hardware only if both fail.

---

**Q2: The Phantom Update**

You added 3 read replicas to your database a week ago. Your CTO calls in a panic: "Why are users complaining that their profile updates are not saving? I just updated my own bio and it reverted to the old version after 2 seconds."

Describe exactly what is happening technically. Trace the path of the write request, the read request, and why the user sees old data. What is the 1-line code fix?

> **Discussion Notes:** The write goes to the leader and succeeds. The profile page redirect sends the user to a GET request that your load balancer routes to a replica. That replica has not received the write yet — replication lag of even 1–2 seconds means the old bio is returned. The 1-line fix: route reads to the leader for any request where a recent write exists for that user. Concretely: after any profile write, set a cookie or session flag with a timestamp. For 30 seconds after a write, any read from that user hits the leader instead of replicas. This is "read-your-writes" consistency. The broader lesson: when you add replicas, you must audit every code path that reads immediately after writing.

---

**Q3: The Async Replication Debate**

Your company's payment database uses asynchronous replication with 2 replicas. Your CTO argues: "Async is fine — the replica has the data within 500ms typically, and we have never had a leader crash in 3 years." Make the case for switching to semi-synchronous replication. Quantify the specific risk of staying on async. What is the latency cost of the switch? Is it acceptable for a payments system?

> **Discussion Notes:** The risk to quantify: at 1,000 payment writes per second with a 500ms async window, there are approximately 500 writes "in flight" at any moment — written to the leader but not yet to any replica. If the leader crashes, all 500 of those writes are lost permanently. For payments: 500 lost transactions could mean thousands of dollars unaccounted for. The argument for semi-synchronous: at 500ms latency to the replica, adding synchronous confirmation adds only that 500ms to write latency. For payments where the network round-trip is already 100–200ms, adding 500ms confirmation latency may bring total write latency from ~50ms to ~550ms. Is that acceptable? For most payment flows where users wait 1–3 seconds for confirmation, yes — a 500ms increase is not user-perceptible. Frame it as: "the cost of semi-sync is 500ms extra latency. The cost of staying async is potential financial data loss on any leader crash."

---

**Q4: The Global Leaderboard**

You are designing a global multiplayer game where players need to see leaderboard updates within 5 seconds from anywhere in the world. Players can update their score from any region — US, EU, Asia.

**Part A:** What replication strategy supports writes from multiple regions without a 200ms cross-region round-trip on every score update?

**Part B:** When two players in different regions update their score simultaneously — say, both write "top score = 50,000" at the same instant — what conflict resolution strategy gives the correct result for a leaderboard? (Hint: think about what "correct" means for a leaderboard — is it consistency or recency that matters?)

> **Discussion Notes:** Part A — multi-leader replication allows each region to accept writes locally (low latency for the player). Writes are then asynchronously replicated to other regions within a few seconds, meeting the 5-second visibility requirement. Leader-follower with a single global leader would require a 200ms+ round-trip to the leader for every score update — too slow for a game. Part B — for a leaderboard, "correct" means the highest score wins, not the most recent write. Last-Write-Wins is wrong here: if a player scores 60,000 in Asia and then scores 40,000 in the US 1ms later, LWW would record 40,000 as the final score. The correct conflict resolution: max-value wins (keep the highest score). This is a domain-specific conflict resolution rule — the leaderboard's semantics define what "merge" means.

---

**Q5: The Slow Replica**

A startup just added their first read replica. They are excited — reads are now spread across 2 nodes. 3 hours later, one replica's queries are taking 2 seconds instead of the normal 5ms. The replica server shows only 20% CPU. The leader is responding normally.

What are the 3 most likely causes of this symptom (slow queries, normal CPU, only affecting one replica)? How do you diagnose which one it is?

> **Discussion Notes:** Three hypotheses: (1) The replica is experiencing lock contention — a long-running replication operation or a manual query running on the replica is holding locks that block other queries. Diagnosis: check `pg_locks` or `SHOW PROCESSLIST` for blocking queries. (2) The replica is IO-bound, not CPU-bound — the storage device is slow (failing disk, throttled IOPS on cloud storage). CPU is normal because the bottleneck is disk wait, not computation. Diagnosis: check disk IO metrics — specifically IO wait percentage and disk queue depth. (3) The replica's query cache or buffer pool is in a bad state — it was recently restarted and is warming up, causing disk reads for queries that would normally hit memory. Diagnosis: check when the replica was last restarted and monitor buffer hit rate. CPU-normal-but-queries-slow almost always points to IO or locking, not compute.

---

**Q6: The Simultaneous Edit**

Your company uses multi-leader replication for a document editing system — both the US and UK offices can accept writes. User Alice edits the document title to "Project Phoenix" from the US office at 2:00:00.000 PM UTC. 200ms later, User Bob edits the same title to "Project Dragon" from the UK office at 2:00:00.200 PM UTC. The network delivers both changes to both leaders simultaneously at 2:00:01 PM UTC.

**Part A:** With Last-Write-Wins conflict resolution, whose title survives? What assumption does this resolution strategy make — and why is that assumption unreliable in distributed systems?

**Part B:** With an OR-Set CRDT, could both names survive simultaneously? If so, how would the document editing UI display this result? If not, why not?

> **Discussion Notes:** Part A — LWW relies on wall-clock timestamps to determine "which write came last." Bob's write at 2:00:00.200 has a later timestamp, so "Project Dragon" would survive. But the assumption LWW makes — that clocks across servers agree on the true ordering of events — is unreliable. Clock skew between servers can be 10–500ms or more. If the US server's clock is 300ms fast, Alice's timestamp might read 2:00:00.300, which is later than Bob's. In that case "Project Phoenix" wins — even though Bob wrote after Alice. The "winner" depends on which server has an inaccurate clock. Part B — an OR-Set CRDT tracks both values as concurrent updates that neither supersedes the other. The document title would be in a "conflict" state holding both "Project Phoenix" and "Project Dragon." The UI must surface this: typically shown as a split view or a visible merge conflict indicator. This is what Google Docs does — it tracks individual character-level operations and merges them, so both users' keystrokes survive and the document shows the combined result.

---

## Section B: Sharding Decisions (Questions 7–12)

---

**Q7: The Multi-Tenant Hot Shard**

You are designing the database for a multi-tenant SaaS collaboration tool, similar to Slack. You have 50,000 customer companies. 3 of those companies each have over 100,000 users. The remaining 49,997 companies average 50 users each.

**Part A:** You decide to shard by company_id (each company's data lives on one shard). Why is this dangerous given the data above? Walk through what happens to the shard that receives one of the 100,000-user companies. Show the math comparing its load to a shard with average-sized companies.

**Part B:** Design a hybrid strategy that gives large companies performance isolation without creating massive shard imbalance. Where do the 3 large companies go? What happens when a medium company grows unexpectedly to 100,000 users?

> **Discussion Notes:** Part A math — average company has 50 users. If you place 200 average companies on one shard, the shard has 10,000 users. One large company has 100,000 users — 10× the load of a full normal shard. That large company's shard is overwhelmed while others are largely idle. Part B — give each large company its own dedicated shard (or dedicated cluster). The 3 large companies each get isolated infrastructure. The 49,997 small companies share shards by company_id as planned. The routing logic: check if company_id is in the "large tenant" table. If yes, route to their dedicated shard. If no, route using the standard hash. For companies that grow: monitor company size. When a company crosses a threshold (say 20,000 users), flag it for migration to a dedicated shard. Have a migration runbook ready — this is a predictable event, not a surprise.

---

**Q8: The Scatter-Gather Nightmare**

Your e-commerce database is sharded by user_id across 16 shards. A new product requirement arrives: "Show the top 100 best-selling products this week, ranked by units sold." This requires aggregating order data from all users — which live on all 16 shards.

How do you answer this query efficiently without scatter-gathering all 16 shards every time? Design the data pipeline that makes this query fast. What is the trade-off in data freshness?

> **Discussion Notes:** The answer is a separate analytics pipeline — not answering this query from the OLTP shards at all. Option 1: a daily or hourly ETL job reads from all 16 shards, aggregates the product sales data, and writes results to a separate analytics database or simple key-value cache. The "top 100 products" query then reads from the pre-computed result — one query, instant response. Option 2: event streaming — every order creation event is published to a message queue (Kafka). A separate stream processor (Flink or Spark) consumes order events in real-time, maintains running totals per product_id, and writes the current top-100 list to Redis every minute. The freshness trade-off: with hourly ETL, your top-100 list is up to 1 hour stale. With streaming, it is under 1 minute stale. Both are far better than scatter-gathering 16 shards on every request.

---

**Q9: The Shard Emergency**

You shard user data by user_id hash across 8 shards. One year later, your dataset has grown 4× and shard 3 is at 94% disk capacity — you expect it to fill completely in 3 weeks. Your engineer suggests: "Just add shard 9 and move half of shard 3's data to it."

**Part A:** Design the minimum viable plan to execute this live, without user-facing downtime. Write each phase with its name, what you are doing, and a rough duration estimate.

**Part B:** What specific monitoring metrics tell you the migration is safe to complete at each phase? What specific metrics trigger an immediate rollback?

> **Discussion Notes:** Part A phases: (1) Provision new shard 9 — spin up hardware, configure replication config, but no data yet. Duration: 1–2 hours. (2) Identify the split — determine which user_ids currently on shard 3 will move to shard 9. With consistent hashing: the new shard takes its arc of the hash ring. (3) Copy data — read from shard 3, write to shard 9. Run during off-peak hours. This is the slow phase: 100M rows, maybe 24–48 hours. (4) Double-write — update routing to write affected user_ids to both shard 3 and shard 9. This ensures writes during the copy are not lost. (5) Verify — row count match, checksum key ranges, confirm writes land correctly on both shards. (6) Switch reads to shard 9 for the migrated users. Watch for 30 minutes. (7) Stop double-write, make shard 9 the primary for those users. Part B rollback trigger: if shard 9 read latency p99 exceeds 3× the shard 3 baseline, roll back reads immediately. If any row count mismatch during verification, stop before switching reads.

---

**Q10: Instagram Stories Architecture**

You are building Instagram Stories — a feature where stories expire after 24 hours. Requirements: write new stories at 100,000 per minute, read stories for a user's feed at 500,000 per minute, and auto-delete all stories older than 24 hours continuously.

**Part A:** What shard key? Which sharding strategy — hash, range, or directory? Justify your choice by listing the primary access patterns.

**Part B:** How do you handle the "delete all 24-hour-old stories" operation efficiently across shards? If stories are sharded by user_id, how does a background deletion job find all stories older than 24 hours without scanning every shard entirely?

> **Discussion Notes:** Part A — shard by user_id with hash sharding. Primary access patterns: (1) "give me the stories for user X" — used when building a feed; single-user lookup maps to single shard. (2) "give me all stories posted by user X" — user's own story management; also single-shard with user_id sharding. Range sharding would create hot spots (all new stories go to the "now" shard). Part B — this is the subtle design challenge. If sharded by user_id, there is no efficient cross-shard time index. Solution: maintain a secondary index by created_at timestamp in each shard. Each shard can independently run: `DELETE FROM stories WHERE created_at < NOW() - INTERVAL 24 HOURS`. The background deletion job broadcasts to all shards in parallel, each deletes its own expired stories independently. This is efficient because the time index within each shard is small and the deletion is embarrassingly parallel across shards.

---

**Q11: The Orphaned Likes**

Your startup's database has: 3 million users, 50 million posts, 500 million post_likes. Posts are sharded by post_id (hash across 16 shards). post_likes are sharded by post_id (hash across 16 shards). A new product requirement arrives: "Show all posts that User X has liked in the last month — for their activity page."

How expensive is this query with current sharding? How many shards must you touch? Design a schema change — without resharding — that makes this query efficient. What is the write cost of your schema change?

> **Discussion Notes:** With current sharding: finding all likes by User X requires scatter-gathering all 16 shards (since likes are sharded by post_id, likes from User X are spread across all shards). 16 parallel queries, wait for all, merge results. At 500M likes across 16 shards, each shard has ~31M likes. Scanning 31M rows per shard filtered by user_id is extremely slow without an index on user_id within each shard. The fix without resharding: add a separate `user_likes_activity` table, sharded by user_id. Whenever User X likes a post, write: (1) to post_likes sharded by post_id (existing, for "how many likes does this post have"), and (2) to user_likes_activity sharded by user_id (new, for "what has User X liked"). The write cost: every like now creates 2 writes instead of 1 — a 2× write amplification on the likes table. At 500M likes created, that is 500M extra writes. Acceptable for the query performance improvement, which goes from "16 shard scatter-gather" to "single-shard lookup."

---

**Q12: The Viral Post Crisis**

A tweet goes viral. 50,000 requests per second are hitting the shard that stores that specific tweet — 10× normal shard traffic. The shard CPU is at 95%. Other shards are at their normal 20–30%.

**Part A:** What are your 3 immediate mitigation options that require no code deployment and no new infrastructure provisioning? Time frame: you have 10 minutes before the shard becomes unavailable.

**Part B:** If this viral content pattern happens regularly — several times per month — what architectural change prevents it permanently, so it is not a crisis every time?

> **Discussion Notes:** Part A immediate options (no deployment, no new infra): (1) Enable or tune the query cache if the tweet data is cacheable at the database level — some databases have a built-in query result cache that can absorb repeated identical reads. (2) Route read traffic to the shard's replicas — if the shard has read replicas, shift 100% of reads to replicas immediately, leaving the leader for writes only. This effectively multiplies read capacity by the replica count. (3) Throttle or rate-limit requests at the load balancer for that specific tweet_id endpoint — this buys time but degrades user experience. Part B architectural fix: implement application-level caching (Redis/Memcached) for tweet content. Any tweet with more than 1,000 reads per second gets automatically promoted to a cache. Cache TTL for tweet content: 60 seconds. Cache absorbs 99% of reads. Only cache misses hit the database. This converts a viral post from a database crisis to a cache hit — completely invisible.

---

## Section C: Failure Scenarios (Questions 13–18)

---

**Q13: The 2 AM Page**

At 2 AM, your monitoring fires: "Shard 5 is unreachable." You have 16 shards total. Each shard has 1 leader and 2 replicas. User data is distributed by user_id hash — approximately 1/16 of users per shard.

**Part A:** Who is immediately affected? Walk through the exact blast radius — which users can do what, which users cannot do what, which operations fail completely versus degrade partially.

**Part B:** Write your exact runbook for the next 30 minutes. What do you check first? In what order do you take actions? What is your decision criteria at each step — specifically, at what point do you escalate versus handle alone?

> **Discussion Notes:** Part A blast radius: approximately 6.25% of users (1/16) are affected. These users cannot log in, cannot load their profile, cannot post or like. The remaining 93.75% of users are completely unaffected — their data is on other shards. Operations that fail entirely: any operation requiring shard 5 data (user profile reads, user writes, login for affected user_ids). Operations that degrade for everyone: if shard 5 handled any global indexes or lookups, those degrade too. Read operations may succeed briefly if replicas are still accessible. Part B runbook: Step 1 (2 min) — confirm the alert is real, not a false positive. Check monitoring from 2 sources. Step 2 (3 min) — determine if replicas are reachable. If replicas are up, promote a replica to leader immediately (automated failover should have triggered). Step 3 (5 min) — check if automated failover already ran. Most setups trigger failover within 1–3 minutes. If it did, check the new leader is accepting writes. Step 4 (10 min) — investigate why the original leader went down. Step 5 (escalate if) — failover did not happen automatically after 5 minutes, or both replicas are also unreachable.

---

**Q14: The Growing Lag**

You are on call. Alert fires: "Replication lag on replica-2 is 8 minutes and growing." Normal lag is under 500ms. The lag has been increasing for 20 minutes and is now 8 minutes.

**Part A:** What does "8 minutes of replication lag" actually mean for users? Give 2 specific, concrete examples of incorrect behavior a user could experience right now.

**Part B:** What 5 specific things do you check to diagnose the root cause of growing replication lag? What is your immediate mitigation while you investigate — before you know the root cause?

> **Discussion Notes:** Part A user impact examples: (1) A user changes their password at 3:00 PM. They log out and log back in at 3:05 PM. If their login check reads from replica-2, the replica shows their old password (from before 3:00 PM). Login with the new password fails. The user thinks the password change did not work and is locked out. (2) A payment is made at 3:00 PM. User checks their transaction history at 3:05 PM. The transaction does not appear because replica-2 does not have it yet. User panics, calls support, reports a "missing payment." Part B — 5 things to check: (1) Is the leader write volume spiking? Check leader writes/sec — a sudden burst could overwhelm the replica. (2) Is something running on replica-2 that is competing for resources? Check for long-running queries or manual VACUUM operations. (3) Is replica-2's disk IO at capacity? Check disk utilization and IO wait. (4) Is there a network issue between leader and replica-2? Check network throughput and dropped packets. (5) Is the replication thread on replica-2 actually running? Check replication status — it might have stopped. Immediate mitigation before root cause: mark replica-2 as unhealthy in the load balancer, stop routing reads to it. Users now read from other replicas or the leader.

---

**Q15: The Shard Key Argument**

Two engineers on your team are arguing. Engineer A: "We should shard by user_id so all of a user's data is co-located on one shard — profile, settings, activity, everything. Queries for a user are always single-shard." Engineer B: "We should shard by timestamp so we can efficiently query recent events and rotate out old data by simply deleting old shards."

Mediate this disagreement. What are the questions you would ask to decide? Is there a design that satisfies both requirements? If you had to choose one, which would you choose for a social media application and why?

> **Discussion Notes:** Questions to ask: What is the primary access pattern — are most queries "all data for user X" or "all data in the last 24 hours"? What is the data lifecycle — do we need to delete old data at scale? What percentage of queries are user-centric vs time-range queries? A design that satisfies both: shard by user_id for the primary user tables, but for event/activity logs (the time-series data), use a separate store with time-based partitioning — a time-series database or range-partitioned table. This way user profile data benefits from co-location, and time-series activity data benefits from time-range queries and TTL-based deletion. If forced to choose one for a social media app: user_id sharding wins. Most social media queries are user-centric: "show me my feed," "show me my profile," "show me my posts." Timestamp sharding would turn all of these into scatter-gather operations. The data rotation problem is solved with TTL at the application layer, not at the shard level.

---

**Q16: The Silent Write Failure**

You are mid-way through a resharding migration from 8 to 32 shards. You are in the double-write phase — all new writes go to both old shards and new shards simultaneously. Your monitoring dashboard shows: new shard 7 is receiving write requests but not applying them. Writes are disappearing silently. No error messages are being returned.

**Part A:** What user impact is happening right now? Which users are affected — all users or a specific subset?

**Part B:** Your application's write confirmation is returning "success" to users. Why? Who confirmed the success? Is the data actually lost?

**Part C:** How do you safely recover? What is the order of operations? What do you do about the data that was written to old shard 7 but not applied to new shard 7?

> **Discussion Notes:** Part A — only users whose data is mapped to new shard 7 are affected. Since you are in double-write mode, the old shard 7 is still receiving and applying those writes correctly. From a user-facing perspective, these users may not notice immediately because reads are still routing to old shards. But their data on new shard 7 is increasingly stale. Part B — "success" is returned because the write to old shard 7 succeeded, and the application considers that sufficient during the double-write phase. The write to new shard 7 failed silently — the application did not treat it as a blocking error. The data is NOT lost yet — it exists on old shard 7. Part C recovery: (1) Immediately pause the migration — stop any plans to switch reads or writes to new shard 7. (2) Investigate and fix why new shard 7 is not applying writes. (3) Once fixed, backfill: replay all writes from old shard 7 to new shard 7 from the migration start time forward. (4) Verify consistency — run checksums before resuming the migration. The lesson: silent failures are the most dangerous in distributed migrations. Build explicit write confirmation checks into the double-write layer.

---

**Q17: The Multi-Leader Proposal**

A new engineer on your team proposes: "Let's implement multi-leader replication for our US and EU datacenters. Both datacenters can accept writes. This gives us zero-downtime failover if one goes down. Users in each region get low write latency." You have a payments database.

Respond to this proposal thoroughly. What would you accept from this proposal? What would you refuse? What are the specific risks that make this dangerous for a payments system? What alternative architecture would give the same benefits with lower risk?

> **Discussion Notes:** What to accept: the motivation is correct — low write latency in each region and resilience to datacenter failure are legitimate goals for a global payments system. What to refuse: multi-leader for financial data is almost never the right answer. The reason: conflicts. If User A's balance is $500 and they spend $400 from the US leader while simultaneously the EU leader processes an $400 charge on the same account, both writes "succeed" locally. During conflict resolution, the system has to decide what the final balance is — and every conflict resolution rule gives the wrong answer. LWW might leave the user at $100 (missing $400). Merge might credit $400 back. Neither is correct. Alternative architecture: regional leader assignment. US users write to the US leader. EU users write to the EU leader. Neither can accept writes for the other region's users. Cross-region reads are served from regional replicas. This gives EU users low latency for their own accounts (which are mastered in EU) without the conflict risk of full multi-leader. If the EU datacenter fails, EU writes temporarily route to the US leader with acceptable latency — acceptable degradation without catastrophic correctness issues.

---

**Q18: The Mystery Slowdown**

Your monitoring shows: all 4 shards have similar CPU utilization (30–40%) and similar disk usage (50%). Shard 2 CPU is normal. But users on shard 2 are reporting 10× slower response times than users on other shards — p99 latency of 8 seconds vs 800ms on other shards.

**Part A:** CPU is normal but queries are slow. What do you check first? Give 4 specific hypotheses that could produce this pattern, and for each, what you would check to confirm or eliminate it.

**Part B:** Upon investigation, the slow queries on shard 2 are all for user accounts created in 2019, which all hash to shard 2 based on the original shard key. These 2019-era accounts have significantly more data per user than newer accounts — more posts, more followers, more history. What does this tell you about the original shard key design? What is the structural problem?

> **Discussion Notes:** Part A — four hypotheses: (1) Lock contention — a long-running query or transaction is holding locks that block other queries. CPU is low because queries are waiting, not computing. Check: `pg_stat_activity` for blocked queries, `pg_locks` for lock waiters. (2) Network saturation — shard 2 is receiving more data in query results (larger rows) even if CPU is similar. Check: network IO on shard 2 vs others. (3) Table bloat — the tables on shard 2 have more dead rows from older data, causing slow sequential scans. CPU does not reflect this because IO does. Check: table bloat statistics, `pg_stat_user_tables`. (4) Index bloat or fragmentation — indexes on shard 2 are fragmented after years of updates and deletes, causing slower index scans. Check: index bloat statistics, run ANALYZE and compare query plans. Part B — the structural problem: the shard key (user_id hash) distributed rows evenly by count but not by row size. 2019 users have much larger rows because they have more historical data. Shard 2 received a disproportionate share of these heavy users by random hash collision. The shard has the same number of rows but far more data. This is "data skew by record size" — a subtler version of the hot-shard problem that does not show up in row count statistics.

---

## Section D: Design Trade-offs (Questions 19–24)

---

**Q19: The Ride-Sharing Schema**

You are designing the database for a ride-sharing app similar to Uber. The main entities are: Drivers, Riders, Trips, and Payments. Design the sharding strategy.

For each entity, answer: (a) what is the shard key and why, (b) what is the consistency requirement for writes to this entity, and (c) what is the hot spot risk for this entity?

Specifically address: a Trip involves both a Driver and a Rider — they may be on different shards. How do you handle reading a trip's full details?

> **Discussion Notes:** Drivers — shard by driver_id. Consistency: strong (driver availability status must be accurate — two riders cannot be assigned the same driver). Hot spot risk: low, drivers are evenly distributed. Riders — shard by rider_id. Consistency: eventual is acceptable for profile data, strong for active trip state. Hot spot risk: low. Trips — shard by rider_id (not trip_id). Primary access pattern is "give me trips for rider X." By sharding trips by rider_id, a rider's trip history is always on the same shard as the rider. Alternative: shard by driver_id for driver-side queries — but riders query trips more often than drivers. Payments — shard by rider_id. Financial transactions need strong consistency. Cross-shard trip reads: a trip has driver_id and rider_id, potentially on different shards. Solution: denormalize the trip record to include the driver's name and current status at the time of the trip. Full driver profile details are fetched separately from the driver shard when needed. The trip record itself is complete enough for most display purposes.

---

**Q20: The Celebrity Fan-Out Design**

Instagram uses push-based fan-out for most users: when you post, your post is immediately written to each follower's feed table. For celebrities with over 1 million followers, they use pull-based: your feed is assembled on request by fetching celebrity posts directly.

Design the data model and routing logic for this hybrid approach. Specifically: When does a user "become" a celebrity for fan-out routing purposes? How does the system detect and handle an account crossing the threshold? What happens to existing feed data for followers when a user transitions from push to pull?

> **Discussion Notes:** Data model: normal user posts → fan_out_queue → writes to follower feed tables (push). Celebrity posts → written to celebrity_posts table only (pull). Feed assembly: for each person User X follows, check if they are a celebrity. If yes, fetch their last 10 posts from celebrity_posts. If no, read from the pre-populated feed table. Celebrity detection: maintain a `celebrity_users` table updated by a background job that checks follower counts every hour. When follower count crosses 1M, add to celebrity table. Threshold crossing: when a user crosses the threshold, stop push fan-out for new posts immediately. Existing pushed posts in followers' feed tables remain — they do not need to be cleaned up, they are just old data. The feed assembly logic handles both: show existing pushed posts + pull new celebrity posts, deduplication by post_id. Transition logic: the switch is safe because it only affects new posts. Old posts were pushed; new posts are pulled. The union is correct.

---

**Q21: The Analytics Query Problem**

A company has a 50TB dataset distributed across 32 shards. They want to run an analytics query: "Calculate the average purchase value for all users who signed up in Q1 2022 and made at least 3 purchases."

**Part A:** How many shards does this query touch? Why can this query not be answered by a single shard?

**Part B:** Design an architecture that can answer this kind of aggregate query without touching all 32 OLTP shards every time. What data pipeline would you use? What separate data store?

**Part C:** What is the consistency trade-off of your analytics architecture? How stale can the analytics results be? Is that acceptable for this query?

> **Discussion Notes:** Part A — this query touches all 32 shards. Users who signed up in Q1 2022 are distributed across all shards by user_id hash. There is no way to know which shards contain Q1 2022 signups without checking all of them. This is fundamentally a full-table-scan query — it filters on signup_date, not on user_id, so sharding by user_id provides no benefit. Part B — dedicated analytics pipeline: replicate all OLTP data to a separate analytics warehouse (BigQuery, Snowflake, Redshift). This replica is read-only and can be queried freely without impacting production. ETL runs every hour: extract changes from all 32 OLTP shards, transform, load into the analytics warehouse. The analytics warehouse is not sharded by user_id — it is optimized for column-store scans and aggregations across all data. Part C — consistency trade-off: with hourly ETL, your analytics data is up to 1 hour stale. For the query "average purchase value for Q1 2022 signups," an hour of staleness is completely acceptable — this is a historical analysis, not a real-time dashboard.

---

**Q22: The Global Chat Architecture**

You are building a global chat application. Messages must satisfy four requirements simultaneously: (1) delivered to recipients within 500ms regardless of region, (2) never duplicated even if the sending client retries, (3) shown in causal order within a conversation, (4) searchable by keyword.

Design the sharding strategy for messages. What is your shard key? How do you technically enforce "never duplicated" across distributed infrastructure? How do you ensure causal ordering?

> **Discussion Notes:** Shard key: conversation_id. Primary access pattern: "give me recent messages in conversation X." Sharding by conversation_id ensures all messages in a conversation land on one shard — no scatter-gather for conversation history, and causal ordering is handled within one shard (write log order = message order). Never duplicated: idempotency keys. The client generates a UUID for each message send attempt. The server stores this UUID in a deduplication table with a TTL of 24 hours. Before inserting a message, check the deduplication table. If the UUID exists, return success without inserting. Causal ordering within a conversation: since all messages in a conversation are on one shard, the shard's write log establishes a total order. Messages are assigned a monotonically increasing sequence number within each conversation by the shard. Searchable: maintain a separate Elasticsearch index for message content. When a message is written to the shard, publish it to a Kafka topic. An Elasticsearch consumer ingests from Kafka and indexes the message. Search queries go to Elasticsearch, which returns message IDs, then you fetch full messages from the shard.

---

**Q23: The Cross-Shard Money Transfer**

Your company processes 1 million financial transactions per day, all involving debit-one-account, credit-another-account. Accounts are sharded by account_id (hash). Source and destination accounts are on different shards approximately 40% of the time.

**Part A:** What is the exact consistency requirement for a financial transfer? Can you use eventual consistency?

**Part B:** Design the transaction logic that guarantees no money is created or destroyed even in these failure scenarios: (a) network timeout occurs after successfully debiting the source but before the credit request is sent, (b) the destination shard crashes mid-transaction after receiving the credit request but before confirming it. Describe the complete flow including idempotency keys and recovery steps.

> **Discussion Notes:** Part A — financial transfers require atomicity: either both the debit and credit happen, or neither does. No money should be "in transit" permanently. Eventual consistency is not acceptable for the outcome (you cannot eventually credit someone's account — it must happen), but it is acceptable for the time delay (the credit may arrive 100ms after the debit — that is fine). Part B — Saga pattern with idempotency: generate a transaction_id UUID. Step 1: write a "PENDING" transaction record to a durable transaction log (separate from both shards). Step 2: debit source shard with transaction_id as idempotency key. Mark source debit as "DEBITED." Step 3: credit destination shard with transaction_id as idempotency key. Mark destination credit as "CREDITED." Step 4: mark transaction as "COMPLETE" in the log. Recovery: a background job scans for transactions stuck in "DEBITED" state for over 60 seconds. It retries the credit with the same idempotency key — safe to retry because idempotency key prevents double-credit. If credit permanently fails after N retries, execute compensating transaction: re-credit the source account. The transaction log is the source of truth — not the individual shard states.

---

**Q24: The GDPR Geo-Partition Decision**

Your team is debating architecture. Option A: one global database with read replicas in each region. Option B: geo-partitioned shards — EU data in EU, US data in US, Asia data in Asia. You serve users in all three regions. Data regulations: EU users' data must physically stay in EU (GDPR). US and Asia have no data residency restrictions. The vast majority of user queries access only their own data.

**Part A:** Design both architectures fully. For each: describe the routing logic, the data model, the operational complexity, and how regulatory compliance is achieved.

**Part B:** A US user wants to view an EU user's public profile page — their name, bio, and public posts. In your chosen architecture, how does this cross-region request work? What is the latency? What is the consistency model?

> **Discussion Notes:** Option A (global DB with regional replicas): all data lives in one logical database, replicated to each region. GDPR compliance is impossible — EU data physically exists on US and Asia replicas. This architecture fails the regulatory requirement. Option A cannot work. Option B (geo-partitioned): EU users' data is mastered in EU infrastructure. EU data never leaves EU. US users' data lives in US. Each region is effectively an independent shard, routed by user's registered region. GDPR compliance is structural — EU data never leaves EU infrastructure. Routing logic: on login, read user's region from a global routing directory (small, fast key-value store). All subsequent requests route to that region's database. Part B cross-region request: US user viewing EU user's public profile sends a request to US region servers. US region recognizes the EU user_id must be fetched from EU database. US server makes an API call to EU servers (150–200ms round-trip latency). EU server fetches the public profile and returns it. US server displays it. Latency: 150–200ms extra vs local profile view. Consistency: the EU data is the source of truth; the US server shows whatever the EU database currently has — fully consistent, just with cross-region latency.

---

## Section E: Real System Design (Questions 25–30)

---

**Q25: WhatsApp Scale**

Design the database layer for a WhatsApp-style messaging system: 500 million daily users, 100 billion messages sent per day, message history must be queryable.

**Part A:** Compare two shard key choices for the messages table: shard by conversation_id versus shard by sender_id. For each option: which queries are fast (single-shard), which queries are slow (multi-shard or impossible), and what write distribution looks like.

**Part B:** You cannot store 100 billion messages per day indefinitely — that is approximately 10TB of new data per day. Design the tiered storage architecture: what data lives in "hot" fast storage, what moves to "warm" storage, what moves to archival cold storage, and at what age thresholds?

> **Discussion Notes:** Part A comparison: Shard by conversation_id — fast: "give me recent messages in conversation X" (single-shard). Slow: "give me all messages sent by user Y" (scatter-gather all shards). Write distribution: uneven if some conversations are much more active — group chats could create hot shards. Shard by sender_id — fast: "give me all messages sent by user Y" (single-shard). Slow: "give me conversation history between User A and User B" (must check both sender shards). Write distribution: more even because each user generates a similar volume of writes. Winner for messaging: conversation_id. The primary product experience is viewing conversation history — that must be fast. Part B tiered storage: Hot tier (SSD, 0–30 days): all recent messages, fully indexed, fast random access. Warm tier (HDD or lower-cost SSD, 30 days – 1 year): messages moved automatically after 30 days. Still queryable but with higher latency. Query patterns here are rare (users rarely read messages from months ago). Cold/archival tier (object storage like S3, 1 year+): compressed, cheap, extremely rare access. Retrieved on demand with minutes of latency. Migration is driven by a background job that checks message age and moves batches nightly.

---

**Q26: Netflix Read Scale**

Netflix serves video metadata — title, description, cast, thumbnail URLs — to 200 million daily active users with extremely high read QPS. Metadata changes rarely: maybe 1,000 updates per day across 15 million total titles.

**Part A:** Given the read/write ratio (millions of reads, 1,000 writes per day), do you actually need sharding? What architecture would you use instead? Walk through the capacity math showing whether sharding is even necessary.

**Part B:** Netflix wants to guarantee that when a title's metadata is updated, all users globally see the updated version within 60 seconds. Design the cache invalidation and replication strategy that achieves this SLO.

> **Discussion Notes:** Part A capacity math: 15 million titles × 10KB average metadata = 150GB total data. 150GB fits entirely in memory on a single large server (1TB RAM servers are available). If all metadata is in memory, read QPS can be millions per second from a single node with replicas. With 10 read replicas: 10 × 1M QPS = 10M reads/second. This is far more than any realistic Netflix workload. Writes: 1,000 updates per day = 0.01 writes per second. Sharding for 0.01 writes/sec is absurd overkill. Architecture: a single database with many read replicas. All metadata fits in the buffer pool across replicas. Reads are essentially memory lookups. No sharding needed. Part B — 60-second update propagation: when metadata is updated, immediately invalidate the CDN cache entries for that title's metadata. CDN cache TTL should be set to 60 seconds (not longer). Replication from leader to replicas should complete within a few seconds normally. For the CDN invalidation: use a cache invalidation API call immediately after the database write succeeds. All CDN edge nodes purge the specific title's cache. Users fetching the title after invalidation get a cache miss, fetch from the database replica, and get the fresh data.

---

**Q27: The Microservices Migration**

A monolith application has a single PostgreSQL database. user_id is a foreign key in 15 different tables. You are migrating to microservices, each with their own database. The 15 tables will be split across 5 microservices: User Service, Order Service, Payment Service, Product Service, and Notification Service.

**Part A:** Once the tables are in separate databases, how do you maintain "referential integrity" — the guarantee that an order cannot exist for a user_id that does not exist in the user table? What is the microservices approach to this problem?

**Part B:** A customer service tool needs to show an order alongside the customer's name and email address. Order Service has the order. User Service has the name and email. User Service is currently down. What options does Order Service have? Which option do you choose and why?

> **Discussion Notes:** Part A — in a monolith, the database enforces foreign key constraints. In microservices, you cannot have foreign key constraints across databases. The microservices approach: eventual consistency with application-level validation. Before creating an order, Order Service calls User Service to verify the user exists. If verification fails, reject the order. This is not a database constraint but an application-level check. For safety: use an outbox pattern — when a user is deleted, User Service publishes a "user_deleted" event. Order Service consumes this event and soft-deletes or marks orders for that user. Referential integrity is maintained by the event system, not the database. Part B options: (1) Fail the request — return an error to the customer service tool. Simple but unhelpful. (2) Return the order data without user info — partial data, user fields shown as "unavailable." (3) Return cached user data — if Order Service caches user name/email for each order (denormalized), it can return the full record from its own data. Option 3 is usually best for customer service tools. Denormalize the user's name and email into the order record at order creation time. This makes Order Service independent of User Service for reads — User Service downtime does not affect order viewing.

---

**Q28: The Stock Trading Storage**

A stock trading platform needs to: insert 50,000 stock price updates per second, query "price history for AAPL in last 30 minutes" in under 10ms, and query "all stock prices at exactly 2:30 PM yesterday" in under 100ms.

Design the complete storage architecture. What sharding strategy? What specific indexes? Given the time-series nature of this data, is a traditional relational database the right tool, or would you use a time-series database? What is the shard key and why?

> **Discussion Notes:** 50,000 inserts/second is a significant write load — most traditional relational databases handle 10,000–50,000 writes/second maximum on one machine. The data is pure time-series: stock symbol + timestamp + price. This is the ideal use case for a time-series database like InfluxDB, TimescaleDB, or Apache Cassandra. Architecture: time-series database sharded by stock_symbol. Each symbol's price history is co-located on one shard. Query "AAPL price history last 30 minutes" → single shard, indexed by timestamp within the symbol's partition. Fast. Query "all stocks at 2:30 PM yesterday" → every shard, but it is a point-in-time read, not a range scan — each shard returns one row for 2:30 PM. Manageable as parallel shard reads. Sharding by symbol works because there are thousands of symbols (no single hot spot) and the primary access pattern is always "symbol + time range." Indexes: composite index on (symbol, timestamp) within each shard — the two query dimensions.

---

**Q29: The Email to Your Engineer**

You are the only engineer at a 5-person startup with 50,000 users and a single PostgreSQL database. Your database is running at 60% capacity — both CPU and disk. A new engineer joins the team and sends you a Slack message: "We should start sharding our database now. If we're already at 60%, we'll hit 100% as we grow. Better to be ready."

Write the email response explaining clearly why you are not sharding right now and what you would do instead. Include specific metrics that would change your decision.

> **Discussion Notes — Sample email text:**
>
> "Hey — good instinct to think about scaling! Let me share my thinking on why sharding is not the right move right now, and what I plan to do instead.
>
> At 50,000 users with 60% CPU and disk, we are in a perfectly normal operating range. Sharding would take 3–6 months of engineering time and add permanent operational complexity to a system that does not need it yet. That is engineering time we could spend on features that grow the business.
>
> Here is what I am going to do instead: First, I am going to look at the slow query log and find our top 5 most expensive queries. I bet 80% of our CPU comes from 3–4 queries that would benefit enormously from better indexes. Second, I am going to add a Redis cache in front of our most-read data — user profiles and session data. That should cut our read load by 40–60%. Third, if we still need more capacity after that, I can upgrade to the next instance size — that doubles CPU and memory for maybe $300/month.
>
> The metrics that would make me consider sharding: write QPS over 5,000/second (we are currently at about 200), dataset size over 500GB (we are at about 30GB), or read replicas not keeping up after we add them. Right now we are nowhere near those thresholds.
>
> Let's revisit in 6 months if we have grown 10× and those thresholds are approaching. Sound good?"

---

**Q30: The Geospatial Problem**

After 5 years of growth, your company serves 50 million users, with 16 database shards, 3 replicas each, distributed across 3 datacenters. Sharding is by user_id hash. The system works well for user-centric queries.

A product manager proposes a new feature: "Show me all users within 5 miles of my location." This requires finding users across all 50 million regardless of their user_id.

**Part A:** Why is this query fundamentally problematic for your current user_id-hashed sharding architecture? Be specific about what must happen to answer this query and how expensive it is.

**Part B:** Design an architecture that can answer this geospatial query efficiently without modifying your existing 16 shards. What new data store? What data model? How does it stay synchronized with your primary user data?

> **Discussion Notes:** Part A — "users within 5 miles" filters by latitude/longitude, not by user_id. With user_id hash sharding, there is no way to route this query to a specific shard — users in any geographic area are distributed across all 16 shards by random hash. To answer this query, you must scatter-gather all 16 shards, filtering every user row by location. At 50M users across 16 shards, each shard holds ~3M users. Scanning 3M rows per shard for latitude/longitude proximity = 16 parallel full scans. Even with a geospatial index within each shard, you are running 16 expensive index scans and merging the results. At high QPS, this is database-killing. Part B — add a dedicated geospatial store. Options: PostGIS (PostgreSQL with geospatial extensions), Elasticsearch with geo_point field type, or Redis with geospatial commands (GEORADIUS). Data model: store user_id + current_location (lat/lng). Queries go directly to the geospatial store — not the OLTP shards. Synchronization: when a user updates their location (or periodically for active users), write to both the OLTP shard (for their full profile) and the geospatial store (just user_id + location). The geospatial store is a lightweight secondary index for location-based queries only. Consistency: eventual — if the geospatial store is 60 seconds behind, showing someone who moved 5 miles away in your results is an acceptable error. The OLTP shards are never touched for geospatial queries.

---

# Homework Exercises — 10 Exercises

These exercises have specific numbers and require you to do real work. Do not treat them as discussion prompts. Work out the math, write the actual documents, and walk through the specific steps.

---

## Exercise 1: Build a Shard Key Decision Document

You are the Staff Engineer at a growing startup. Your five core tables: users (30 million rows), posts (500 million rows), comments (2 billion rows), likes (5 billion rows), user_follows (1 billion rows). Current measured bottleneck: write throughput on the likes table — users are liking posts fast enough that the single-node likes table is at 90% write capacity.

**Part A:** For each of the five tables, propose a shard key. Justify each choice by identifying the top 2 most common queries that table serves and showing that your shard key makes those queries single-shard (no scatter-gather). If your shard key makes a query multi-shard, acknowledge it and explain why that is an acceptable trade-off.

**Part B:** For the likes table — your specific bottleneck — do this calculation: 5 billion rows × 100 bytes per row = 500GB total. With 16 shards, how much data per shard? If likes are sharded by user_id and you query "all likes on post X," how many shards must you touch? What if likes are sharded by post_id instead? Which shard key fixes the bottleneck while also making "all likes on post X" efficient?

**Part C:** Your comments table has a hot post problem. When a post goes viral and gets 500,000 comments in a day, those comments are sharded by post_id — all 500,000 comments for that post land on one shard. Describe exactly what happens to that shard during the viral event. Design a mitigation strategy that does not require resharding. Consider: caching, write queuing, read replicas, or application-level changes.

**Part D:** Write a one-page technical decision document as if presenting to your engineering team. Include: the shard key decision for each table, the rationale, the trade-offs you accepted, and the monitoring you will put in place to detect if a shard key choice is causing problems.

*What to check in your answer: Part B math: 500GB / 16 shards = 31.25GB per shard. Sharding by user_id: "all likes on post X" requires all 16 shards (scatter-gather). Sharding by post_id: "all likes on post X" is a single shard. Post_id wins for the "all likes on post X" query but makes "all posts liked by User X" a scatter-gather. The write bottleneck is fixed regardless of which key you choose — either distributes writes across 16 shards.*

---

## Exercise 2: Replication Lag Debugging

Your monitoring system fires an alert at 3:15 PM: replica-3 has 4 minutes of replication lag. Normal lag is under 500ms. Lag has been growing for 20 minutes. Traffic appears normal.

**Part A:** List 5 possible root causes in order of likelihood for a replica that is consistently falling further behind. For each root cause, describe exactly one metric or command that would confirm it or rule it out. Be specific — name the actual query or monitoring panel.

**Part B:** Users are starting to notice stale data. What is your immediate mitigation action — not a fix, just a way to stop the bleeding right now — while you continue investigating? Write the specific routing rule change that reroutes users away from replica-3.

**Part C:** You discover the root cause: a `VACUUM FULL` command was run manually on replica-3 two hours ago. It is still running. While it runs, it holds a lock that prevents the replication stream from applying new writes. You cannot kill the VACUUM FULL without risking table corruption. How do you handle this? What are your options? What is the recovery order?

**Part D:** Write the runbook entry that your on-call rotation will follow the next time they see "replication lag > 2 minutes." Assume the person following the runbook does not know the history of your database. The runbook should be self-contained: what to check, in what order, what actions to take at each decision point, and what escalation path to follow.

*What to check in your answer: Part A — most likely causes in order: (1) A blocking lock on the replica (check `pg_stat_activity` for blocked processes), (2) A batch write spike on the leader exceeding replica capacity (check leader writes/sec history), (3) Disk IO saturation on replica-3 (check disk IO wait %), (4) Replication thread paused or errored (check replica status: `SELECT * FROM pg_stat_replication`), (5) Network issue between leader and replica-3 (check network throughput and packet loss). Part B: mark replica-3 as unhealthy in your load balancer or connection pool, stop routing reads to it immediately.*

---

## Exercise 3: Design a Resharding Plan

Current state: 8 shards, simple modulo hash (user_id % 8). Each shard has approximately 100 million rows. Total traffic: 50,000 writes per second, 200,000 reads per second. Users are distributed globally across 15 countries. Requirement: zero downtime — you cannot take the service offline at any point.

Goal: migrate to 16 shards.

**Part A:** Design the complete migration using a double-write strategy. Write each phase with: phase name, description of what is happening technically, estimated duration for this phase, and what monitoring confirms the phase completed successfully and safely.

**Part B:** During the double-write phase, all writes go to both old shards and new shards simultaneously. At 50,000 writes per second currently, what is the write load during double-write? Do your current servers handle this? Show your reasoning. If they cannot handle it, what do you do before starting the migration?

**Part C:** Define your rollback trigger conditions. At what specific metric values do you abort the migration and roll back? At what point in the migration process is rollback more expensive than completing the migration (the point of no return)? Design 3 automated checks — specific metrics with specific thresholds — that run continuously during migration and trigger automatic rollback.

**Part D:** This migration touches 5 different systems: database routing layer, application servers, monitoring dashboards, ops runbooks, and on-call training. For each system, identify who needs to be involved, what they need to do before the migration starts, and what they need to do during. Write a brief communication plan — who gets notified, when, and with what information.

*What to check in your answer: Part B — double-write doubles write load to 100,000 writes/second. At 8 shards (now receiving both old and new shard writes), each shard handles 12,500 writes/second instead of 6,250. If servers were at 80% capacity, doubling write load exceeds capacity. You should: scale up servers or add capacity before starting. Alternatively, throttle the migration speed — only copy data at a rate that keeps servers below 70% capacity. Part C — rollback triggers: (1) Error rate on new shards > 0.1%, (2) P99 latency on new shards > 2× old shard baseline, (3) Row count mismatch > 0.01% between old and new shards during verification.*

---

## Exercise 4: The Celebrity Hot Spot Problem

Your social network has 50 million users. The top 1,000 users each have over 10 million followers. You are sharded by user_id hash across 32 shards. You use push-based fan-out: when a user posts, their post_id is written to each follower's feed table immediately, creating one feed row per follower.

**Part A:** Celebrity user @star has exactly 50 million followers — every user on the platform follows them. @star posts once. How many write operations does this fan-out create? Those writes are writing to the feed tables of 50 million users — those users are distributed across all 32 shards. But the read traffic for @star's profile all hits which shard? Show the math on both write fan-out volume and read hot-spot.

**Part B:** Shortly after @star posts, the shard containing @star's profile hits 95% CPU. The other 31 shards are at 20% CPU. The high CPU causes queries to slow down. Your shard does not just contain @star — it contains approximately 1/32 of all users (about 1.56 million normal users). Describe the cascade failure: what do the 1.56 million normal users on that shard experience during the @star CPU spike? What operations fail first? What operations degrade but continue?

**Part C:** Design a hybrid fan-out system. For normal users (under 1 million followers), use push: their posts are written to follower feed tables immediately. For celebrities (1 million or more followers), use pull: feeds are assembled on request by fetching celebrity posts directly. Draw the data flow for both types. Write out the feed assembly logic: when User X opens their feed, what queries run? For each person X follows, is it a push lookup or a pull fetch?

**Part D:** User @rising_star currently has 800,000 followers (under the 1 million threshold, so they use push fan-out). They go viral over 48 hours and hit 2 million followers. How does the system detect that @rising_star has crossed the threshold? What happens to the existing pre-populated feed rows in followers' feed tables from when they were a push user? Design the transition process: how do you safely move @rising_star from push to pull without either losing feed data or duplicating posts in followers' feeds?

*What to check in your answer: Part A — 50 million writes for a single post. If you write at 100,000 writes/second, the fan-out takes 500 seconds — over 8 minutes. This is clearly not viable. The read hot-spot: @star's profile_id hashes to one specific shard. Every request to view @star's profile or posts hits that one shard, regardless of which of 32 shards that is. Part D — threshold detection: a background job runs every hour and checks follower counts. When @rising_star crosses 1M, the job adds them to the celebrity table. From that point forward, new posts go to the celebrity_posts table (pull model). Existing pushed feed rows stay in place — they represent older posts accurately. The feed assembly deduplicates by post_id.*

---

## Exercise 5: Cross-Shard Transaction Design

You are designing a wallet transfer feature for a fintech app. Two users can send money to each other. Each user has an account balance stored in the database, sharded by user_id. Source and destination accounts are on different shards approximately 50% of the time. Transfer must be atomic: either both balances update or neither does.

**Part A:** Design the complete Saga pattern for this transfer. Write out each step by name, what it does technically, and what the compensating transaction (rollback step) is if this step fails. At minimum: Saga step 1 is the debit. Saga step 2 is the credit. For each, write the compensating step. What does the state machine look like?

**Part B:** Your product team requires an idempotency key to prevent duplicate transfers — the mobile app has retry logic that might fire the same transfer twice if the network is slow. The idempotency key is a unique string tied to this specific transfer attempt. Where in your architecture is the idempotency key stored? Which database or shard? How does the system use it to detect and reject a duplicate?

**Part C:** Walk through this failure scenario step by step: the transfer succeeds (money successfully debited from source, successfully credited to destination), the database confirms both operations, but the application server crashes before returning the "success" response to the user. The user's mobile app times out and retries the transfer. Walk through exactly what happens with and without idempotency keys.

**Part D:** Your legal team requires an immutable audit log of every transfer. The audit log lives in a separate compliance system that is not sharded the same way as the wallet database. The compliance system is occasionally unavailable for up to 5 minutes at a time. Design an eventual consistency approach to ensuring that every successful transfer is eventually recorded in the audit log, even if the audit system is temporarily down during the transfer. How do you guarantee no transfers are ever missing from the audit log?

*What to check in your answer: Part C without idempotency — the retry creates a second debit and second credit. User loses double the money. Catastrophic. With idempotency — the retry sends the same idempotency key. Server checks: has this key been processed? Yes. Returns the cached success response. No second debit, no second credit. Part D — outbox pattern: when a transfer completes, write a record to a `pending_audit_events` table in the same transaction as the wallet update. A background job reads from `pending_audit_events` and sends records to the compliance system. On success: delete from `pending_audit_events`. On failure: leave it, retry in 5 minutes. The pending_audit_events table acts as a durable buffer. No transfer ever misses the audit log because the audit event is written atomically with the transfer.*

---

## Exercise 6: Designing for Regulatory Compliance

Your application serves users globally. GDPR requires: all EU user data must physically reside in EU infrastructure. Right to erasure: delete all of a user's data within 30 days of a deletion request. Data portability: export all of a user's data in machine-readable format within 72 hours of a request.

**Part A:** Design a geo-partitioned database architecture with separate data stores for EU, US, and Asia regions. For each region: what infrastructure, what data resides there. Critically: how does your application routing layer know which region a given user's data lives in? Where is that mapping stored?

**Part B:** EU user Elena submits an account deletion request. Her data is spread across: users shard (EU), posts shard (EU), comments shard (EU), and the likes table (also EU). Additionally, other users may have liked her posts or replied to her comments — that data lives in other users' shards. Design the deletion process: what is the order of operations, how do you handle data that references Elena but lives in other users' records, and how do you generate a verifiable confirmation that deletion is complete?

**Part C:** Asia user Ravi is traveling in Germany and posts a photo while connected to German Wi-Fi. His account is registered to India. His post was created while physically in Germany. Is this post subject to GDPR? Where should the post's data be stored?

**Part D:** Your backup system takes nightly full database backups. Backups are encrypted and stored for 30 days for disaster recovery purposes. User Elena requests deletion. You delete her records from all live production databases. But her data exists in 30 days of backup files. How do you handle this? Describe at least two approaches. Which approach do you choose and why?

*What to check in your answer: Part A routing — store user_id → region mapping in a lightweight global directory (small Redis cluster or distributed key-value store). This mapping is read on every request but rarely written (only when a user is created or explicitly migrates region). Part C — GDPR applies to EU residents, not to everyone physically in the EU. Ravi is an India resident traveling. His post is not automatically subject to GDPR. Store it in the Asia region as usual. Part D — two approaches: (1) Pseudonymization: replace all EU user's personally identifiable information in backups with a random token. The backup still contains transaction records, but the user cannot be identified. GDPR considers this compliant if the mapping between token and identity is also deleted. (2) Accept the backup risk with a documented policy: backups are encrypted, access-controlled, and will naturally expire within 30 days. GDPR allows for "reasonable technical and organizational measures" — a 30-day backup expiry window is commonly accepted. Approach 2 is simpler and widely practiced.*

---

## Exercise 7: Interview Dry Run

Set a timer for exactly 35 minutes. Design the storage architecture for Twitter — specifically focused on three components: the tweets table, the follow relationships, and the home timeline feed.

Scale parameters: 10,000 new tweets per second, 500,000 tweet reads per second, 300 billion total tweets in history, 500 million users, each user follows an average of 300 others.

**Minutes 0–5:** Ask and answer clarifying questions. Write them down on paper as if asking an interviewer. Consider: consistency requirements (does a tweet need to be immediately visible to all followers?), availability requirements (what is the SLA?), geographic distribution, and which features are in scope. These questions should meaningfully change your design choices.

**Minutes 5–15:** Design the tweets table sharding. Work through: shard key choice and justification, capacity math (how many shards? how much data per shard?), write distribution (are writes even or is there a hot spot?), and what happens when a shard fails.

**Minutes 15–25:** Design the follow relationships table. Questions to answer: where do you store "user X follows user Y"? What shard key? How do you efficiently answer "give me all followers of user X" (used for fan-out on post) and "give me all accounts user X follows" (used for feed assembly)?

**Minutes 25–35:** Design the home timeline — the personalized feed of tweets from people you follow. Push fan-out versus pull fan-out versus hybrid. For each approach: what writes happen when a tweet is posted, what reads happen when a user opens their app, and what is the latency profile.

After the timer: spend 10 minutes in self-critique. Write down: one architectural decision you would make differently now, one assumption you made early that you should have questioned explicitly, and specifically how you handled (or failed to handle) the celebrity accounts problem.

*Capacity math hints: 300 billion tweets × 500 bytes each = 150TB total. At 32 shards: ~5TB per shard. At 10,000 tweets/sec across 32 shards: 312 writes/sec per shard. Manageable. Follow relationships: 500M users × 300 follows each = 150 billion rows in the follows table. At 100 bytes per row: 15TB. Shard follows by follower_id (the person who is following) — this makes "who does User X follow?" a single-shard query. Getting all followers of a celebrity is still expensive — it requires the celebrity's data from one shard but then fanning out to 100M+ follower records distributed across all shards.*

---

## Exercise 8: Cost Analysis

Your company is choosing between two database architectures:

**Option A:** 1 large dedicated server ($5,000/month) with a hot standby in the same datacenter ($5,000/month for failover). Total: $10,000/month. Failover time if leader fails: 1–5 minutes.

**Option B:** 8 shards with 3 replicas each = 24 medium servers. Each server costs $500/month. Total: $12,000/month. If one server fails, that shard's replicas handle the traffic. Failover to a replica: 30 seconds.

**Part A:** Option A has limits. What specific metrics — write QPS, dataset size, read QPS — would make Option A insufficient regardless of cost? Show the rough calculations. At what scale does Option A become the bottleneck, not a cost question?

**Part B:** Option A has a single shard. When the leader fails: 100% of users are affected for the failover duration. Option B has 8 shards. When one leader fails: what percentage of users are affected? For how long? Compare the expected user-minutes of outage per failure event for each option.

**Part C:** Your product requires 99.99% annual uptime (less than 53 minutes of downtime per year). Calculate expected annual downtime for both options. Assume: servers fail approximately once per 18 months on average (MTBF = 18 months). For Option A: one failure = 1–5 minutes down (100% of users). For Option B: one failure = 30 seconds down for 12.5% of users. Which option meets the 99.99% SLO? Show your work.

**Part D:** There is an Option C: AWS RDS Multi-AZ with Read Replicas — a fully managed database service at $8,000/month. Compare Option C against A and B on four dimensions: operational overhead (engineer-hours per month to maintain), automated failover time, horizontal scaling flexibility, and 3-year total cost of ownership including estimated engineering time at $200/hour.

*What to check in your answer: Part C math: Option A — 1 failure per 18 months = 0.67 failures/year. Each failure = 3 minutes average = 3 minutes downtime/year × 0.67 = 2 minutes. Well within 53-minute SLO. But wait — is the hot standby in the same datacenter? If the whole datacenter fails, you have zero redundancy. The 99.99% calculation only holds if failures are independent hardware failures, not datacenter-level events. Option B — 24 servers, each fails once per 18 months = 1.33 failures/month across all servers. Each failure = 30 seconds × 12.5% of users = 3.75 user-seconds of downtime per failure. Per year: 16 failures × 30 seconds × 12.5% = 60 seconds of equivalent downtime. Meets 99.99% comfortably. Option B is more resilient.*

---

## Exercise 9: Monitoring Dashboard Design

You are building the monitoring and alerting system for your production database. The system has 16 shards. Each shard has 1 leader and 3 replicas. Total: 64 database instances. Traffic: 50,000 writes per second, 400,000 reads per second.

**Part A:** List 10 metrics you would track at the shard level or instance level. For each metric, specify: the metric name, what it measures, the warning threshold (alert the team during business hours), and the critical threshold (page the on-call engineer immediately regardless of time of day). Justify the thresholds — why those specific numbers?

**Part B:** Design a composite "shard health score" from 0 to 100. The score should incorporate: CPU utilization of the leader, average replication lag across the 3 replicas, p99 query latency, and disk usage percentage. Write out the formula or weighting logic. A healthy shard should score above 80. A shard that needs immediate attention should score below 40. What specific conditions would result in a score of 0 (critical emergency) versus 60 (degraded but operational)?

**Part C:** Sketch the layout of a monitoring dashboard for this system. Describe what appears in the top row (highest priority information, seen first), the second row (important but not immediately alarming), and the detail panels (drill-down when investigating). For each panel, specify: what it shows, what time range it displays, and why it is in its position on the dashboard.

**Part D:** It is 3 AM. You receive a page: "Shard 7 health score dropped to 18 (critical)." You have never seen this shard before. Write the first 10 steps of your incident response runbook in exact order, with the specific command or panel to check at each step, and the decision tree: what you do if the check reveals X versus if it reveals Y.

*What to check in your answer: Part A — 10 metrics: (1) Leader CPU (warn >70%, page >90%), (2) Replica replication lag in seconds (warn >5s, page >30s), (3) Disk usage % (warn >80%, page >90%), (4) Query latency p99 ms (warn >500ms, page >2000ms), (5) Active connections vs max connections (warn >80% of max, page >95%), (6) Writes per second per shard (warn >2× baseline, page >5×), (7) Reads per second per shard (warn >2× baseline, page >5×), (8) Replication thread running (binary — page immediately if stopped), (9) Failed query rate (warn >0.1%, page >1%), (10) Lock wait time average (warn >100ms, page >1000ms). Part B health score formula example: CPU score = max(0, 100 - (CPU_pct - 50) × 2) if CPU > 50%, else 100. Replication score = 100 if lag < 1s, 80 if lag < 5s, 40 if lag < 30s, 0 if lag > 30s. Latency score = max(0, 100 - (p99_ms / 10)). Disk score = max(0, (100 - disk_pct) × 1.2). Health = average of four scores.*

---

## Exercise 10: Scale From 0 to 1 Billion Users

Design the evolution of a food delivery app's database — similar to DoorDash — from its first day to 1 billion users. The app has four core entities: Users, Restaurants, Orders, and Deliveries.

At each stage: describe the architecture, identify what specific metric is about to break, explain the minimum change required, and note one decision made at this stage that you would do differently with hindsight.

---

**Stage 1: 0 to 10,000 users**

Architecture: single PostgreSQL instance on a cloud VM. All four tables live together. No replication. No cache. Total data: maybe 10MB. Daily orders: a few hundred.

What to avoid: do not shard preemptively. Do not add microservices. Ship the product. The database is bored — it is handling trivial load. The business risk (product failing) is 1000× higher than the technical risk (database failing).

Hindsight note: index your database from day one on the columns you query most — user_id, restaurant_id, created_at. Adding indexes to a large table later is painful; adding them to a tiny table is free.

---

**Stage 2: 10,000 to 100,000 users**

What breaks: your database has no redundancy. If it fails, the app is down until you restore from backup — potentially hours. At this stage, a single hardware failure causes a real outage.

Minimum change: add a read replica. Not for performance — for availability. The replica can serve as a hot standby. If the leader fails, you manually promote the replica in under 15 minutes. This is not automated failover but it is far better than restoring from backup.

Metric that forces this change: zero replicas = zero redundancy. The forcing function is business risk, not performance metrics.

Hindsight note: set up automated backups and practice restoring from them before you have a real emergency.

---

**Stage 3: 100,000 to 1,000,000 users**

What breaks: at 1M users with typical food delivery ordering patterns (5% of users ordering on any given day, concentrated in meal windows), you might see 50,000 order reads per hour during dinner time — about 14 reads per second. Your database handles this fine. But the orders table is growing: maybe 100K orders per day = 36M orders per year. At 2KB per order: 72GB in year one. Starting to feel substantial.

Real bottleneck at this stage: slow queries. The orders table is large enough that unindexed queries start taking seconds. Full table scans become painful.

Minimum change: query optimization and index tuning. Identify the 5 slowest queries via the slow query log. Add composite indexes for the most common access patterns. This is free (no new hardware) and typically buys another year of runway.

If that is not enough: upgrade to a larger instance (more RAM = larger buffer pool = more data stays in memory, fewer disk reads).

Hindsight note: set up query performance monitoring early. The slow query log is your best friend at this stage.

---

**Stage 4: 1,000,000 to 10,000,000 users**

Running the numbers: 10M users. If 5% order per day, that is 500K orders per day = 5.8 orders per second average, with dinner peaks 5–10× higher = 30–60 orders per second. The orders table now has perhaps 500M rows (several years of history). At 2KB each: 1TB of order data.

What must be sharded now: the orders table. Write throughput is becoming the bottleneck: 60 orders per second is approaching the limit for a single-node write path, and the table is too large for a single machine to handle efficiently.

Shard key for orders: user_id. Most queries are "show me my orders" — user-centric. Co-locating with the user table is ideal.

What does not need sharding yet: Users (still manageable at 10M rows), Restaurants (small table), Deliveries (can be sharded at this stage too if needed).

Hindsight note: pick the shard key by access pattern, not by what feels natural. user_id for orders feels less natural than order_id but it is the right choice.

---

**Stage 5: 10,000,000 to 100,000,000 users**

The monolith database is straining under four completely different workloads: Restaurants (read-heavy, rarely written, ideal for aggressive caching), Users (moderate reads and writes, standard profile access), Orders (high write throughput, large dataset), Deliveries (extremely high write frequency — location updates every 10 seconds per active delivery).

At 1M concurrent active deliveries, location updates = 100K writes per second. PostgreSQL cannot handle 100K writes per second on one machine. And these writes are tiny (just lat/lng coordinates) — they are better served by a specialized store.

Functional decomposition: Deliveries get their own store (time-series or key-value, optimized for high-frequency small writes). Restaurants get their own read-optimized database with heavy caching (Redis in front, database behind for rare updates). Users and Orders remain on the main PostgreSQL cluster (sharded).

This is the microservices inflection point — driven by technical requirements, not organizational preferences.

Hindsight note: when you decompose, define the service boundaries by data access pattern, not by team structure. Data that is always written and read together belongs in the same service.

---

**Stage 6: 100,000,000 to 1,000,000,000 users**

The full architecture at 1 billion users looks nothing like the single PostgreSQL from Stage 1. It is a collection of specialized systems, each optimized for its specific workload:

User database: sharded by user_id, 32 shards, 3 replicas each, across 3 geographic regions. Celebrity users cached in Redis. Authentication state in a separate fast key-value store.

Order database: sharded by user_id, 64 shards, 3 replicas each. A separate analytics replica feeds a data warehouse (BigQuery or Snowflake) for business intelligence queries. Orders older than 2 years archived to cold storage.

Restaurant database: single globally replicated database (restaurants are few enough — even 1 million restaurants is a small dataset). Heavily cached at CDN edge for menu reads. Writes are rare.

Delivery tracking: Cassandra or InfluxDB cluster, sharded by delivery_id, 90-day hot retention, then archival. Designed for 1 million concurrent write streams.

Search: Elasticsearch cluster for restaurant search by cuisine, location, name, rating. Separate from all transactional databases.

Cache layer: Redis clusters in each geographic region for session data, hot user profiles, current delivery status, and restaurant menu data.

Message queue: Kafka connecting all services for event propagation (order created → notification → driver assignment → delivery tracking).

Consistency model per feature: order creation requires strong consistency (no duplicate orders, no lost money). Delivery location updates require eventual consistency (5-second staleness is fine for ETA estimates). Restaurant menu display requires eventual consistency (60-second TTL on cache is acceptable).

Total infrastructure: approximately 300 database instances across all stores, 5+ distinct database technologies, 3 geographic regions, with automated failover and health checks everywhere.

---

# Quick Reference Card

Cut this out (metaphorically) and review it the night before your interview.

---

## Replication Cheat Sheet

| Model | Write Target | Read Target | Best For | Key Risk |
|---|---|---|---|---|
| Leader-follower, async | Leader only | Any replica | 90% of web applications | Replication lag; rare data loss if leader crashes before replication |
| Leader-follower, sync | Leader only | Any (lag = 0) | Financial data, critical state | Higher write latency — waits for at least one replica to confirm |
| Semi-synchronous | Leader only | Any replica | Balance between async and sync | At least 1 replica guaranteed; others may still lag |
| Multi-leader | Any leader | Any leader | Multi-region writes, offline-first apps | Conflicts require resolution logic; complex to reason about |
| Leaderless (Dynamo-style) | Quorum W of N nodes | Quorum R of N nodes | Maximum availability, no single leader | More complex; tunable consistency with trade-offs |

---

## Sharding Strategy Cheat Sheet

| Strategy | How It Works | Best For | Worst For |
|---|---|---|---|
| Hash sharding | hash(shard_key) % N → shard number | Even write distribution, point lookups by shard key | Range queries (must scatter-gather); painful to reshard with naive modulo |
| Range sharding | key range → shard (e.g. A–M on shard 1) | Range queries, time-series queries, easy data rotation | Hot spots — all recent data hits one shard |
| Directory sharding | lookup table maps key → shard | VIP tenants, flexible placement, special-case routing | Directory service is a potential single point of failure |
| Consistent hashing | Keys mapped to a hash ring; shards own arcs of the ring | Dynamic scaling — adding a shard moves only ~1/N of data | More complex to implement and reason about than modulo hash |

---

## Shard Key Decision: Quick Guide

Your shard key is your most common query. Answer this single question: "What is the first piece of information I have when I need to find this data?"

- If you usually look up data by user_id → shard by user_id
- If you usually look up data by conversation_id → shard by conversation_id
- If you usually look up by tenant/company → shard by tenant_id (watch for large-tenant hot spots)
- If you usually look up by timestamp → shard by something else (timestamp = guaranteed hot spot on current time window)

**The co-location rule:** if two tables are almost always queried together, use the same shard key for both. Shard orders by user_id (not order_id) so that "all orders for user X" is always a single-shard query. Shard post_likes by post_id (not user_id) so that "all likes on post X" is always a single-shard query. Choose based on which query runs more often.

---

## Key Interview Numbers — Reference Table

| Metric | Typical Ballpark Value |
|---|---|
| Read replica capacity | 10,000–50,000 QPS per replica (depends on query complexity) |
| Replication lag, healthy | Under 100ms within same datacenter |
| Replication lag, warning threshold | Over 5 seconds — investigate |
| Replication lag, critical threshold | Over 30 seconds — immediate action, route reads to leader |
| Leader failover time, automated | 30 seconds to 5 minutes |
| Shard hot spot alert | Over 3× average shard load |
| Resharding timeline, live system | 2–4 months minimum safely |
| Consistent hashing, add 1 shard | Approximately 1/N of total data moves |
| Naive modulo reshard (4 → 5 shards) | Approximately 75–80% of data moves |
| Logical shards per physical node | 4–16 (allows gradual rebalancing without full data movement) |
| Typical web app read/write ratio | 80:20 to 95:5 reads to writes |
| Cost of wrong shard key discovery | 2–4 months to fix via resharding |
| Sharding engineering cost | 3–6 months of migration work for a mature system |

---

## The 5-Minute Mental Model

When someone asks you about database scaling in an interview, run this sequence before you speak:

**Step 1: What is the actual bottleneck?**
Do not propose solutions before you have diagnosed the problem. Ask or state specific numbers: read QPS, write QPS, dataset size. Is the bottleneck reads, writes, or storage? Name it explicitly.

**Step 2: If reads are the bottleneck → add replicas.**
Read replicas are fast to add, simple to operate, and solve the majority of database scaling problems for most web applications. They do not fix write bottlenecks — at all.

**Step 3: If writes or storage are the bottleneck → consider sharding.**
But first: can you batch writes? Use write-behind caching? Vertically scale to a larger machine? These are 10× cheaper than sharding. Try them first. Sharding is the last resort.

**Step 4: If sharding is necessary → choose the shard key carefully.**
Shard key = your primary access pattern. What do you know first when you need to fetch this data? Shard by that. Make sure related data that is always queried together uses the same shard key.

**Step 5: Plan for resharding from day one.**
Use consistent hashing or logical shards. Never use naive modulo hashing — you will regret it the day you need to add one more shard to a live production system.

**Step 6: Name the trade-offs of your solution explicitly.**
Every choice has a cost. Read replicas introduce replication lag. Sharding makes cross-shard queries expensive. Multi-leader means conflicts. Say the trade-off out loud. This is what L6 thinking looks like.

---

## The L6 One-Sentence Principle

Before you choose any solution, say this out loud: **"What specifically is broken, and what is the cheapest thing that fixes it?"**

The cheapest fix — better indexes, caching, vertical scale, query optimization — is almost always the right first answer. Sharding is almost always the last answer.

---

## Before and After: Rewriting L5 Answers as L6

This section takes six common interview moments and shows the L5 answer versus the L6 answer side by side. The goal is to make the difference viscerally clear, not just abstractly described.

---

### Scenario 1: "How would you handle the database as Instagram scales to 100 million users?"

**L5 Answer:**
"I would use a combination of read replicas for read traffic and shard the database by user_id for write traffic. This way reads are handled by replicas and writes are distributed across shards evenly."

**L6 Answer:**
"Before I answer, I want to understand the actual bottleneck at 100 million users. Instagram's traffic is overwhelmingly read-heavy — people scroll feeds and view profiles far more than they post. Let me estimate: if each of 100 million users views 10 profiles per day, that is 1 billion profile reads per day — about 11,600 reads per second. If each user posts once per day on average, that is 1,160 writes per second. That is a roughly 10:1 read/write ratio. The bottleneck is clearly reads, not writes. So the first move is read replicas, not sharding. At 11,600 reads per second, even 3 replicas at 50,000 QPS each gives us 150,000 QPS of read capacity — more than 10× what we need. Sharding would be premature. I would hold off on sharding until write QPS actually becomes the constraint, which at these numbers might be 2–3 years away."

**What changed:** L5 applied the pattern reflexively. L6 diagnosed first (read-heavy, not write-heavy), ran the math (actual QPS vs. capacity), and concluded the simpler solution (replicas) is sufficient. L6 explicitly said sharding would be premature.

---

### Scenario 2: "Your database is at 80% CPU. What do you do?"

**L5 Answer:**
"I would add read replicas to distribute the load across more database instances."

**L6 Answer:**
"I would not add replicas yet — I want to understand what is causing the 80% CPU before I throw hardware at it. Read replicas only help if the CPU is high because of read volume. If the CPU is high because of 3 slow, unindexed queries that each do full table scans, adding replicas means each replica also runs those slow queries — the problem scales with the hardware, not away from it. My first step: check the slow query log. What are the 5 most CPU-expensive queries right now? Can any of them be fixed with an index? I have seen cases where one missing index was responsible for 60% of database CPU. That is a 10-minute fix versus a multi-week replica deployment. I would spend 2 hours on query analysis before deploying any new infrastructure."

**What changed:** L5 matched "high CPU" to "add replicas." L6 asked why the CPU is high, identified that the solution depends on the root cause, and proposed a diagnostic step before any infrastructure change.

---

### Scenario 3: "How would you shard a payment database?"

**L5 Answer:**
"I would shard by account_id using hash sharding. This distributes data evenly across shards and ensures each payment lookup can go to exactly one shard."

**L6 Answer:**
"Before choosing a shard key, I need to think through the consistency requirements for payments, because that constrains the architecture more than the distribution does. A payment involves two accounts — debit one, credit the other. If those two accounts are on different shards, I have a distributed transaction. Distributed transactions are hard to get right: if the network times out between the debit and credit steps, money is in limbo. So the first question is: how often are source and destination accounts on the same shard? With hash(account_id) % N sharding, two random accounts land on the same shard only 1/N of the time — so about 12.5% of the time with 8 shards. The other 87.5% of transfers are cross-shard. I need a robust saga pattern with idempotency keys for all of those. That is significant complexity. I would also look at whether there is a natural grouping that reduces cross-shard transactions — for example, if this is a consumer app, most transfers happen between people who know each other. If we could shard by social graph clusters, more transfers would be intra-shard. But that is complex to implement. Realistically for a payment database, hash(account_id) is the right shard key, with a well-designed saga pattern for cross-shard transactions."

**What changed:** L5 gave a textbook answer. L6 surfaced the real complexity — distributed transactions — analyzed how often they would occur, discussed the operational implication, and then concluded the same shard key is correct but with explicit acknowledgment of the saga requirement.

---

### Scenario 4: "What would you do if replication lag spikes to 30 seconds?"

**L5 Answer:**
"I would investigate the replicas to find what is causing the lag and fix the underlying issue."

**L6 Answer:**
"Two simultaneous actions, not sequential. While I am investigating, I am also stopping the bleeding. Immediate action: route all critical reads to the leader. At 30-second lag, users are seeing data that is 30 seconds stale. For a social feed that is usually acceptable, but for user settings, password changes, payment status, or session management — that is dangerous. I would immediately update the read routing to send critical operations to the leader. This increases leader load but prevents data consistency issues. Now for investigation: the 30-second lag symptom has about 4–5 likely root causes. I am checking: is it a write spike on the leader (check write QPS history for the last hour), is there a blocking operation on the replica (check pg_stat_activity for long-running queries or VACUUM operations), is the replica's disk IO saturated (check IO wait percentage), did the replica recently restart and is catching up (check uptime), or is there a network issue between leader and replica (check network throughput). I would run through these in order. Usually one of the first two is the cause."

**What changed:** L5 said "investigate." L6 named the two parallel tracks (immediate mitigation + root cause investigation), gave the exact immediate action, and listed the specific diagnostic steps in order of likelihood.

---

### Scenario 5: "You need to store 10TB of user data. How do you shard it?"

**L5 Answer:**
"I would use hash sharding with 10 shards, giving about 1TB per shard. This distributes data evenly."

**L6 Answer:**
"10TB total storage does not automatically mean I need sharding. Let me think about whether the problem is storage or throughput. A modern server with 32 1TB SSDs can handle 32TB of storage on one machine. So 10TB fits on a single machine with room to grow. The question is whether write throughput or read throughput is the actual bottleneck. If this is a read-heavy workload (say 90% reads), I could serve 10TB from a single primary with 5 read replicas — that is 6 database instances, cheap and simple. If write throughput is the bottleneck — say we have 100,000 writes per second — then one machine cannot keep up regardless of storage capacity, and sharding is necessary. So before I decide on 10 shards, I want to know: what is the write QPS? What is the read QPS? How is this data accessed — by primary key (fast), by range queries (potentially expensive across shards), or by full-text search (needs a separate index)? The 10TB number is almost irrelevant without the access pattern and throughput requirements."

**What changed:** L5 treated "10TB" as the signal to shard. L6 correctly identified that storage size does not determine whether you need sharding — throughput does — and asked for the actual requirements.

---

### Scenario 6: "The database is slow during peak hours. How do you fix it?"

**L5 Answer:**
"I would scale up the database server or add more read replicas to handle the peak load."

**L6 Answer:**
"Peak-hour slowness is usually one of three things. First — connection pool exhaustion. At peak, your application servers are all trying to open database connections simultaneously, and you hit the max connection limit. Queries queue up and time out. This looks like slowness but is actually a concurrency problem. Fix: connection pooling (PgBouncer) between application and database — this multiplexes many application connections over a small number of actual database connections. Second — lock contention. Peak hours might coincide with a scheduled batch job — a report generation, a data cleanup, a re-indexing — that holds locks and blocks concurrent operations. Fix: move batch jobs to off-peak hours, or use non-blocking index creation. Third — genuine throughput saturation — the database actually cannot process that many queries per second at this hardware level. Only in this case do you need more replicas or a hardware upgrade. I would rule out the first two causes first because they are free to fix, while the third requires infrastructure investment."

**What changed:** L5 jumped to the infrastructure solution. L6 identified that peak slowness has multiple root causes with different costs, and proposed diagnosing the cheap-to-fix causes first.

---

## Vocabulary Glossary

These are the exact terms interviewers use when asking about replication and sharding. Know them precisely.

---

**Replication lag** — the delay between when a write lands on the leader and when it appears on a replica. Measured in milliseconds (healthy) to seconds (concerning) to minutes (critical).

**Read replica** — a copy of a database that receives the same writes as the primary via replication, but is used exclusively for read queries. Does not help with write throughput.

**Leader election** — the process by which a cluster of database nodes selects one node to be the new leader after the current leader becomes unavailable. Requires consensus — majority agreement.

**Fencing token** — a monotonically increasing number associated with each leader term. Any write carrying an old fencing token is rejected by the storage layer, preventing stale leaders from corrupting data after they have been replaced.

**Split-brain** — a state where two nodes in a cluster both believe they are the leader simultaneously. Results in diverging data. Prevented by quorum-based elections and fencing tokens.

**Shard key** — the field (or combination of fields) used to determine which physical shard stores a given record. Once chosen, extremely expensive to change. Determines which queries are efficient and which are not.

**Hash sharding** — a sharding strategy where hash(shard_key) modulo N determines the shard number. Distributes data evenly but makes range queries expensive.

**Range sharding** — a sharding strategy where records are assigned to shards based on key ranges (e.g., user IDs 1–1,000,000 on shard 1). Makes range queries efficient but creates hot spots for recent data.

**Consistent hashing** — a hashing scheme that arranges shard keys on a virtual ring. Adding or removing a shard only moves approximately 1/N of data rather than nearly all of it as with naive modulo hashing.

**Hot spot** — a shard receiving disproportionately high traffic relative to other shards. Caused by either data skew (more records on that shard) or access skew (more requests for data on that shard).

**Scatter-gather** — a query execution pattern where a request is broadcast to all shards, each shard searches for matching records, and results are assembled in the application layer. Expensive at high shard counts.

**Fan-out** — the process of distributing a write to many downstream targets. Push fan-out: write to all follower feeds on post creation. Pull fan-out: assemble the feed on request.

**Saga pattern** — a design pattern for distributed transactions. Instead of a single atomic transaction across services, a saga is a sequence of local transactions with compensating transactions (rollbacks) for each step.

**Idempotency key** — a unique identifier attached to a request that allows the server to detect and safely ignore duplicate requests. Used to make retries safe in distributed systems.

**Compensating transaction** — a transaction that reverses the effect of a previous transaction when a multi-step operation needs to be rolled back. Example: if Step 2 of a payment saga fails, the compensating transaction for Step 1 refunds the debit.

**Write-behind caching** — a caching pattern where writes are immediately acknowledged and stored in cache, with the database update happening asynchronously in the background. Reduces write latency at the cost of durability risk.

**Read-your-writes consistency** — a consistency guarantee that ensures a client always sees the effects of its own previous writes, even if those writes have not yet propagated to all replicas.

**Quorum** — in a distributed system with N nodes, a quorum is a majority: floor(N/2) + 1 nodes. A write is "durable" if acknowledged by a quorum. A read is "consistent" if it queries a quorum. This prevents split-brain.

**Logical shard** — a virtual shard that maps to a physical database node. One physical node can host multiple logical shards. When you add a physical node, you move some logical shards to it — no data re-hashing required.

**Resharding** — the process of moving from one shard configuration to another. For example, from 8 shards to 16 shards. Requires live data migration, typically takes 2–4 months safely.

**Double-write phase** — a stage in a live database migration where writes are sent to both the old database structure and the new one simultaneously. This ensures the new system is caught up before the old one is decommissioned.

**Backfill** — in a migration context, the process of copying historical data from the old system to the new one. Happens alongside live traffic and must be designed not to overload either system.

**Directory service** — a routing component that maintains a lookup table mapping shard keys to shard locations. Provides maximum flexibility for shard placement at the cost of a potential single point of failure if not cached properly.

**Replication factor** — the total number of copies of data maintained in a replicated system. A replication factor of 3 means one leader copy and two replica copies.

**WAL (Write-Ahead Log)** — the mechanism used by most relational databases for replication. Every write is first written to an append-only log. Replicas replay this log to stay in sync with the leader.

**Eventual consistency** — a consistency model where, given no new writes, all replicas will eventually converge to the same state. Does not specify how long "eventually" takes.

**Strong consistency** — a consistency model where every read reflects the most recent write. Typically requires reading from the leader or from a quorum.

**Causal consistency** — a consistency model that preserves cause-and-effect ordering. If Event A caused Event B, any observer who sees B must also have seen A first.

---

## The "Scale This System" Decision Tree

When an interviewer asks "how would you scale this database?" use this decision tree to structure your answer:

```
START: What is the current bottleneck?
    │
    ├── "We have not measured yet" → Ask: current QPS, dataset size, read/write ratio
    │
    ├── HIGH READ LOAD (reads >> writes, read replicas overwhelmed)
    │       │
    │       ├── Is a cache layer in place? → No → Add Redis/Memcached FIRST
    │       │                                         (handles 80%+ of reads)
    │       │
    │       └── Cache not sufficient? → Add read replicas (2-5 usually enough)
    │
    ├── HIGH WRITE LOAD (writes approaching single-node capacity)
    │       │
    │       ├── Can writes be batched or buffered? → Yes → Use write-behind cache
    │       │
    │       ├── Can vertical scale buy time? → Yes → Upgrade machine first
    │       │
    │       └── None of the above? → Shard the database
    │                                   → Choose shard key based on access pattern
    │                                   → Plan migration (2-4 months)
    │
    ├── HIGH STORAGE (dataset too large for one machine)
    │       │
    │       ├── Is read/write QPS actually high? → No → Just add disk/larger machine
    │       │
    │       └── QPS also high? → Shard (solves both storage and throughput)
    │
    └── SLOW QUERIES (CPU high, response times degraded)
            │
            ├── Run slow query log analysis → Are 3-5 queries responsible?
            │       → Yes → Add indexes, rewrite queries → DONE
            │
            ├── Lock contention? → Move batch jobs to off-peak hours
            │
            └── Genuine throughput saturation? → Then consider replicas or sharding
```

This tree encodes the L6 principle: cheaper, simpler solutions first. Sharding appears at the bottom — after everything else has been considered.

---

# Part 7: Interview Flow Walkthrough — Minute by Minute

This section walks you through an entire 45-minute system design interview specifically focused on "Design a URL Shortener." The candidate's goal is to score at L6 on the database scaling portion. Read through this as if watching someone think out loud.

---

## The Setup

**Interviewer:** "Design a URL shortener like bit.ly. We want to handle 1 billion URLs shortened per day."

Before speaking, the candidate takes 30 seconds to mentally frame the problem:
- Write operation: user submits long URL, gets back short code
- Read operation: user visits short URL, gets redirected to long URL
- Read/write ratio: almost certainly 100:1 or higher — URLs are shortened once, visited many times

---

## Minutes 0–5: Clarifying Questions

**Candidate:** "Before I design anything, I want to make sure I understand the access patterns. A few questions:

First — when you say 1 billion URLs shortened per day, what is the expected read volume? I am guessing that each URL gets visited multiple times on average?

Second — do we need analytics? Can I see click counts and referrer data for each shortened URL?

Third — what is the latency requirement for the redirect? Is 100ms acceptable, or is this more like 20ms?

Fourth — is there a geographic dimension? Do global users need low latency everywhere, or is this primarily one region?

Fifth — what is the storage requirement? How long do URLs live — forever, or do they expire?"

**Interviewer:** "Great questions. Reads are roughly 100:1 over writes — so about 100 billion redirects per day. Analytics yes, but basic — just click count. Redirect latency ideally under 50ms. Global. URLs live indefinitely."

**Candidate (thinking out loud):** "Okay. 100 billion reads per day = 1.16 million reads per second. 1 billion writes per day = 11,574 writes per second. This is very read-heavy. That immediately tells me: read replicas and caching will be the primary scaling mechanism. Sharding may be needed for writes but let me see."

---

## Minutes 5–15: Core Data Model

**Candidate:** "The core data model is simple: a urls table with columns — short_code (the 6-character identifier), long_url (the destination), created_at, click_count.

Let me estimate dataset size. 1 billion new URLs per day × 365 days × 5 years = 1.825 trillion URLs. Even at 200 bytes per URL record: 1.825 trillion × 200 bytes = 365 TB. That is a lot. We definitely cannot serve 365TB from a single machine's memory.

The read pattern is: look up long_url by short_code. Single key lookup — very amenable to sharding and caching.

The write pattern is: insert new URL record. 11,574 writes per second — significant but not extreme."

---

## Minutes 15–25: Database Scaling Design

**Candidate:** "Now for the database scaling question. Let me think about the bottleneck.

For reads: 1.16 million reads per second. A single database replica handles maybe 50,000 QPS for simple key lookups. To handle 1.16M QPS from the database layer alone, I would need roughly 24 replicas. That is expensive and complex.

But wait — do I actually need the database to handle 1.16M QPS? Most URL lookups are for recently created or popular URLs. A cache can absorb the vast majority of these. If I put a Redis cache in front of the database with the short_code as the cache key and long_url as the value, and I set a TTL of maybe 24 hours, then maybe 90–95% of requests hit the cache and never touch the database. That reduces database read load to maybe 60,000–120,000 QPS — much more manageable. I would still need maybe 3–5 read replicas, but not 24.

For writes: 11,574 writes per second is the real challenge. A single-node PostgreSQL handles maybe 5,000–15,000 simple inserts per second depending on hardware. So we are right at the edge. I should shard the database.

Shard key: short_code. The short_code is always known at write time and at read time. Sharding by hash(short_code) distributes writes perfectly evenly — short codes are randomly generated, so no hot spots. With 8 shards, each handles about 1,450 writes per second — well within capacity.

Let me trace a write request: user submits long URL → application generates a unique short_code (random 6 characters, base62) → hash(short_code) mod 8 determines which shard → insert into that shard → return short_code to user. Simple.

Let me trace a read request: user visits short URL → application extracts short_code → check Redis cache. Cache hit? Return long_url, done, under 5ms. Cache miss? → hash(short_code) mod 8 → read from that shard's replica → write result to Redis cache → return long_url to user. Cache warm-up period aside, 95% of redirects complete in under 5ms."

---

## Minutes 25–35: Failure Modes and Edge Cases

**Candidate:** "Let me think through failure modes.

What if a shard goes down? 1/8 of short codes become temporarily unresolvable — redirects for those URLs fail. Users see a broken link for 30 seconds to 5 minutes until failover completes. This is unavoidable with sharding. We can minimize it with replicas and automated failover.

What if Redis goes down? Cache falls through to database. Database load spikes from 60,000 to 1.16 million QPS. This would overwhelm the database cluster. Mitigation: Redis cluster with 3 nodes, so single-node failure does not take down the cache. Also: a circuit breaker — if database load exceeds 200% of normal, return a graceful error rather than cascade failing.

What about the click_count increment? Every redirect needs to increment click_count. At 1.16 million redirects per second, doing a synchronous `UPDATE urls SET click_count = click_count + 1` per redirect would generate 1.16 million write operations per second — far exceeding our write capacity. Solution: use an in-memory counter per short_code in Redis. Increment a Redis counter on every redirect (Redis handles millions of operations per second). A background job periodically flushes Redis counter values to the database — say every 5 minutes. Click counts are eventually consistent, which is fine for analytics.

What about short_code collisions? If we generate a random 6-character base62 code (62^6 = 56 billion possibilities), collisions become likely after sharding when we have written more than sqrt(56 billion) ≈ 237,000 URLs. At 1 billion URLs per day, collisions are certain. Solution: use a distributed ID generator (Snowflake-style) that generates globally unique IDs, then encode to base62. The ID incorporates timestamp and machine ID — guaranteed globally unique without a collision check."

---

## Minutes 35–45: Trade-offs and Refinement

**Candidate:** "Let me summarize the trade-offs in this design.

The big bets I am making:
- Redis caching absorbs 90–95% of reads. If I am wrong about the hit rate (maybe URLs are more uniformly distributed than I think), I need more database replicas.
- Sharding by short_code gives even write distribution. If the random short_code generation has any bias, I could get hot spots. But base62 with a good RNG should be fine.
- Eventual consistency on click counts. If business requires exact real-time counts (for billing purposes), I need a different approach — synchronous database writes or a stream processing system.

If I had more time, I would add: CDN in front of everything (redirect responses are cacheable at the CDN edge — the fastest possible response), a write-through cache (on URL creation, immediately warm the cache entry so the first redirect hits cache), and geographic distribution (shard replicas in each region for low global latency).

What questions do you have?"

---

## Post-Interview Analysis: What Made This L6

Notice what the candidate did:

1. **Asked clarifying questions that changed the design.** The 100:1 read/write ratio was the most important fact — it determined that caching was the primary scaling mechanism, not sharding.

2. **Did math before recommending solutions.** "50,000 QPS per replica, 1.16M QPS needed = 24 replicas" — then questioned whether you actually need 24 replicas or whether cache makes them unnecessary.

3. **Tried the simpler solution before the complex one.** Cache before sharding. Showed that sharding might not even be needed for reads.

4. **Addressed the specific bottleneck.** Writes at 11,574/second → this is the actual constraint → this is why sharding is necessary. Not "sharding is good for scale," but "sharding is needed specifically because write QPS exceeds single-node capacity."

5. **Proactively named failure modes of their own design.** Redis falling down, shard going down, click_count increment problem — all surfaced by the candidate, not discovered by the interviewer.

6. **Flagged the assumptions and their risks.** "If cache hit rate is lower than I assumed, my design needs more replicas." Naming the sensitivity of your design is L6 behavior.

---

## Common Interview Anti-Patterns to Avoid

Here are the phrases and behaviors that immediately signal junior-level thinking in a database scaling discussion:

**"I would just use a NoSQL database."**
This answers "what technology?" when the question is "how do you scale?" NoSQL is not inherently scalable and relational databases are not inherently unscalable. The question is about architecture, not technology labels.

**"I would shard by the primary key."**
Every table already indexes by primary key. Sharding by primary key is the default and often wrong — it often creates hot spots or makes your most common queries into scatter-gather operations. The shard key should be chosen based on your access pattern, not your schema.

**"I would use eventual consistency."**
This alone is not an answer. Every consistency model is "eventual consistency" on a long enough timescale. The real question is: how stale can this specific piece of data be? 1ms? 1 second? 1 minute? 1 day? The business requirement defines the answer, not a generic preference for eventual consistency.

**"We can always add more servers later."**
This is true but meaningless without explaining how the architecture accommodates adding servers. With naive modulo hashing, adding a server requires moving 80% of data. With consistent hashing, adding a server moves 1/N of data. "Add more servers" is only a plan if your architecture is designed for it.

**Proposing sharding as the first answer to any scaling question.**
Sharding is the last resort. Indexing, caching, read replicas, query optimization, vertical scaling — all of these should be considered and potentially exhausted before sharding. An interviewer who hears "I'd shard this" as the first word out of your mouth knows they are talking to someone who does not have production experience with database scaling.

---

## The 3 Questions to Ask Yourself Before Every Answer

Before you speak in a system design interview about database scaling, ask yourself:

**1. Do I know the actual bottleneck?**
If you do not know whether the system is read-heavy, write-heavy, or storage-constrained — you cannot propose the right solution. Ask the interviewer. Estimate from first principles. Do not skip this step.

**2. Is there a simpler solution I am overlooking?**
Sharding is complex, expensive, and semi-permanent. Before proposing it, run through the checklist: better indexes? Query optimization? Read replicas? Application-level caching? Vertical scaling? Write batching? One of these may solve the problem for the next 18 months at 1/10 the cost and risk of sharding.

**3. What breaks in my proposed solution?**
Every architecture has failure modes. Name yours before the interviewer finds them. This signals that you have thought through the design, not just pattern-matched to a solution. Proactively discussing failure modes is one of the clearest L6 signals.

---

# Part 8: Real Production Patterns — How Major Systems Actually Do It

This section describes how real production systems at major companies have solved replication and sharding problems. These are patterns that have been publicly documented by the companies themselves in engineering blog posts and conference talks. Knowing these examples gives you grounding in "this is how it actually works in practice," which is invaluable in interviews.

---

## Pattern 1: Facebook's TAO — Social Graph at Scale

**The problem:** Facebook needs to store and query a massive social graph — billions of users, each with hundreds of friends, posts, likes, comments, and page relationships. The access pattern is almost entirely read-heavy (people scrolling feeds, loading profiles). Writes are infrequent relative to reads.

**The solution:** TAO (The Associations and Objects) is Facebook's distributed data store for the social graph. Key design decisions:

- Data is sharded by the object ID (user ID, post ID, etc.) using a consistent hash
- Every shard is replicated across multiple datacenters
- Reads are served from local replicas in each datacenter — even if the data is a few seconds stale, it is acceptable for most social graph data
- The shard assignment is cached at each application server — the routing directory is consulted only on cache miss

**The lesson for your interview:** Eventual consistency is acceptable for social graph data. You do not need to see your friend's profile update immediately — you can tolerate 5–30 seconds of staleness. This allows aggressive use of local replicas and caching, which is what makes billions of social graph reads per day tractable.

**The trade-off explicitly made:** Consistency was sacrificed for availability and performance. If Facebook's servers in Europe cannot reach the US datacenter for 10 seconds, European users still see their friends' profiles — just slightly stale ones. They never see an error page. That choice was intentional.

---

## Pattern 2: YouTube's Vitess — MySQL Sharding at Massive Scale

**The problem:** YouTube needed to shard MySQL — a database not natively designed for sharding — to handle billions of video metadata records and massive write throughput.

**The solution:** Vitess — an open-source system that wraps MySQL and adds horizontal sharding. Key decisions:

- Vitess uses a concept called "keyspaces" — logical sharding that can be remapped to physical shards without changing application code
- The shard key is embedded in the primary key — every table's primary key starts with a shard key prefix, so the routing layer always knows exactly which shard to query without consulting a directory service
- Vitess handles connection pooling, query routing, and resharding transparently to the application

**The lesson for your interview:** Embedding the shard key in the primary key is an elegant solution to the routing problem. Instead of a separate directory lookup, the key itself encodes where it lives. This removes a network hop from every query.

**The trade-off explicitly made:** You lose the ability to use natural primary keys. Auto-increment integer IDs become composite IDs (shard_key + local_id). This complicates joins and foreign key references, but YouTube decided that horizontal scaling was worth this schema trade-off.

---

## Pattern 3: Cassandra's Leaderless Replication — DynamoDB's Approach

**The problem:** Amazon needed a database for its product catalog and shopping cart that could guarantee availability even during network partitions — it could not afford for the add-to-cart button to fail even if half the datacenter was unreachable.

**The solution:** DynamoDB (and Cassandra, inspired by it) uses leaderless replication with tunable consistency. Key decisions:

- Data is partitioned by a partition key using consistent hashing across a ring of nodes
- There is no leader — any node can accept reads or writes
- A write is considered successful if W of N nodes acknowledge it (W is configurable)
- A read is considered successful if R of N nodes respond (R is configurable)
- When W + R > N, you get strong consistency. When W + R ≤ N, you get eventual consistency with better performance

**The lesson for your interview:** Consistency is a dial, not a binary choice. For shopping cart data (if it is stale for 2 seconds, not catastrophic), you tune for availability (low W, low R). For financial data (must be current), you tune for consistency (W + R > N). The same database can serve both purposes with different consistency settings per table.

**The trade-off explicitly made:** Conflict resolution is the complexity you pay. When two nodes accept writes for the same key simultaneously, you have a conflict. DynamoDB uses vector clocks to detect conflicts and surfaces them to the application for resolution. This is operationally complex but necessary for a truly leaderless system.

---

## Pattern 4: Slack's Sharding by Workspace — Multi-Tenant Architecture

**The problem:** Slack serves millions of workspaces (companies). Each workspace has its own set of channels, messages, users, and files. The access pattern is almost entirely workspace-local — users only access data within their own workspace.

**The solution:** Shard by workspace_id. Every piece of data — messages, channels, user memberships — is co-located on the same shard as the workspace it belongs to. Key benefits:

- Every query is a single-shard query (no scatter-gather)
- Each workspace's data is isolated — a slow query for one workspace does not affect another
- Workspace-level operations (exporting all data, deleting a workspace) are single-shard operations

**The complication:** Large workspaces (like a 50,000-person company) create hot shards. Slack solved this with dedicated infrastructure for enterprise customers — large customers get their own shards or dedicated database clusters.

**The lesson for your interview:** Multi-tenant systems with workspace/company/tenant structure almost always shard by tenant ID. It is the cleanest possible co-location: all of a tenant's data on one shard. The large-tenant hot spot problem is solved by giving large tenants dedicated infrastructure, not by changing the shard key.

---

## Pattern 5: Twitter's Timeline Service — Fan-Out at Scale

**The problem:** Twitter needs to deliver tweets to followers' timelines within seconds of posting. With some users having 100+ million followers, a naive push-based fan-out is impossible.

**The solution:** A hybrid fan-out architecture documented in Twitter's engineering blog:

- For "normal" users (under a configurable threshold, roughly 1 million followers): push fan-out. When a tweet is posted, a fan-out service reads the user's follower list and writes the tweet ID to each follower's timeline cache (Redis). Followers see the tweet almost instantly.

- For "notable" users (above the threshold): pull-based. The tweet is stored in a separate notable users store. When a follower opens their timeline, tweets from notable users they follow are fetched on demand and merged into the timeline view.

- Timeline assembly: a user's timeline is the union of (pre-computed pushed tweets from normal users they follow) + (on-demand fetched tweets from notable users they follow). The merge is done at read time in the timeline service.

**The lesson for your interview:** The celebrity/normal user distinction is a real architectural pattern at production scale, not a clever trick. The threshold for "notable" is configurable and based on measured fan-out cost, not a fixed rule. The hybrid approach allows the system to handle both Kylie Jenner (190M followers) and your friend with 50 followers with a single coherent architecture.

**The trade-off explicitly made:** Notable user tweets appear in followers' timelines with slightly higher latency (on-demand fetch vs. pre-computed push). Twitter decided this was acceptable — most users do not perceive a 50–100ms difference in tweet delivery time.

---

## Pattern 6: Stripe's Strong Consistency for Payments — The Unavoidable Cost

**The problem:** Stripe processes financial transactions. Unlike social media data, payment data cannot tolerate staleness. If a user's balance shows $500 when it is actually $0 after a recent payment, a second payment could overdraft the account. Eventual consistency is unacceptable.

**The solution:** Stripe uses synchronous replication with careful shard design:

- Accounts are sharded by account_id. All transactions for an account are on the same shard — no cross-shard reads for a single account's balance.
- Cross-account transfers (like sending money to another user) use a saga pattern with idempotency keys, designed to be safe to retry.
- Reads for financial data go to the leader — never to replicas. The extra latency is non-negotiable for correctness.
- Write QPS for financial operations is generally not extreme (people do not send thousands of payments per second per account), so even strong consistency with leader reads is manageable at scale.

**The lesson for your interview:** Financial data is the case where you pay the full price for consistency. No replicas for reads, synchronous replication, saga for cross-shard operations. The cost is higher latency (100–300ms for the leader read vs. 5ms for a replica or cache read). The business requirement — never showing incorrect balances — is worth it.

**The pattern to memorize:** read critical financial data from the leader, always. Not from replicas, not from cache. Leader only. Budget for the latency.

---

## Pattern 7: Redis Cluster — Automatic Sharding Made Visible

**The problem:** Redis is a single-threaded in-memory store. At some scale, a single Redis instance cannot handle the QPS or fit all the data in memory. You need to shard Redis.

**The solution:** Redis Cluster provides automatic sharding across multiple Redis nodes. Key design decisions:

- Redis Cluster uses 16,384 "hash slots." Each key is assigned to a slot by CRC16(key) % 16384. Each Redis node is responsible for a range of slots.
- When a client connects to any Redis node, if the requested key is not on that node, the node returns a MOVED error pointing to the correct node. The client caches this routing information.
- Adding or removing nodes: Redis Cluster can move hash slots from one node to another without downtime. Data in the moved slots is migrated key by key.

**The lesson for your interview:** Redis Cluster is a production example of consistent hashing principles in a widely deployed system. The 16,384 hash slots are the "logical shards" — physical Redis nodes hold ranges of these slots. Adding a node moves some slots (with their data) to the new node. No rehashing of all keys required.

**The number to remember:** 16,384 hash slots in Redis Cluster. This is why "logical shards" (slots) are decoupled from "physical nodes" — you can have any number of physical nodes up to 16,384, and rebalancing moves slots between nodes smoothly.

---

## Pattern 8: CockroachDB — Distributed SQL Without Manual Sharding

**The problem:** Application developers want to use SQL (familiar, powerful) but need horizontal scalability. Traditional sharding requires the application to be shard-aware — every query must know which shard to target. This is operational complexity the application developer should not have to manage.

**The solution:** CockroachDB provides distributed SQL that handles sharding transparently:

- Data is automatically split into "ranges" (similar to logical shards) as it grows
- Ranges are automatically balanced across nodes
- The application writes SQL queries exactly as if using a single-node PostgreSQL — no shard key awareness required
- Under the hood, CockroachDB uses the Raft consensus algorithm to replicate each range across nodes, providing strong consistency automatically

**The lesson for your interview:** Transparent sharding exists but comes at a cost. CockroachDB achieves transparency by using Raft consensus on every write — this adds latency compared to a single-node database. For many applications, the operational simplicity is worth the latency overhead. For ultra-low-latency writes, manual sharding with a simpler replication model is faster.

**When to mention this in an interview:** If the interviewer asks "is there a way to shard without the application being shard-aware?" — yes, NewSQL databases like CockroachDB or Google Spanner do exactly this. Trade-off: higher write latency (Raft rounds add 1–5ms per write) for operational simplicity and automatic resharding.

---

## Connecting the Patterns: What They Have in Common

After reading these eight production patterns, notice what every one of them shares:

**1. The access pattern determined the shard key.**
Facebook shards by object ID because objects are looked up by ID. Slack shards by workspace_id because all queries are workspace-local. YouTube embeds the shard key in the primary key to make routing zero-cost. Every shard key choice traces back to an access pattern analysis.

**2. Consistency requirements determined the replication model.**
Twitter uses eventual consistency for timeline data (staleness is fine). Stripe uses strong consistency for payment data (staleness is catastrophic). They are not using different systems because of personal preference — they use different models because the business requirements are different.

**3. The simple solution was tried first, and sharding came later.**
None of these companies started with 64 shards on day one. They started with a single database, added replicas when reads grew, added caching when replicas were not enough, and sharded when writes became the bottleneck. Each additional layer of complexity was forced by a specific, measured constraint.

**4. Hot spots are handled by caching and dedicated infrastructure, not by re-sharding.**
Celebrity users at Twitter get pull-based fan-out. Large enterprise workspaces at Slack get dedicated clusters. Viral tweets at Facebook get cached aggressively. The hot spot problem is addressed by a parallel mechanism — not by changing the fundamental shard key.

These patterns will not all appear in any one interview. But when you can say "this is similar to how Slack handles their multi-tenant sharding, and here is what I am taking from that pattern and adapting," you demonstrate that your designs are grounded in real systems, not invented on a whiteboard. That credibility is worth a lot in a staff-level interview.

---

# Conclusion

Replication and sharding are not advanced topics reserved for the largest companies in the world. They are the standard building blocks of any system that serves more than roughly one million users. If you want to design systems at that scale — and most interesting systems operate at that scale — you need to be able to talk about replication lag, shard keys, consistent hashing, hot spots, and failure modes as fluently as you talk about REST APIs or SQL queries. These are not exotic concepts. They are the infrastructure vocabulary of modern distributed systems. Understanding them gives you the language to reason intelligently about any large-scale system design, whether it is a social network, a payment processor, a messaging app, or a ride-sharing platform.

The mental shift from "how do I build this feature?" to "how do I make this feature work reliably for 100 million people?" is exactly what separates L5 engineers from L6 engineers. Features are built once. Scale is something the system has to live with every day — at 3 AM during an incident, under the load of a marketing campaign nobody anticipated, during the one week of the year when traffic spikes 10× for a product launch. Replication and sharding are the most common mechanisms that make scale actually work. They determine how your system behaves when traffic doubles overnight, when a database crashes during peak hours, when a celebrity user triggers a cascade failure, when a shard fills up. Engineers who understand these mechanisms deeply can navigate these situations with calm and precision. Engineers who only know the surface patterns get surprised.

Do not be intimidated by the complexity. Strip away all the vocabulary and here is what remains: every shard is just a regular database, holding a fraction of your data. Every replica is just a copy of a database, receiving the same writes as the original. The complexity is entirely in the coordination — making these independent pieces act as one coherent system, keeping them consistent with each other, recovering gracefully when one fails, scaling without destroying what was built before. That coordination problem is genuinely hard. But it is learnable. And the engineers who learn it thoroughly are the ones who build the systems that hundreds of millions of people depend on every day.

---

---

# The Week Before Your Interview — Study Plan

If you have a system design interview in one week and this chapter is new to you, here is how to use the material efficiently.

---

## Day 1: Fundamentals (Parts A and B)

Read Parts A and B of this chapter. Do not skip ahead to the interview questions yet. The fundamentals are load-bearing — you cannot answer the interview questions without them.

Focus on: what replication lag actually means (not just the word, but the concrete scenario of a user updating their profile and seeing old data). What a shard key does. Why consistent hashing beats modulo hashing.

At the end of Day 1, try to explain these three things out loud to yourself or someone else: (1) the difference between async and sync replication, with the trade-off for each, (2) why timestamp is a bad shard key for a write-heavy system, (3) the co-location principle.

If you cannot explain them clearly, re-read the relevant sections.

---

## Day 2: Advanced Patterns (Parts B and C)

Read Parts C of the chapter — failure modes, celebrity hot spots, cross-shard transactions, resharding.

Focus on: the saga pattern for distributed transactions (this comes up constantly in payment system design questions). The double-write migration strategy. The celebrity fan-out hybrid (push for normal users, pull for celebrities).

At the end of Day 2: work through Brainstorming Questions 1–6 in Part 6 of this document. Do not just read them — actually answer them out loud or write answers down. Check your answers against the Discussion Notes.

---

## Day 3: Interview Calibration (Part D, this document)

Read the L5 vs L6 contrast table. Read the sample L6 answer ("Design a User Database"). Read the common mistakes section.

Work through Brainstorming Questions 7–18. These are the failure scenarios — practice diagnosing problems before jumping to solutions.

At the end of Day 3: read the "Before and After" section (L5 vs L6 answers). For each scenario, cover the L6 answer and try to generate your own version before reading the correct one.

---

## Day 4: Design Practice (30-Minute Sessions)

Pick any 3 questions from Section E (Questions 25–30). Set a 30-minute timer for each. Work through the design as if in a real interview.

After each 30-minute session: check the Discussion Notes for that question. Identify one thing you missed or would have said differently.

At the end of Day 4: review the Quick Reference Card. Memorize the key numbers table — these will make your interview answers sound credible.

---

## Day 5: Full Interview Dry Run

Read Part 7 (the URL Shortener interview walkthrough) carefully. Notice the structure: clarifying questions first, capacity math before architecture, simpler solutions before complex ones, failure modes proactively named.

Then do Exercise 7 (the Twitter interview dry run) with a real 35-minute timer. Record yourself if possible. Watch back and notice where you skipped diagnostic steps or jumped to sharding without calculating whether it was necessary.

---

## Day 6: Real Production Patterns and Review

Read Part 8 (real production patterns). Pick 2–3 that are most relevant to the interview you are having (payment system → Stripe's pattern; social media → Twitter/Facebook patterns).

Spend 30 minutes reviewing the Vocabulary Glossary. Every term in the glossary is a term your interviewer will use. Make sure you can define each one without looking.

---

## Day 7: Rest and Light Review

Do not cram. Review the Quick Reference Card one more time. Review the 5-Minute Mental Model. Sleep well.

On the day of the interview: before you speak about database scaling, ask yourself the 3 questions: Do I know the bottleneck? Have I considered simpler solutions? What breaks in my proposed solution?

---

## The 10 Most Important Things to Know for the Interview

If you only have time to review one page, review this:

**1. Diagnosis before prescription.** Ask what the bottleneck is before proposing a solution. Never skip this step.

**2. Read bottleneck → add replicas.** Replicas handle read scaling. They do nothing for write scaling.

**3. Write bottleneck → consider sharding.** But try indexes, caching, batching, and vertical scale first. Sharding is the last resort.

**4. Shard key = primary access pattern.** Ask: what do I know first when I look up this data? Shard by that.

**5. Co-locate related data.** If tables are always queried together, use the same shard key for both.

**6. Consistent hashing over modulo hashing.** Adding a shard moves 1/N of data, not 80%.

**7. Celebrity users require special treatment.** Cache them in Redis or use pull-based fan-out. More shards does not help access skew.

**8. Financial data reads go to the leader.** Never to replicas. Never from cache. Leader only.

**9. Idempotency keys for any retryable operation.** Especially cross-shard transactions and payment operations.

**10. Resharding takes 2–4 months safely.** Plan for it from day one with consistent hashing or logical shards.

If you can speak fluently about all 10 of these in the context of a real system design scenario, you are ready for the database scaling portion of a staff-level interview.

---

# Chapter 21 Complete Summary — All Four Parts

This summary covers the key ideas from all four parts of Chapter 21. Use it as a last-pass review or as a rapid orientation if you are returning to this material after a break.

---

## Part A Summary: What Is Replication?

Replication means keeping copies of your data on multiple machines so that if one machine fails, others continue serving traffic.

The core design choice: how do you propagate writes from the leader to replicas?

**Async replication:** The leader acknowledges the write immediately and propagates to replicas in the background. Benefit: fast write confirmation. Risk: if the leader crashes before propagating, data is lost permanently.

**Sync replication:** The leader waits for at least one replica to confirm receipt before acknowledging the write. Benefit: no data loss on leader crash. Cost: write latency increases by the network round-trip to the replica (usually 1–10ms within a datacenter).

**Semi-synchronous:** One replica must confirm. Others are async. A pragmatic compromise for most applications.

**Multi-leader:** Multiple nodes accept writes. Writes propagate to all leaders. Risk: conflicts when two leaders accept different writes for the same record simultaneously.

**Leaderless:** Any node accepts reads or writes. Consistency achieved through quorum: W nodes confirm the write, R nodes respond to the read. When W + R > N, reads always see the latest write.

The most important concept: replication lag. The delay between a write on the leader and its appearance on a replica. Causes "read-your-writes" bugs when a user reads from a replica immediately after writing to the leader and sees their old data.

---

## Part B Summary: What Is Sharding?

Sharding means splitting your data across multiple machines so each machine holds a fraction of the total data. Unlike replication (copies), sharding uses partitioning (slices).

**When do you shard?** When writes or storage have grown beyond what a single machine can handle. Not when you have read bottlenecks (replicas solve reads). Not preemptively.

**The shard key:** the field you use to determine which shard holds a given record. This is the most consequential decision in your database architecture. A wrong shard key causes hot spots, expensive queries, or extremely costly migrations.

Rules for picking a shard key:
- It should be the first thing you know when looking up data
- It should distribute writes evenly
- It should co-locate data that is frequently queried together

**Sharding strategies:**
- Hash sharding: even distribution, good for point lookups, bad for range queries
- Range sharding: good for range queries, creates hot spots for current data
- Directory sharding: most flexible, requires careful design to avoid SPOF
- Consistent hashing: smooth rebalancing when nodes are added or removed

**Hot spots:** When one shard receives far more traffic than others. Two types: data skew (shard has more rows) and access skew (shard has more requests). Access skew is fixed with caching, not resharding.

**Resharding:** Moving data from one shard configuration to another. Takes 2–4 months on a live system. Use consistent hashing or logical shards from day one to make this cheaper.

---

## Part C Summary: Advanced Patterns and Failure Modes

**The celebrity problem:** A single entity (user, post, tweet) receives drastically more requests than others. Cache the hot entity in Redis. Pull-based fan-out for celebrities. More shards does not help access skew.

**Cross-shard transactions:** The hardest problem in sharding. Money transfer across two shards: either both accounts update or neither. Use the Saga pattern: local transactions with compensating transactions for rollback. Use idempotency keys for safe retries.

**Failure modes:**
- Leader crash: automatic failover to replica, possible data loss window (async replication)
- Replica lag spike: route critical reads to leader immediately while investigating
- Split-brain: two nodes both believe they are leader. Prevented by fencing tokens and quorum elections.
- Hot shard: cache the hot data, not add more shards

**Live resharding process:** Provision new shards → double-write phase (writes go to both old and new) → backfill historical data → verify consistency → switch reads → switch writes → decommission old shards. Zero downtime but high complexity.

**Co-location principle:** Data that is always queried together should live on the same shard. Shard orders by user_id, not order_id, if you always look up "all orders for user X."

---

## Part D Summary: Interview Performance

The table below maps every major topic in Chapter 21 to the interview question type it answers. Use it to identify gaps in your preparation.

| Topic | Interview Question It Answers |
|---|---|
| Async vs sync replication | "What happens if the leader crashes mid-write?" |
| Replication lag | "Why does the user see their old bio after updating?" |
| Multi-leader conflicts | "How do you handle two users editing the same document simultaneously?" |
| Hash sharding | "How would you distribute user data across 16 database nodes?" |
| Range sharding hot spots | "Why is timestamp a bad shard key?" |
| Consistent hashing | "How do you add a new shard without moving all data?" |
| Shard key selection | "How would you shard the Twitter tweets table?" |
| Co-location | "How do you make 'all orders for user X' a fast query when orders are sharded?" |
| Celebrity hot spot | "How does Instagram handle Kylie Jenner's 190M followers?" |
| Fan-out design | "Design the home timeline for Twitter." |
| Saga pattern | "User A transfers $100 to User B. They are on different shards. How do you do this safely?" |
| Idempotency keys | "How do you prevent duplicate payments when the user double-clicks Submit?" |
| Split-brain prevention | "How do you prevent two database nodes from both believing they are the leader?" |
| Leader failover | "What happens to the 10% of users on a downed shard?" |
| Live resharding | "How do you add shards to a live production system without downtime?" |
| Double-write migration | "Walk me through how you would migrate from 8 to 16 shards." |
| GDPR geo-partitioning | "How do you ensure EU user data never leaves EU infrastructure?" |
| Read-your-writes consistency | "After a user updates their profile, they see old data for 3 seconds. Why?" |
| L6 diagnosis-first thinking | "Your database CPU is at 80%. What do you do?" |
| Sharding vs replicas decision | "How would you scale this database for 100 million users?" |



The core L6 principle: diagnose before prescribing. Name the bottleneck (reads? writes? storage? specific query?). Try the simpler fix first (indexes, caching, replicas, vertical scale). Only shard when simpler solutions are exhausted.

The L5-to-L6 shift: L5 applies patterns reflexively. L6 reasons about specific bottlenecks, runs capacity math, considers trade-offs, and explicitly rejects over-engineering.

Common mistakes: sharding preemptively, using timestamp as shard key, ignoring co-location, making the directory service a SPOF, forgetting replication lag in application design, using naive modulo hashing.

Key numbers: less than 100ms replication lag (healthy), more than 5 seconds (alert), more than 30 seconds (critical). 30 seconds to 5 minutes for leader failover. 2–4 months for resharding. 1/N data movement with consistent hashing vs 75–80% with naive modulo.

The 30 brainstorming questions in Part D cover: replication fundamentals, sharding decisions, failure scenarios, design trade-offs, and real system design cases. Work through them before your interview.

The 10 exercises build: shard key decision documents, debugging runbooks, resharding plans, celebrity fan-out design, cross-shard transaction design, GDPR compliance architecture, interview dry runs, cost analyses, monitoring dashboards, and system evolution from 0 to 1 billion users.

---

*End of Chapter 21, Part D*

*End of Chapter 21: Replication and Sharding*
