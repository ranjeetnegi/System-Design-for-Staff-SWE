# Inverted Index: How Search Engines Work

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

The index at the back of a book. "Machine Learning... page 45, 78, 102." You look up a word. You get which pages contain it. That's an inverted index. In search: you look up a word and get which documents contain it. Google's entire search engine—trillions of pages—is built on this idea. For every word in the world, know which web pages have it. Simple. Revolutionary. Let's see how.

---

## The Story

A book. Forward: you read page 1, then page 2, then page 3. Page → words. "Page 1 contains: the, cat, sat, mat." That's a forward index. Document-centric.

Now invert it. Word → documents. "The word 'cat' appears in: Doc1, Doc5, Doc99, Doc1002." "The word 'shoes' appears in: Doc3, Doc5, Doc7." That's the inverted index. Word-centric. You want to find documents about "shoes"? Look up "shoes." Get the list. Done.

For "blue shoes": look up "blue" → [Doc1, Doc3, Doc7]. Look up "shoes" → [Doc3, Doc5, Doc7]. Intersection → [Doc3, Doc7]. Those documents contain both words. Results. Ranking comes later—TF-IDF, PageRank, neural—but the core is the inverted index.

---

## Another Way to See It

A library. Forward: each book has a list of words (its contents). To find "quantum," you'd scan every book. Inverted: one big catalog. "Quantum" → list of every book that mentions it. Look up one word. Get the list. That catalog is the inverted index. It's the wrong way around from how we read—and that's exactly why it works for search.

---

## Connecting to Software

**Forward index:** Document → list of words. "Doc1: the, cat, sat, mat." Easy to build. Hard to search. "Which docs have 'cat'?" Scan every document. O(N). Slow.

**Inverted index:** Word → list of documents (posting list). "cat: [Doc1, Doc5, Doc99]." Build it once. Search: O(1) lookup + merge of posting lists. Fast.

**Building:** For each document, tokenize (split into words). For each word, add document ID to that word's posting list. "cat" → append Doc1. "cat" → append Doc5. Eventually: "cat" → [Doc1, Doc5, ...]. Batch or stream. Incremental updates possible.

**Querying "blue shoes":** Look up "blue." Look up "shoes." Intersect lists. Documents in both = results. For phrase "blue shoes": need position info—word "blue" at position 5, "shoes" at 6. Adjacent = phrase match. Positional indexes add size but enable phrase and proximity queries. Trade-off: space for accuracy.

**Ranking:** Intersection gives you candidate documents. Which first? TF-IDF: term frequency (how often the word appears in the doc) × inverse document frequency (how rare the word is globally). "Quantum" in a doc = high score—rare word. "The" in a doc = low score—common word. Modern systems add BM25, learn-to-rank, neural rankers. But the inverted index is still the retrieval layer. Get candidates fast, then rank.

---

## Let's Walk Through the Diagram

```
Forward Index:                    Inverted Index:
Doc1 -> [the, cat, sat, mat]      the   -> [Doc1, Doc2, Doc3, ...]
Doc2 -> [the, dog, ran]           cat   -> [Doc1, Doc5, Doc99]
Doc3 -> [blue, shoes, sale]       blue  -> [Doc3, Doc7]
                                 shoes -> [Doc3, Doc5, Doc7]

Query: "blue shoes"
  Lookup "blue"  -> [Doc3, Doc7]
  Lookup "shoes" -> [Doc3, Doc5, Doc7]
  Intersect      -> [Doc3, Doc7]  ✓ Results
```

---

## Real-World Examples (2-3)

**Elasticsearch:** Built on inverted indexes. Lucene under the hood. Every field can be indexed. Full-text search. Filters. Aggregations. Billions of documents.

**Google:** The scale is ludicrous. Trillions of pages. Millions of words. Distributed inverted indexes. Sharded by word or document. Same idea, planetary scale.

**Your IDE:** "Find in files." Search for "function." IDE has an index. Word → files. Instant. Same structure. Smaller scale. Same idea—inverted index—whether you're searching code, documents, or the web.

**Slack search:** Indexes messages. Word → message IDs. Full-text search across your workspace. Inverted index under the hood. At scale, distributed—shard by document or by term. Elasticsearch is the common choice for this kind of search at scale. Lucene (which Elasticsearch uses) has refined the inverted index for decades.

---

## Let's Think Together

**Question:** The index has 1 billion documents. The word "the" appears in 900 million. The word "quantum" in 50,000. Which is more useful for search?

**Answer:** "Quantum." "The" matches almost everything—900 million docs. Intersection with another word still leaves millions. "Quantum" narrows fast—50,000 docs. Rare words are discriminative. That's why TF-IDF works: rare words get higher scores. "The" is stop-word—often ignored. "Quantum" is gold. The best index terms are selective. Common words dilute. Rare words focus.

---

## What Could Go Wrong? (Mini Disaster Story)

A search engine indexes every word. Including "a," "the," "is." Posting lists for these: hundreds of millions of documents. Merge "the" and "computer" = still millions. Slow. Index size explodes. Disk fills. Queries time out. Fix: stop words. Don't index "a," "the," "is." Saves space. Speeds up. Or index them but with special handling—smaller posting lists, different merge strategy. Trade-off: phrase search "the king" needs "the" in the index. Nuance matters. Some search engines keep stop words for phrase matching but don't use them in scoring. Engineering is full of these trade-offs.

---

## Surprising Truth / Fun Fact

The inverted index isn't new. Card catalogs in libraries—by subject, by author—were manual inverted indexes. Books (documents) indexed by attributes (words). The digital version scales to billions. The idea is centuries old. The implementation is modern. Sometimes the oldest ideas work best. Lucene, the library behind Elasticsearch and Solr, has been refining the inverted index since 1999. Compression, skip lists, merging strategies—decades of optimization. The core structure hasn't changed. The engineering around it has. That's robust design. Simple structure. Decades of refinement. The inverted index is a lesson in enduring architecture. Simple idea. Flip the mapping. Scale it. That's how search works—at every scale from your IDE to Google. One structure. Infinite scale.

---

## Quick Recap (5 bullets)

- **Inverted index** = word → list of documents; opposite of document → words
- **Query** = look up words, intersect posting lists; "blue shoes" = intersect blue + shoes
- **Building** = tokenize docs, for each word add doc to posting list
- **Enhancements** = TF-IDF (rare words score higher), positions (phrase match), stemming
- **Scale** = Elasticsearch, Lucene, Google; same core idea, massively different sizes and optimizations

---

## One-Liner to Remember

**Inverted index: look up a word, get the documents—the simple flip that makes search at any scale possible.**

---

## Next Video

Up next: Cache key design. Why the wrong key means your cache is useless. What to include, what to leave out.
