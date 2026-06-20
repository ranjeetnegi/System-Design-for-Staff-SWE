# Chapter 86: Video Streaming — YouTube / Netflix / TikTok

> One of the top 5 system design interview questions at every major tech company.
> The candidate who says "upload to S3 and serve from CDN" fails. The candidate
> who traces adaptive bitrate, transcoding pipelines, and CDN cache warming wins.

---

## Why This Chapter Matters

Video streaming combines every hard distributed systems problem in one question. You get storage at extreme scale — YouTube has 500 hours of video uploaded every single minute, which means roughly 720,000 hours of new content every day. You get compute-intensive transformation work — one uploaded video must be converted into 15 or more quality variants before a single viewer can watch it. You get global low-latency delivery — a user in Jakarta expects the same sub-2-second start time as a user in Seattle. You get client-side intelligence — the video player itself must continuously decide which quality to request next based on network conditions. And you get metadata at scale — search, recommendations, comments, and thumbnails layered on top of all of it.

This question appears at Google, Meta, Netflix, Amazon, TikTok, Snap, and every other company with video features at L5 and above. At L6, the bar is: you must understand not just what each component does, but why it was designed that way, what breaks at scale, and what trade-offs each design choice implies.

---

## Key Numbers to Have Cold

| Metric | Value |
|--------|-------|
| YouTube uploads | 500 hours/minute |
| YouTube daily watch time | 1 billion hours/day |
| Netflix share of US internet traffic | ~15% at peak |
| Video start latency target | < 2 seconds |
| Buffering ratio target (rebuffer) | < 0.1% of play time |
| Typical encoding ladder variants | 6–15 |
| H.264 bitrate at 1080p30 | ~4–8 Mbps |
| H.265 bandwidth savings vs H.264 | ~40–50% |
| AV1 bandwidth savings vs H.264 | ~30–50% |
| CDN cache hit ratio target | > 95% for popular content |
| HLS/DASH segment duration | 2–10 seconds |
| TUS chunk size (typical) | 5–50 MB |
| RTMP ingest latency | < 500ms |
| HLS live latency (standard) | 20–30 seconds |
| CMAF / Low-Latency HLS | 2–5 seconds |
| WebRTC latency | < 500ms |

---

## Part 1: The Video Streaming Problem — What We Are Actually Building

### 1.1 Two Completely Separate Systems

The first thing most candidates miss is that video streaming is not one system — it is two fundamentally different systems that happen to share some storage:

**The Upload Path** is a write-heavy, asynchronous, compute-intensive pipeline. A creator uploads a raw video file — often gigabytes in size, in whatever codec their camera used. The system must receive that file reliably, store the raw version, transform it into dozens of optimized variants, and make it available for playback. This entire process can take minutes to hours. It does not need to be instantaneous.

**The Playback Path** is a read-heavy, latency-sensitive, globally distributed system. A viewer clicks play and expects video to start within two seconds. The system must deliver the right quality variant to the right device at the right location, continuously adapt as network conditions change, and do this for billions of concurrent streams without the origin servers being involved for most requests.

These two paths have almost nothing in common architecturally except that they share object storage (S3, GCS, or equivalent) as the handoff point. The upload path writes processed segments to object storage. The playback path reads those segments — usually via CDN, which has cached them from object storage.

```
UPLOAD PATH (Write, Async, Compute-Heavy)
=========================================

Creator Device
    |
    | [Chunked Upload — TUS Protocol]
    v
Upload Service (stateful, resumable)
    |
    | Raw video file stored
    v
Raw Object Storage (S3 / GCS)
    |
    | [Event: upload complete → Kafka/Pub-Sub]
    v
Transcoding Pipeline (DAG of workers)
    |  |- Worker: 240p H.264
    |  |- Worker: 480p H.264
    |  |- Worker: 720p H.264 + H.265
    |  |- Worker: 1080p H.264 + H.265 + AV1
    |  |- Worker: Thumbnail extraction
    |  |- Worker: Audio normalization
    |  `- Worker: Subtitle extraction
    v
Processed Object Storage (segmented .ts/.mp4 files + manifests)
    |
    | [Metadata DB write: video now "available"]
    v
CDN Origin Pull or Push


PLAYBACK PATH (Read, Sync, Latency-Sensitive)
=============================================

Viewer Device (Browser / Mobile App / Smart TV)
    |
    | [DNS lookup → Anycast → Nearest CDN PoP]
    v
CDN Edge Node (L1 cache — city level)
    |  Hit: serve segment immediately (~5ms)
    |  Miss: fetch from Regional PoP
    v
CDN Regional PoP (L2 cache — continent level)
    |  Hit: serve segment (~20ms)
    |  Miss: fetch from Origin Shield
    v
Origin Shield (single entry point per region)
    |  Hit: serve segment
    |  Miss: fetch from Object Storage
    v
Object Storage (S3 / GCS / Open Connect)
```

### 1.2 The Scale That Makes This Hard

Let's make the numbers concrete so you feel why naive approaches fail.

YouTube: 500 hours of video uploaded per minute means 720,000 hours per day. If each hour of 1080p video transcodes to roughly 10 quality variants, each taking 2x real-time compute (optimistic), that is 720,000 × 10 × 2 = 14.4 million CPU-hours of transcoding per day just to keep up. That requires a massive, continuously running fleet of transcoding workers.

On the delivery side: 1 billion hours of video watched per day means roughly 11.5 million concurrent viewers at any moment (1B / 24 / 3600 × some peak factor). A 1080p stream at 4 Mbps × 11.5M viewers = 46 Tbps of egress bandwidth. No single data center can serve this. Even distributing across 100 data centers would be 460 Gbps each — still enormous. CDNs with thousands of edge nodes are not optional; they are the only solution.

Netflix at peak carries roughly 15% of all downstream internet traffic in North America. Their answer was to build their own CDN (Open Connect) with server appliances physically placed inside ISP networks — bypassing the public internet entirely for the last mile.

TikTok's challenge is different: the content is short (15 seconds to 3 minutes), but the volume of unique content consumed per session is extremely high. A user might watch 50 different videos in a 10-minute session. The CDN cache hit ratio problem is brutal: 50 different videos, each potentially unique to that user's feed, means you cannot rely on the same segment being requested by many users simultaneously.

### 1.3 User Expectations That Drive the Architecture

Three metrics define whether a video streaming system is working:

**Time to First Frame (TTFF)**: The time from when the user clicks play to when the first frame appears on screen. Target: under 2 seconds. Missing this is perceptible and causes users to abandon. It is driven by: CDN latency (edge cache hit vs. miss), manifest fetch time, initial segment download time, and decoder startup time.

**Rebuffering Ratio**: The fraction of total playback time during which the video is paused waiting for data. Target: under 0.1%. A 1% rebuffering rate causes measurable viewer drop-off. It is driven by: ABR algorithm quality (did it pick the right bitrate?), CDN throughput consistency, and TCP connection quality.

**Seek Latency**: When a user scrubs to a different position in the video, how long before playback resumes there. Target: under 500ms. It is driven by: segment-based indexing (the player knows which segment contains the target timestamp and can request it directly) and CDN cache coverage of non-beginning segments.

### 1.4 Brainstorming — Part 1

**Q: Why can't you just upload the video file to S3 and serve it directly from S3?**

You could, and for very small scale it would work. The problems emerge as soon as you think about what "serving a video" actually means. First, S3 is a blob store optimized for durability and throughput, not for the thousands of small, parallel HTTP range requests that video streaming generates. Serving millions of concurrent streams directly from S3 would be astronomically expensive — S3 charges per GET request and per GB of egress, and the costs would be 10–100x what a CDN costs for the same delivery. Second, S3 is not geographically distributed in the way that video streaming requires. A viewer in Mumbai hitting an S3 bucket in us-east-1 would experience 200ms+ round-trip latency just for the TCP handshake, before any data transfer. That alone would blow the TTFF budget. Third, a raw camera file cannot be played by most browsers and devices — you need transcoded versions in standard codecs and container formats that browsers understand.

**Q: What is the single hardest technical problem in video streaming, and why?**

The hardest problem is the interaction between the ABR algorithm and the CDN cache. Here is why: the ABR algorithm on the client side is making decisions — which quality segment to request next — based on current network conditions. But the quality of the CDN response depends heavily on whether the requested segment is cached at the edge. If the segment is not cached, the CDN must fetch it from the origin, which takes longer and has lower throughput, which causes the ABR algorithm to see poor network conditions, which causes it to request a lower quality segment, which might happen to be cached — so the ABR algorithm sees good conditions and requests higher quality again, which might not be cached. This oscillation can produce a poor viewing experience that looks like a network problem but is actually a CDN cache coverage problem. Understanding this interaction is what separates L5 from L6 answers.

**Q: How does TikTok's architecture differ from YouTube's, given that TikTok videos are much shorter?**

TikTok's short video format creates several interesting architectural differences. Because videos are 15 seconds to 3 minutes long, the entire video can be prefetched into the client's buffer before the user even requests it — TikTok aggressively pre-buffers the next 2–3 videos in a user's feed. This eliminates rebuffering almost entirely at the cost of wasted bandwidth (videos prefetched but never watched). The CDN challenge is inverted from YouTube: YouTube has popular content that many people watch simultaneously (high cache hit ratio) plus long-tail content (low hit ratio). TikTok has an algorithm-driven feed where every user's next video is different, so the cache hit ratio is inherently lower, which pushes TikTok to pre-position content more aggressively at edge nodes based on prediction of what content the recommendation algorithm is likely to surface.

---

## Part 2: Video Upload Pipeline — Getting the File In Reliably

### 2.1 The Problem with Naive Upload

Imagine a creator uploading a 10GB raw 4K video file. A naive implementation sends the entire file in a single HTTP POST request. This fails in practice for several reasons:

- Mobile connections drop. If the upload fails at 9.9GB, the creator must start over.
- Large HTTP request bodies time out at load balancers, API gateways, and proxies.
- You cannot show upload progress accurately without chunking.
- You cannot parallelize a single-stream upload to saturate available bandwidth.
- If two creators upload the same video (or the same creator uploads twice), you waste storage and compute.

### 2.2 The TUS Protocol — Resumable Uploads from First Principles

TUS (Tus.io, an open protocol adopted by YouTube, Vimeo, and others) solves resumable uploads with a simple state machine. The name stands for "Tus Upload Server" — the protocol itself.

**How TUS works:**

Step 1 — Create: The client sends a POST request to the upload endpoint with metadata (file size, content type, filename). The server creates an upload resource and returns a unique upload URL. No file content is sent yet.

```
POST /uploads HTTP/1.1
Tus-Resumable: 1.0.0
Upload-Length: 10737418240        <- 10 GB
Upload-Metadata: filename dmlkZW8ubXA0,content-type dmlkZW8vbXA0

HTTP/1.1 201 Created
Location: /uploads/abc123def456
Tus-Resumable: 1.0.0
```

Step 2 — Upload chunks: The client sends PATCH requests to the upload URL, with each request containing a chunk of bytes and the byte offset where that chunk starts. Typical chunk size: 5–50 MB.

```
PATCH /uploads/abc123def456 HTTP/1.1
Content-Type: application/offset+octet-stream
Content-Length: 52428800          <- 50 MB chunk
Upload-Offset: 0                  <- starting at byte 0

[50 MB of binary data]

HTTP/1.1 204 No Content
Upload-Offset: 52428800           <- server confirms new offset
```

Step 3 — Resume after interruption: If the connection drops at offset 3.2GB, the client queries the server for the current offset:

```
HEAD /uploads/abc123def456 HTTP/1.1
Tus-Resumable: 1.0.0

HTTP/1.1 200 OK
Upload-Offset: 3221225472         <- server's confirmed offset
Upload-Length: 10737418240
```

The client then resumes from byte 3,221,225,472. Only the bytes not yet confirmed by the server need to be retransmitted.

Step 4 — Completion: When the final chunk is uploaded (Upload-Offset reaches Upload-Length), the server fires an event to trigger downstream processing.

```
UPLOAD PIPELINE STATE MACHINE
==============================

Client                        Upload Service               Raw Storage
  |                                |                            |
  |--- POST /uploads (metadata) -->|                            |
  |<-- 201 Created (upload_id) ----|                            |
  |                                |                            |
  |--- PATCH chunk 1 (0-50MB) ---->|                            |
  |                                |--- write chunk 1 --------->|
  |<-- 204 (offset: 50MB) ---------|<-- ack -------------------|
  |                                |                            |
  |--- PATCH chunk 2 (50-100MB) -->|                            |
  |                                |--- write chunk 2 --------->|
  |<-- 204 (offset: 100MB) --------|<-- ack -------------------|
  |                                |                            |
  |   [CONNECTION DROPS]           |                            |
  |                                |                            |
  |--- HEAD /uploads/abc123 ------>|                            |
  |<-- 200 (offset: 100MB) --------|  <- server remembers       |
  |                                |                            |
  |--- PATCH chunk 2 retry ------->|  <- resumes from 100MB     |
  |   (offset: 100MB, next data)   |                            |
  |                                |                            |
  |   ... (continue until done)    |                            |
  |                                |                            |
  |--- PATCH final chunk --------->|                            |
  |<-- 204 (offset = file size) ---|                            |
  |                                |--- emit "upload_complete" ->|
  |                                |    event to Kafka           |
```

### 2.3 Multipart Upload on the Backend

While TUS handles the client-to-upload-service leg, the upload service itself typically uses the cloud provider's multipart upload API (e.g., S3 Multipart Upload) to write to object storage. This is a different protocol but solves the same problem at the backend level:

1. Initiate multipart upload → get upload_id from S3
2. Upload each part with a part number → get ETag per part
3. Complete multipart upload with list of (part_number, ETag) pairs → S3 assembles the object

The upload service acts as a proxy: it receives TUS chunks from the client and converts them into S3 multipart upload parts. The chunk sizes may differ between the two legs — TUS chunks from the client might be 10MB while S3 multipart parts might be 100MB, requiring the upload service to buffer and combine before forwarding.

### 2.4 Deduplication via Content Hash

Before spending CPU-hours transcoding a video, the system should check whether an identical video already exists. This is done via content hashing:

1. As chunks arrive, the upload service computes a running SHA-256 (or MD5 for speed) hash of the entire file content.
2. When upload completes, the final hash is looked up in a deduplication index (a key-value store: hash → existing_video_id).
3. If the hash exists: skip transcoding, link the new video record to the existing processed segments.
4. If the hash is new: proceed with transcoding, store the hash in the dedup index.

This catches exact duplicates — the same bytes uploaded twice. It does not catch near-duplicates (re-compressed versions, slight edits). For near-duplicate detection, platforms use perceptual hashing (pHash) on video frames, but that is a separate pipeline run after transcoding and is primarily used for copyright enforcement (Content ID system at YouTube) rather than storage deduplication.

### 2.5 The DAG-Based Processing Pipeline

After the raw video is in object storage and the upload-complete event fires, the transcoding pipeline begins. Modern video processing pipelines are modeled as Directed Acyclic Graphs (DAGs) of tasks — the same conceptual model as Airflow or Spark DAGs.

Why a DAG? Because video processing involves many tasks with complex dependencies:

- Demux (separate audio and video streams) must happen before any encoding
- Thumbnail generation requires at least one decoded video frame
- All quality variants can be encoded in parallel once demux is done
- Manifest generation requires all quality variant encodings to complete
- Publishing the video requires the manifest to exist

```
DAG-BASED VIDEO PROCESSING PIPELINE
=====================================

[Raw Video in S3]
      |
      v
[DEMUX WORKER]
 Separate audio track(s) from video stream
 Extract metadata: duration, resolution, frame rate, codec
      |
      +---------------------------+---------------------------+
      |                           |                           |
      v                           v                           v
[VIDEO ENCODE]              [AUDIO ENCODE]            [THUMBNAIL]
 |- 240p H.264               Normalize loudness         Extract frames
 |- 480p H.264               Encode to AAC 128kbps       at intervals
 |- 720p H.264               Encode to AAC 256kbps      Run ML ranking
 |- 720p H.265               (for different devices)     Select best N
 |- 1080p H.264                                          Store sprites
 |- 1080p H.265                    |
 |- 1080p AV1                      |
 |- 4K H.264 (if source is 4K)    |
 |- 4K H.265                       |
      |                            |
      +----------------------------+
      |
      v
[MANIFEST GENERATOR]
 Create .m3u8 (HLS master manifest)
 Create .mpd (DASH manifest)
 List all quality variants with bandwidth and resolution
      |
      v
[METADATA WRITER]
 Update video DB: status = "available"
 Index in Elasticsearch for search
 Trigger recommendation system update
      |
      v
[CDN WARM] (optional, for expected-popular content)
 Pre-push manifest + first segments to edge nodes
