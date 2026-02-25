# Data Compression: Why and When

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

You're packing for a trip. Small suitcase. Too many clothes. Leave some behind? Or vacuum bags—suck out the air, clothes shrink. Same clothes. Half the space.

That's compression. Keep everything. Make it smaller. Less storage. Faster transfer. Lower cost. But you have to unpack before you use it.

---

## The Story

Jake is packing. His suitcase is full. He has two choices. Leave clothes behind—lose stuff. Or use vacuum bags. Compress. The clothes are still there. Same shirts, same pants. Just smaller. He packs more. Bag fits. When he arrives, he unpacks. Decompress. Everything back to normal.

Data compression is the same. You encode data to use fewer bits. Same information. Less space. A 10TB dataset might become 3TB. You save storage. You send less over the network—faster. You fit more in cache. But reading requires decompression. CPU work. Trade-off: space and bandwidth vs CPU and latency.

---

## Another Way to See It

A summary vs a full book. The summary is "compressed"—same story, fewer words. Lossy in a sense. But for data, we usually want **lossless**. Uncompress and get the exact original back. Like a zip file. Nothing lost. Just packed tighter.

For images and video, **lossy** is fine. JPEG throws away detail you can't see. MP3 throws away sounds you can't hear. Close enough. Much smaller.

The aha: text compresses incredibly well. Logs, JSON, code—often 5–10x. Repeated patterns get squeezed. "ERROR" appearing 1000 times becomes one entry plus a count. That's why compression is often the first optimization to try.

---

## Connecting to Software

**Compression** = encoding data to use fewer bits. Same info (lossless) or "close enough" (lossy). Less space. Faster transfer. Cheaper storage.

**Lossless:** ZIP, gzip, LZ4, zstd. Perfect restoration. For text, code, databases, logs. No information lost.

**Lossy:** JPEG, MP3, H.264. Some data discarded. Acceptable for humans. For images, audio, video.

**Where it helps:**
1. **Storage** — 10TB → 3TB. Save money. Save space.
2. **Network** — Send less. Transfer faster. Lower bandwidth costs.
3. **Cache** — Fit more in RAM. More cache hits.

**Trade-off:** Compression uses CPU. Compress too aggressively → CPU bottleneck. Compress too little → waste storage and bandwidth. Choose the right algorithm for your workload.

**Popular algorithms:**
- **gzip:** Common. Moderate compression. Moderate speed.
- **LZ4:** Very fast. Less compression. Good for real-time.
- **zstd:** Great balance. Fast and good ratio. Netflix, Meta use it.
- **Snappy:** Google's. Fast. Moderate compression.

**Columnar compression:** Parquet, columnar DBs. Store by column. Similar values (e.g., ages 25–35) compress amazingly. Run-length encoding. Often 10x compression on analytical data.

The trade-off hits you when you least expect it: compress with the wrong algorithm and every read becomes slow. Choose gzip for cold storage. Choose LZ4 for hot paths. Know your workload. One size does not fit all.

When to enable compression: logs, backups, data at rest, API responses. When to skip: real-time low-latency paths where every millisecond counts. Profile first. Then compress.

---

## Let's Walk Through the Diagram

```
    UNCOMPRESSED                    COMPRESSED
    10 GB log file                  2 GB (gzip)
         │                              │
         │  ── compress ──>             │
         │         (CPU)                │
         │                              │
         │  <── decompress ──          │
         │         (CPU)                │
         │                              │
    Storage: $$$$                 Storage: $
    Transfer: slow                Transfer: faster
    Read: instant                 Read: +decompress time
```

Compress for storage and transfer. Pay CPU on read. Choose algorithm based on your bottleneck. Cold data? Compress aggressively. Hot data? Compress lightly or not at all. Know your trade-off.

---

## Real-World Examples (2-3)

**Example 1 — Logs:** 1TB/day uncompressed. With zstd: 200GB/day. Stored 90 days. Huge savings. Logs compress well—lots of repeated text. Timestamps, log levels, stack traces—all have patterns. Compression loves patterns.

**Example 2 — Databases:** PostgreSQL, MySQL support compressed tablespaces. Data at rest is smaller. Backup files are compressed. Restore decompresses on the fly.

**Example 3 — HTTP:** gzip or Brotli for API responses. JSON compresses 5–10x. Bandwidth drops. Page load improves.

The quick win: enable gzip on your web server. One config line. Immediate savings. JSON, HTML, and text compress beautifully. Binary data? Less so. But for APIs, compression is free performance.

---

## Let's Think Together

Your logs are 1TB/day. Compressed with zstd = 200GB/day. Stored for 90 days. How much storage saved over 90 days?

Pause and think.

Uncompressed: 90 TB. Compressed: 18 TB. Saved: 72 TB. At $0.023/GB (S3): about $1,656 saved just for those 90 days. And that's one tier. Retention and archival multiply the savings.

Compression is one of the highest-ROI optimizations. Often a config change. Enable gzip on your API. Enable compression in your database. The CPU cost is usually negligible. The storage and bandwidth savings are real. Check your system. Are you compressing?

---

## What Could Go Wrong? (Mini Disaster Story)

A team compressed data at rest with a slow algorithm—bzip2. Great ratio. But every read required decompression. Read latency doubled. Users complained. Analytics jobs that scanned TB of data took 3x longer. CPU became the bottleneck. They switched to LZ4. Slightly larger files. Much faster reads. Right algorithm for the use case matters. For cold storage, bzip2 is fine. For hot paths, LZ4 or Snappy. For a balance, zstd. Profile your workload. Don't assume. Benchmark. A 10% compression improvement might not matter. A 5x slowdown on read definitely does.

---

## Surprising Truth / Fun Fact

Netflix uses zstd for their data pipelines. Facebook created zstd and open-sourced it. It's now used everywhere—databases, message queues, file formats. One algorithm, global impact.

---

## Quick Recap (5 bullets)

- **Compression** = encode data to use fewer bits. Same info (lossless) or close enough (lossy).
- **Lossless:** gzip, LZ4, zstd for text, logs, databases. Lossy: JPEG, MP3 for media.
- **Benefits:** Less storage, faster transfer, more in cache.
- **Trade-off:** CPU for compress/decompress. Choose algorithm for your bottleneck.
- **Columnar:** Parquet, columnar DBs compress similar values 10x+. Great for analytics.

---

## One-Liner to Remember

Vacuum bag for data. Same stuff, less space. Unpack when you need it. Same data, less space. Choose the right algorithm. Profile before you compress. It's free performance if you do it right.

---

## Next Video

Why does every big system use cache? Latency. Load. One library visit vs a million. Next: Why cache?