```

### 2.6 Intern → Staff Progression: Upload Pipeline

**Intern**: "The creator uploads the video file to our servers, we store it, and start transcoding."

**Junior**: "We use chunked upload so large files can be resumed. The file goes to S3. A Lambda or Cloud Run job picks it up and runs ffmpeg to create multiple quality levels."

**Mid-level**: "We implement TUS protocol for resumable chunked uploads. We use S3 multipart upload on the backend. After upload completes we publish an event to Kafka. A fleet of transcoding workers consume from that topic and process videos in parallel. We have separate workers for different quality levels to maximize parallelism."

**Senior (L5)**: "The upload service is stateful — it tracks per-upload offset in Redis (keyed by upload_id) so any upload service instance can handle a resume request. We do content hashing for deduplication before triggering transcoding. The transcoding pipeline is a DAG orchestrated by a workflow engine (Temporal or Airflow) so individual task failures can be retried without restarting the whole pipeline. We separate audio and video encoding into different worker types because they have different CPU and memory profiles."

**Staff (L6)**: "At YouTube scale, the upload service cluster must handle ~500 hours × 60 / average_video_length = thousands of concurrent uploads at all times. We shard upload state across Redis clusters by upload_id. We also run upload acceleration: the creator's client connects to the nearest Google PoP, and the upload is tunneled over Google's internal fiber backbone to the transcoding cluster — avoiding the public internet for the upload leg entirely. Transcoding workers are heterogeneous: we use GPU-accelerated instances for H.265 and AV1 (which are compute-heavy) and cheaper CPU instances for H.264 (which has mature hardware acceleration). We preemptible-spot-instance the transcoding fleet because jobs can be checkpointed and resumed. The DAG engine tracks each task's idempotency key so retries do not produce duplicate encoded files."

### 2.7 Brainstorming — Part 2

**Q: What happens if the transcoding pipeline falls behind — more uploads arriving than workers can process?**

This is a real operational problem that every video platform has faced. The upload pipeline is bursty — a product launch, a breaking news event, or a viral moment can cause uploads to spike 10–100x normal volume. The transcoding pipeline must absorb this spike.

The primary tool is autoscaling the transcoding worker fleet. Because transcoding workers consume from a Kafka topic (or equivalent queue), adding more workers means adding more Kafka consumers up to the partition count. The lag on the Kafka consumer group is a direct signal for autoscaling — if lag exceeds N minutes, spin up more workers. Cloud providers' managed instance groups can launch new VMs in 2–5 minutes, and spot/preemptible instances significantly reduce cost for this workload.

The secondary tool is quality-tier prioritization. When the system is overloaded, it should first produce the lowest quality variants (240p, 480p) — these are fast to encode and allow the video to be marked "available" for viewers with poor connections. Higher quality tiers (1080p, 4K) are lower priority and can lag further behind. This is implemented by having separate Kafka topics per quality tier with different consumer group priorities.

The long-term mitigation is per-title encoding (covered in Part 3), which reduces the total compute needed by right-sizing the bitrate for each video's actual content complexity.

**Q: How do you handle a creator who uploads the same video 50 times?**

Content deduplication via SHA-256 hash handles exact duplicates — the second through fiftieth uploads resolve to the same hash and skip transcoding entirely. The system just creates a new video metadata record pointing to the existing processed segments.

For near-duplicates (re-compressed, slightly trimmed, watermark added), SHA-256 will not match. YouTube's Content ID system uses audio fingerprinting and video perceptual hashing — comparing frame-level feature vectors against a database of known content. This runs as a separate asynchronous pipeline after transcoding and is primarily used for copyright enforcement rather than storage savings. At the storage level, near-duplicates do result in duplicate storage — the platform accepts this cost as cheaper than the compute cost of near-duplicate detection at upload time.

---

## Part 3: Transcoding — Making One Video Into Many

### 3.1 Why Transcode?

A creator uploads a video in whatever format their camera or screen recorder produced. This might be H.264 in an MP4 container, H.265 in an MKV container, ProRes from a professional camera, or VP9 from a screen recorder. The viewer might be on:

- An iPhone (prefers H.264 or H.265, Safari requires HLS)
- An Android phone (supports H.264, H.265, AV1, VP9, prefers DASH)
- A 4K smart TV with HDMI 2.0 (can handle H.265 or AV1 at 4K 60fps)
- A web browser on a 2015 laptop (H.264 only, limited to 1080p30)
- A user on a 2G mobile connection (needs 240p at 200kbps)

No single file can serve all these viewers optimally. Transcoding produces a family of output files — the encoding ladder — that covers this diversity.

### 3.2 The Encoding Ladder

The encoding ladder is the set of quality variants produced for each video. A typical ladder for YouTube-style content:

| Resolution | Framerate | H.264 Bitrate | H.265 Bitrate | AV1 Bitrate |
|------------|-----------|---------------|---------------|-------------|
| 240p | 30fps | 400 kbps | 240 kbps | 200 kbps |
| 360p | 30fps | 800 kbps | 480 kbps | 400 kbps |
| 480p | 30fps | 1.5 Mbps | 900 kbps | 750 kbps |
| 720p | 30fps | 2.5 Mbps | 1.5 Mbps | 1.2 Mbps |
| 720p | 60fps | 4 Mbps | 2.4 Mbps | 2 Mbps |
| 1080p | 30fps | 6 Mbps | 3.6 Mbps | 3 Mbps |
| 1080p | 60fps | 9 Mbps | 5.4 Mbps | 4.5 Mbps |
| 1440p | 60fps | 16 Mbps | 9.6 Mbps | 8 Mbps |
| 4K | 30fps | 35 Mbps | 21 Mbps | 17.5 Mbps |
| 4K | 60fps | 53 Mbps | 32 Mbps | 26.5 Mbps |

The platform does not necessarily produce all combinations. A cost-optimized ladder might produce H.264 for all tiers (widest device support), H.265 for 1080p and above (40% bandwidth savings for capable devices), and AV1 only for the most popular content where bandwidth savings justify the encoding cost.

### 3.3 Codecs Deep Dive — H.264 vs H.265 vs AV1 vs VP9

Understanding the codec landscape is essential at L6 because every encoding decision is a trade-off between encode time, decode complexity, bandwidth, and license cost.

**H.264 (AVC — Advanced Video Coding)**: Released 2003, now the universal baseline. Every device on earth supports H.264 hardware decode. At 1080p30, a high-quality H.264 stream needs ~4–8 Mbps. H.264 encoding is fast — even software encoding is manageable, and hardware encoders (NVENC on NVIDIA GPUs, Quick Sync on Intel CPUs) make it near-realtime. The downside: it is old. Newer codecs achieve the same quality at half the bitrate.

**H.265 (HEVC — High Efficiency Video Coding)**: Released 2013. Approximately 40–50% bitrate reduction vs H.264 at the same quality. The catch: royalty-encumbered (patent pool requiring licensing fees), so some open-source software distributions excluded it. Hardware decode is now widespread on devices from 2017 onward. Encoding is 2–4x slower than H.264. Netflix uses H.265 extensively for 4K HDR content.

**VP9**: Google's open, royalty-free alternative to H.265. Similar compression efficiency to H.265 (~30–40% better than H.264). Supported by Chrome, Firefox, Android, and most modern smart TVs. Not supported on Safari/iOS (a major gap). YouTube uses VP9 as its primary codec for most content — you are almost certainly watching VP9 right now when using Chrome on desktop.

**AV1**: Released 2018 by the Alliance for Open Media (Google, Mozilla, Microsoft, Netflix, Amazon, Apple). Royalty-free. Approximately 30–50% better compression than H.264, ~20% better than H.265/VP9 at the same quality. Hardware decode chips began appearing in 2020–2021. The catch: AV1 encoding is 5–50x slower than H.264 encoding. At Netflix scale, this means AV1 encoding for a 2-hour movie takes 1,000+ CPU-hours. Only deployed for the most-watched content where bandwidth savings justify the compute cost.

```
CODEC TRADE-OFF MATRIX
=======================

                    Compression    Encode Speed   Decode Support   License
                    Efficiency     (relative)     (2024)
H.264               Baseline        Fastest        Universal        Royalty
H.265/HEVC          +40-50%         2-4x slower    Widespread       Royalty
VP9                 +30-40%         3-5x slower    Good (no iOS)    Free
AV1                 +30-50%         10-50x slower  Growing          Free

Decision matrix:
- Always encode H.264 (universal fallback)
- Encode VP9 or H.265 for 720p+ (bandwidth savings justify cost)
- Encode AV1 only for top-N% most-watched content
```

### 3.4 Per-Title Encoding — Netflix's Innovation

Traditional encoding ladders use fixed bitrates per resolution. A 240p stream always gets 400 kbps regardless of content. This is wasteful in both directions:

- A static talking-head video at 240p looks fine at 150 kbps. Forcing 400 kbps wastes bandwidth.
- A high-motion action sequence at 240p might look terrible at 400 kbps. The encoder needed more bits.

Netflix's per-title encoding (published 2015) solves this by running the encoder on each video at multiple quality levels, computing the actual quality achieved (using VMAF or SSIM as the quality metric), and finding the bitrate at which each quality level saturates. Different content needs different bitrates for the same perceptual quality.

The algorithm:
1. Encode a few "probe" encodes at different bitrates for each resolution tier
2. Measure VMAF (Video Multi-method Assessment Fusion) score for each probe
3. Fit a rate-distortion curve: quality as a function of bitrate
4. Find the bitrate at which quality plateaus — encode at that bitrate, not higher
5. Also find the minimum bitrate below which quality drops unacceptably

This produces a custom encoding ladder per video. An animated cartoon at 1080p might only need 2 Mbps (very compressible: large flat-color areas, predictable motion). A fast-paced football match at 1080p might need 8 Mbps. The traditional fixed ladder would either over-encode the cartoon or under-encode the football — per-title encoding right-sizes both.

Netflix reported ~20% overall bandwidth reduction from per-title encoding. At their scale (15% of US internet traffic), this is a massive infrastructure saving.

### 3.5 Parallel Transcoding Architecture

Transcoding is embarrassingly parallel across two dimensions:

**Across videos**: Each video is an independent job. You can run N transcoding jobs simultaneously, limited only by your fleet size.

**Within a single video**: A video can be split into temporal chunks — groups of frames called GOPs (Groups of Pictures). Each chunk can be encoded independently on a separate worker, then the encoded chunks are concatenated. This is called chunked-encoding or parallel transcoding.

```
PARALLEL TRANSCODING WITHIN ONE VIDEO
======================================

Input: raw_video.mp4 (10 minutes = 600 seconds)

Splitter Worker:
    Split into 60 x 10-second chunks
    Chunk 0: frames 0-300
    Chunk 1: frames 300-600
    ...
    Chunk 59: frames 17700-18000

Encode Workers (run in parallel):
    Worker A: encode chunk 0 at 720p H.264
    Worker B: encode chunk 1 at 720p H.264
    Worker C: encode chunk 2 at 720p H.264
    ... (60 workers in parallel)

    Worker D: encode chunk 0 at 1080p H.265
    Worker E: encode chunk 1 at 1080p H.265
    ... (another 60 workers)

Stitch Worker:
    Concatenate encoded chunks in order
    Verify frame continuity at boundaries
    Output: final 720p.mp4 + final 1080p.mp4

Total wall time: (single chunk encode time) + overhead
                 vs. 60 minutes sequential encode
```

At YouTube scale, this parallel transcoding model means a 10-minute video can be available for playback in roughly the same time as it takes to encode one 10-second chunk — potentially under a minute from upload completion to availability for viewers.

### 3.6 Brainstorming — Part 3

**Q: Why does YouTube sometimes show a video at lower quality immediately after upload, with higher qualities becoming available later?**

This is exactly the per-tier prioritization described in Part 2. When a creator finishes uploading, YouTube immediately begins encoding the lowest quality tiers — 360p and 480p. These encode fast (less data, simpler codec settings) and are made available first, so viewers can start watching within minutes even if the creator has a large following. The 1080p and 4K tiers take longer — both because there is more data to encode and because the encoder uses more computationally expensive settings for higher quality. YouTube progressively updates the video's available resolutions as each tier completes. This is why you sometimes see a newly uploaded video capped at 480p and then see 1080p appear 15–30 minutes later.

**Q: Why is AV1 not used for all content if it offers better compression?**

The encoding cost is the barrier. AV1's encoder is so much slower than H.264's that encoding a 2-hour movie in AV1 at high quality can take thousands of CPU-hours. At Netflix scale with tens of thousands of titles and new content added daily, encoding everything in AV1 would require an encoder fleet 10–50x larger than what H.264 requires. The bandwidth savings from AV1 are real — roughly 30–50% per stream — but the economics only work out for the most-viewed content, where the bandwidth savings over millions of views exceed the one-time encoding cost. For a video watched 100 times total, the AV1 encoding cost is never recovered by bandwidth savings. Platforms therefore use AV1 only for their top-N% most popular content, using H.264 or VP9 for the long tail.

**Q: What is VMAF and why does Netflix use it instead of PSNR for encoding decisions?**

PSNR (Peak Signal-to-Noise Ratio) is the traditional metric for measuring video quality after compression. It measures the mathematical difference between the original and compressed frames, pixel by pixel. The problem is that PSNR correlates poorly with human perception — a video can have high PSNR but look terrible to a human (e.g., high-frequency noise across the entire frame scores poorly on PSNR but might be perceptually invisible). Netflix developed VMAF (Video Multi-method Assessment Fusion) to solve this. VMAF uses machine learning trained on human quality ratings — the model predicts what a human would rate the quality of a compressed video relative to the original. This correlation with human perception is what makes VMAF useful for encoding decisions: if VMAF says quality is 95/100 at a given bitrate, increasing the bitrate to 96/100 is probably not worth the bandwidth cost, because humans cannot reliably perceive the difference. VMAF has become the industry standard for perceptual quality measurement and is now used by YouTube, Amazon Prime Video, and most major platforms.

---

## Part 4: HLS and DASH — The Delivery Protocols

### 4.1 The Fundamental Idea: Segment-Based Streaming

Before HLS and DASH existed, video streaming used proprietary protocols like RTSP or Adobe's RTMP. These were stateful protocols that maintained a persistent connection for the duration of playback. They were not HTTP, which meant CDNs could not cache them (CDNs work by caching HTTP responses). Firewalls often blocked them. And they were difficult to load-balance.

HLS (HTTP Live Streaming) was invented by Apple in 2009. MPEG-DASH (Dynamic Adaptive Streaming over HTTP) was standardized in 2012. Both solve the same problem with the same core idea:

**Chop the video into small segments. Serve each segment as a normal HTTP GET request. A manifest file tells the player what segments exist.**

Because each segment is served via HTTP, CDNs can cache segments exactly like any other web asset. Firewalls that pass HTTP traffic pass video segments. Load balancers that handle HTTP requests handle video segment requests. The complexity of streaming is moved to the client (the player) and the manifest format, while the delivery infrastructure remains stateless HTTP.

### 4.2 HLS — The Master Manifest and Media Playlists

An HLS stream consists of:

1. **Master Playlist** (`.m3u8`): Lists all available quality variants. The player fetches this once at startup.
2. **Media Playlist** (`.m3u8` per variant): Lists the segment files for one quality variant. The player fetches this periodically for live streams.
3. **Segment files** (`.ts` or `.mp4` fragments): The actual video data.

```
HLS MANIFEST STRUCTURE
=======================

MASTER PLAYLIST (https://cdn.example.com/video/abc123/master.m3u8)
-------------------------------------------------------------------
#EXTM3U
#EXT-X-VERSION:6

#EXT-X-STREAM-INF:BANDWIDTH=400000,RESOLUTION=426x240,CODECS="avc1.42c01e,mp4a.40.2"
/video/abc123/240p/playlist.m3u8

#EXT-X-STREAM-INF:BANDWIDTH=800000,RESOLUTION=640x360,CODECS="avc1.42c01e,mp4a.40.2"
/video/abc123/360p/playlist.m3u8

#EXT-X-STREAM-INF:BANDWIDTH=2500000,RESOLUTION=1280x720,CODECS="avc1.4d401f,mp4a.40.2"
/video/abc123/720p/playlist.m3u8

#EXT-X-STREAM-INF:BANDWIDTH=6000000,RESOLUTION=1920x1080,CODECS="avc1.640028,mp4a.40.2"
/video/abc123/1080p/playlist.m3u8

#EXT-X-STREAM-INF:BANDWIDTH=6000000,RESOLUTION=1920x1080,CODECS="hev1.1.6.L150.B0,mp4a.40.2"
/video/abc123/1080p_h265/playlist.m3u8


MEDIA PLAYLIST for 720p (https://cdn.example.com/video/abc123/720p/playlist.m3u8)
----------------------------------------------------------------------------------
#EXTM3U
#EXT-X-VERSION:6
#EXT-X-TARGETDURATION:6
#EXT-X-PLAYLIST-TYPE:VOD

#EXTINF:6.000000,
/video/abc123/720p/seg000.ts    <- segment 0: seconds 0-6
#EXTINF:6.000000,
/video/abc123/720p/seg001.ts    <- segment 1: seconds 6-12
#EXTINF:6.000000,
/video/abc123/720p/seg002.ts    <- segment 2: seconds 12-18
#EXTINF:6.000000,
/video/abc123/720p/seg003.ts    <- segment 3: seconds 18-24
... (thousands more segments for a long video)

#EXT-X-ENDLIST                  <- VOD: playlist is complete
```

### 4.3 DASH — MPD Format

DASH uses an XML-based manifest called the MPD (Media Presentation Description). The concepts are identical to HLS — quality variants, segments, manifests — but the syntax and some capabilities differ.

```xml
DASH MANIFEST (https://cdn.example.com/video/abc123/manifest.mpd)
-----------------------------------------------------------------
<?xml version="1.0" encoding="UTF-8"?>
<MPD xmlns="urn:mpeg:dash:schema:mpd:2011"
     type="static"
     mediaPresentationDuration="PT1H30M0S">

  <Period duration="PT1H30M0S">
    <!-- Video tracks -->
    <AdaptationSet mimeType="video/mp4" codecs="avc1.640028">

      <Representation id="720p" bandwidth="2500000"
                      width="1280" height="720">
        <SegmentTemplate timescale="90000"
                         media="720p/seg$Number$.mp4"
                         initialization="720p/init.mp4"
                         startNumber="0">
          <SegmentTimeline>
            <S t="0" d="540000" r="899"/>  <!-- 900 segments of 6s each -->
          </SegmentTimeline>
        </SegmentTemplate>
      </Representation>

      <Representation id="1080p" bandwidth="6000000"
                      width="1920" height="1080">
        <SegmentTemplate .../>
      </Representation>

    </AdaptationSet>

    <!-- Audio tracks -->
    <AdaptationSet mimeType="audio/mp4" codecs="mp4a.40.2">
      <Representation id="audio_128k" bandwidth="128000">
        ...
      </Representation>
    </AdaptationSet>
  </Period>
</MPD>
```

### 4.4 Segment Duration Trade-offs

The segment duration (typically 2–10 seconds) is one of the most important tuning knobs in HLS/DASH:

| Segment Duration | Advantages | Disadvantages |
|-----------------|------------|---------------|
| 2 seconds | Fast quality switching, low buffering latency | More HTTP requests, more metadata overhead, harder to achieve good compression (IDR frames every 2s) |
| 6 seconds | Good balance (Netflix default) | Quality switch takes up to 6s to take effect |
| 10 seconds | Fewer HTTP requests, better compression | Slow quality adaptation, high initial buffering if first segment slow |

The fundamental constraint is that each segment must start with a keyframe (IDR frame in H.264/H.265). The encoder must insert IDR frames at every segment boundary, which increases bitrate slightly (IDR frames are much larger than P/B frames). Shorter segments mean more IDR frames, slightly worse compression.

Netflix uses 6-second segments for VOD. YouTube uses 2-second segments for adaptive streaming. Live streaming often uses 2-second segments for faster adaptation.

### 4.5 DRM Integration — Widevine and FairPlay

Premium content (movies, sports, music videos with licensing) requires DRM (Digital Rights Management) to prevent unauthorized copying.

The two dominant DRM systems in video streaming:
- **Widevine** (Google): Used by Chrome, Android, most smart TVs, Chromecast. Three security levels: L1 (hardware-protected, required for 1080p+), L2 (rarely used), L3 (software only, limited to 480p on Netflix).
- **FairPlay** (Apple): Required for Safari and iOS. No alternative on Apple devices.

DRM in HLS/DASH works as follows:

1. During transcoding, each segment is encrypted with AES-128 (or AES-CTR for CMAF) using a content key.
2. The manifest includes a reference to a license server URL.
3. When the player encounters DRM-protected content, it sends a license request to the license server, authenticating the user's device and account.
4. The license server returns the decryption key, encrypted with a device-specific key that only the hardware DRM module can decrypt.
5. The hardware DRM module decrypts the content key and passes it to the hardware video decoder. The decrypted video never exists in unprotected memory — it goes directly from DRM module to display.

This is why screen recording a Netflix stream in Chrome produces a black screen — the video is decrypted in a protected hardware pipeline that the OS's screen capture API cannot access.

### 4.6 Brainstorming — Part 4

**Q: What is the difference between HLS and DASH in practice, and why do most platforms support both?**

At a conceptual level, HLS and DASH are nearly identical — both use HTTP-served segments and manifest files for adaptive bitrate streaming. The practical differences are driven by ecosystem support rather than technical merit. HLS was invented by Apple and remains required for Safari and iOS — there is no alternative on Apple's platform, as Safari only supports HLS for video streaming. DASH is an open standard with broader support across Android, Chrome, Firefox, and most smart TV platforms. Both have similar features: ABR, DRM support, live streaming capability, multi-track audio/subtitle support.

Most major platforms support both because they need to cover both Apple and non-Apple devices. YouTube uses DASH for most browsers (they have their own JavaScript player that parses MPD files) but falls back to HLS for iOS. Netflix uses both. The transcoding pipeline produces the video segments once — the same segment files can be referenced by both the .m3u8 and .mpd manifests. So the overhead of supporting both is primarily in manifest generation (cheap) rather than additional encoding (expensive).

**Q: How does seeking work in a segmented streaming system? Why is it faster than seeking in traditional video streaming?**

In a traditional streaming system (RTSP-based), seeking required the server to seek within the file and start sending data from the new position — a server-side operation that could take several seconds and required a stateful connection. In HLS/DASH, seeking is a client-side operation that requires no server coordination. Each segment is a fixed time range, and the manifest lists all segments with their timestamps. When the user seeks to, say, minute 43:27, the player computes which segment contains that timestamp (segment number = floor(43*60+27 / segment_duration)), constructs the URL for that segment, and issues a standard HTTP GET request. If that segment is cached in the CDN, it is served in milliseconds. If not, the CDN fetches it from origin and caches it. The player typically also pre-fetches the next 1–2 segments immediately after the seek target, so playback from the new position is seamless. This is dramatically faster and more scalable than stateful seeking because it requires no server-side state — every request is stateless HTTP.

---

## Part 5: Adaptive Bitrate Streaming (ABR) — The Intelligence Inside the Player

### 5.1 The Core Problem ABR Solves

A mobile user commuting on a train watches a YouTube video. As the train passes through dense urban areas, the LTE signal is strong: 20 Mbps available. As it enters a tunnel, bandwidth drops to 500 kbps. As it emerges, bandwidth recovers. The user expects continuous playback with no buffering, at the best quality the available bandwidth supports at each moment.

ABR (Adaptive Bitrate) streaming is the set of algorithms inside the video player that continuously decide: which quality variant should I request for the next segment?

The decision is made every segment — every 2–6 seconds. Get it right and the user has a great experience. Get it wrong in one direction (too aggressive: pick quality that exceeds available bandwidth) and the buffer drains — rebuffering. Get it wrong in the other direction (too conservative: stick to 240p when 1080p would work) and the user has unnecessary poor quality.

### 5.2 Two Families of ABR Algorithms

**Rate-Based ABR**: Estimate available bandwidth, pick the quality that fits within that bandwidth estimate.

The simplest version: measure the download time for the last segment, compute throughput = segment_size / download_time, and request the highest quality whose bitrate is below (throughput × safety_factor, where safety_factor is typically 0.8–0.9).

The problem: bandwidth estimation from segment download time is noisy. A segment might download slowly because the CDN was slow (temporary), or because bandwidth genuinely dropped, or because the TCP connection had a cold start. Reacting too quickly causes oscillation — constant quality switches up and down that the viewer sees as flickering quality.

**Buffer-Based ABR (BOLA — Buffer Occupancy Level based Lyapunov Algorithm)**: Use the current buffer fill level as the primary signal, not instantaneous bandwidth.

The insight: if the buffer is full (e.g., 30 seconds of video ahead of playback position), you can afford to request high quality — even if this segment downloads slowly, you have buffer to cover the wait. If the buffer is nearly empty (e.g., 2 seconds of video ahead), request low quality — it downloads fast and prevents rebuffering.

BOLA formalizes this as an optimization problem: maximize average quality subject to the constraint that the buffer never empties. It is rate-agnostic — it does not try to estimate available bandwidth at all.

**Hybrid ABR**: Combine bandwidth estimation and buffer state. This is what most production players use. Netflix's ABR uses bandwidth estimation for steady-state quality selection but uses buffer state as a safety valve — if the buffer drops below a threshold, immediately drop to a lower quality regardless of bandwidth estimate.

```
ABR ALGORITHM DECISION FLOW
============================

Every segment decision cycle:

[Measure inputs]
    buffer_level = (bytes in buffer) / (current bitrate)
                   -> how many seconds of video ahead
    bw_estimate   = EWMA of recent segment throughput
                   -> estimated available bandwidth

[Buffer-based safety check]
    if buffer_level < CRITICAL (e.g., 2 seconds):
        -> SELECT lowest quality (emergency, prevent rebuffer)
        -> goto [request segment]

    if buffer_level < LOW (e.g., 5 seconds):
        -> SELECT one step below current quality (cautious)
        -> goto [request segment]

[Rate-based quality selection]
    target_bitrate = bw_estimate * safety_factor (0.85)
    candidates = [all quality levels with bitrate <= target_bitrate]
    
    if buffer_level > HIGH (e.g., 20 seconds):
        -> allow upgrade: consider one step above candidates
    
    -> SELECT highest quality in candidates

[Avoid oscillation]
    if selected_quality != current_quality:
        apply hysteresis: only switch if new quality is
        significantly better/worse (avoid rapid toggling)
    
    -> EMIT: request next segment at selected_quality

[After segment downloads]
    update bw_estimate with actual download throughput
    update buffer_level with new data
    schedule next decision cycle
```

### 5.3 Startup Optimization

The startup sequence — from clicking play to the first frame — is a special case. The buffer starts at zero, so ABR cannot use buffer state. The bandwidth is unknown, so rate-based estimation has no history.

Common strategies:
1. **Start at low quality**: Request the lowest quality segment first. It downloads fast, so the first frame appears quickly. Then ramp up over subsequent segments. This prioritizes TTFF over initial quality.
2. **Probe-based startup**: Send a small probe request to estimate bandwidth before the first real segment request. Start at the quality that fits the estimated bandwidth. Adds 50–200ms latency but better initial quality.
3. **Session history**: If the user has watched videos recently from the same network, the player can use the bandwidth estimate from the previous session as a starting point. YouTube does this.

Netflix's approach: start at the lowest quality (or a pre-buffered ultra-low-quality "tip" segment), then ramp up aggressively. They prioritize sub-2-second TTFF over initial quality because users who see buffering in the first 2 seconds abandon at higher rates than users who see low quality that quickly improves.

### 5.4 Rebuffering as the Key Metric

Rebuffering (the video pauses to load more data) is the single most impactful metric for viewer experience. Research across Netflix, YouTube, and Akamai consistently shows:

- Each rebuffering event increases session abandonment probability by ~10–20%
- Rebuffering ratio > 1% causes measurable drop in user retention
- A 240p stream with zero rebuffering is preferred by users over a 1080p stream with 2% rebuffering

This is why ABR algorithms are asymmetrically conservative: they accept unnecessary quality reduction much more readily than they risk rebuffering. A brief period of 480p is invisible to most users; a 3-second buffering pause is extremely noticeable.

### 5.5 Intern → Staff Progression: ABR

**Intern**: "The player picks the video quality based on the user's internet speed."

**Junior**: "We implement a simple rate-based ABR: measure the download time for each segment, estimate available bandwidth, and request the highest quality that fits within that bandwidth with a 20% safety margin."

**Mid-level**: "We use a hybrid ABR combining buffer level and bandwidth estimation. Buffer level is the primary signal — if buffer is below 5 seconds, we drop quality regardless of bandwidth estimate. Above 20 seconds, we allow quality upgrades. We also implement hysteresis to prevent oscillation — only switch quality if the new level has been stable for 2 consecutive segments."

**Senior (L5)**: "Our ABR implementation must handle the CDN cache cold-start problem: a segment that is not cached at the CDN edge takes much longer to download than a cached segment, causing artificially low bandwidth estimates and unnecessary quality drops. We use a per-CDN-node cache-aware estimate: if we detect a cache miss (via the X-Cache response header), we exclude that download from the bandwidth EWMA to avoid polluting the estimate. We also pre-warm segments at the edge for expected-popular content."

**Staff (L6)**: "At Netflix scale, ABR is a machine learning problem. We train models per device type, per network type (WiFi vs LTE vs 5G), per geographic region, and per time-of-day. The model predicts the probability of rebuffering for each quality choice given the current context. We use offline A/B testing on historical playback data to validate model changes before rolling them out. We also run server-side ABR for some constrained environments — the client sends buffer state and network metrics to a server, which returns the quality decision. This allows us to update the ABR algorithm without a client release cycle and to use server-side information (CDN load, expected cache hit ratio) in the decision."

### 5.6 Brainstorming — Part 5

**Q: Why do ABR algorithms use EWMA (Exponential Weighted Moving Average) for bandwidth estimation rather than a simple average?**

A simple average of all historical segment download throughputs gives equal weight to a measurement from 10 minutes ago and one from 2 seconds ago. But bandwidth conditions can change dramatically within seconds — the user moves from WiFi to LTE, or a background download starts. The ABR algorithm needs to respond to current conditions, not historical averages. EWMA solves this by giving exponentially more weight to recent measurements: the estimate for the current time step is alpha × current_measurement + (1 - alpha) × previous_estimate, where alpha controls the decay rate. A higher alpha (e.g., 0.8) makes the estimate react quickly to changes but is noisy. A lower alpha (e.g., 0.1) is smoother but slow to respond. Production players often use different alphas for upward bandwidth changes (slower to increase, avoid quality oscillation) and downward bandwidth changes (faster to decrease, avoid rebuffering). This asymmetric EWMA is a well-known technique in bandwidth estimation for video streaming.

**Q: What happens to ABR when a user seeks to a new position in the video?**

A seek event is a discontinuity that invalidates most of the player's state. The buffer is cleared (or partially cleared — some players keep buffered data near the new position if it happens to be pre-fetched). The new segment starts downloading. Because the buffer starts at near-zero again, the ABR algorithm enters startup mode: it should request a low quality segment first to quickly fill the buffer and start playback from the new position, then ramp up. Many players implement a "seek startup" mode that is even more aggressive about starting at the lowest quality than normal startup, because users who seek are already engaged with the content and do not want to see the buffering indicator — they traded away quality momentarily for responsiveness. After 2–4 segments from the seek point, the player has re-estimated bandwidth and filled some buffer, and it can begin ramping quality back up normally.

---

## Part 6: CDN Architecture for Video — Making Global Delivery Possible

### 6.1 Why CDNs Are Non-Negotiable

A 4K H.264 video stream at 35 Mbps, watched by 1 million concurrent viewers: 35 Mbps × 1,000,000 = 35 Tbps of egress bandwidth. No single origin server cluster can serve this. Even if you had 350 servers each capable of 100 Gbps egress (which is not realistic), you still have the latency problem: viewers in Tokyo, London, and São Paulo all hitting your us-east-1 data center would have 100–300ms round-trip latency, which degrades TCP throughput and makes sub-2-second TTFF impossible.

CDNs (Content Delivery Networks) solve both problems: they distribute content geographically close to viewers (solving latency) and aggregate cache many viewers per edge location (solving egress capacity).

### 6.2 The Three-Tier CDN Hierarchy

```
CDN TIER HIERARCHY FOR VIDEO STREAMING
========================================

TIER 0: ORIGIN
==============
Object Storage (S3/GCS) + Origin Shield
Location: 1-3 data centers worldwide
Responsibility: canonical source of all content
Traffic: only cache misses from Tier 1 reach here
Typical cache hit: N/A (this is the source)

        |
        | (only cache misses, ~1-5% of total requests)
        |
        v

TIER 1: REGIONAL PoP (Points of Presence)
==========================================
~20-50 locations worldwide (continent level)
e.g.: North America x8, Europe x10, APAC x15, etc.
Server count per PoP: 50-500
Storage per PoP: 50-500 TB (popular content cached here)
Cache hit ratio target: 85-95% (of what reaches this tier)
CDN examples: Akamai Regional Cache, CloudFront Regional Edge

        |
        | (cache misses: ~5-15% of total requests reach Tier 0)
        |
        v

TIER 2: EDGE PoP (City Level)
==============================
~500-4000 locations worldwide (city level)
e.g.: Every major city + many secondary cities
Server count per PoP: 5-50
Storage per PoP: 2-50 TB (hot content cached here)
Cache hit ratio target: 80-95% (for popular content)
CDN examples: Cloudflare, Fastly edge nodes, Akamai edge

        |
        | (cache hits: serve directly to viewer in <10ms)
        |
        v

END USERS
=========
Viewer's device makes HTTP GET to nearest edge PoP
via Anycast DNS routing (user's DNS resolves to
nearest edge PoP IP address automatically)
RTT to edge: typically 5-30ms
RTT to regional: 20-80ms
RTT to origin: 50-300ms

EXAMPLE CACHE HIT RATIOS (combined):
- Tier 2 edge hit: ~80% of requests
- Tier 1 regional hit: ~15% of requests
- Tier 0 origin served: ~5% of requests
- Effective CDN hit ratio: ~95%
```

### 6.3 Cache Warming — Pre-Populating Edges

For highly anticipated content (a Netflix series premiere, a championship sports event, a YouTube creator's scheduled upload), waiting for the first viewer to trigger cache population is too slow. Cache warming proactively pushes content to edge nodes before any viewer requests it.

**When is cache warming used?**
- Netflix: Before a new season premiere of a popular show, they push the first episode's first segments to the top 1,000 edge nodes that serve the largest viewer populations.
- Sports streaming: A Super Bowl live stream is pre-staged at every edge node before kickoff. The first viewer's request hits cache, not origin.
- YouTube: Videos from creators with >10M subscribers are flagged for cache warming — as soon as transcoding completes, the manifest and first 2–3 minutes of segments are pushed to edge nodes in the creator's primary viewer geographies.

**How cache warming works technically:**

The transcoding pipeline's completion event triggers a cache warming job. This job has a list of target edge nodes (determined by expected viewer geography, based on creator location, audience analytics). It sends a synthetic GET request for each segment to each edge node. The edge node fetches from origin, caches the response, and subsequent real viewer requests hit cache.

The challenge: a 2-hour movie at 1080p H.264 at 6 Mbps produces ~5.4 GB of segment data. Pre-pushing to 1,000 edge nodes would require 5.4 TB of transfer just for that one quality tier. In practice, warm only the most popular quality variants (720p and 1080p) and warm the first 30 minutes — the part viewers are most likely to watch before abandoning if the content is not for them.

### 6.4 Origin Shield

A naive CDN design has all edge nodes fetching directly from origin on cache misses. If a cache miss rate of 5% applies to 35 Tbps of traffic, that is 1.75 Tbps hitting origin — still a lot. More importantly, if the CDN has 4,000 edge nodes and they all independently cache-miss for a new viral video simultaneously, they each independently hit origin, causing a thundering herd.

Origin Shield is a dedicated intermediate cache layer that all edge nodes go through on cache misses. Instead of 4,000 edge nodes independently hitting origin, they all hit the origin shield for their region, which has a single unified cache. The first request to origin shield triggers one origin fetch. All subsequent requests hit the shield's cache.

This collapses the thundering herd: 4,000 simultaneous cache misses for the same video segment produce 1 origin request (via the shield) instead of 4,000. The origin shield is typically 3–5 nodes per region with large shared caches (TB-scale).

### 6.5 Cache Key Design for Video Segments

A CDN caches responses keyed by URL (and sometimes Vary headers). For video segments, cache key design matters:

**Good design**: `https://cdn.example.com/v/abc123/720p/seg042.ts`
- The URL uniquely identifies the content. CDN caches it. Every viewer requesting this segment gets the cached response.

**Bad design**: `https://cdn.example.com/v/abc123/720p/seg042.ts?user_id=12345&session_token=xyz`
- The query parameters make each user's request a different cache key. The CDN never gets a cache hit. Every request goes to origin.

This seems obvious, but it is a subtle trap. Authorization tokens, A/B test assignments, and session identifiers must never be in the segment URL. The authorization check happens at the manifest level or via a signed URL mechanism (AWS CloudFront signed URLs, for example) — not at the segment level.

### 6.6 Anycast DNS — How Users Find the Nearest Edge

When a viewer's browser requests the video manifest, the hostname resolves to the nearest CDN edge node via anycast routing:

1. The viewer's device sends a DNS query for `cdn.example.com`
2. The DNS resolver (at their ISP or a public resolver like 8.8.8.8) queries the CDN's authoritative DNS server
3. The CDN's DNS server knows the querying resolver's IP address (and thus approximate location)
4. It returns the IP address of the closest edge PoP to that location
5. All subsequent requests to `cdn.example.com` go to that PoP

For anycast IP (used by Cloudflare and some other CDNs), multiple edge nodes advertise the same IP address via BGP. Internet routing automatically routes packets to the topologically closest node advertising that IP. This is faster for initial connection than DNS-based routing but harder to control load distribution across nodes.

### 6.7 Brainstorming — Part 6

**Q: How does Netflix's Open Connect CDN differ from a commercial CDN, and why did Netflix build their own?**

Netflix built Open Connect (announced 2012) because commercial CDNs could not give them the control and cost structure they needed at their scale. Open Connect works by placing Netflix-owned server appliances directly inside ISP networks — literally in the ISP's data center, connected to the ISP's core network. These appliances receive Netflix content proactively (Netflix pushes content to them overnight during off-peak hours) and serve it directly to the ISP's subscribers over the ISP's internal network, bypassing the public internet entirely. This means: zero transit costs (the data never crosses a CDN provider's network), sub-millisecond latency to the appliance (it is in the same network as the subscriber), and extremely high throughput (the ISP's internal network is not congested the way the internet edge can be). The trade-off is capital expenditure (Netflix owns the hardware) and operational complexity (managing thousands of appliances at ISPs worldwide). At Netflix's scale — 15% of US internet traffic — the cost savings from avoiding commercial CDN per-GB pricing justify this investment many times over.

**Q: What happens to CDN performance during a thundering herd — e.g., when a viral video gets shared and 10 million people click it within 5 minutes?**

The thundering herd is one of the most challenging operational scenarios in CDN management. In the first seconds, the video's segments are not cached anywhere — not at edge, not at regional PoPs. Every viewer's request is a cache miss. With origin shield in place, each edge PoP sends one cache-miss request to the regional PoP, which sends one to the origin shield, which sends one to origin. But with 4,000 edge nodes all missing at the same time for the same segments, the origin shield receives 4,000 requests in seconds. Modern CDNs handle this with request coalescing at every tier: if a segment is already being fetched (in-flight), subsequent miss requests for the same segment wait for the first fetch to complete and return the cached result, rather than issuing independent origin requests. Once the first edge PoP caches the segment, it fills extremely quickly to all PoPs. The worst case is the first 2–5 seconds of a viral event — after that, cache coverage reaches most of the PoP network and origin load drops dramatically.

---

## Part 7: The Long-Tail Problem — 80% of Videos Watched by Almost Nobody

### 7.1 The Pareto Distribution of Video Consumption

YouTube has roughly 800 million videos. Studies consistently show that roughly 1% of videos account for 90%+ of total views. The remaining 99% — hundreds of millions of videos — are watched a handful of times each. This is the long tail: an enormous volume of content with very little demand per piece.

This creates several hard problems:

**Storage cost**: Storing every video in 10+ quality variants × average video size means petabytes of storage for videos that will never be watched again. Is this justified?

**Transcoding cost**: Transcoding every video to the full encoding ladder — H.264, H.265, AV1, in 10 quality levels — for a video that will be watched twice ever is pure waste.

**CDN cache hit ratio**: Popular content achieves 95%+ cache hit ratios at CDN edges because many viewers request the same segments. Long-tail content achieves near-zero cache hit ratios — each view triggers an origin fetch, making CDN delivery nearly pointless for these videos.

### 7.2 Lazy Transcoding for Long-Tail Content

YouTube and similar platforms implement tiered transcoding strategies:

**Eager (immediate) transcoding**: Applied to all uploads. Produce a small set of quality variants immediately — typically 360p and 480p H.264 only. This makes the video watchable within minutes of upload.

**Demand-driven transcoding**: When a video starts receiving significant traffic (e.g., >100 views in 24 hours), the system automatically triggers additional quality tiers — 720p, 1080p. A Kafka consumer monitoring view counts fires a transcoding job when the threshold is crossed.

**Cold storage for dormant content**: Videos with no views in 6–12 months are moved to cold storage (Glacier-equivalent). If a view request arrives, the video is retrieved, and the segment is served with higher latency. The viewer may experience a longer start time (several seconds), which is acceptable for truly obscure content. Some platforms show a "warming up" message.

**Never transcode to AV1 unless popular**: The compute cost of AV1 encoding is never justified for long-tail content. Only content in the top 5–10% of views by watch time gets AV1 encoding.

### 7.3 Storage Cost Analysis

A 10-minute 1080p H.264 video at 6 Mbps:
- Raw size: 6 Mbps × 600 seconds / 8 = 450 MB
- Full encoding ladder (10 variants): ~1.5 GB stored

For 800 million videos × 1.5 GB = 1.2 exabytes of storage just for video segments, plus raw files, thumbnails, metadata.

At AWS S3 prices (~$0.023/GB/month), 1.2 exabytes = ~$27.6 billion per month in storage costs. Obviously this is not what platforms pay — they negotiate enterprise storage contracts and run their own storage infrastructure. But it illustrates why storage optimization for the long tail is not academic.

YouTube's actual storage architecture (inferred from public information):
- Highly watched content: multiple replicas, fast storage, all quality tiers
- Moderately watched content: 2 replicas, standard storage, selected quality tiers
- Rarely watched content: 1 replica (or erasure coded across fewer shards), cold storage, only lowest quality tiers
- Zero-view content after 1 year: compressed further, potentially single-region storage only

### 7.4 CDN Strategy for Long-Tail Content

For long-tail content, the CDN cache is largely useless. A video watched 5 times per year will never be cached at an edge PoP that handles millions of daily requests — the cache eviction policy will remove it before the next viewer arrives.

The strategies for serving long-tail efficiently:
1. **Serve directly from regional storage clusters** with HTTP range request support, bypassing CDN entirely for content below a view-count threshold.
2. **On-demand CDN caching**: Allow the segment to be served from origin on first request, cached at edge for a short TTL (e.g., 1 hour). If more views arrive in that hour, they hit cache. If not, the cache entry expires and storage is reclaimed.
3. **Geographic co-location**: Store long-tail content in the region closest to the creator's primary audience. A German-language cooking video is almost exclusively watched by viewers in Germany and Austria — store it in a European region only.

### 7.5 Brainstorming — Part 7

**Q: Should you store the raw (original) video file after transcoding is complete?**

This is a genuine trade-off with no universal answer. Arguments for keeping the raw file: transcoding technology improves over time. AV1 did not exist in 2015. If YouTube had kept raw video files for all 2015 uploads, they could re-encode them in AV1 now at dramatically better compression. Without raw files, re-encoding means starting from an already-compressed source, which introduces generation loss (compressing a compressed video is always worse quality than compressing the original). Arguments against keeping the raw file: raw files are enormous — professional camera footage can be 10–50× larger than the H.264 encoded version. At YouTube's scale, storing raw files alongside encoded variants could require 10–50x more storage. The cost is enormous, and the benefit only materializes if: (a) you actually re-encode those videos, (b) the re-encoding produces quality improvement that viewers can perceive, and (c) the content is still being watched when you re-encode it. In practice, YouTube keeps raw files for some duration (possibly 6–12 months) and then deletes them, re-encoding is done selectively for popular content.

---

## Part 8: Live Streaming — Real-Time Video Delivery

### 8.1 How Live Streaming Differs from VOD

Video on Demand (VOD) — the majority of YouTube and Netflix content — has a fundamental property: the entire video exists before the first viewer watches it. The transcoding pipeline can take minutes or hours. CDN cache can be warmed in advance. ABR quality variants can be pre-computed.

Live streaming has the opposite constraint: the video is being created in real-time. A segment does not exist until the encoder produces it. The transcoding must complete within seconds of the input arriving. CDN caching cannot be warm before viewing begins — the content did not exist when the first viewer connected.

### 8.2 RTMP Ingest — Getting the Live Stream In

Live streams typically begin at a streaming encoder — OBS Studio, a hardware encoder like Teradek, or a phone app. This encoder captures audio/video from the camera and microphone, compresses it in real-time (typically H.264 because it is fast enough for realtime encoding on consumer hardware), and sends it to an ingest server.

The protocol used for this: RTMP (Real-Time Messaging Protocol), developed by Macromedia in the early 2000s. RTMP is a TCP-based protocol designed for low-latency AV transport. It maintains a persistent connection and sends video/audio data in small chunks (128 bytes for video, 64 bytes for audio by default) interleaved with control messages.

Why RTMP for ingest despite being old and proprietary? Because it has extremely wide support in streaming encoders — every hardware and software encoder supports RTMP. The streaming platform uses RTMP only for the creator-to-ingest-server leg (a private connection). For viewer delivery, the platform converts the stream to HLS/DASH.

Newer ingest protocols gaining adoption:
- **SRT (Secure Reliable Transport)**: UDP-based, lower latency than RTMP over lossy networks, used by professional broadcast equipment.
- **WebRTC**: Used for ultra-low-latency interactive streaming where sub-second latency is required.

### 8.3 The Real-Time Transcoding Pipeline

```
LIVE STREAMING PIPELINE
========================

Streamer's Device (OBS / phone app / hardware encoder)
    |
    | RTMP ingest (continuous TCP stream)
    | video: H.264, audio: AAC
    v
Ingest Server (geographically closest to streamer)
    |
    | Parse RTMP stream into raw frames
    | Buffer: enough to detect keyframe boundaries
    v
Real-Time Transcoder (GPU-accelerated, must keep up with real-time)
    |  |- Output 1: 240p H.264 -> segment every 2 seconds
    |  |- Output 2: 480p H.264 -> segment every 2 seconds
    |  |- Output 3: 720p H.264 -> segment every 2 seconds
    |  |- Output 4: 1080p H.264 -> segment every 2 seconds
    |
    v
Segment Store (fast in-memory or NVMe storage)
    | Segments appended every 2 seconds
    | Media playlist updated every 2 seconds
    v
CDN Ingest (live manifest + new segments pushed to CDN)
    |
    v
CDN Edge Nodes (serve manifest + segments to viewers)
    |
    v
Viewers (ABR player polls for updated manifest every ~segment_duration)
```

The critical difference from VOD: the media playlist is continuously appended to. The player polls the manifest URL every N seconds (where N = target segment duration) to discover new segments. When the playlist has a new segment that the player has not yet downloaded, it fetches it.

### 8.4 Latency Modes in Live Streaming

Latency in live streaming is the delay between when the streamer says something and when the viewer hears it. This matters enormously for interactive content (viewers chatting with streamers) but less for broadcast content (watching a football game).

```
LIVE STREAMING LATENCY COMPARISON
===================================

STANDARD HLS / DASH:
    Encoder buffer: 2-4 segments = 4-12 seconds
    Segment size: 6-10 seconds
    CDN propagation: 2-5 seconds
    Player buffer: 2-3 segments = 12-30 seconds
    Total latency: 20-45 seconds
    Use case: broadcast TV replacement, sports (casual)

LOW-LATENCY HLS (LL-HLS, Apple) / CMAF:
    Segment size: 2 seconds, but delivered in 200ms "parts"
    Player requests parts before segment completes
    Total latency: 2-5 seconds
    Use case: sports where real-time matters, live events

WEBRTC:
    Browser-to-browser real-time video
    Uses UDP with DTLS encryption
    Latency: 100-500ms
    Use case: video calls, interactive streaming (Twitch Drops)
    Challenge: does not scale to millions of viewers
               (requires relay infrastructure like SFU/MCU)

Twitch's architecture:
    WebRTC for ultra-low latency to ~1% of viewers
    (closest to streamer geographically)
    LL-HLS / DASH for low latency to ~30% of viewers
    Standard HLS for remaining ~69%
    ABR player selects latency mode based on device capability
```

### 8.5 The Super Bowl Problem — Synchronized Spikes

Live events create the hardest scaling challenge: a single moment (kickoff, a goal, a product reveal) causes millions of simultaneous requests. At the 2012 Super Bowl on NBC Sports' streaming platform, a spike crashed the system. By 2020, streaming infrastructure had improved dramatically — but the challenge remains.

For a 100M concurrent viewer event:
- 100M viewers × (one new segment every 2 seconds) = 50M segment requests per second
- At 1 MB per segment: 50 TB/second of CDN egress
- CDN edge nodes must serve these requests simultaneously without the requests cascading to origin

The mitigation strategies:
1. **Aggressive pre-warming**: For a scheduled event (Super Bowl, Apple keynote), pre-push the initial stream segments to every edge node before kickoff. The first manifest update arrives at every edge simultaneously, and all edges are ready to serve it.
2. **Manifest caching**: The HLS manifest for a live stream updates every 2 seconds. With 100M viewers all requesting the manifest every 2 seconds, that is 50M manifest fetches/second. The manifest itself is tiny (<5KB) but the request rate is enormous. CDN edge nodes must cache the manifest with a TTL slightly shorter than the segment duration and serve from cache rather than fetching from origin per-viewer.
3. **Origin shield for live streams**: All edge nodes route manifest misses through origin shield, which fetches the manifest from the live transcoder once and serves all edge nodes from that single fetch.

### 8.6 Brainstorming — Part 8

**Q: How does a live stream DVR (rewind) feature work? Can viewers rewind to the beginning of a long live stream?**

DVR functionality in live streaming is implemented by retaining a sliding window of past segments. The standard HLS live playlist only references the most recent N segments — older ones are implicitly expired. To support DVR, the media playlist format switches to include older segments with a sliding window marker. The platform retains the actual segment files in storage for a configurable window (e.g., last 4 hours). A viewer who joins a live stream 30 minutes late can request the media playlist for 30 minutes ago, which references the segments from that time, and play from there in a "time-shifted" mode. Full DVR (rewind to the very beginning of a multi-hour stream) requires storing all segments from stream start, which at 720p H.264 is ~675 MB per hour — manageable for a few hours but expensive for 24-hour streams. Twitch, for example, retains full VOD archives of live streams (converted to VOD after the stream ends) for paying subscribers. Free users get a shorter retention window. The implementation detail is that the live stream's ingest and transcoding pipeline writes every segment to a persistent store (S3), while the live CDN delivery serves from a separate manifest that references only the current sliding window. After the stream ends, a post-processing job converts the full archive to a VOD with a complete manifest.

**Q: What is the latency impact of encryption (DRM) in live streaming?**

DRM in live streaming adds latency in several places. The initial license request requires a round trip to the license server — this happens at stream start and must complete before the first frame plays, adding 50–200ms depending on license server location. For live streams where viewers join mid-stream, this delay is acceptable. The bigger latency concern is key rotation: DRM systems periodically change the encryption key used for segments (called key rotation). If the player's current key expires while watching a live stream, it must fetch a new license before it can decrypt the next segment. If this coincides with a peak viewing moment (e.g., a touchdown), even a 100ms license fetch latency is noticeable. Well-designed systems pre-fetch the next key during segment download — the player requests the upcoming key when it sees the new key ID in the manifest, before the corresponding encrypted segments arrive. This eliminates the mid-stream license-fetch latency spike at the cost of slightly higher license server request rate.

---

## Part 9: Metadata and Search — Making Videos Discoverable

### 9.1 The Metadata Data Model

A video in a streaming system has two completely separate data layers:

**Binary content**: The actual video/audio segments stored in object storage. Addressed by URL. Served via CDN.

**Metadata**: Everything else — title, description, tags, creator info, view count, like count, upload timestamp, privacy setting, language, category, geographic restrictions, monetization settings.

Metadata lives in a relational database (PostgreSQL or MySQL) for structured querying, with high consistency requirements (view counts update atomically, privacy settings must be immediately consistent — you cannot briefly make a private video public due to an eventual consistency lag).

For YouTube-scale (800M videos), a naive single-table approach fails. The videos table would have hundreds of millions of rows with complex relationships (creator → videos, videos → tags, videos → comments). The schema must be carefully designed:

```sql
-- Core video record
videos (
    video_id        VARCHAR(11) PRIMARY KEY,  -- YouTube's 11-char IDs
    creator_id      BIGINT NOT NULL,
    title           VARCHAR(100) NOT NULL,
    description     TEXT,
    privacy         ENUM('public','unlisted','private'),
    status          ENUM('uploading','processing','available','deleted'),
    duration_ms     INT,
    upload_ts       TIMESTAMP,
    publish_ts      TIMESTAMP,
    raw_storage_key VARCHAR(512),
    -- denormalized for read performance:
    view_count      BIGINT DEFAULT 0,
    like_count      INT DEFAULT 0,
    comment_count   INT DEFAULT 0
);

-- Separate table for encoding variants (one per quality tier)
video_variants (
    video_id        VARCHAR(11),
    quality         VARCHAR(20),   -- '720p', '1080p_h265', etc.
    codec           VARCHAR(20),
    bitrate_kbps    INT,
    width           INT,
    height          INT,
    manifest_url    VARCHAR(512),
    status          ENUM('pending','encoding','available'),
    PRIMARY KEY (video_id, quality)
);

-- Tags as separate table (many-to-many)
video_tags (
    video_id        VARCHAR(11),
    tag             VARCHAR(100),
    PRIMARY KEY (video_id, tag)
);
```

### 9.2 Full-Text Search with Elasticsearch

The videos table in PostgreSQL is excellent for structured queries (get all videos by creator, get video by ID, update view count). It is terrible for full-text search (find all videos where the title or description contains "machine learning tutorial" ranked by relevance).

Full-text search for video titles and descriptions is handled by Elasticsearch, a distributed search engine built on Apache Lucene. Elasticsearch indexes the title, description, and tags of every video and maintains an inverted index: for every word (or word stem), the list of video_ids that contain that word in their searchable text.

When a user searches "machine learning tutorial":
1. The query is tokenized: ["machine", "learning", "tutorial"]
2. Elasticsearch looks up each token in the inverted index
3. The intersection of video_ids that contain all three tokens is scored using BM25 (a relevance ranking algorithm that considers term frequency, document frequency, and document length)
4. Results are ranked by BM25 score, then re-ranked by view count or watch time signals
5. The top N video_ids are returned and the API layer fetches full metadata from PostgreSQL (or a cache)

Elasticsearch is eventually consistent with the PostgreSQL source of truth. New videos are indexed asynchronously — a Kafka consumer reads video metadata events and writes to Elasticsearch. There may be a few seconds' delay between a video becoming available and it appearing in search results. This is acceptable.

### 9.3 Thumbnail Generation

Thumbnails are a significant driver of click-through rate (CTR) on video platforms. A compelling thumbnail can 3–5× a video's views versus a poor one.

**Automatic thumbnail generation**:
1. During transcoding, extract frames at regular intervals (e.g., every 10% of duration, giving 10 candidate frames)
2. Run ML scoring on each candidate frame:
   - Face detection (frames with faces get higher CTR)
   - Blur detection (reject blurry frames)
   - Aesthetic quality scoring (composition, color balance)
   - Brand safety scoring (flag inappropriate thumbnails)
3. Select the top 3 candidates and present them to the creator for selection
4. Store all candidates in object storage at multiple resolutions (for different UI contexts)

**Thumbnail sprite sheets** (for hover preview on web):
As you hover over a video's progress bar on YouTube, a thumbnail preview appears showing what the video looks like at that timestamp. This is implemented via sprite sheets: a single large image containing many small thumbnails arranged in a grid, one per time interval (e.g., one frame every 10 seconds). The player downloads this sprite sheet once and uses CSS to display the appropriate region as the user scrubs.

### 9.4 View Count at Scale — Approximate Counters

YouTube's view count is not an exact real-time counter. With 1 billion hours of views per day, incrementing a single database counter 10 billion times per day (roughly 100,000 times per second) would cause massive write contention.

The actual architecture (inferred from YouTube's engineering blog posts):
1. View events are written to a distributed log (Kafka) — each view is a Kafka record
2. A streaming aggregation layer (Flink or Spark Streaming) consumes the Kafka topic and aggregates view counts in 1–5 minute windows
3. The aggregated counts are periodically written to the database — much lower write rate than per-view updates
4. For very new, viral videos where the exact count matters for trending algorithms: a more frequent aggregation cycle (every 30 seconds)

The count displayed on the UI may be up to 5 minutes stale. YouTube explicitly shows "views" counts that are rounded or approximate ("1.2M views" vs. "1,234,567 views") for very high view counts — this indicates they are using an approximate counter for display.

### 9.5 Brainstorming — Part 9

**Q: How would you design the recommendation system integration with the video streaming architecture?**

The recommendation system is a separate subsystem from the video streaming pipeline, but they share data at several integration points. The streaming system produces the raw signals that the recommendation system consumes: view events (video_id, user_id, watch_duration, timestamp, quality_level), like/dislike events, comment events, and search-to-click events. These signals flow into the recommendation system via a Kafka topic. The recommendation system processes them offline (batch model training on Spark or similar) and online (real-time feature updates for personalization). The output of the recommendation system is a ranked list of video_ids per user — served through a recommendation API. The video streaming system's homepage and search ranking components query this API. From the streaming architecture perspective, the key design decision is that recommendation is stateless from the player's point of view: the player requests the next video and receives a video_id and manifest URL. The recommendation logic is entirely server-side. This allows the recommendation model to be updated independently of the player code, which is important because client updates (especially on smart TVs and game consoles) can take months to propagate.

---

## Part 10: The 45-Minute Interview Framework — L5 vs L6 Calibration

### 10.1 The Structure of a Strong Answer

Most video streaming interview questions are open-ended: "Design YouTube" or "Design a video streaming service." Without structure, candidates meander across components without depth anywhere. The following framework covers the key areas in 45 minutes while demonstrating genuine understanding.

**Minutes 0–5: Scope Clarification**

Do not start designing immediately. Ask clarifying questions that signal you know what the important dimensions are:

- "Are we designing for upload + playback, or primarily one direction?"
- "Is this VOD, live streaming, or both?"
- "What is the scale? Billions of views per day like YouTube, or a new product?"
- "Are we focused on a single region or globally distributed?"
- "Is premium DRM-protected content in scope, or user-generated content only?"
- "Do we need to support live streaming at Super Bowl scale, or just small creator streams?"

Good clarifying questions show you know that upload and playback are different systems, that live vs. VOD requires different architectures, and that scale determines which optimizations matter.

**Minutes 5–15: Upload and Processing Pipeline**

Sketch the upload path:
1. Client does chunked upload (TUS or multipart) to upload service
2. Raw video stored in object storage
3. Upload-complete event fires to message queue (Kafka)
4. Transcoding workers consume events, run DAG of encoding tasks
5. Outputs: manifests (.m3u8/.mpd) + segments in object storage
6. Metadata DB updated: video status → "available"

Key discussion points:
- Why chunked upload (resumability, parallelism)
- Why a DAG (parallel encoding across quality tiers, failure recovery)
- Where per-title encoding fits (mention Netflix, shows depth)
- Deduplication via content hash (shows you think about waste)

**Minutes 15–25: CDN and Playback**

Sketch the playback path:
1. Viewer's DNS request → anycast → nearest CDN edge PoP
2. Player fetches master manifest → lists quality variants
3. Player fetches media playlist for selected quality
4. Player fetches first segment (at low quality for fast start)
5. ABR loop: measure throughput, adjust quality per segment
6. Cache hit: edge → regional → origin shield → origin
7. Seek: player computes segment number, requests directly

Key discussion points:
- CDN tier hierarchy (edge → regional → origin shield → origin)
- Cache warming for popular content
- Long-tail cache miss strategy
- ABR algorithm (buffer-based, rate-based, hybrid)
- Rebuffering as the key metric

**Minutes 25–35: Deep Dive**

The interviewer will ask you to go deep on one area. Common choices:

*"Tell me more about the transcoding pipeline"* → Encoding ladder trade-offs, parallel transcoding, per-title encoding, codec selection (H.264 baseline everywhere, H.265/AV1 for popular content).

*"How would you handle the long-tail storage problem?"* → Lazy transcoding, cold storage migration, CDN strategy (skip CDN for low-view content), geographic colocation.

*"Walk me through how ABR handles a network transition"* → EWMA bandwidth estimation, buffer level monitoring, quality decision loop, hysteresis to prevent oscillation, startup sequence.

**Minutes 35–45: Failure Modes and Operations**

This is where L6 candidates separate from L5:

- What happens if the transcoding pipeline goes down? (Videos pile up in queue, creators are notified of delay, no data loss because raw file is in durable object storage)
- What happens if a CDN PoP goes down? (Anycast or DNS re-routes to next nearest PoP, increased latency for viewers in that region, origin sees increased load)
- What if the origin goes down? (Cached content continues serving from CDN until TTL expires, new content unavailable, streaming continues for cached segments)
- How do you detect quality problems before viewers complain? (Client-side metrics: TTFF, rebuffering ratio, quality switches per minute — reported to backend analytics, aggregated, alerting on degradation)

### 10.2 L5 vs L6 Calibration

**L5 Answer Characteristics**:
- Correctly identifies the two main paths (upload vs. playback)
- Knows that CDN is required and explains cache hierarchy
- Understands HLS/DASH at the concept level (manifests + segments)
- Can describe ABR at a high level (picks quality based on bandwidth)
- Knows the encoding ladder exists and why
- Discusses failure recovery for the transcoding pipeline
- Makes reasonable database schema choices for metadata

**L6 Answer Characteristics**:
- All of the above, plus:
- Quantifies scale accurately and uses it to drive decisions (500 hours/min → fleet size calculations)
- Distinguishes codec trade-offs concretely (H.264 vs H.265 vs AV1: encode time, bandwidth savings, device support)
- Understands per-title encoding and why it matters at Netflix scale
- Can explain BOLA or hybrid ABR with actual algorithm logic
- Discusses origin shield and request coalescing for thundering herd
- Addresses long-tail explicitly with tiered transcoding and storage strategy
- Knows DRM integration at the manifest/segment encryption level
- Discusses operations: metrics, alerting, what breaks and why
- Mentions real incidents to demonstrate lived knowledge

### 10.3 Key Trade-offs to Drive Discussion

These are the trade-offs that reveal depth. Mention them proactively:

| Trade-off | Option A | Option B | When to pick A vs B |
|-----------|----------|----------|---------------------|
| Segment duration | 2s (fast adaptation) | 10s (better compression, fewer requests) | 2s for live/interactive; 6-10s for VOD |
| Codec coverage | H.264 only (universal) | H.264 + H.265 + AV1 (optimal) | H.264 only for MVP; tiered by content popularity |
| Transcoding eagerness | Transcode all variants immediately | Lazy transcode on demand | Immediate for popular creators; lazy for long tail |
| CDN strategy | Commercial CDN (Cloudflare/Akamai) | Own CDN (Netflix Open Connect) | Commercial for <$100M/year traffic; own CDN for Netflix scale |
| Live latency | Standard HLS (20-30s) | LL-HLS/CMAF (2-5s) | Standard for broadcast; LL for interactive |
| View count consistency | Strong consistency (exact) | Eventual (5-min staleness) | Strong for billing/moderation; eventual for display |

### 10.4 Common Mistakes at Each Level

Interviewers at L5/L6 see these mistakes repeatedly. Avoid them:

**Mistake 1**: "I'll put all the video data in S3 and serve directly from S3."
Fix: S3 is the origin. CDN is required. Explain the CDN tier hierarchy.

**Mistake 2**: Designing only the happy path.
Fix: Always discuss what happens when a component fails. Transcoding worker failure, CDN PoP failure, database unavailability.

**Mistake 3**: Treating upload and playback as the same system.
Fix: These are fundamentally different traffic patterns (write-heavy async vs. read-heavy sync). Make the separation explicit.

**Mistake 4**: Ignoring the long tail.
Fix: Explicitly mention that 99% of content gets very few views and requires a different cost strategy (lazy transcoding, cold storage, CDN bypass).

**Mistake 5**: ABR described as "it automatically adjusts quality."
Fix: Describe the actual mechanism — segment-by-segment decision based on buffer level and bandwidth estimation. Mention BOLA or hybrid approaches.

**Mistake 6**: Not quantifying anything.
Fix: Know the key numbers cold (500 hours/min uploaded, 1B hours/day watched, 35 Mbps for 4K, <2s TTFF target). Use them to justify architectural choices.

### 10.5 Brainstorming — Part 10

**Q: How should a candidate handle the situation where they do not know a specific detail the interviewer is asking about?**

This is a meta-skill that separates strong candidates from weak ones. If an interviewer asks "Can you walk me through exactly how BOLA computes the quality decision?" and you cannot recall the specifics, the worst response is to guess and be wrong — that signals overconfidence and inaccuracy. A better response is to describe what you know at the level of abstraction you are confident about: "I know BOLA is a buffer-based ABR algorithm that frames the quality selection as an optimization problem maximizing average quality subject to a buffer-constraint, without requiring bandwidth estimation. I do not remember the exact Lyapunov formulation, but the key insight is that if the buffer is full, you can request high quality — if it is nearly empty, you request low quality to refill it quickly." This demonstrates you understand the concept even if you cannot produce the formula. Then pivot: "In practice I would validate the algorithm choice by A/B testing against a rate-based baseline and measuring rebuffering ratio and mean quality metrics." This shows engineering judgment, which is more valuable than memorized formulas.

**Q: The interviewer says "your system needs to handle 1 million concurrent live viewers for a single stream." How do you approach the calculation?**

First translate the user-facing requirement into system-level numbers. 1 million concurrent viewers each requesting one new segment every 2 seconds = 500,000 segment requests per second. At 1 MB per segment average, that is 500 GB/second = 4 Tbps of egress bandwidth from the CDN for this single stream. A typical CDN edge PoP can serve 10–100 Gbps. So we need at least 40–400 edge PoPs engaged for this stream. Since major CDNs have 4,000+ PoPs, the aggregate capacity is more than sufficient if the load is distributed across them. But the manifest is the chokepoint: 1 million viewers each polling the manifest every 2 seconds = 500,000 manifest requests/second. The manifest is tiny (<5 KB) but the request rate is enormous. Manifests must be cached at every edge with a 1-second TTL — and the CDN must serve from cache even before the TTL expires, using a stale-while-revalidate strategy. The live transcoder produces a new manifest every 2 seconds and pushes it to the origin shield, which propagates to all edge nodes. This keeps the origin shield handling only one manifest fetch per 2-second interval globally, not 500,000.

---

## Part 11: Real Incidents and Operational Lessons

### 11.1 Netflix and the 2012 Super Bowl — The Birth of Proactive Resilience

While Netflix did not host the Super Bowl, the 2012 Super Bowl broadcast on NBC highlighted the fragility of streaming infrastructure under synchronized load. NBC Sports' streaming platform, serving the game online for the first time to millions of viewers simultaneously, experienced significant degradation at kickoff — exactly when everyone pressed play at the same moment. The root cause was a classic thundering herd: millions of clients simultaneously requested the stream manifest, all received cache misses (the stream had just started), and all requests cascaded to origin. The origin could not handle the flood.

This incident and similar ones at Netflix shaped modern CDN design. Netflix's response, developed over subsequent years with Open Connect:

1. **Pre-positioning**: Netflix identified that popular content (a new season premiere) creates a predictable spike at midnight Pacific time (when new episodes release). They began pre-pushing not just segments but entire first episodes to high-traffic edge nodes in the 4 hours before release. By the time users hit play, every segment was already cached.

2. **Jitter in client polling**: A million Netflix apps all polling for the manifest at exactly midnight would overload even a well-architected system. Netflix introduced random jitter in polling intervals — instead of every app polling at exactly T=0, apps poll at T=0 + random(0, 30) seconds. This spreads the load across 30 seconds instead of a single instant.

3. **Graduated release**: Instead of making a new show available globally at midnight Pacific simultaneously, Netflix staggers release by region — Pacific first, then Eastern, then Europe, then Asia. This turns a single global spike into a series of smaller regional spikes that the system handles sequentially.

The lesson: synchronized user behavior is the enemy of scalable systems. Wherever you see millions of users doing the same thing at the same time, introduce mechanisms to de-synchronize them.

### 11.2 YouTube's 2018 AV1 Rollout — Compute vs. Bandwidth Trade-off at Scale

In 2018, YouTube began rolling out AV1 encoding, a new royalty-free codec that promised 30–50% bandwidth savings over VP9 (which YouTube was already using instead of H.264 on most desktop clients). The rollout took approximately 6 months and required encoding the YouTube library — hundreds of millions of videos — in the new codec.

The technical challenges:

**Encoding speed**: AV1 encoding in 2018 was 10–100x slower than H.264 encoding with equivalent quality settings. Encoding even a subset of YouTube's library required months of continuous work on a large compute cluster. YouTube had to prioritize: which videos to encode first? The answer was by view count — the top 1% of videos by watch time accounted for the majority of bandwidth. Encoding the top 1% first achieved most of the bandwidth savings immediately.

**Decoder availability**: AV1 can only be used on devices with AV1 decoder support. In 2018, this meant Chrome on desktop (software AV1 decode available from Chrome 70) and almost nothing else. Hardware AV1 decoders began appearing in 2020–2021 on Apple Silicon, new Android chips, and Intel 11th-gen CPUs. YouTube served AV1 only to clients that advertised AV1 support in their Accept header — other clients continued to receive VP9 or H.264.

**The result**: YouTube reported ~30% bandwidth reduction on AV1-decoded streams vs. their previous VP9 streams. At YouTube's scale (millions of terabits of video served daily), this 30% reduction represents enormous infrastructure cost savings. The 6-month encoding project cost significant compute, but the ongoing bandwidth savings justify it many times over.

The lesson: encoding costs are one-time; bandwidth savings are perpetual. For content watched millions of times, the math strongly favors re-encoding with better codecs even at high encoding cost.

### 11.3 TikTok's CDN Expansion and the Challenge of Regional Content

TikTok's global expansion from China (where it operated as Douyin) to Western markets created a unique CDN challenge. The content consumption patterns on TikTok differ fundamentally from YouTube: TikTok's algorithm serves highly personalized feeds, meaning different users watch completely different content even at the same moment. The cache hit ratio — the fraction of CDN requests served from cache — is inherently lower than YouTube's, because YouTube's top content gets millions of views (high CDN cache utility) while TikTok's algorithm distributes views more broadly.

TikTok's response to the CDN challenge has evolved in several directions (inferred from infrastructure talks and job postings):

**Aggressive prefetching**: TikTok's mobile app prefetches not just the current video but the next 2–3 videos the algorithm predicts the user will watch. This trades bandwidth (downloading videos the user might not watch) for seamless playback (no buffering because the next video is already fully downloaded). For short 15-second videos, prefetching 3 videos ahead costs roughly 3 × 5 MB = 15 MB of data download — acceptable on most mobile connections.

**Regional content tiering**: TikTok categorizes content into global (watched everywhere), regional (watched primarily in one country or region), and local (watched almost exclusively in a single city or area). Regional and local content is cached only in geographically appropriate CDN nodes. A video primarily watched by users in Brazil need not be cached at CDN nodes in Germany — caching it only in Latin American nodes reduces storage cost while maintaining hit ratio for the relevant viewers.

**Multi-CDN strategy**: TikTok uses multiple CDN providers simultaneously (Akamai, Cloudflare, and their own infrastructure). The client's manifest request is routed to the best CDN for that viewer's location at that moment, based on real-time performance data. If Akamai's performance degrades in a region, traffic shifts to Cloudflare. This redundancy prevents single-CDN outages from affecting viewers.

The lesson: CDN strategy must match your content distribution pattern. YouTube-style CDN design assumes high cache hit ratios from popular content. TikTok-style requires a different approach: aggressive prefetching to the client device to compensate for lower CDN hit ratios.

### 11.4 The 2022 YouTube Infrastructure Incident — Database Schema Migration

In early 2022, YouTube experienced a significant service degradation related to a database schema migration that went wrong at scale. While YouTube has not published a full postmortem, the engineering community pieced together the incident from status page updates and engineering comments.

The core lesson (applicable generally): database schema migrations on billion-row tables require special handling. Adding a column, changing a data type, or adding an index on a 800-million-row table is not a simple ALTER TABLE operation. At YouTube scale:

- A naive ALTER TABLE to add a column can lock the table for minutes to hours
- An online schema change (pt-online-schema-change or gh-ost) generates significant additional load on the database as it copies rows to a new table
- If the migration fails halfway, rollback is expensive (reversing the online copy)

YouTube's standard practice (based on their engineering blog) is to dual-write during migrations: the application writes to both old and new schema simultaneously for a period, reads from the old, then gradually shifts reads to the new schema, then stops writing to the old. This makes migrations safe but slow — weeks or months for large schema changes.

The operational lesson: at YouTube scale, there is no such thing as a "quick database change." Every migration is a months-long project with careful rollout planning.

### 11.5 Operational Metrics — What You Monitor in Production

A video streaming system requires monitoring at multiple levels:

**Infrastructure metrics** (collected by monitoring systems like Prometheus/Datadog):
- CDN cache hit ratio per PoP and globally
- CDN edge node throughput and error rates
- Transcoding job queue depth and processing latency
- Upload service request rate and error rate
- Object storage request rate, latency, and error rate

**Player-side metrics** (collected by client SDK, sent to backend analytics):
- Time to First Frame (TTFF): from play button click to first frame rendered
- Rebuffering ratio: fraction of playback time spent buffering
- Quality distribution: what fraction of playback time was at each quality level
- Quality switch rate: how often the ABR algorithm changed quality (high rate = network instability or poor ABR)
- Initial startup quality: what quality level was requested for the very first segment

**Business metrics** (derived from player metrics and engagement data):
- Session abandonment rate during startup (correlated with TTFF)
- Session abandonment rate during playback (correlated with rebuffering)
- Rebuffering-attributable churn (long-term subscriber churn correlated with playback quality)

Alert thresholds:
- TTFF p95 > 3 seconds: page on-call
- Rebuffering ratio > 0.5%: page on-call
- CDN cache hit ratio < 80%: page on-call
- Transcoding queue lag > 30 minutes: page on-call

### 11.6 Brainstorming — Part 11

**Q: What would you do on-call if you saw the CDN cache hit ratio drop from 95% to 60% suddenly?**

A sudden drop in CDN cache hit ratio is a serious incident — it means origin is receiving 2.5x more traffic than normal, which can cascade into origin overload and viewer-facing errors. The immediate response is to investigate the cause before taking any action, because the mitigation depends entirely on the root cause. Check whether the drop is global (all edge PoPs) or regional (one or a few PoPs). If regional, the likely cause is a CDN PoP failure causing traffic to reroute to a different PoP that does not have the same cached content — the fix is ensuring the CDN provider is addressing the PoP failure and monitoring the rerouted traffic load. If the drop is global, check whether the CDN cache key has been accidentally changed — a code deployment that added a query parameter or changed the URL structure for segments would make every existing cached URL a miss. Roll back the deployment if that is the cause. Also check whether there is a sudden traffic spike from new viral content — cache hit ratio naturally drops temporarily when a new video goes viral because no edge has cached its segments yet. In this case, the fix is triggering a cache warming job for the viral video. While investigating, place the origin shield in high-capacity mode (if the CDN supports this) to prevent the increased miss traffic from overwhelming origin.

**Q: A creator complains their video looks worse than expected at 1080p. What is your debugging process?**

The "video looks bad at 1080p" complaint has multiple potential causes, and diagnosing it requires systematic elimination. First: confirm that the viewer is actually receiving 1080p. The player's debug overlay (most players have one) shows current quality level, and the CDN response headers show whether the request was served from cache or origin. If the viewer is on 1080p but quality looks poor, the issue is the encoding quality, not the delivery. Second: check which codec the viewer received — a browser receiving H.265 might have a software decoder with different quality characteristics than a browser receiving H.264. Third: examine the source video. If the creator uploaded a heavily compressed 1080p source (e.g., a 1080p video that had already been compressed to low bitrate before upload), the transcoded output will also look poor because you cannot recover information that was discarded in prior compression — this is generation loss. The platform's transcoder cannot invent quality that was not in the source. Fourth: check whether the video's per-title encoding parameters resulted in an unusually low bitrate allocation. The VMAF quality metric might have scored the video's visual complexity as low (e.g., if it is a screen recording with a lot of static content), resulting in a lower bitrate assignment that a human perceives as poor quality for their specific content type. The resolution: re-encode with higher quality settings for that video, or explain to the creator that source quality limits transcoded quality.

---

## Part 12: Putting It All Together — End-to-End System Diagram

```
COMPLETE VIDEO STREAMING SYSTEM
================================

CREATOR SIDE (Upload Path)
===========================

[Camera / Screen Recorder]
        |
        | Raw video (H.264/ProRes/etc. in MP4/MKV)
        v
[Creator's Device - Upload Client]
  - Computes SHA-256 hash of file
  - Splits file into 50MB TUS chunks
        |
        | TUS PATCH requests (HTTPS)
        v
[Load Balancer / API Gateway]
        |
        v
[Upload Service Cluster]
  - Tracks per-upload offset in Redis
  - Checks SHA-256 hash in dedup store (Redis/DynamoDB)
  - Forwards chunks to S3 via Multipart Upload API
        |
        |--- On completion: write event to Kafka (topic: video.uploads)
        |--- Update video record: status = "processing"
        |
        v
[Raw Video Storage — S3/GCS]
  (raw_uploads/creator_id/video_id/raw.mp4)

        |
        | Kafka consumer: TranscodingOrchestrator
        v
[Transcoding Orchestrator — Temporal Workflow Engine]
  DAG tasks:
        |
        +-- [Demux Worker]: split audio/video streams
        |         |
        |         v
        |   [Audio Encoder Workers (parallel)]
        |     - AAC 128kbps
        |     - AAC 256kbps (for HD content)
        |         |
        |         v
        |   [Audio segments in S3]
        |
        +-- [Video Encoder Workers (parallel)]
        |     Group A (fast, low quality — publish first):
        |       - 360p H.264
        |       - 480p H.264
        |     Group B (medium quality):
        |       - 720p H.264
        |       - 720p H.265
        |     Group C (high quality — may lag):
        |       - 1080p H.264
        |       - 1080p H.265
        |       - 1080p AV1 (only if popular enough)
        |       - 4K H.264/H.265 (if source is 4K)
        |         |
        |         v
        |   [Video segments in S3]
        |   (processed/video_id/720p/seg000.ts ... segN.ts)
        |
        +-- [Thumbnail Worker]
        |     - Extract frames at 10% intervals
        |     - ML quality scoring
        |     - Store top 3 candidates in S3
        |     - Generate sprite sheet for hover preview
        |
        +-- [Subtitle Worker (if auto-captions enabled)]
              - ASR (Automatic Speech Recognition) pipeline
              - Store .vtt files in S3
                    |
        +-----------+-----------+
        |                       |
        v                       v
[Manifest Generator]    [Metadata Writer]
  - Create master.m3u8    - Update video DB:
  - Create manifest.mpd     status = "available"
  - Store in S3             available_qualities = [...]
        |                 - Write to Elasticsearch index
        |                 - Emit event: video.available
        |
        v
[CDN Pre-warm Job] (if creator has >1M subscribers)
  - Push manifest + first 5 segments to top-100 edge nodes
    in creator's primary viewer geographies


VIEWER SIDE (Playback Path)
============================

[Viewer's Device — Browser / Mobile App / Smart TV]
        |
        | DNS lookup: cdn.example.com
        v
[Anycast DNS] → routes to nearest CDN edge PoP IP
        |
        | HTTPS GET /v/abc123/master.m3u8
        v
[CDN Edge PoP — City Level]
  ┌─────────────────────┐
  │ Cache check:         │
  │  HIT → serve (5ms)  │
  │  MISS → fetch from  │
  │         Regional PoP │
  └─────────────────────┘
        |
        | (on cache miss)
        v
[CDN Regional PoP — Continent Level]
  ┌─────────────────────┐
  │ Cache check:         │
  │  HIT → serve (20ms) │
  │  MISS → fetch from  │
  │         Origin Shield│
  └─────────────────────┘
        |
        | (on cache miss)
        v
[Origin Shield — 3-5 nodes per region]
  ┌────────────────────────────────────────┐
  │ Cache check:                            │
  │  HIT → serve                           │
  │  MISS → fetch from Object Storage      │
  │ Request coalescing: multiple edge misses│
  │ for same segment → 1 origin request     │
  └────────────────────────────────────────┘
        |
        | (on cache miss, ~5% of all requests)
        v
[Object Storage — S3/GCS]
  (processed/video_id/720p/seg042.ts)


PLAYER ABR LOOP (runs on viewer's device)
==========================================

Every 2-6 seconds (per segment):

[Download segment at current quality]
        |
        | Measure: actual_throughput = bytes / download_time
        v
[Update bandwidth EWMA]
  bw_estimate = 0.7 * bw_estimate + 0.3 * actual_throughput
        |
        v
[Compute buffer_level]
  buffer_level = bytes_buffered / current_bitrate (in seconds)
        |
        v
[Quality Decision]
  if buffer_level < 2s:         → select LOWEST quality
  elif buffer_level < 5s:       → select one step DOWN
  elif buffer_level > 20s:      → consider one step UP
  else:                         → select quality at 0.85 * bw_estimate
        |
        v
[Hysteresis check]
  only switch if new quality differs from current for 2+ cycles
        |
        v
[Request next segment at decided quality]
  GET /v/abc123/{quality}/seg{n+1}.ts
```

---

## Common Interview Mistakes — 6 to Avoid

**Mistake 1: Treating video streaming as a simple file hosting problem.**
The candidate says: "Upload to S3, serve from CDN, done." This fails to address the upload pipeline (chunked upload, deduplication), transcoding (why, how, what codecs, how parallelized), ABR (how quality adaptation actually works), and the CDN cache strategy (warming, long-tail, origin shield). The interviewer is testing whether you understand that video streaming is a purpose-built system, not commodity file hosting.

**Mistake 2: Describing ABR as a black box.**
"The player automatically adjusts quality" is not an answer — it is a restatement of the question. A strong answer describes the mechanism: segment-by-segment decisions, buffer level as the primary safety signal, bandwidth estimation via EWMA, quality switching with hysteresis to prevent oscillation. If you cannot explain how ABR works mechanistically, you cannot discuss failure modes, tuning, or trade-offs.

**Mistake 3: Forgetting the long tail.**
YouTube has 800 million videos. Most have nearly zero views. Designing as if all content is as popular as "Baby Shark" — with full encoding ladders, aggressive CDN caching, and immediate AV1 encoding — produces an astronomically expensive design. L6 candidates proactively address the long tail: lazy transcoding, cold storage migration, CDN bypass for sub-threshold content, geographic colocation.

**Mistake 4: Ignoring the operational dimension.**
After designing the happy path, the interviewer expects discussion of: what breaks, how you detect it, how you recover. Candidates who stop at the architecture diagram without discussing monitoring (TTFF, rebuffering ratio), alerting thresholds, and failure scenarios leave a significant part of the L6 bar unaddressed. Video streaming has measurable, well-defined metrics — use them.

**Mistake 5: Not distinguishing VOD from live streaming.**
Live streaming requires real-time transcoding (fundamentally different from batch transcoding), has strict latency requirements (2 seconds to 30 seconds depending on mode), and creates synchronized viewer spikes at event start. Conflating VOD and live streaming architecture shows you have not thought through the design space.

**Mistake 6: Missing the CDN request coalescing / origin shield concept.**
Many candidates know CDN caches content. Far fewer understand how CDNs handle the thundering herd — when a viral video's first viewer requests a segment not yet cached, and 10,000 simultaneous viewers make the same request. Without origin shield and request coalescing, all 10,000 requests hit origin simultaneously. Origin shield is not obvious knowledge — knowing it demonstrates genuine operational experience or deep study.

---

## Exercises

**Exercise 1**: Calculate the transcoding fleet size needed to process YouTube's upload volume (500 hours/minute) assuming each minute of video at 1080p H.264 takes 2 minutes to encode on a single CPU core, and the platform produces 8 quality variants per video. Show your work.

**Exercise 2**: Design the database schema for a video streaming platform's video metadata, supporting: video CRUD, per-creator video listing, tag-based search, and view count reads (high throughput, approximate OK). Justify your indexing choices.

**Exercise 3**: Trace the full request path for a user who clicks play on a video, encounters a cache miss at the CDN edge, and successfully streams the first 30 seconds. Include all network round trips, cache lookups, and data transfers. Estimate total latency from click to first frame.

**Exercise 4**: Implement a simplified ABR algorithm in pseudocode. It should select quality based on buffer level and bandwidth estimate, with hysteresis to prevent oscillation. Include the buffer-level thresholds, quality transition logic, and EWMA bandwidth update.

**Exercise 5**: A creator uploads a 4K 60fps video. The platform must produce the full encoding ladder (8 quality variants) in under 10 minutes of wall-clock time using parallel transcoding. Design the parallel transcoding architecture, including temporal chunking strategy, worker assignment, and stitch step.

**Exercise 6**: Design the cache warming strategy for a streaming platform hosting a major live sports event (championship game, expected 5 million concurrent viewers). Specify: which content to warm, when, to which CDN nodes, and how to handle the manifest update cadence during the live stream.

**Exercise 7**: The platform wants to migrate from serving H.264 to serving AV1 for its top 10% of videos by view count. Design the migration strategy: how to identify eligible videos, how to run the re-encoding without impacting live traffic, how to roll out AV1 serving incrementally, and how to measure success.

**Exercise 8**: Implement a simplified TUS server that handles chunked upload with resumability. The server should: create uploads (POST), handle chunk uploads with idempotent PATCH (same chunk resent should not double-write), handle progress queries (HEAD), and emit a completion event when the full file is received.

---

## Homework

**Homework 1**: Watch Netflix's 2015 Tech Blog post on per-title encoding (search "Netflix per-title encoding optimization"). Summarize the algorithm they use for finding the optimal encoding parameters per video. Then find their 2018 follow-up on Dynamic Optimizer. What improvement did it add?

**Homework 2**: Open YouTube in Chrome, start playing a video, open Chrome DevTools → Network tab, filter by ".m3u8" or ".mpd". Observe the manifest fetch and the segment requests. Identify: the segment size, the quality variant being served, and the request rate. Change your network throttling (DevTools → Network → Throttling) and observe how the quality changes. Write a paragraph describing what you observed about the ABR algorithm in action.

**Homework 3**: Read Apple's WWDC 2019 talk on Low-Latency HLS (available on developer.apple.com). Understand how LL-HLS achieves 2–3 second latency vs. standard HLS's 20–30 seconds. Write up the key protocol changes that enable this: partial segments, rendition reports, and blocking playlist reload.

**Homework 4**: Design a system for storing and serving video thumbnail previews during seek (the hover effect on YouTube's progress bar). The system must serve a specific frame from any timestamp in the video within 50ms p95. Consider two approaches: (a) pre-generate sprite sheets at upload time, (b) serve on-demand from video segments. Analyze the storage, compute, and latency trade-offs for each approach. Which would you choose for YouTube scale?

**Homework 5**: Study Cloudflare's Stream product (https://developers.cloudflare.com/stream/) and Netflix's Open Connect (https://openconnect.netflix.com). Write a 500-word comparison of: how each CDN is architected, what trade-offs each makes, and which approach scales better to the 1 exabyte/month egress level.

---

## KEY TAKEAWAYS

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                    KEY TAKEAWAYS: VIDEO STREAMING                          ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  1. TWO SYSTEMS, NOT ONE                                                     ║
║     Upload path (async, compute-heavy, write-once) and playback path         ║
║     (sync, read-heavy, globally distributed) are architecturally distinct.   ║
║     Treat them separately in your answer.                                    ║
║                                                                              ║
║  2. CHUNKED UPLOAD IS NON-NEGOTIABLE                                         ║
║     TUS protocol or equivalent: resumability, parallelism, progress          ║
║     reporting. Never upload a video as a single HTTP body.                   ║
║                                                                              ║
║  3. TRANSCODING IS A DAG                                                     ║
║     One video → 10+ quality variants in parallel. Per-title encoding         ║
║     (Netflix) right-sizes bitrate per content complexity. H.264 everywhere;  ║
║     H.265/AV1 for high-traffic content only.                                 ║
║                                                                              ║
║  4. HLS/DASH: MANIFESTS + SEGMENTS                                           ║
║     Master manifest → lists quality variants.                                ║
║     Media playlist → lists segment URLs per quality.                         ║
║     Segments: 2–10 seconds of video, served as plain HTTP.                   ║
║     Seeking = computing segment number, GET that segment.                    ║
║                                                                              ║
║  5. ABR = BUFFER + BANDWIDTH                                                 ║
║     Buffer level is the safety signal (< 2s → lowest quality immediately).   ║
║     Bandwidth EWMA drives quality selection when buffer is healthy.           ║
║     Rebuffering ratio is THE metric. 0.1% is the target.                     ║
║                                                                              ║
║  6. CDN HIERARCHY: EDGE → REGIONAL → SHIELD → ORIGIN                        ║
║     95%+ of requests should be served from edge cache.                       ║
║     Origin shield collapses thundering herds via request coalescing.          ║
║     Cache warm popular content proactively. Bypass CDN for long tail.        ║
║                                                                              ║
║  7. THE LONG TAIL IS MOST OF YOUR CONTENT                                    ║
║     99% of videos get <1% of views. Lazy transcode on demand.                ║
║     Cold storage for dormant videos. Skip CDN for sub-threshold content.     ║
║                                                                              ║
║  8. LIVE STREAMING: RTMP IN, HLS/DASH OUT                                    ║
║     Real-time transcoding (must keep up, can't batch).                       ║
║     Standard HLS: 20–30s latency. LL-HLS: 2–5s. WebRTC: <500ms.            ║
║     Synchronized spikes at event start require pre-warming + jitter.         ║
║                                                                              ║
║  9. METRICS DRIVE OPERATIONS                                                 ║
║     TTFF, rebuffering ratio, quality distribution, CDN cache hit ratio.      ║
║     Collect player-side metrics. Alert on degradation before users complain. ║
║                                                                              ║
║  10. THE INTERVIEW WIN                                                        ║
║     Know the numbers cold. Separate upload from playback. Explain ABR        ║
║     mechanistically. Address the long tail. Discuss what breaks and why.     ║
║     Know at least one real incident.                                          ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

---

## One-Sentence Summary

> "Video streaming = upload pipeline (TUS chunked upload → DAG transcoding into 10+ quality variants in multiple codecs) + CDN delivery (three-tier hierarchy with origin shield and cache warming, 95%+ hit ratio) + adaptive bitrate streaming (player selects quality per segment based on buffer level and bandwidth estimate, optimizing for sub-0.1% rebuffering) — the interview is won by knowing how all three interact under failure, not each piece in isolation."

---

*This chapter pairs with Chapter 71 (Media Upload Pipeline), Chapter 56 (Distributed Cache), Chapter 33 (Event-Driven Architecture with Kafka), and Chapter 64 (Recommendation Systems).*

---

## Part 13: Deep Dive — Storage Architecture for Video at Scale

### 13.1 Why Object Storage Is the Right Choice

Video segments are immutable blobs — once a segment is written by the transcoder, it is never modified. It is only read (many times) or deleted. This access pattern is a perfect fit for object storage:

- **Write once, read many**: S3/GCS is optimized for this. Objects are replicated for durability the moment they are written.
- **Immutable content addressed**: A segment URL contains the video_id, quality, and segment number. It never changes. This makes HTTP caching trivial (Content can be cached forever — the URL itself encodes the version).
- **Infinite horizontal scale**: Object storage scales storage capacity and request throughput horizontally. You do not need to shard video segments across database tables or worry about hot partitions.
- **Decoupled from compute**: The transcoding fleet can write to object storage at full speed. CDN nodes can read from object storage independently. There is no tight coupling.

The alternative — block storage (EBS, GCE Persistent Disk) — fails at video scale because block volumes are attached to specific VMs. Serving from block storage requires the serving VM to be up. Object storage is addressed by URL and can be served by any node with network access to the storage backend.

### 13.2 Object Storage Structure and Naming Convention

The naming convention for objects in storage matters for CDN cache key design, operational debugging, and bulk operations (transcoding pipeline writing, cleanup jobs deleting old files).

A production-quality naming convention:

```
OBJECT STORAGE NAMESPACE DESIGN
================================

Raw (pre-transcoding) uploads:
raw/{creator_id}/{video_id}/original.{ext}
raw/{creator_id}/{video_id}/metadata.json

Transcoded segments:
processed/{video_id}/hls/{quality}/seg{n:06d}.ts
processed/{video_id}/hls/{quality}/init.mp4      (CMAF)
processed/{video_id}/dash/{quality}/seg{n:06d}.m4s
processed/{video_id}/dash/{quality}/init.mp4

Manifests:
manifests/{video_id}/master.m3u8
manifests/{video_id}/manifest.mpd
manifests/{video_id}/hls/{quality}/playlist.m3u8

Thumbnails:
thumbnails/{video_id}/thumb_{size}.jpg            (240x135, 480x270, etc.)
thumbnails/{video_id}/sprite_{interval}s.jpg      (hover preview sprites)
thumbnails/{video_id}/sprite_{interval}s.vtt      (WebVTT index for sprites)

Subtitles / Closed Captions:
subtitles/{video_id}/{language_code}/subs.vtt
subtitles/{video_id}/{language_code}/subs.srt

Segment numbering is zero-padded to 6 digits (seg000042.ts) so lexicographic
sort equals chronological sort — critical for bulk cleanup operations.

quality encoding:
  240p    -> "240p"
  1080p_h265 -> "1080p_h265"
  4k_av1  -> "2160p_av1"
  (always lowercase, underscores, resolution first)
```

### 13.3 Storage Classes and Lifecycle Policies

Object storage providers offer multiple storage classes with different cost and access latency profiles. Lifecycle policies automatically migrate objects between classes based on age or access patterns.

```
STORAGE LIFECYCLE POLICY FOR VIDEO SEGMENTS
=============================================

Day 0 (upload):
  raw/{video_id}/* -> STANDARD (fast access, transcoding starts immediately)
  processed/{video_id}/* -> STANDARD (CDN serves from here)

Day 1-30 (active content):
  No change. Standard storage for fast CDN origin pulls.

Day 30:
  raw/{video_id}/* -> GLACIER_INSTANT_RETRIEVAL
  (raw file rarely needed; keep for possible re-transcoding)
  Cost: ~$0.004/GB/month vs $0.023/GB/month for Standard
  
Day 180 (no views in 90 days):
  processed/{video_id}/hls/4k_* -> GLACIER (rarely viewed 4K)
  processed/{video_id}/hls/1080p_av1_* -> GLACIER
  (keep 720p and below in Standard for occasional views)

Day 365 (no views in 270 days):
  processed/{video_id}/* -> GLACIER_DEEP_ARCHIVE
  Cost: ~$0.00099/GB/month
  Retrieval: 12-48 hours (acceptable for obscure content)
  
Day 730+ (video deleted or creator account deactivated):
  All objects -> DELETE
  (after grace period for creator to appeal)
```

Lifecycle policies are set once at the bucket level and execute automatically. This turns a manual storage management problem into a set-and-forget operational task.

### 13.4 Erasure Coding vs. Replication

S3 and GCS use erasure coding (not full replication) for durability within a region. Understanding this matters at L6.

**Full replication** (naive approach): Store 3 copies of every object on 3 different servers. If any server fails, the other 2 copies are available. Storage overhead: 3×. This is what HDFS uses by default.

**Erasure coding** (what S3 uses): The data is split into K data shards and M parity shards, stored on K+M different servers. Any M server failures can be tolerated — the original data can be reconstructed from any K of the K+M shards. S3 uses Reed-Solomon codes. Common configuration: 6 data shards + 2 parity shards (6+2). Storage overhead: (6+2)/6 = 1.33×. You get similar fault tolerance to 3× replication at only 1.33× storage overhead.

The trade-off: erasure coding requires computation to reconstruct data when a shard is missing (reading from a degraded server means reconstructing from other shards). For video segments that are read sequentially and infrequently from origin (because CDN handles most reads), this reconstruction cost is irrelevant — it only occurs on server failures, which are rare.

### 13.5 Cross-Region Replication

For global platforms, relying on a single region's object storage for origin creates a single point of failure and adds latency for CDN nodes in distant regions.

Cross-region replication strategies:

**Active-active**: Segments are stored in multiple regions simultaneously. A CDN edge in Asia can pull from an Asian origin instead of routing across the Pacific. This reduces origin pull latency from 200ms to 20ms for the cache-miss case. Cost: paying for storage in multiple regions (2–3× storage cost).

**Active-passive**: Segments are in one primary region, with async replication to secondary regions. Used for disaster recovery. Replication lag means briefly stale data in the secondary. Acceptable for video segments (a segment written 30 seconds ago being unavailable in the secondary for another 30 seconds is rarely user-visible).

**On-demand replication via origin shield**: Instead of pre-replicating all content to all regions, origin shield per region fetches from the primary region on the first miss and caches locally. Subsequent requests from that region hit the shield's cache. This is the most common approach because it avoids paying for full multi-region storage.

### 13.6 Brainstorming — Part 13

**Q: How do you handle the case where a creator wants to delete their video? What needs to happen at the storage level?**

Video deletion is more complex than it appears because the video's segments might be cached at thousands of CDN edge nodes with TTLs of hours or days. Simply deleting from object storage does not immediately prevent the CDN from serving cached segments. A full deletion flow:

First, immediately update the metadata database to mark the video as deleted and revoke access — the manifest URL should return 404 or 403 immediately. This is fast and prevents new viewers from starting playback. Existing sessions may continue until their next manifest poll, at which point they receive the error.

Second, issue CDN cache invalidation requests. Most CDN providers support programmatic cache purge: given a URL pattern, the CDN immediately expires all cached copies at all edge nodes. This is expensive (CloudFront charges per invalidation), so it is reserved for deletions rather than normal content expiration.

Third, submit a job to delete the objects from object storage. This can be deferred — the segments are inaccessible via CDN within seconds of invalidation. Object storage deletion is async and completes within minutes.

Fourth, handle the raw file deletion based on retention policy. Many platforms retain the raw file for 30 days after creator deletion to allow dispute resolution (copyright claims, content moderation appeals) before permanent deletion.

**Q: At YouTube's scale, how many objects are stored in object storage, and what are the operational challenges of managing that many objects?**

An estimate: 800 million videos × average 10 quality variants × average 1,000 segments per variant = 8 trillion segment objects, plus manifests, thumbnails, subtitles. At 8 trillion objects, even listing all objects (to find ones needing cleanup or migration) is a multi-day operation. Standard object storage list operations return 1,000 objects per API call — 8 trillion objects / 1,000 = 8 billion API calls just to list everything.

At this scale, Google (for YouTube) and Amazon (for S3 infrastructure) build internal indexing systems on top of object storage. Rather than relying on the standard list-objects API for bulk operations, they maintain a separate metadata index (essentially a table of (object_key, creation_time, last_access_time, size, storage_class)) that can be queried efficiently. Lifecycle policy execution, storage analytics, and cleanup jobs all run against this index rather than the raw object storage API. This turns an O(N) object listing problem into an indexed database query problem.

---

## Part 14: Deep Dive — Player Architecture and State Machine

### 14.1 The Video Player Is a Distributed System Client

The video player running in a browser or mobile app is not a simple media player — it is a sophisticated client that must:

- Manage an HLS/DASH manifest parsing library
- Run the ABR algorithm continuously
- Manage a segment download pipeline (multiple in-flight segment downloads for prefetching)
- Manage a decode pipeline (hardware or software decoding)
- Manage a render pipeline (frames to display buffer, synchronized with audio)
- Report telemetry back to backend analytics
- Handle DRM key fetching and management
- Handle errors (segment 404, manifest update failure, decoder error)
- Implement seek, pause, resume, playback rate change

### 14.2 The Player State Machine

```
VIDEO PLAYER STATE MACHINE
============================

STATES:
  IDLE        - Player initialized, no content loaded
  LOADING     - Manifest being fetched, initial segments downloading
  BUFFERING   - Waiting for segments to fill buffer (also: startup buffering)
  PLAYING     - Video playing, ABR loop running, segments prefetching
  PAUSED      - User paused playback; buffer retained
  SEEKING     - User scrubbed to new position; buffer cleared at seek point
  ENDED       - Video complete; autoplay next if applicable
  ERROR       - Unrecoverable error (manifest 404, all quality tiers failed)

TRANSITIONS:
  IDLE ──────────────────────────────────────────────────► LOADING
    [user clicks play / autoplay]

  LOADING ───────────────────────────────────────────────► BUFFERING
    [manifest fetched, initial segments downloading]

  LOADING ───────────────────────────────────────────────► ERROR
    [manifest 404, network timeout with no retry success]

  BUFFERING ─────────────────────────────────────────────► PLAYING
    [buffer_level >= startup_threshold (e.g., 4 seconds)]

  PLAYING ───────────────────────────────────────────────► BUFFERING
    [buffer_level drops below 0.5 seconds]

  PLAYING ───────────────────────────────────────────────► PAUSED
    [user clicks pause]

  PLAYING ───────────────────────────────────────────────► SEEKING
    [user scrubs to new timestamp]

  SEEKING ───────────────────────────────────────────────► BUFFERING
    [seek target set; new segments being downloaded]

  PAUSED ────────────────────────────────────────────────► PLAYING
    [user clicks play]

  PAUSED ────────────────────────────────────────────────► SEEKING
    [user scrubs while paused]

  PLAYING ───────────────────────────────────────────────► ENDED
    [final segment played, EXT-X-ENDLIST reached (VOD)]

  ANY STATE ─────────────────────────────────────────────► ERROR
    [unrecoverable error: all retry attempts exhausted]

ERROR RECOVERY:
  Most player errors should attempt retry before transitioning to ERROR state.
  Retry strategy: exponential backoff with jitter.
  Segment 404: try next lower quality tier (the segment may exist there)
  Network timeout: wait and retry same request
  Manifest 404: try alternate manifest URL (DASH vs HLS fallback)
  DRM license error: retry license request with fresh auth token
```

### 14.3 The Segment Download Pipeline

The player does not download segments one at a time sequentially. It maintains a pipeline of in-flight requests:

**Current segment**: The segment currently being decoded and played.
**Prefetch buffer**: The next 2–4 segments, downloaded in advance. Most players target 20–30 seconds of prefetched content.
**Parallel downloads**: Multiple HTTP/2 or HTTP/3 connections can download different segments simultaneously. This saturates available bandwidth more effectively than a single connection.

The prefetch strategy is careful about quality:
- Prefetch at the current quality level for near-future segments (high confidence these will be played)
- For segments far in the future, possibly drop to a lower quality to avoid wasting bandwidth on content the user might never watch (they might seek or stop watching)

TikTok takes this to an extreme: they prefetch the next 1–2 complete videos (not just segments) because their videos are short enough that a full video is only 5–20 MB. The probability the user watches the next video is high (60–70% of users swipe to the next video), making this prefetch worth the bandwidth.

### 14.4 Telemetry — What the Player Reports Back

Every commercial video player sends detailed telemetry to backend analytics. This data is used for:
- Detecting quality regressions (ABR algorithm change caused more rebuffering)
- Identifying CDN performance issues (cache miss rate spike in a region)
- Personalizing ABR starting quality (this user's ISP consistently supports 1080p)
- A/B testing ABR algorithm changes

Key events reported (typically via a background HTTP POST or beacon):

```
PLAYER TELEMETRY EVENTS
========================

session_start:
  user_id, session_id, video_id, device_type, os, browser,
  network_type (WiFi/LTE/5G), ISP, geographic region

playback_start:
  timestamp, initial_quality, time_to_first_frame_ms,
  startup_buffering_duration_ms

quality_change:
  timestamp, from_quality, to_quality, reason (ABR/user-manual),
  current_buffer_level, bw_estimate_at_decision

rebuffering:
  timestamp, duration_ms, buffer_level_at_start,
  quality_being_played, network_conditions

heartbeat (every 10 seconds during playback):
  current_timestamp_in_video, current_quality,
  buffer_level, cumulative_rebuffering_ms,
  cdp_node_serving (from response headers)

playback_end:
  reason (completed/user-quit/error/navigated-away),
  total_duration_watched, percentage_watched,
  total_rebuffering_ms, quality_distribution

error:
  error_code, error_message, last_segment_url, quality,
  http_response_code
```

This telemetry is the backbone of video quality monitoring. Aggregate it in a streaming analytics system (Flink, Spark Streaming) and you can detect a CDN regional outage within 60 seconds of it starting — before any monitoring system alert fires — because you see rebuffering spikes from users in that region.

### 14.5 Brainstorming — Part 14

**Q: How does a video player on a smart TV differ architecturally from a browser-based player?**

Smart TV players are constrained in ways that browser-based players are not. Smart TV operating systems (Tizen on Samsung, webOS on LG, Roku OS, Fire TV) have specific DRM requirements — they must use device-certified Widevine L1 or equivalent hardware DRM, which requires the platform to be certified by Google and the TV manufacturer. This certification process means TV platforms are often months to years behind browser capabilities. A feature available in Chrome the week it ships might take 18 months to reach the LG TV shipped in the same year.

Memory is another constraint: smart TVs typically have 1–4 GB of RAM total, with much of it reserved for the OS and UI. The video player must operate within a much tighter memory budget than a browser on a laptop. This affects the prefetch buffer size — a browser player might maintain 60 seconds of prefetch; a TV player on a constrained platform might keep only 15–20 seconds. The decoder pipeline is also different: smart TVs almost always use hardware video decode (the SoC has a dedicated video decode block), which means the codec support is locked to hardware capabilities. A TV with hardware H.264 and H.265 decode but no AV1 hardware decode block simply cannot play AV1, even if the TV's OS is updated.

**Q: What happens to the player's ABR state when the user changes the video quality manually (e.g., explicitly selecting "720p" from the YouTube quality menu)?**

A manual quality selection overrides the ABR algorithm for as long as the user's choice remains in effect. The implementation varies: YouTube's approach is to mark the player as "locked quality mode" — the ABR algorithm suspends its automatic quality decisions and the player requests segments only at the user-selected quality level. Buffer-based safety is still active: if the buffer drains completely (the user picked 1080p on a slow connection), the player may temporarily drop to a lower quality to prevent rebuffering, then return to the user's selected quality when the buffer recovers. Some platforms (Netflix) do not expose manual quality selection at all, relying entirely on ABR, because user-selected quality rarely outperforms the algorithm and creates support tickets when users select a quality their connection cannot sustain.

---

## Part 15: System Design Variations — Different Products, Different Architectures

### 15.1 YouTube vs. Netflix vs. TikTok: Where They Diverge

Understanding that "video streaming" is not monolithic — that different products make fundamentally different architectural choices — is a mark of L6 thinking.

```
PLATFORM ARCHITECTURE COMPARISON
==================================

                    YouTube          Netflix          TikTok
                    --------         -------          ------
Content Type        UGC (user-gen)   Professional     UGC (short-form)
Video Length        Seconds to 12hr  Minutes to 3hr   15s to 10min
Upload Volume       500 hr/min       ~1000 titles/mo  Millions/day
Primary Codec       VP9 (desktop)    H.265 / AV1      H.264 / H.265
                    H.264 (mobile)
ABR Approach        Hybrid ABR       ML-driven ABR    Aggressive prefetch
CDN                 Google Global    Open Connect     Multi-CDN
                    Cache (GGC)      (own CDN)        (Akamai + others)
DRM                 Widevine         Widevine L1       None (UGC)
                    (for rented)     (required)
Transcoding         Eager (popular)  Per-title         Eager (short videos)
                    Lazy (long-tail) encoding
Segment Duration    2 seconds        6 seconds        2 seconds
Live Streaming      Yes (Streams)    No               Yes (TikTok Live)
Recommendation      Server-side      Server-side      Algorithm-driven
                    + client hist.   (opaque)         infinite scroll
View Count          Approximate      Exact (billing)  Approximate
Consistency         (5-min lag)      (used for        (5-min lag)
                                     licensing calc)
```

### 15.2 Designing for a New Video Platform

If asked "design a new video streaming startup," the constraints differ from designing YouTube:

**At startup scale (0–1M users)**:
- Use a commercial CDN (Cloudflare or CloudFront) — do not build your own
- Use a managed transcoding service (AWS MediaConvert, Mux, Cloudflare Stream) — do not build your own transcoding pipeline
- Store everything in S3 Standard — lifecycle policies not worth the complexity yet
- Use a simple rate-based ABR — HLS.js or Video.js libraries handle this for you
- One quality tier to start (720p H.264) — add more as traffic justifies
- Single region — global distribution not needed yet

**At growth scale (1–100M users)**:
- Implement your own transcoding pipeline (managed services become expensive)
- Add the encoding ladder (240p through 1080p)
- Implement per-creator cache warming for top creators
- Add H.265 for top 20% of traffic
- Consider a second region for geographic redundancy
- Implement player telemetry for quality monitoring

**At scale (100M+ users)**:
- Consider building private CDN infrastructure (ISP peering, owned hardware)
- Implement per-title encoding
- Add AV1 for top content
- Multi-CDN for redundancy and performance
- ML-driven ABR
- Full long-tail storage optimization

### 15.3 The Clip Platform Variant — Twitch Clips, YouTube Shorts

Short-form video clips have different characteristics than long-form video:

- **Duration**: 15 seconds to 60 seconds. The entire video is often smaller than a single segment of a long-form video.
- **ABR unnecessary for short clips**: If the entire video is 5 MB, just download the whole thing. The single-quality download completes in under a second on any reasonable connection. ABR adds latency without benefit.
- **Pre-download entire video**: For sub-30-second videos, pre-download on page load. Time to first frame = 0 (video starts instantly from pre-downloaded content).
- **Different encoding**: Short clips often use shorter GOPs (smaller keyframe interval) for accurate seeking. Seek to any frame, not just the nearest keyframe.

YouTube Shorts / TikTok implementation insight: the video file for a 15-second clip might be delivered as a single progressive MP4 download rather than via HLS/DASH. The browser can download and play a 5 MB MP4 file faster than it can fetch and parse an HLS manifest and then download segments. ABR is bypassed entirely for content below a duration threshold (e.g., < 60 seconds).

### 15.4 The Interactive Video Variant — Choose Your Own Adventure / Commentary

Some platforms (Netflix's Bandersnatch, YouTube's interactive cards, educational platforms) need interactive video — the viewer's choice determines which video segment plays next. This breaks the linear segment-download model:

Standard HLS/DASH assumes a linear sequence: seg001 → seg002 → seg003. For interactive video, after seg047 the next segment might be seg048a (choice A) or seg048b (choice B), depending on user input.

Implementation approaches:

**Multiple playlists**: Maintain separate HLS playlists for each path through the interactive video. At each branch point, switch to the appropriate playlist. Pre-buffer both possible next segments so the transition is seamless regardless of which choice the user makes.

**Segment graph**: Replace the linear segment list with a graph of segments. The manifest encodes the graph structure. The player downloads the current segment and pre-fetches all possible next segments (fan-out at branch points). Memory-intensive but ensures zero-latency transitions.

Netflix's Bandersnatch: Netflix pre-buffered all possible next segments at every branch point. Because Bandersnatch had limited branching choices (not an infinite combinatorial explosion), the total number of segments was manageable and could all be pre-fetched.

### 15.5 Brainstorming — Part 15

**Q: Why did Netflix invest in building their own CDN (Open Connect) rather than using Akamai or Cloudflare?**

The decision to build Open Connect was driven by economics, control, and performance — in roughly that order. On economics: at Netflix's scale in 2012, they were paying Akamai hundreds of millions of dollars per year in CDN fees. The per-GB CDN cost was manageable at small scale but became the company's largest infrastructure cost as streaming took over from DVD. Building their own CDN required capital expenditure (servers, rack space at ISPs) but eliminated the per-GB variable cost. The break-even analysis was clear by 2012: building was cheaper than buying at Netflix's scale.

On control: commercial CDNs serve thousands of customers. Netflix's content delivery needs are specialized — proactive content push (rather than reactive caching), very large object sizes (video segments vs. typical web assets), aggressive prefill during off-peak hours, and deep ISP integration. Commercial CDNs optimize for average customer needs. Open Connect is optimized entirely for Netflix's workload. On performance: ISP-embedded appliances serve content from inside the ISP's network, eliminating the last-mile internet hop entirely. A Netflix subscriber's video never crosses a commercial internet exchange — it goes from the Open Connect appliance in their ISP's core network directly to their home via the ISP's own infrastructure. This eliminates the congestion and variability of the public internet, which is the dominant source of video quality degradation in practice.

**Q: How would you design a video streaming system for a sports league that needs both live streaming and VOD replay of the same events?**

A live sports event streaming system has several distinct requirements: live delivery during the game, VOD replay immediately after the game ends, and clip/highlight delivery within seconds of key moments (a goal, a touchdown). The architecture must handle all three simultaneously.

During the live event: the real-time transcoding pipeline (RTMP ingest → GPU transcoder → segment store → CDN) handles live delivery. Simultaneously, every segment produced for live delivery is also written to object storage for VOD replay. When the game ends, the live manifest is converted to a VOD manifest (EXT-X-ENDLIST is appended), and the replay is immediately available without any re-transcoding. The entire game has been transcoded in real-time and stored.

Highlights require a more sophisticated approach. A highlights system monitors the event feed (scoreboard data, broadcast annotations) for significant moments. When a goal is scored, the system knows the timestamp. It computes which segments contain that timestamp (trivial: segment_number = floor(timestamp / segment_duration)), assembles a sub-playlist covering the relevant window (e.g., 30 seconds before to 30 seconds after the goal), and makes that sub-playlist available as a clip URL within seconds. Because the segments already exist in storage (they were produced by the live transcoder), creating a highlight requires only manifest manipulation — no re-encoding.

---

## Part 16: Security and Content Protection

### 16.1 Preventing Unauthorized Access to Videos

Not all videos are public. A platform needs:
- **Private videos** (creator-only, or shared via secret link)
- **Paid content** (subscription-only or pay-per-view)
- **Geo-restricted content** (available only in certain countries due to licensing)
- **Age-restricted content** (requires authentication and age verification)

The mechanism for access control in HLS/DASH streaming:

**Signed URLs**: The manifest URL and optionally segment URLs are signed with a HMAC or RSA signature that includes an expiration timestamp and optionally the viewer's IP address. The CDN validates the signature before serving. If the signature is invalid or expired, the CDN returns 403. AWS CloudFront signed URLs and Google Cloud CDN signed URLs implement this pattern.

```
SIGNED URL FLOW
================

1. Viewer requests to play video abc123
   → Backend verifies user has access (subscription, not geo-blocked)
   → Backend generates signed manifest URL:
     https://cdn.example.com/v/abc123/master.m3u8
       ?Expires=1700000000
       &KeyPairId=K1234
       &Signature=ABCD...
       (signature covers path + expiry, computed with private key)

2. Player fetches signed manifest URL
   → CDN validates signature and expiry
   → If valid: serve manifest
   → If invalid/expired: return 403

3. Manifest contains segment URLs (can be pre-signed or use
   cookie-based auth)

4. Player fetches each segment
   → CDN validates signature
   → Serve segment
```

**Signed Cookies**: Rather than signing every segment URL (thousands per viewing session), a signed cookie is set once and sent with every segment request. The CDN validates the cookie on each request. This is the preferred approach because it does not require re-signing when segment URLs are long or numerous.

### 16.2 Hotlink Prevention

Without access control, anyone who discovers a segment URL can download it indefinitely, even after their subscription expires or the video is deleted. Hotlink prevention ensures URLs are time-limited:

- Signed URLs with short expiry (15–60 minutes for a streaming session)
- Referer checking (CDN rejects requests where Referer header is not from the platform's domain) — weak protection, easily bypassed
- Token-based access: a session token is validated on the first request, and the CDN node whitelists the client's IP for subsequent requests for a short window

### 16.3 DRM for Premium Content

For premium content (movies, sports with exclusive rights, music videos), signed URLs are not sufficient because they prevent unauthorized URL sharing but do not prevent recording the stream. DRM (covered in Part 4) adds a hardware-enforced protection layer:

- Content is encrypted with a per-video content key
- The content key is stored in a License Server, not in the CDN or object storage
- The player must authenticate and obtain a license (decryption key) from the License Server
- The license is bound to the specific device via hardware key — it cannot be extracted and used on another device
- Hardware DRM (Widevine L1, FairPlay) ensures the decrypted video never exists in unprotected memory

The License Server is a high-availability service: if it goes down, no new playback sessions can start (existing sessions continue until their license expires). Typical SLA: 99.99% uptime, <100ms license issuance latency.

### 16.4 Content Moderation at Upload Time

For UGC platforms, every uploaded video must be checked before it is made public:

1. **Hash-based matching**: The video's perceptual hash is compared against a database of known-bad content (child exploitation material, terrorist content). This database is maintained by industry consortia (NCMEC, GIFCT). If there is a match, the video is immediately rejected and law enforcement is notified.

2. **ML-based classification**: A video understanding model analyzes sample frames from the video for policy violations (nudity, violence, hate symbols). This runs asynchronously after upload as part of the transcoding DAG. If the model flags the video, it is held in a pending-review state until a human moderator reviews it.

3. **Audio analysis**: Speech-to-text transcription followed by NLP classification for hate speech in audio. This is a separate parallel pipeline from video analysis.

4. **Community reporting**: Even after publication, the community can report videos. Reports go into a moderation queue, prioritized by report count and content sensitivity signals.

The challenge: with 500 hours of video uploaded per minute, even a 0.01% false positive rate for the ML classifier means thousands of mistakenly flagged videos per day, each requiring human review. Calibrating the classifier threshold is a constant operational challenge.

### 16.5 Brainstorming — Part 16

**Q: How does YouTube's Content ID system work, and how does it relate to the video streaming architecture?**

Content ID is YouTube's system for allowing rights holders (music labels, movie studios, sports leagues) to automatically identify and monetize or block their content when users upload it. The system works as follows: rights holders submit reference files (audio fingerprints, video hashes) to YouTube. When a new video is uploaded and transcoded, YouTube's pipeline runs a matching step that compares the uploaded video's audio and video fingerprints against the Content ID database of ~800 million reference files. This matching runs asynchronously after the initial transcoding — the video can be published while Content ID is still running. If a match is found, the rights holder's policy is applied: monetize (ads revenue splits to the rights holder), track (the rights holder sees view counts but does not take action), or block (video taken down or blocked in specific countries).

From an architecture perspective, Content ID is a separate processing pipeline that consumes from the same video upload events that trigger transcoding. The audio fingerprinting uses a perceptual audio hash (similar to Shazam's algorithm), and the video matching uses a frame-level feature vector comparison. The database of reference fingerprints must support sub-100ms lookups for 800 million entries — this is an approximate nearest-neighbor search problem, solved with specialized indexing structures (LSH — Locality Sensitive Hashing) that allow efficient similarity search at scale.

---

## Part 17: Cost Optimization Strategies at Scale

### 17.1 The Largest Cost Centers in Video Streaming

At YouTube or Netflix scale, the infrastructure cost profile is:

1. **CDN egress** (~40–50% of total infrastructure cost): paying for the terabits per second of video data delivered to viewers. The primary optimization lever is codec efficiency — AV1 saves 30–50% bandwidth, directly reducing CDN egress cost.

2. **Transcoding compute** (~20–30% of total): the CPU/GPU fleet running ffmpeg variants continuously. Optimization levers: spot/preemptible instances, GPU-accelerated encoding, lazy transcoding for long-tail, smarter scheduling.

3. **Object storage** (~15–20% of total): storing petabytes of video segments. Optimization levers: lifecycle policies (cold storage for dormant content), erasure coding, deduplication.

4. **Origin infrastructure** (~5–10% of total): the servers and networking for CDN origin pulls. Optimization levers: origin shield (reduces origin requests), better CDN hit ratio (reduces cache misses).

5. **Transcoding storage** (~5% of total): temporary storage used during transcoding (input and output files before they are moved to final storage). Optimization lever: use instance-attached NVMe for speed, delete immediately after transcoding.

### 17.2 Spot/Preemptible Instances for Transcoding

Transcoding is the ideal workload for spot/preemptible compute because:
- It is embarrassingly parallel (each job is independent)
- Jobs can be checkpointed (save encoded progress, resume after preemption)
- There is no strict latency requirement (minutes to hours is acceptable)
- The alternative (on-demand instances) is 3–5× more expensive

Implementation: transcoding workers save a checkpoint every N encoded frames. If the spot instance is preempted, the job is returned to the Kafka queue and a new spot instance picks it up from the last checkpoint. This requires that the transcoding framework supports resume — ffmpeg supports this natively via the -ss (start_time) flag and segment-based encoding.

At YouTube scale, using spot instances for 70–80% of transcoding work and on-demand for the remaining 20–30% (high-priority videos that must be available quickly) can reduce transcoding costs by 50–60%.

### 17.3 Bandwidth Cost vs. Encoding Cost Trade-off

The fundamental trade-off: encoding more expensive codecs (H.265, AV1) costs more compute but saves bandwidth. The crossover point depends on:

- How many times the video is watched (more views → bandwidth savings accumulate)
- The bandwidth savings percentage for the specific content type
- The cost difference between encoding and bandwidth per GB

A simple model for deciding whether to encode AV1 for a given video:

```
CODEC SELECTION ECONOMIC MODEL
================================

Given:
  encoding_cost_per_hour_cpu = $0.05 (spot instance rate)
  bandwidth_cost_per_gb = $0.008 (CDN egress cost)
  video_duration = D hours
  expected_views = V
  avg_viewer_watch_fraction = 0.6  (60% of video watched on avg)

H.264 baseline encoding cost:
  h264_encode_time = D * 0.5 hours (0.5x real-time for 1080p H.264)
  h264_cost = h264_encode_time * encoding_cost_per_hour_cpu

AV1 encoding cost:
  av1_encode_time = D * 20 hours (20x real-time for 1080p AV1)
  av1_cost = av1_encode_time * encoding_cost_per_hour_cpu

AV1 bandwidth savings per view:
  h264_bitrate = 6 Mbps for 1080p
  av1_bitrate = 3.6 Mbps for 1080p (40% savings)
  savings_per_view_gb = (6 - 3.6) Mbps * D * 3600 * 0.6 / 8 / 1024
  savings_per_view_dollars = savings_per_view_gb * bandwidth_cost_per_gb

Break-even views:
  av1_cost - h264_cost = savings_per_view_dollars * break_even_views
  break_even_views = (av1_cost - h264_cost) / savings_per_view_dollars

Example: 1-hour video (D=1):
  h264_cost = 0.5 * $0.05 = $0.025
  av1_cost  = 20  * $0.05 = $1.00
  extra_encoding_cost = $0.975

  savings_per_view_gb = 2.4 Mbps * 3600 * 0.6 / 8 / 1024 = 0.633 GB
  savings_per_view_dollars = 0.633 * $0.008 = $0.00506

  break_even_views = $0.975 / $0.00506 ≈ 193 views

Conclusion: if a 1-hour video will receive >193 views total,
            AV1 encoding is economically justified.
```

This model shows why AV1 is reserved for popular content. For a video expected to receive 1,000 views, AV1 is clearly justified. For a video expected to receive 10 views, it is clearly not. The platform sets a threshold (e.g., 500+ views in first 48 hours triggers AV1 re-encoding) based on this analysis.

### 17.4 Brainstorming — Part 17

**Q: How do you reduce CDN egress costs for the top 0.1% of videos that account for 50% of total bandwidth?**

The top 0.1% of videos are the highest-leverage targets for optimization because any per-video optimization (better codec, lower bitrate for same quality) is amplified by the enormous view count. Several strategies apply specifically to this tier. First, encode with the most efficient codec available — AV1 with maximum compression effort — accepting weeks of encoding time because the bandwidth savings over millions of views easily justify it. Second, implement per-title encoding with a higher quality bar than the default ladder. Measure VMAF across more bitrate points to find the exact knee of the rate-distortion curve. Third, implement thumbnail-quality preview optimization: videos on the home page or search results load a low-quality preview before the user clicks. If 90% of users decide to click or not within the first 3 seconds of preview, optimizing those first 3 seconds for minimum bandwidth (lowest quality preview) saves bandwidth that would otherwise be wasted on videos the user does not watch. Fourth, consider dynamic ABR trajectory optimization: for the most popular videos, offline analysis of historical viewer ABR decisions (quality distributions, where rebuffering occurred) can inform precomputed ABR recommendations that the player client uses as a starting point, reducing trial-and-error in quality selection and avoiding wasted bandwidth on unnecessarily high quality.

---

## Appendix: Quick Reference Architecture Diagrams

### Upload Pipeline (Condensed)

```
Creator → [TUS Chunked Upload] → Upload Service → [SHA-256 dedup check]
       → Raw S3 → [Kafka: upload_complete] → Transcoding Orchestrator
       → [DAG: Demux → parallel encode → manifest gen → metadata write]
       → Processed S3 → CDN Origin → CDN Edge → Viewer
```

### CDN Tier Summary

```
Origin (S3/GCS) ← [1-5% of requests]
      ↑
Origin Shield ← [3-8% of requests, collapses thundering herd]
      ↑
Regional PoP (20-50 worldwide) ← [10-15% of requests]
      ↑
Edge PoP (500-4000 worldwide) ← [80-85% of requests — cache HIT]
      ↑
Viewer Device (anycast DNS → nearest edge)
```

### HLS Segment Request Sequence

```
Player → GET master.m3u8     (once at startup)
Player → GET 720p/playlist.m3u8  (once, or polling if live)
Player → GET 720p/seg000.ts  (startup — low quality)
Player → GET 720p/seg001.ts  (startup — ramping)
Player → GET 1080p/seg002.ts (ABR: bandwidth sufficient, upgrade)
Player → GET 1080p/seg003.ts (continue)
Player → GET 480p/seg004.ts  (ABR: bandwidth dropped, downgrade)
```

### ABR Decision Summary

```
buffer < 2s:   → emergency: lowest quality
buffer < 5s:   → conservative: one step down
buffer OK:     → bw_estimate * 0.85 → pick best fitting quality
buffer > 20s:  → aggressive: consider one step up
```

---

## Part 18: Capacity Planning and Back-of-Envelope Calculations

### 18.1 Transcoding Fleet Sizing

The interview question "how many transcoding workers do you need?" requires a back-of-envelope calculation. Here is the structured approach:

**Given**: YouTube uploads 500 hours of video per minute.

**Assumption**: Average video is 10 minutes long (conservative — many are shorter).
- Uploads per minute: 500 hours × 60 minutes / 10 minutes per video = 3,000 videos per minute

**Assumption**: Each video is encoded into 8 quality variants (240p through 4K).
- Encoding jobs per minute: 3,000 × 8 = 24,000 encoding jobs per minute

**Assumption**: Each encoding job takes an average of 1x real-time (optimistic for a mix of H.264 across quality levels with hardware acceleration; H.264 at 720p on modern hardware runs ~5x real-time, H.264 at 4K runs ~0.5x real-time, giving a weighted average around 1x real-time).
- Worker-minutes needed per minute: 24,000 × 10 minutes = 240,000 worker-minutes per minute = 4,000 concurrent workers

**Sizing**: 4,000 concurrent transcoding workers continuously running. With spot instance reliability (~90% availability), need 4,000 / 0.9 ≈ 4,500 instances. Using c5.4xlarge instances (16 vCPU, well-suited for ffmpeg): each instance handles ~16 parallel single-threaded ffmpeg jobs. Instances needed: 4,500 / 16 ≈ 280 instances.

**Reality check**: This is a floor estimate. It does not include: H.265 and AV1 encoding (much slower), 4K content (slower), content-aware encoding (additional probe passes), audio encoding, thumbnail generation, subtitle processing. Real fleet is likely 5–10× larger: 1,500–3,000 compute instances.

### 18.2 Storage Sizing

**Video storage calculation**:

- YouTube library: ~800 million videos
- Average video duration: 7 minutes (skewed by many short videos)
- Quality variants: 8 (one per tier)
- Storage per variant at 1080p H.264: 6 Mbps × 7 × 60 / 8 = 315 MB
- Weighted average across all tiers: ~100 MB per variant (lower quality tiers are much smaller)
- Storage per video: 8 × 100 MB = 800 MB
- Total storage: 800 million × 800 MB = 640 petabytes for processed video

Plus raw files (if retained, likely 3–5× larger than processed): another 1.5–3 exabytes. 

Total: ~2–4 exabytes of video data. This aligns with public estimates of YouTube's storage footprint.

**Daily storage growth**:
- 500 hours/minute × 60 × 24 = 720,000 hours per day
- At 800 MB per video and 7 minutes per video: 720,000 × 60 / 7 × 800 MB = ~5 petabytes per day

5 petabytes of new storage required per day. This requires a storage expansion strategy — cloud object storage scales automatically, but at 5 PB/day the cost and the data management complexity are significant operational concerns.

### 18.3 CDN Sizing

**Egress bandwidth calculation**:

- 1 billion hours of video watched per day
- Average bitrate of served content: mix of 480p (1.5 Mbps), 720p (2.5 Mbps), 1080p (6 Mbps), with 720p being the median
- Weighted average bitrate: ~2 Mbps
- Total egress per day: 1 billion hours × 3600 seconds × 2 Mbps / 8 = 900,000 TB = 900 petabytes per day
- Average egress rate: 900 PB / 86,400 seconds = ~10 Tbps average
- Peak (2–3× average): ~20–30 Tbps

30 Tbps of peak CDN capacity. Major CDNs (Akamai, Cloudflare) have aggregate capacity in the hundreds of Tbps across their PoP networks. YouTube's CDN (Google Global Cache) is embedded in ISP networks similar to Netflix Open Connect, giving them effectively unlimited capacity via ISP peering.

### 18.4 Database Sizing

**Video metadata database**:

- 800 million video records
- Average row size: ~2 KB (title, description, timestamps, counts, settings)
- Total: 800 million × 2 KB = 1.6 TB

1.6 TB is entirely manageable in a single large PostgreSQL instance (or sharded across a few). This is not the hard problem. The hard problem is write throughput for view count updates:

- 1 billion views per day / 86,400 seconds = ~11,574 view events per second
- If each view event is an atomic increment on the video's row: 11,574 writes/second on the videos table
- PostgreSQL handles ~10,000–50,000 writes/second — technically feasible but dangerously close to limits

The real-world solution (described in Part 9): approximate counters via Kafka aggregation. The 11,574 writes/second collapses to ~120 batch updates/second (one per video per 5-minute window if the video is being viewed). This is trivially within any database's capacity.

**Search index sizing** (Elasticsearch):

- 800 million videos × average document size of 5 KB (title + description + tags + metadata for indexing)
- Total index size: ~4 TB
- Elasticsearch cluster: 4 TB / 50 GB per data node = ~80 data nodes (at standard replication factor 1). With 2 replicas: 240 data nodes.

This is a large but completely standard Elasticsearch deployment. Major search platforms run clusters much larger than this.

### 18.5 Brainstorming — Part 18

**Q: How do you plan for the storage growth of 5 petabytes per day without running out of capacity?**

Storage capacity planning at video scale is a continuous operational process, not a one-time calculation. The key is having a long enough lead time on capacity procurement and a clear growth projection model. In practice, platforms use a combination of strategies. First, historical growth rate extrapolation: if uploads have been growing at 15% year-over-year, storage procurement should be planned for 15% annual growth plus safety margin (usually 20–30%). Cloud providers like AWS and Google Cloud can provision essentially unlimited object storage with 24-hour lead time, so there is no procurement cycle risk — only cost risk if projections are wrong. Second, cost-based storage tiering reduces the effective storage footprint by automatically migrating older or less-accessed content to cheaper storage classes. If 60% of the library is in Glacier at $0.004/GB versus Standard at $0.023/GB, the effective storage cost per PB drops dramatically, making higher absolute storage volumes affordable. Third, codec improvements provide a one-time storage compression opportunity: re-encoding the library in AV1 would reduce the processed video storage footprint by ~30–40%, equivalent to 2–3 years of growth paid off in a single encoding project. YouTube and Netflix periodically run such re-encoding projects as new codecs become available. The cost of re-encoding is justified by the storage cost savings and bandwidth savings combined.

**Q: When a new video goes viral within minutes of upload (before CDN cache warming can occur), how does the system handle the sudden load?**

The viral video cold start is one of the most operationally interesting scenarios in video streaming. When a video goes viral before cache warming, the first wave of viewers all experience CDN cache misses — their requests propagate all the way to origin. The key insight is that this origin spike is self-limiting and brief. Here is why: the first edge node to receive a cache miss for a segment fetches it from origin and caches it. All subsequent viewers served by that same edge node get a cache hit. The edge node serves thousands of simultaneous viewers for that same video, so after the first miss, the edge cache fills within seconds. With thousands of edge nodes across the CDN, the total number of origin cache miss requests is bounded by the number of edge nodes, not the number of viewers. For a platform with 4,000 edge nodes and 10 million simultaneous viewers, the origin receives at most 4,000 × (number of unique segments requested) = perhaps a few hundred thousand origin requests total before the cache warms. The origin must handle this spike, which is why origin shield and request coalescing are essential — they ensure the 4,000 edge nodes produce a maximum of one origin request per unique segment (not thousands). After the cache warms (typically within 30–60 seconds of the viral spike starting), 95%+ of subsequent requests are served from edge cache, and origin load returns to normal. The system also detects viral patterns in real-time (view count velocity monitoring) and can trigger an emergency cache warming job to push content to additional edge nodes proactively as the virality signal appears.

---

## Part 19: Advanced Topics — Low-Latency and Ultra-Low-Latency Streaming

### 19.1 Why Low Latency Is Hard for HTTP-Based Streaming

Standard HLS and DASH were designed with simplicity and CDN compatibility as primary goals, not latency. The mechanisms that make them CDN-friendly — segment-based delivery, playlist polling, cacheable HTTP responses — also introduce inherent latency:

1. **Segment buffering**: To produce a 6-second segment, the encoder must receive 6 seconds of input. So even before any network delay, there is a 6-second encoding delay.

2. **Playlist polling**: The player polls the manifest URL every N seconds (where N ≈ segment duration). If the manifest was updated 1 second ago, the player waits up to N-1 more seconds to discover it. Average delay from manifest update to player discovery: N/2.

3. **Segment download**: After discovering the new segment in the manifest, the player fetches it. This takes 1–5 seconds depending on segment size and bandwidth.

Total standard HLS latency:
Encoder delay (6s) + playlist poll delay (3s average) + download time (2s) = ~11 seconds, plus any CDN/network RTT. In practice: 20–30 seconds end-to-end.

### 19.2 Low-Latency HLS (LL-HLS) — How Apple Cut Latency to 3 Seconds

Apple's Low-Latency HLS (published 2019, standardized in HLS specification) reduces latency to 2–3 seconds while maintaining CDN compatibility.

The key innovations:

**Partial Segments**: Instead of waiting for a full 6-second segment to complete before making it available, the server delivers the segment in small parts (0.5–1 second each). The manifest lists both the current partial segment in progress and the next full segment. The player can start downloading and playing the partial segment before it is complete.

```
LL-HLS MANIFEST (in-progress live stream)
==========================================
#EXTM3U
#EXT-X-TARGETDURATION:6
#EXT-X-SERVER-CONTROL:CAN-BLOCK-RELOAD=YES,PART-HOLD-BACK=1.0

#EXT-X-PART-INF:PART-TARGET=0.5

#EXTINF:6.0,
seg000.ts           ← completed 6-second segment

#EXTINF:6.0,
seg001.ts           ← completed 6-second segment

#EXT-X-PART:DURATION=0.5,URI="seg002_part0.ts"   ← completed part
#EXT-X-PART:DURATION=0.5,URI="seg002_part1.ts"   ← completed part
#EXT-X-PART:DURATION=0.5,URI="seg002_part2.ts"   ← completed part
#EXT-X-PART:DURATION=0.5,URI="seg002_part3.ts"   ← IN PROGRESS
```

**Blocking Playlist Reload (Push-based polling)**: Instead of the player polling every 6 seconds and potentially waiting up to 6 seconds for a new update, the player sends a request with a `_HLS_msn` (media sequence number) and `_HLS_part` (part number) parameter. The CDN holds the response until the requested part is available, then immediately returns the updated playlist. This is essentially HTTP long-polling for playlist updates — the player always gets the latest manifest within milliseconds of it being available.

**Rendition Reports**: The manifest includes recent throughput data from the server's perspective, helping the player start ABR from a better initial estimate without needing its own slow ramp-up.

Combined effect: encoder delay (0.5s per part) + blocking poll delay (~0ms) + download time (0.5s) = ~2–3 seconds. CDN compatibility is maintained because parts are still cacheable HTTP objects.

### 19.3 WebRTC for Sub-Second Latency

When even 2–3 seconds of latency is too much — video calls, interactive gaming, real-time bidding streams — WebRTC (Web Real-Time Communication) provides sub-500ms latency.

WebRTC uses UDP instead of TCP, allowing the transport layer to prioritize timeliness over reliability (occasional packet loss is acceptable; waiting for TCP retransmission is not). Key characteristics:

- **Protocol**: UDP with SRTP (Secure Real-time Transport Protocol) for encryption
- **Latency**: 100–500ms end-to-end
- **Codec**: VP8/VP9 for video, Opus for audio (designed for variable network conditions)
- **Connection**: P2P when possible (direct browser-to-browser with NAT traversal via STUN/TURN), or via SFU (Selective Forwarding Unit) for many-to-many

The scaling problem with WebRTC: traditional WebRTC is designed for small groups (video conferencing). Every viewer receives an individual media stream — there is no CDN-level caching. To serve 1 million concurrent viewers with WebRTC latency, you need a cascade of SFUs that progressively fan out:

```
WEBRTC SCALE ARCHITECTURE (SFU cascade)
========================================

Broadcaster
    |
    | WebRTC (1 upload stream)
    v
SFU Tier 1 (origin SFUs, ~5 nodes)
    |  Each SFU relays to ~200 Tier-2 SFUs
    v
SFU Tier 2 (regional SFUs, ~1000 nodes)
    |  Each SFU relays to ~1000 viewers
    v
Viewers (~1M total)
```

This requires 1,005 SFU nodes continuously running, each processing real-time media. The latency at each hop adds ~50–100ms, so 2 SFU hops add 100–200ms to the base latency. Total end-to-end: 300–700ms — still sub-second but less impressive than direct P2P.

This is why WebRTC-scale streaming is expensive: no CDN caching possible, dedicated compute per stream, high memory and CPU for real-time transcoding at each SFU. Platforms that offer ultra-low-latency streaming (Twitch, YouTube, Amazon Live) typically reserve WebRTC delivery for a small fraction of viewers (closest geographically, lowest latency requirements met) and serve the majority via LL-HLS.

### 19.4 Brainstorming — Part 19

**Q: Why do sports broadcasters care about latency more than, say, movie streaming platforms?**

For movie streaming, a 30-second latency is completely acceptable — the viewer is watching a pre-recorded story, and whether they are 30 seconds or 3 seconds behind the "live" edge does not matter because the content is not interactive. For sports broadcasting, latency matters for several reasons. The most important is social context: sports viewers often watch with friends or follow a social media timeline. If the CDN-served stream is 45 seconds behind the low-latency stream available on the app, a viewer can see a social media post about a goal before it appears on their TV. This "spoiler" experience is a major driver of viewer dissatisfaction and abandonment. Second, for sports with mobile in-stadium betting or prediction games, even 5-second latency means the outcome may be known before a bet is placed — regulators and betting operators require very low-latency streams for these use cases. Third, for interactive sports features (polls, predictions synchronized to live action), a 30-second lag makes the feature unusable. Broadcasters differentiate on latency — Fox Sports, ESPN+, and others explicitly advertise latency figures as competitive features.

---

## Final Notes — What This Chapter Covered

This chapter built a complete mental model of video streaming systems from the ground up. Starting from first principles (why you cannot just serve a video file directly from a server), we built up through:

- **TUS chunked upload** and why resumability requires server-side offset tracking
- **DAG-based transcoding pipelines** and why parallel workers across both the quality dimension and the temporal dimension reduce wall-clock time dramatically
- **H.264 / H.265 / AV1 codec trade-offs** and the economic model for deciding which codec to use for which content
- **Per-title encoding** and why right-sizing bitrate per content complexity reduces bandwidth without reducing quality
- **HLS and DASH** segment-based delivery and why serving video as plain HTTP objects was a revolution in streaming architecture
- **ABR algorithms** from simple rate-based estimation through buffer-based BOLA to production ML-driven approaches
- **Three-tier CDN hierarchy** with origin shield, request coalescing, and cache warming for popular content
- **The long-tail problem** and why 99% of content requires a different cost strategy than the popular 1%
- **Live streaming** with RTMP ingest, real-time transcoding, and the latency/reliability trade-off across HLS, LL-HLS, and WebRTC
- **Player state machine** and the telemetry pipeline that makes quality monitoring possible
- **Capacity planning calculations** that connect user-facing requirements to infrastructure sizing

The interview win is not memorizing these facts — it is understanding the constraints that forced each design choice, and being able to reason about new scenarios (a new codec, a new use case, a new scale requirement) from those constraints.

---

*This chapter pairs with Chapter 71 (Media Upload Pipeline), Chapter 56 (Distributed Cache), Chapter 33 (Event-Driven Architecture with Kafka), and Chapter 64 (Recommendation Systems).*
