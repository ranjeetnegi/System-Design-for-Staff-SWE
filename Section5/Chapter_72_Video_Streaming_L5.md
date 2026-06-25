# Chapter 72: Video Streaming — Design YouTube / Netflix (L5)

> "Design a video streaming platform" is one of the five most common L5 system design questions.
> It tests upload pipelines, asynchronous processing, CDN architecture, and adaptive bitrate
> streaming — four separate systems you must scope, size, and compose under 45 minutes of pressure.
> Most candidates blur the upload path with the delivery path and lose the interview.
> This chapter teaches you to separate them clearly and defend every choice with numbers.

---

## AT A GLANCE

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                CHAPTER 72 — VIDEO STREAMING (L5) AT A GLANCE               ║
╠═══════════════════════════╦══════════════════════════════════════════════════╣
║  System                   ║  Core Design Choices                            ║
╠═══════════════════════════╬══════════════════════════════════════════════════╣
║  Upload pipeline          ║  Chunked/resumable upload → S3 multipart        ║
║                           ║  → Job queue → Transcoder worker pool           ║
╠═══════════════════════════╬══════════════════════════════════════════════════╣
║  Transcoding              ║  FFmpeg, encoding ladder (360p/480p/720p/1080p) ║
║                           ║  H.264 codec, HLS segments (6s each)            ║
╠═══════════════════════════╬══════════════════════════════════════════════════╣
║  Storage                  ║  S3-compatible object store for all video data  ║
║                           ║  PostgreSQL for metadata, Redis for hot paths   ║
╠═══════════════════════════╬══════════════════════════════════════════════════╣
║  Delivery                 ║  CDN (CloudFront/Fastly) with 90-95% hit rate  ║
║                           ║  Segments: long TTL. Manifests: short TTL.      ║
╠═══════════════════════════╬══════════════════════════════════════════════════╣
║  Streaming protocol       ║  HLS (.m3u8 manifest + .ts segments)           ║
║                           ║  Adaptive bitrate: quality per bandwidth        ║
╠═══════════════════════════╬══════════════════════════════════════════════════╣
║  Scale targets            ║  Upload: 100K videos/day                        ║
║                           ║  Streaming: 1M concurrent viewers               ║
║                           ║  Storage: ~900 TB/year (100K × ~25 MB avg)      ║
╠═══════════════════════════╬══════════════════════════════════════════════════╣
║  Key numbers              ║  Segment: 6s, ~2-3 MB at 720p                  ║
║                           ║  TTFF target: < 2 seconds                       ║
║                           ║  Rebuffering target: < 1% of playback time      ║
╠═══════════════════════════╬══════════════════════════════════════════════════╣
║  Scope OUT (L5)           ║  DRM, live streaming, multi-DC geo-routing,    ║
║                           ║  recommendation engine, per-title encoding      ║
╠═══════════════════════════╬══════════════════════════════════════════════════╣
║  Staff level (Ch100)      ║  TUS protocol, per-title encoding, BOLA ABR,   ║
║                           ║  multi-CDN, origin shield, DRM integration      ║
╚═══════════════════════════╩══════════════════════════════════════════════════╝
```

**Parts in this chapter:**
- Part 1: The Problem — Why Video Is Hard
- Part 2: Requirements
- Part 3: High-Level Design
- Part 4: API Design
- Part 5: Database Schema
- Part 6: Upload Pipeline
- Part 7: Transcoding Pipeline
- Part 8: CDN Delivery
- Part 9: Adaptive Bitrate Streaming
- Part 10: Scaling and Failure Handling
- Part 11: The 45-Minute Interview Framework
- Part 12: Thumbnail Generation Pipeline
- Part 13: Video Search and Discovery
- Part 14: Security and Abuse Prevention
- Part 15: Pre-Interview Drill

---

## Why This Chapter Matters

"Design YouTube," "Design Netflix," "Design a video-on-demand platform" — this question appears at
virtually every company that has ever touched video: YouTube, Netflix, TikTok, Meta (Reels/Watch),
Snap (Stories), Twitter/X (video tweets), Cloudflare (Stream), and every streaming startup.

At L5, the question tests whether you understand:
- Why you cannot upload a video the same way you upload a JPEG
- What transcoding is and why every video platform does it
- How CDNs make global video delivery economically and physically possible
- What adaptive bitrate streaming is and why it matters for user experience

You do not need to design a multi-datacenter globally distributed system (that is Ch100, the
Staff version). You need a clean, correct, single-region design with real numbers.

**Scope for this chapter (L5)**:
- Single-region deployment
- Video-on-demand (pre-recorded, not live streaming)
- Upload pipeline + async transcoding + CDN delivery + adaptive bitrate
- Skip: multi-DC geo-routing, DRM/content protection, live streaming, recommendation engine

---

## Part 1: The Problem — Why Video Is Hard

### 1.1 Video Is Not a JPEG

The single most important mental model for this interview: video is fundamentally
different from every other type of content a web application serves.

A text post is 1-10 KB. An image is 100 KB to a few MB. A 10-minute 1080p video is
**1-3 GB** before compression, and even after heavy compression, a typical YouTube video
is 500 MB to 1 GB. Serving this at scale means:

- A server cannot send 1 GB in one HTTP response — it must stream in chunks
- A single format does not work for all devices (iPhone, Android, 4K TV, slow 3G phone)
- One copy of the video is not enough — you need multiple quality versions
- Serving from a single origin server to users worldwide is physically impossible (speed of light)

These four facts — chunked delivery, multiple formats, multiple quality levels, geographic
distribution — are the entire reason video streaming is a distinct engineering discipline.

### 1.2 Two Completely Separate Systems

The moment you receive a "design YouTube" question, split it mentally into two systems:

```
THE TWO SYSTEMS
=================

  SYSTEM 1: UPLOAD PIPELINE (write path)
  ────────────────────────────────────────
  User uploads video → your servers → storage → transcoding → ready to watch
  
  Key properties:
  • Async (happens in background after upload completes)
  • Expensive compute (transcoding is CPU-intensive)
  • Takes minutes to hours per video
  • Triggered by: video upload
  
  SYSTEM 2: STREAMING DELIVERY (read path)
  ──────────────────────────────────────────
  User presses play → your CDN → player → smooth video
  
  Key properties:
  • Synchronous (user is watching in real time)
  • Latency-critical (stalls = users leave)
  • Extremely high read volume (millions of concurrent viewers)
  • Triggered by: watch request
```

The upload pipeline is a data engineering problem. The delivery pipeline is a
distributed systems problem. They share almost no code and very few components.

### 1.3 The User Journey

Understanding the full user journey prevents gaps in your design:

**Upload side:**
1. Creator selects video file on their device
2. Client uploads the raw video file to your upload service (this could take minutes)
3. Upload service stores the raw file in object storage
4. A message is published to a queue: "new video to process"
5. Transcoding workers pick up the job and create multiple quality versions
6. Processed segments are stored in object storage and pushed to CDN edge nodes
7. Video metadata (title, status, available qualities) is updated in the database
8. Creator's video is now visible and playable

**Watch side:**
1. Viewer clicks on a video
2. Player fetches the video manifest file (a text file listing all available quality segments)
3. Player selects an initial quality based on current network speed
4. Player fetches video segments one at a time from the CDN
5. CDN serves segments from cache (fast) or fetches from origin (slower, rare)
6. Player continuously adjusts quality based on measured download speed (adaptive bitrate)
7. Viewer watches without buffering (if everything works)

### 1.4 Scale Numbers to Know

For a YouTube-scale system (memorize these for the interview):

| Metric | Number | Why It Matters |
|--------|--------|----------------|
| Videos uploaded per day | 500 hours/minute | Sets transcoding throughput requirement |
| Concurrent viewers | 30M+ at peak | Sets CDN capacity requirement |
| Average video size (raw) | 300 MB (10 min, 1080p) | Sets storage requirement |
| Storage for transcoded versions | ~3× raw size | Multiple quality versions |
| CDN cache hit rate | 80-95% | % of requests served from edge |
| Segment size (HLS) | 2-6 seconds | Trade-off: latency vs. overhead |
| Time to transcode 1hr video | 30-120 min (worker) | Parallelism needed |
| Monthly storage growth | Petabytes | Why you need object storage |

For a typical interview, you will scale to "a medium-sized video platform" — say 100K
uploads per day, 1M concurrent viewers at peak. The architecture is the same; only
the numbers differ.

### 1.5 Brainstorming Q&A — Part 1

**Q: Should I ask if we need live streaming or just video-on-demand?**

Yes — this is the first clarifying question to ask. Live streaming and video-on-demand
share some components (CDN, adaptive bitrate) but differ significantly in the upload
pipeline. Live streaming requires a real-time ingest protocol (RTMP), segment
generation in real time (latency: 2-6 seconds), and cannot do the multi-hour transcoding
job that VOD does offline. At L5, clarifying this question and then scoping to VOD is
the right move: "Let me focus on video-on-demand first — if we have time, I'll discuss
how live streaming would change the ingest pipeline."

**Q: Why not just upload directly to S3 and serve from S3?**

Upload to S3 is fine for the raw file. But serving video directly from S3 is wrong
for two reasons. First, S3 is not a CDN — it does not cache content at edge locations
near users. A viewer in Tokyo streaming from an S3 bucket in Virginia pays full
cross-continent latency on every segment. Second, S3 costs scale with egress — serving
millions of video streams directly from S3 would be catastrophically expensive. CDN
dramatically reduces both latency and egress cost. The correct design: S3 (or equivalent)
as origin store, CDN as the delivery layer.

**Q: Why transcode? Why not just serve the original file the user uploaded?**

Two reasons. First, format compatibility: a user might upload a `.mov` file from their
iPhone, but Samsung TVs expect `.mp4`, Android Chrome expects WebM, and Safari expects
HLS. You cannot serve one format that works everywhere. Transcoding converts to universal
formats. Second, adaptive bitrate: you need the video at multiple quality levels (360p,
480p, 720p, 1080p) so you can serve lower quality to viewers on slow connections. You
cannot create lower-quality versions without transcoding. Serving the raw upload would
mean either breaking some devices or forcing everyone onto one quality level.

---

## Part 2: Requirements

### 2.1 Functional Requirements

Confirm these with the interviewer before designing anything:

**Core upload features:**
- Users can upload videos (up to 10 GB file size)
- After upload, videos are processed (transcoded) and become watchable
- Video metadata: title, description, thumbnail, duration, owner

**Core streaming features:**
- Users can watch videos by URL
- Video plays at appropriate quality for their connection speed
- Seeking (jumping to a specific timestamp) works
- Buffering is minimal (< 1% of playback time)

**Basic social features (in scope but not the focus):**
- View count
- Like/dislike
- Comments (simplified — just store, no complex threading)
- Basic search by title (not full-text search relevance ranking)

### 2.2 Non-Functional Requirements

| Requirement | Target | Why |
|-------------|--------|-----|
| Upload latency | < 5 min for a 1 GB file | Users abandon long uploads |
| Processing time | < 30 min for a 10 min video | Creator wants feedback quickly |
| Streaming start time | < 2 seconds (TTFF) | Time-to-first-frame: key UX metric |
| Buffering ratio | < 1% | % of playback time spent buffering |
| Availability | 99.9% | Acceptable for L5 scope |
| Durability | 99.999999% (11 nines) | Video files must never be lost |
| Concurrent viewers | 1M+ | Peak load |
| Storage | Petabytes | Long-term video retention |

### 2.3 Clarifying Questions for the Interview

Ask these in the first 3 minutes before drawing anything:

1. "Are we designing upload + storage + streaming, or just one piece?"
2. "VOD only, or does this include live streaming?"
3. "What's the target geography — single region, or global?"
4. "Rough scale: how many uploads per day, concurrent viewers at peak?"
5. "Do we need DRM / content protection?" (Scope it out at L5)

### 2.4 What We Are NOT Building (Scope Boundaries)

Explicitly stating scope-outs prevents interview derailment:

- **Not in scope**: Live streaming, DRM, multi-region geo-routing, recommendation engine, monetization (ads), creator analytics dashboard
- **Simplified**: Search (basic keyword match on title, not semantic ranking), comments (flat list, no threading), thumbnails (auto-generated, no manual upload)

---

## Part 3: High-Level Design

### 3.1 The Four Main Subsystems

```
HIGH-LEVEL ARCHITECTURE
=========================

  UPLOAD PATH (write):

  Creator → [Client App]
                │
                ▼
         [Upload Service]  ←── Handles chunked upload
                │
                ▼
         [Object Storage]  ←── Raw video files (S3-equivalent)
                │
                ▼
         [Job Queue]       ←── Kafka / SQS: "transcode this video"
                │
                ▼
       [Transcoder Workers] (pool of N machines)
                │ (creates multiple qualities: 360p / 480p / 720p / 1080p)
                ▼
         [Object Storage]  ←── Processed segments + manifests
                │
                ▼
            [CDN]          ←── Pre-warmed or lazily populated


  STREAMING PATH (read):

  Viewer → [API Server]   ←── Fetch video metadata + manifest URL
              │
              ▼
           [CDN]           ←── Serve video segments (cached)
              │ (cache miss: fetch from origin)
              ▼
       [Object Storage]    ←── Origin: segments + manifests
              │
              ▼
         [Video Player]    ←── ABR: picks quality per segment


  SHARED COMPONENTS:
  
  [Metadata DB]  ←── PostgreSQL: video records, user records, view counts
  [Cache]        ←── Redis: hot video metadata, manifest file cache
  [CDN]          ←── CloudFront / Fastly: serves 95%+ of video traffic
```

### 3.2 Component Responsibilities

| Component | Responsibility | Technology |
|-----------|---------------|------------|
| Upload Service | Receive chunked upload, store raw video | Node.js / Go |
| Object Storage | Store raw + processed video files | S3 / GCS |
| Job Queue | Decouple upload from transcoding | Kafka or SQS |
| Transcoder Workers | Convert video to multiple formats/qualities | FFmpeg on EC2 spot |
| Metadata DB | Video records, user records, view counts | PostgreSQL |
| Cache | Hot metadata, manifest files | Redis |
| CDN | Edge delivery of video segments | CloudFront / Fastly |
| Video Player | ABR algorithm, segment fetching, playback | HLS.js / Shaka Player |

---

## Part 4: API Design

### 4.1 Upload APIs

**Initialize Upload**
```
POST /api/v1/uploads
Request:  { file_name, file_size_bytes, content_type, title, description }
Response: { upload_id, upload_url, chunk_size_bytes, total_chunks }
Errors:   400 (invalid file type), 413 (file too large > 10GB), 401 (not authenticated)
```

**Upload Chunk**
```
PUT /api/v1/uploads/{upload_id}/chunks/{chunk_number}
Headers:  Content-Range: bytes 0-5242879/1073741824
Body:     [binary chunk data]
Response: { chunk_number, received, upload_progress_pct }
Errors:   409 (chunk already uploaded), 416 (invalid range), 404 (upload_id not found)
```

**Complete Upload**
```
POST /api/v1/uploads/{upload_id}/complete
Request:  { chunk_checksums: ["sha256:...", ...] }
Response: { video_id, status: "processing", estimated_ready_at }
Errors:   400 (missing chunks), 422 (checksum mismatch)
```

**Get Upload Status**
```
GET /api/v1/uploads/{upload_id}/status
Response: {
  upload_id, video_id,
  status: "uploading" | "processing" | "ready" | "failed",
  progress_pct,
  available_qualities: ["360p", "720p", "1080p"],
  error_message?
}
Errors:   404 (upload not found), 403 (not owner)
```

### 4.2 Streaming APIs

**Get Video Metadata + Manifest URL**
```
GET /api/v1/videos/{video_id}
Response: {
  video_id, title, description, duration_seconds,
  view_count, like_count,
  owner: { user_id, username, avatar_url },
  thumbnail_url,
  manifest_url,          ← CDN URL for the HLS master manifest
  available_qualities,
  created_at
}
Errors:   404 (video not found), 403 (private video, not authorized)
```

**Record View**
```
POST /api/v1/videos/{video_id}/views
Request:  { watch_duration_seconds, quality_watched }
Response: 204 No Content
Errors:   404 (video not found)
```

**Get Comments**
```
GET /api/v1/videos/{video_id}/comments?page=1&limit=20
Response: {
  comments: [{ comment_id, user, text, created_at, like_count }],
  next_page_token
}
```

**Post Comment**
```
POST /api/v1/videos/{video_id}/comments
Request:  { text }
Response: { comment_id, text, created_at }
Errors:   400 (text too long > 2000 chars), 401 (not authenticated)
```

---

## Part 5: Database Schema

### 5.1 Videos Table

```sql
CREATE TABLE videos (
  video_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_id        UUID NOT NULL REFERENCES users(user_id),
  title           VARCHAR(200) NOT NULL,
  description     TEXT,
  status          VARCHAR(20) NOT NULL DEFAULT 'processing',
                  -- 'processing' | 'ready' | 'failed' | 'deleted'
  duration_seconds INT,
  raw_storage_key  VARCHAR(500),   -- S3 key for the raw uploaded file
  manifest_url     VARCHAR(500),   -- CDN URL for the HLS master playlist
  thumbnail_url    VARCHAR(500),
  view_count       BIGINT NOT NULL DEFAULT 0,
  like_count       BIGINT NOT NULL DEFAULT 0,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  published_at     TIMESTAMPTZ
);

CREATE INDEX idx_videos_owner ON videos(owner_id);
CREATE INDEX idx_videos_status ON videos(status);
CREATE INDEX idx_videos_published ON videos(published_at DESC)
  WHERE status = 'ready';

-- Full-text search index on title
CREATE INDEX idx_videos_title_fts ON videos
  USING gin(to_tsvector('english', title));
```

### 5.2 Upload Sessions Table

```sql
CREATE TABLE upload_sessions (
  upload_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  video_id         UUID REFERENCES videos(video_id),
  owner_id         UUID NOT NULL REFERENCES users(user_id),
  file_name        VARCHAR(255) NOT NULL,
  file_size_bytes  BIGINT NOT NULL,
  chunk_size_bytes INT NOT NULL DEFAULT 5242880,  -- 5 MB per chunk
  total_chunks     INT NOT NULL,
  uploaded_chunks  INT NOT NULL DEFAULT 0,
  status           VARCHAR(20) NOT NULL DEFAULT 'in_progress',
                   -- 'in_progress' | 'complete' | 'expired'
  raw_storage_key  VARCHAR(500),  -- S3 multipart upload ID
  expires_at       TIMESTAMPTZ NOT NULL,  -- 24 hours from creation
  created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_upload_sessions_owner ON upload_sessions(owner_id);
CREATE INDEX idx_upload_sessions_expires ON upload_sessions(expires_at)
  WHERE status = 'in_progress';

-- Track which chunks have been received (for resumability)
CREATE TABLE upload_chunks (
  upload_id    UUID NOT NULL REFERENCES upload_sessions(upload_id),
  chunk_number INT NOT NULL,
  checksum     CHAR(64) NOT NULL,  -- SHA-256
  received_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (upload_id, chunk_number)
);
```

### 5.3 Video Qualities Table

```sql
CREATE TABLE video_qualities (
  video_id       UUID NOT NULL REFERENCES videos(video_id),
  quality_label  VARCHAR(10) NOT NULL,  -- '360p', '480p', '720p', '1080p'
  width          INT NOT NULL,
  height         INT NOT NULL,
  bitrate_kbps   INT NOT NULL,
  codec          VARCHAR(20) NOT NULL DEFAULT 'h264',
  storage_key    VARCHAR(500) NOT NULL,  -- S3 prefix for segments
  segment_count  INT,
  duration_seconds DECIMAL(10,3),
  file_size_bytes BIGINT,
  status         VARCHAR(20) NOT NULL DEFAULT 'processing',
  created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (video_id, quality_label)
);
```

### 5.4 Comments Table

```sql
CREATE TABLE comments (
  comment_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  video_id     UUID NOT NULL REFERENCES videos(video_id),
  user_id      UUID NOT NULL REFERENCES users(user_id),
  text         TEXT NOT NULL CHECK (char_length(text) <= 2000),
  like_count   INT NOT NULL DEFAULT 0,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  deleted_at   TIMESTAMPTZ  -- soft delete
);

CREATE INDEX idx_comments_video ON comments(video_id, created_at DESC)
  WHERE deleted_at IS NULL;
```

---

## Part 6: Upload Pipeline — Getting the Video In

### 6.1 Why Naive Upload Fails

The simplest approach: accept a file in one HTTP POST request. This fails at video scale:

- A 1 GB video on a 10 Mbps upload connection takes **800 seconds** (~13 minutes)
- If the connection drops at second 700, the entire upload restarts from zero
- The HTTP server must hold the connection open for the entire duration
- Memory pressure on the server if buffering the entire body before writing

The correct approach: **chunked upload with resumability**.

### 6.2 Chunked Upload Design

```
CHUNKED UPLOAD FLOW
=====================

  CLIENT                          UPLOAD SERVICE              OBJECT STORAGE

  1. POST /uploads                 Create upload session
     (file_name, file_size)        Generate upload_id
                                   Reserve S3 multipart upload
                                   ─────────────────────────────────────────
                                   Return: upload_id, chunk_size

  2. PUT /uploads/{id}/chunks/0    Validate auth + chunk number
     [binary chunk 0-5MB]         Write chunk 0 to S3 multipart part 1 ──────►
                                   Record in upload_chunks table
                                   Return: received=true

  3. PUT /uploads/{id}/chunks/1
     [binary chunk 5-10MB]        Write chunk 1 to S3 multipart part 2 ──────►
                                   ...

  [Network drops at chunk 45]

  CLIENT RECONNECTS:
  4. GET /uploads/{id}/status      Query upload_chunks table
                                   Return: uploaded_chunks=[0..44]

  5. Resume from chunk 45 ───────► Continue from where it left off

  AFTER ALL CHUNKS:
  6. POST /uploads/{id}/complete   Validate all chunks received
                                   Complete S3 multipart upload ─────────────►
                                   Create video record (status=processing)
                                   Publish to job queue
                                   Return: video_id
```

**Chunk size**: 5-10 MB per chunk is the sweet spot. Too small (< 1MB) → too many
requests overhead. Too large (> 50MB) → long recovery time if a chunk fails.

**Checksum per chunk**: Send SHA-256 of each chunk. The upload service verifies before
accepting. Prevents silent data corruption (bit flips during network transmission).

**Presigned URLs** (optimization): For large files, instead of the upload service
receiving bytes and forwarding to S3, generate a presigned S3 URL per chunk and have
the client upload directly to S3. This removes the upload service from the data path,
reducing bandwidth cost and increasing throughput. The upload service only handles
metadata (tracking which chunks completed).

### 6.3 Job Queue: Decoupling Upload from Transcoding

After the upload completes, the upload service publishes a message:

```json
{
  "video_id": "vid_abc123",
  "raw_s3_key": "raw/vid_abc123/original.mp4",
  "file_size_bytes": 1073741824,
  "duration_seconds": 600,
  "requested_qualities": ["360p", "480p", "720p", "1080p"]
}
```

Why a queue (Kafka/SQS) rather than calling the transcoder directly?

1. **Durability**: If all transcoders are busy, the job waits in the queue rather than failing
2. **Retry logic**: Failed transcoding jobs are re-queued automatically
3. **Backpressure**: The queue absorbs spikes — 1,000 uploads in a minute queue up, transcoders
   process at their own rate
4. **Decoupling**: Upload service and transcoding service can scale independently

### 6.4 Brainstorming Q&A — Part 6

**Q: What happens if the user closes the browser tab in the middle of an upload?**

The upload session record remains in the database with `status='in_progress'`. The chunks
uploaded so far are preserved in both the `upload_chunks` table and the S3 multipart upload.
When the user returns (same browser, or a different device if they log in), the client
calls `GET /uploads/{id}/status` to discover which chunks were already uploaded. The upload
resumes from the first missing chunk. The session has an `expires_at` (typically 24 hours).
After expiry, a background job cancels the S3 multipart upload (to avoid orphaned charges)
and marks the session expired. This is the TUS protocol approach, which YouTube and
Google Drive both implement.

**Q: How do you handle duplicate uploads (same user uploads the same video twice)?**

Content-addressable deduplication: compute a SHA-256 hash of the complete file on the client
before uploading. Send the hash with the `POST /uploads` request. The server checks if a video
with this content hash already exists for this user. If yes, return the existing `video_id`
immediately without re-uploading. This prevents users from accidentally re-uploading by
clicking the button twice. Cross-user deduplication (don't store two copies of the exact same
video file) is a more complex optimization (it requires matching across users and handling
copyright considerations) — scope it out at L5.

**Q: How do we handle files larger than S3's multipart limit?**

S3 multipart upload supports up to 10,000 parts, with a minimum part size of 5 MB.
Maximum object size: 5 TB. For practical video files (up to 10 GB as stated in our
requirements), this is more than sufficient. A 10 GB file with 5 MB chunks = 2,000
parts, well under the limit. Even if we extended to 100 GB files, 5 MB × 10,000 = 50 GB
per file — still fine for broadcast-quality video. For truly massive files (feature film
raw footage at 1 TB+), you would use a larger chunk size (50-100 MB per chunk).

---

## Part 7: Transcoding Pipeline — One Video, Many Formats

### 7.1 Why Transcode?

A raw video uploaded from a creator's iPhone might be:
- Format: `.mov` (QuickTime container)
- Codec: HEVC / H.265 (Apple's preferred codec)
- Resolution: 4K (3840×2160)
- File size: 3 GB for a 10-minute clip

This file is not suitable for streaming because:
1. HEVC is not universally supported (Android Chrome on old devices can't decode it)
2. 4K at 3 GB is too large for mobile viewers on LTE
3. `.mov` is not streamable (the metadata is at the end of the file, so you cannot seek
   to the middle without downloading the whole file)

Transcoding converts this into multiple streamable versions:

### 7.2 The Encoding Ladder

For L5, know this encoding ladder:

| Quality | Resolution | Bitrate | Use Case |
|---------|------------|---------|----------|
| 360p | 640×360 | 400 Kbps | 3G mobile, very slow connections |
| 480p | 854×480 | 700 Kbps | Standard mobile on LTE |
| 720p | 1280×720 | 2.5 Mbps | Default desktop, good WiFi |
| 1080p | 1920×1080 | 5 Mbps | Fast connection, good TV/monitor |
| 1080p60 | 1920×1080 | 8 Mbps | Gaming/sports content at 60fps |

Each version is:
- Encoded with H.264 (AVC) codec — the universal baseline, supported everywhere
- Packaged in MP4 container (or segmented into HLS chunks)
- Segmented into 6-second chunks for adaptive bitrate streaming

**Total storage multiplier**: If the original 10-minute video is 300 MB in 1080p,
the transcoded versions add: 360p (~15MB) + 480p (~25MB) + 720p (~90MB) + 1080p (~180MB)
= ~310 MB more. Total storage ≈ 2× the original file. Add thumbnails and manifest files:
roughly 3× the original file size for the complete processed set.

### 7.3 Transcoding is CPU-Intensive

Transcoding a 1-hour video at 1080p → 720p takes roughly 1-2 hours of CPU time on a
single core. Real transcoding systems:
- Use multiple CPU cores per job (FFmpeg is parallelized with `-threads N`)
- Split a video into segments and transcode segments in parallel across multiple workers
- Use hardware acceleration (NVIDIA NVENC, Intel QuickSync) to speed up encoding 5-10×

For an L5 interview, the key architectural point is: **transcoding is the most expensive
operation in the system**. You must use a worker pool with a queue, not inline processing.

### 7.4 Transcoder Worker Architecture

```
TRANSCODING PIPELINE
======================

  JOB QUEUE (Kafka)
       │
       ▼
  ┌─────────────────────────────────────────────────────────┐
  │                 TRANSCODER WORKER POOL                   │
  │                                                         │
  │  Worker 1:  [Downloading raw from S3...]               │
  │  Worker 2:  [Transcoding: 720p pass 1/3...]            │
  │  Worker 3:  [Uploading 480p segments to S3...]         │
  │  Worker 4:  [Transcoding: 1080p pass 2/3...]           │
  │  Worker N:  [Idle — waiting for work]                  │
  │                                                         │
  └─────────────────────────────────────────────────────────┘
       │
       ▼
  PER-QUALITY PARALLELISM:
  A single video can be split: worker 1 → 360p, worker 2 → 480p, worker 3 → 720p
  All qualities processed simultaneously (not sequentially)
       │
       ▼
  S3: segments + manifest files stored
       │
       ▼
  DB UPDATE: video status = 'ready', qualities populated
       │
       ▼
  NOTIFY CREATOR: webhook / email "Your video is ready"
```

**Worker failure handling**:
- Jobs have a visibility timeout (SQS: 30 minutes, Kafka: consumer group tracking)
- If a worker dies mid-transcode, the job becomes visible again after the timeout
- Another worker picks it up and starts over
- Idempotent: transcoding is deterministic (same input → same output), so re-running is safe
- Failed jobs (after N retries) go to a dead-letter queue for manual inspection

### 7.5 Output: HLS Segments + Manifest

The transcoder outputs:

**For each quality level (e.g., 720p)**:
```
s3://my-videos/vid_abc123/720p/segment_000.ts
s3://my-videos/vid_abc123/720p/segment_001.ts
...
s3://my-videos/vid_abc123/720p/segment_299.ts  (300 segments × 2 sec = 10 min)
s3://my-videos/vid_abc123/720p/playlist.m3u8   (lists all segments)
```

**Master manifest** (tells the player which qualities are available):
```
s3://my-videos/vid_abc123/master.m3u8
```

The master manifest is a text file:
```
#EXTM3U
#EXT-X-VERSION:3
#EXT-X-STREAM-INF:BANDWIDTH=400000,RESOLUTION=640x360
360p/playlist.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=700000,RESOLUTION=854x480
480p/playlist.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=2500000,RESOLUTION=1280x720
720p/playlist.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=5000000,RESOLUTION=1920x1080
1080p/playlist.m3u8
```

This is the HLS (HTTP Live Streaming) format, developed by Apple and now an industry standard.

### 7.6 Intern → Staff Progression: Transcoding

**Intern**: "We transcode the video to different formats."

**L3**: "We use FFmpeg to convert the uploaded video to H.264 MP4 at multiple resolutions:
360p, 720p, and 1080p. The worker polls a queue for jobs."

**L4**: "Each quality is transcoded in parallel on separate workers to minimize total
processing time. FFmpeg outputs HLS segments (6-second `.ts` files) and a playlist manifest.
The master manifest lists all quality variants. If a worker fails, the job returns to the
queue after the visibility timeout expires."

**L5**: "Per-quality parallelism reduces transcoding time from O(N qualities) sequential
to O(1 quality) — they all finish at roughly the same time. I'd also consider segment-level
parallelism: split a 1-hour video into 60 one-minute chunks, transcode each chunk in parallel
on separate workers, then concatenate the outputs. This reduces the time to first segment
available from 30+ minutes to 2-3 minutes. The first few segments can be pushed to the CDN
immediately, making the video 'watchable' while the full transcode completes."

### 7.7 Brainstorming Q&A — Part 7

**Q: What codec should we use for transcoding?**

At L5, say H.264 (AVC) as the baseline codec — it runs on every device built in the last
15 years. More advanced options: H.265 (HEVC) achieves the same quality at ~50% lower
bitrate, but is not universally hardware-decoded on older devices. AV1 (by Google/Netflix)
is even more efficient but encoding is 50-100× slower than H.264. The practical choice
for an L5 design: H.264 for universal compatibility, with H.265 as an optional upgrade
for newer devices. The decision is a business trade-off between transcoding cost, storage
cost, and device support.

**Q: How do you handle a video that fails transcoding partway through?**

The job failure goes to a dead-letter queue after N retry attempts. The video record stays
in `status='processing'` until a background sweeper notices it has been stuck for more than
2× the expected processing time and moves it to `status='failed'`. The creator is notified
(email/webhook). In production, the most common failure causes are: codec not supported by
FFmpeg, corrupted file (dropped during upload), and resource exhaustion on the worker. The
retries handle transient resource issues; the dead-letter queue handles structural failures
(corrupted file) that need human review.

**Q: When should we push segments to the CDN vs. letting CDN pull from origin?**

Two approaches: push (proactive cache warming) and pull (lazy loading). For popular
content (new video from a creator with 10M subscribers), push is better — pre-populate
CDN edge nodes before the video is published, so the first wave of viewers gets a cache hit.
For long-tail content (videos with 100 views), lazy loading is fine — the first viewer
experiences the cache miss (CDN fetches from S3), subsequent viewers hit cache. At L5
scale, the top 20% of videos account for 80%+ of watch traffic — pre-warming only those
videos is a high-ROI optimization.

---

## Part 8: CDN Delivery — Getting Video to Users Fast

### 8.1 Why CDNs Are Non-Negotiable

Without a CDN, every video request goes to your origin servers. For a popular video
with 1 million concurrent viewers:
- Each viewer fetches a new 6-second segment every 6 seconds
- That's 1M requests/6 seconds = ~167,000 requests/second to your origin
- Each segment is ~2-3 MB = 167,000 × 2.5 MB = 417 GB/second of egress
- No single server or even cluster of servers can handle this
- Cross-continent latency means a viewer in Tokyo streaming from Virginia waits 150ms
  per segment fetch — that's 25 seconds of buffering in a 10-minute video

A CDN solves all of this by caching content at edge nodes worldwide.

### 8.2 How CDN Delivery Works

```
CDN DELIVERY MODEL
===================

  Viewer in Tokyo ──► Tokyo CDN Edge ──► Cache HIT ──► Serve from edge (fast, < 5ms)
                                    │
                                    └─► Cache MISS ──► Fetch from S3 (slow, once)
                                                           │
                                                           └─► Store in cache
                                                               Next viewer: cache HIT

  KEY INSIGHT:
  A 1080p 6-second segment ≈ 3.75 MB
  Once cached at the Tokyo edge, it serves ALL Tokyo viewers simultaneously.
  The origin (S3) is only hit once per segment per edge node.
  
  With 95% cache hit rate:
  - 1M viewers → 5% cache misses = 50,000 origin requests/6sec ≈ 8,333/sec to S3
  - Much more manageable than 167,000/sec
```

### 8.3 Cache Key Design

The CDN caches segments by their URL. URLs must be stable:
```
https://cdn.yourdomain.com/vid_abc123/720p/segment_042.ts
```

**Do NOT include timestamps or user-specific data in segment URLs.** Every user watching
at the same quality gets the same URL, which means they all share the same cached copy.

**Manifest files are different**: The master manifest is small (< 1KB) and changes as
qualities become available. Cache it with a short TTL (60 seconds) so the player gets
updated quality options quickly after a new quality finishes transcoding.

**Segments are immutable**: Once a segment is created, its content never changes.
Cache segments with a long TTL (24 hours or more). There is no cache invalidation needed.

### 8.4 Cache Hit Rate Optimization

Cache hit rate is the single most important CDN metric. Higher hit rate = lower origin
cost + lower latency for viewers.

Factors that improve hit rate:
1. **Segment reuse**: All viewers of the same video at the same quality share the same segments.
   A video with 1M views per day has near-100% hit rate after the first few viewers.
2. **Pre-warming popular videos**: Push new videos from popular creators to CDN edges before
   publishing. The first wave of viewers gets cache hits.
3. **Geographic hot-spot matching**: If 80% of a video's viewers are in the US, ensure US
   CDN edges have the video. Use CDN analytics to understand per-geography hit rates.
4. **Avoiding cache busting**: Never put user-specific query parameters in segment URLs.

### 8.5 Brainstorming Q&A — Part 8

**Q: What is the CDN's origin? Is it always S3?**

In our design, yes — the CDN's origin is S3, where all transcoded segments live. Some
systems add an "origin shield" layer between the CDN edges and S3: one regional cache that
absorbs all CDN edge misses for a region before they reach S3. This reduces S3 egress costs
significantly. Example: if 100 CDN edges in Asia Pacific all miss a segment simultaneously
(cold start), they all fire separate requests to S3. With an origin shield in Singapore,
only one request goes to S3 — the shield serves the other 99 CDN edges. At L5 scale, an
origin shield is an important optimization but not strictly required for the design to be
correct.

**Q: How do we handle CDN costs? CDN egress is expensive.**

CDN egress is typically $0.02-0.08 per GB depending on the CDN provider and region.
For a platform streaming 100 TB/day, that's $2,000-$8,000/day in CDN costs alone. Cost
reduction strategies: (1) negotiate volume discounts with CDN providers; (2) use multi-CDN
routing to optimize for cost vs. performance; (3) use more aggressive compression (HEVC
instead of H.264 halves storage and egress costs at same quality); (4) use a tiered quality
ladder — don't serve 1080p to viewers with slow connections. At L5, acknowledging CDN cost
as a major operational expense demonstrates mature engineering thinking.

---

## Part 9: Adaptive Bitrate Streaming (ABR)

### 9.1 The Problem ABR Solves

Imagine you're on a train watching a video on your phone. The train enters a tunnel —
network speed drops from 20 Mbps to 1 Mbps. If the player is fetching 5 Mbps 1080p
segments, it will buffer (freeze) for several seconds until it has enough data buffered
to keep playing.

The alternative: the player dynamically adjusts the quality it downloads based on
available bandwidth. When bandwidth drops, switch to lower quality. When it improves,
switch back to higher quality. The video never freezes — it just briefly looks worse,
then recovers.

This is Adaptive Bitrate Streaming (ABR). It is the core technology that makes
mobile video watching actually work.

### 9.2 HLS: How It Works at the Player Level

The player implements ABR using the HLS protocol:

**Step 1**: Fetch the master manifest from the CDN.
The master manifest lists all quality variants and their bitrates.

**Step 2**: Measure current network bandwidth.
The player downloads the first segment at a default quality (usually 480p) and measures
how long it took. If it took 1 second to download a 6-second 480p segment (700 Kbps),
the estimated bandwidth is 700 Kbps × (segment_size / segment_duration) ≈ 700 Kbps.

**Step 3**: Pick the quality whose bitrate is ≤ 80% of measured bandwidth.
80% safety margin accounts for variability. If measured bandwidth is 3 Mbps:
- 360p (400 Kbps) ✓
- 480p (700 Kbps) ✓
- **720p (2.5 Mbps) ← Pick this (2.5 < 0.8 × 3)**
- 1080p (5 Mbps) ✗ (too risky)

**Step 4**: Fetch the next segment at the chosen quality. Repeat.

```
ABR QUALITY SWITCHING
======================

  Time:      0s   6s   12s  18s  24s  30s  36s  42s
  Bandwidth: 10   10   10   2    1    2    8    10  (Mbps)
  Quality:  1080 1080 1080  720  480  480  720 1080

  Viewer experience: 3 quality drops, no buffering.
  vs. fixed 1080p:   buffers at t=18s and stays buffered.
```

### 9.3 Buffer Management

The player always maintains a buffer — downloaded but not yet played video:

- **Startup**: Fill buffer to N seconds (typically 10-15s) before starting playback
- **Steady state**: Keep buffer between 15-30 seconds
- **Bandwidth drop**: Stop fetching high-quality segments, fetch lower quality to maintain buffer
- **Buffer depleted to 0**: Rebuffering event — the player pauses. This is the worst
  user experience outcome.

The player never wants to drop below a "panic threshold" (~5 seconds) — if the buffer
is draining toward 5 seconds, it aggressively drops to the lowest quality regardless
of what the bandwidth estimate says.

### 9.4 Seeking (Jumping to a Timestamp)

A key feature: users can jump to any point in the video (seek). HLS makes this efficient:

Since video is pre-segmented into 6-second chunks, seeking to timestamp 200s means:
- Calculate which segment contains second 200: segment 33 (200 / 6 = 33.3)
- Fetch segment 33 from CDN
- Discard everything in the current buffer
- Begin playing from segment 33

No need to download the entire video up to second 200. Seeking is O(1) in terms of
data transfer.

### 9.5 Intern → Staff Progression: ABR

**Intern**: "The player downloads the video in chunks."

**L3**: "HLS splits video into 6-second segments. The player downloads segments one at a
time. A manifest file lists all available segments."

**L4**: "The master manifest lists quality variants. The player picks a quality based on
measured bandwidth. When bandwidth drops, it switches to lower quality segments. This prevents
rebuffering at the cost of temporary quality reduction."

**L5**: "The ABR algorithm must balance two competing goals: maximize quality (pick highest
bitrate that fits in bandwidth) and avoid rebuffering (maintain buffer above panic threshold).
Buffer-based ABR (like Netflix's BOLA) uses buffer occupancy as the primary signal rather
than bandwidth estimates, because bandwidth estimates are noisy. When buffer > 15s, pick
higher quality. When buffer < 10s, drop quality regardless of bandwidth. This is more
robust than pure bandwidth-based algorithms on variable networks (mobile, WiFi). The
startup experience is also separate: play at low quality immediately (to hit TTFF < 2s),
then aggressively ramp up quality over the first 30 seconds once the buffer is filled."

### 9.6 Brainstorming Q&A — Part 9

**Q: Why 6-second segments? Why not 1 second or 30 seconds?**

Segment duration is a fundamental trade-off:
- **Short segments (1-2s)**: Faster adaptation to bandwidth changes (quality switches faster),
  but high overhead — each segment requires a separate HTTP request, and HTTP round-trip time
  is wasted per segment.
- **Long segments (30s)**: Very low overhead, but if bandwidth drops, the player is committed
  to 30 seconds of high-quality data it can't afford — leading to rebuffering before it can
  switch quality.
- **6-second sweet spot**: Adapts within 6 seconds of a bandwidth change, overhead is 1 HTTP
  request per 6 seconds (manageable), and file size (~3 MB) is small enough to download quickly.

**Q: What happens if a CDN edge goes down while a user is watching?**

The player detects the failure when a segment request times out or returns an error.
Modern HLS players (HLS.js, Shaka Player) implement automatic failover: they try an
alternative CDN endpoint, a different edge node, or fall back to the origin. This is
called "CDN fallback" or "multi-CDN failover." For our single-CDN design at L5, the player
retries the same URL 2-3 times with exponential backoff before showing an error. In practice,
CDN availability is > 99.9%, making this a rare event.

---

## Part 10: Scaling and Failure Handling

### 10.1 Transcoding at Scale: Spot Instances

Transcoding workers are CPU-intensive but not latency-sensitive (a 30-minute transcode
is fine). This makes them ideal for EC2 Spot Instances (AWS) or preemptible VMs (GCP):
- 60-70% cheaper than on-demand instances
- Can be interrupted at any time (2-minute warning)
- The job queue + retry logic handles interruptions gracefully
- A new worker picks up the interrupted job automatically

For a burst of uploads (e.g., a major event causing 10× normal uploads), the worker pool
auto-scales: add more spot instances, consume the queue faster, scale back when the queue
drains. The queue absorbs the burst.

### 10.2 Video Metadata: Cache Hot Videos

The video metadata (title, view count, manifest URL) is read on every video page load.
For popular videos, this is a very hot read path:

```
READ PATH OPTIMIZATION
========================

  Request: GET /api/v1/videos/{video_id}
  
  1. Check Redis cache key: "video:{video_id}"
     HIT (95%+ for popular videos) → Return from cache
     MISS → Query PostgreSQL
  
  2. Cache TTL: 60 seconds for hot videos
     (view count can be stale by up to 60s — acceptable)
  
  3. Cache invalidation: when video status changes
     (processing → ready), publish an invalidation event
     and delete/update the cache key

  View count updates:
  - Do NOT update the DB on every view (too many writes for viral videos)
  - Batch updates: accumulate view counts in Redis (INCR), flush to DB every minute
  - Result: view count in DB may lag by up to 1 minute — acceptable
```

### 10.3 Storage Lifecycle Management

Videos accumulate over time. Storage cost grows linearly. Lifecycle management:

- **Hot tier (S3 Standard)**: Videos less than 30 days old. Frequent access.
- **Warm tier (S3-IA / Infrequent Access)**: 30-365 days old. Lower cost, slightly higher retrieval fee.
- **Cold tier (S3 Glacier)**: > 1 year old, or videos with < 100 views/month. Very low cost, retrieval takes minutes.
- **Deletion policy**: Apply per platform rules (e.g., deleted videos removed from all tiers after 30 days).

Automated lifecycle policies move segments between tiers based on age and access frequency.
For most L5 interviews, mentioning "object storage lifecycle policies for cold archival"
is sufficient depth.

### 10.4 Key Metrics to Monitor

| Metric | Alert Threshold | Indicates |
|--------|----------------|-----------|
| Upload success rate | < 98% | Upload service issue |
| Transcoding queue depth | > 500 jobs | Workers falling behind |
| Transcoding failure rate | > 2% | Worker or FFmpeg issue |
| CDN cache hit rate | < 90% | Cache warming issue |
| TTFF (time to first frame) | P99 > 5s | CDN or manifest serving issue |
| Rebuffering ratio | > 2% | Bitrate ladder or CDN issue |
| Segment error rate | > 0.1% | Storage or CDN issue |

---

## Part 11: The 45-Minute Interview Framework

### 11.1 Suggested Time Split

```
TIMING FOR "DESIGN A VIDEO STREAMING PLATFORM"
================================================

  0-5 min:   Clarify requirements
             (VOD vs live? Scale? Geographic scope? DRM?)
             State scope: "Single-region VOD, upload + transcode + CDN + ABR"
  
  5-10 min:  Scale estimation
             "500K uploads/day, 1M concurrent viewers..."
             "1M viewers × 2.5 MB/segment / 6s = 416 GB/s egress → CDN is required"
  
  10-20 min: High-level design
             Draw the two systems (upload path + delivery path)
             Label every component with its technology
             Show data flow with arrows
  
  20-30 min: Deep dive #1 — Upload pipeline
             Chunked upload, S3 multipart, job queue, transcoding workers
             Encoding ladder, HLS segments + manifest
  
  30-40 min: Deep dive #2 — CDN delivery + ABR
             How segments are cached, cache key design
             ABR algorithm: bandwidth estimation → quality selection → segment fetch
             Seeking mechanics
  
  40-45 min: Failure handling + what you'd add with more time
             Spot instances for transcoders, lifecycle management, monitoring
             "If I had more time: origin shield, per-title encoding, live streaming"
```

### 11.2 L5 vs. L6 Answer Comparison

**Question**: "How does the player decide which video quality to download?"

**L3 answer**: "The player checks the user's connection speed and downloads the appropriate
quality."

**L4 answer**: "The player uses the HLS protocol. It fetches the master manifest which lists
all quality variants. It measures download speed and picks the highest quality that fits
within the available bandwidth."

**L5 answer** (target for this chapter): "The player uses adaptive bitrate (ABR) with HLS.
After fetching the master manifest, it downloads the first segment at a conservative quality
(480p) and measures actual throughput. Based on that, it selects quality for the next segment:
if measured bandwidth is 3 Mbps, it picks 720p (2.5 Mbps) with a 20% safety margin. It
continuously re-evaluates: every segment download gives a new bandwidth sample. The player
also tracks buffer occupancy — if buffer drops below a panic threshold (5 seconds), it
immediately drops to the lowest quality regardless of bandwidth estimate, prioritizing
uninterrupted playback over quality. On bandwidth recovery, it gradually ramps up quality
to avoid flapping."

**L6 additions** (covered in Ch100): "Buffer-based ABR (BOLA algorithm) outperforms
bandwidth-based ABR on variable networks because bandwidth estimates are noisy. Also:
per-title encoding generates a custom bitrate ladder per video (action content needs
higher bitrate than talking heads), client-side quality prediction using ML on historical
network patterns, and multi-CDN routing that switches CDN providers per segment based on
real-time performance."

### 11.3 Common Mistakes at L5

**Mistake 1: Treating upload and streaming as one system**
Most candidates draw one box labeled "video server" that handles both upload and serving.
These are architecturally completely different: upload is write-heavy, rate-limited,
async; streaming is read-heavy, latency-critical, synchronous. Separate them from the start.

**Mistake 2: Not mentioning transcoding**
Some candidates skip transcoding entirely ("just store the uploaded file and serve it").
This fails in two ways: format incompatibility across devices, and inability to do adaptive
bitrate. Transcoding is not optional for a real video platform.

**Mistake 3: Serving video directly from S3**
S3 is origin storage, not a CDN. Serving directly from S3 means: no edge caching, full
cross-continent latency, extremely high egress cost at scale. Always add a CDN layer.

**Mistake 4: Not knowing what a manifest file is**
If you say "use HLS" but cannot explain what an `.m3u8` manifest file contains or how the
player uses it, the depth signal falls flat. Know: master manifest lists quality variants,
media playlist lists segment URLs + durations, segments are the actual video bytes.

**Mistake 5: Forgetting chunked/resumable upload**
Saying "user uploads the file" without mentioning that a 1 GB file cannot be sent in a
single HTTP request (unreliable, no resumability) is a gap the interviewer will probe.
Mention chunked upload with resumability early.

### 11.4 Numbers to Memorize

| Fact | Number |
|------|--------|
| Typical HLS segment duration | 6 seconds |
| Segment size at 720p | ~2-3 MB |
| Encoding ladder range | 360p (400 Kbps) – 1080p (5 Mbps) |
| Target CDN cache hit rate | 90-95% |
| Target TTFF (time to first frame) | < 2 seconds |
| Target rebuffering ratio | < 1% |
| Storage multiplier (all qualities vs raw) | ~3× |
| Transcoding time (1hr video, 1 worker) | 30-120 min |

---

## Part 12: Thumbnail Generation Pipeline

### 12.1 Why Thumbnails Matter

Thumbnails are one of the most underrated components of a video platform design.
They represent video content in every feed, search result, recommendation list, and
notification. A broken or missing thumbnail is immediately visible to users.

In a YouTube-scale system:
- Every video needs at least one thumbnail
- Popular creators upload custom thumbnails (click-through rate optimization)
- Auto-generated thumbnails are needed as fallback

### 12.2 Auto-Generated Thumbnails

The transcoding worker can generate thumbnails as a side task during transcoding:

```
THUMBNAIL GENERATION (during transcoding)
==========================================

  Raw video in S3
       │
       ▼
  FFmpeg: extract frames at 10%, 30%, 50%, 70%, 90% of video duration
  (5 candidate frames)
       │
       ▼
  For each frame:
    - Resize to 1280×720 (16:9 aspect ratio)
    - Compress as JPEG at quality 85
    - Store: s3://my-videos/vid_abc123/thumbnails/thumb_01.jpg
             s3://my-videos/vid_abc123/thumbnails/thumb_02.jpg
             ...

  Auto-select default thumbnail:
    - Simple heuristic: pick the most visually "active" frame
    - Measure: frame with the highest edge density (not a black frame or freeze)
    - Store as: thumbnails/default.jpg
       │
       ▼
  CDN-served URL: https://cdn.example.com/vid_abc123/thumbnails/default.jpg
```

**Frame selection heuristic at L5**: Pick the frame at 30% of video duration.
Avoids opening credits (which are often at 0-10%) and trailing content (90-100%).
For L6+: train a model to pick "interesting" frames based on face detection,
text presence, and motion blur score.

### 12.3 Custom Thumbnails (Creator-Uploaded)

```
CUSTOM THUMBNAIL UPLOAD
=========================

  POST /api/v1/videos/{video_id}/thumbnail
  Request: multipart/form-data with image file (JPEG/PNG)
  
  Server:
  1. Validate: image only (not video), max 2 MB, dimensions > 720p
  2. Resize/crop to 1280×720 if needed (maintain aspect ratio)
  3. Store: s3://my-videos/vid_abc123/thumbnails/custom.jpg
  4. Update video record: thumbnail_url → CDN URL for custom thumbnail
  5. Invalidate CDN cache for old thumbnail URL
  
  Response: { thumbnail_url: "https://cdn.example.com/.../custom.jpg" }
```

**Cache invalidation for thumbnails**: When a creator updates their thumbnail,
the old URL is still cached at CDN edges. Two approaches:
- **Versioned URLs**: Include a version or hash in the URL (`?v=abc123`). When creator
  uploads new thumbnail, the URL changes, bypassing the CDN cache automatically.
  No cache invalidation needed. Preferred approach.
- **CDN invalidation API**: Call the CDN's invalidation API to purge the old URL
  from all edge caches. This takes 1-5 minutes to propagate. Slower and has cost.

### 12.4 Intern → Staff Progression: Thumbnails

**Intern**: "We show a screenshot from the video as the thumbnail."

**L4**: "We extract multiple frames during transcoding and pick one as the default.
Creators can upload custom thumbnails. CDN serves thumbnails."

**L5**: "Thumbnail selection matters for creator monetization — a better thumbnail
increases click-through rate. We auto-generate 5 candidates at different timestamps
and select the one with the highest "interest score" (edge density, face detection,
avoiding motion blur). Custom thumbnails overwrite the auto-generated one; we version
the URL to avoid cache invalidation delays. Thumbnails are separate from video segments
in CDN config — they use 24-hour TTL since they change infrequently."

---

## Part 13: Video Search and Discovery

### 13.1 Scope at L5

At L5, video search is "basic keyword match on title." Full semantic search
(content understanding, semantic matching, personalized ranking) is a Staff-level topic.

For L5, implement:
- Full-text search on video title and description
- Filter by creator, date, duration range
- Sort by: relevance, upload date, view count
- Basic pagination

### 13.2 PostgreSQL Full-Text Search (Simple Approach)

For L5 scale (< 10M videos), PostgreSQL's built-in full-text search is sufficient:

```sql
-- Search query
SELECT
  v.video_id,
  v.title,
  v.description,
  v.view_count,
  v.thumbnail_url,
  v.duration_seconds,
  ts_rank(
    to_tsvector('english', v.title || ' ' || COALESCE(v.description, '')),
    plainto_tsquery('english', $1)
  ) AS relevance_score
FROM videos v
WHERE
  v.status = 'ready'
  AND to_tsvector('english', v.title || ' ' || COALESCE(v.description, ''))
      @@ plainto_tsquery('english', $1)
ORDER BY relevance_score DESC, v.view_count DESC
LIMIT 20 OFFSET $2;
```

The GIN index on `to_tsvector(title)` (defined in the schema) makes this fast
for typical query patterns.

**When does PostgreSQL full-text break down?**
- > 10-20M videos: full index scan becomes slow even with GIN index
- Synonym matching: "car" doesn't match "automobile" by default
- Typo tolerance: "Youtueb" doesn't match "YouTube"
- Personalization: no way to incorporate user watch history into ranking

**Scaling path**: Introduce Elasticsearch or Solr at > 10M videos.
The video service publishes a `video.published` event; an indexer consumer
writes to Elasticsearch. Queries go to Elasticsearch, not PostgreSQL.
For L5, mentioning this migration path demonstrates forward-thinking.

### 13.3 Search API Design

```
GET /api/v1/search?q=cooking+recipes&page=1&sort=relevance
  
  Query params:
  - q: search query (required)
  - page: pagination (default 1, max 100)
  - sort: relevance | date | views (default: relevance)
  - duration: short (<4min) | medium (4-20min) | long (>20min)
  - upload_date: hour | today | week | month | year
  - creator_id: filter to specific creator (optional)
  
  Response: {
    results: [{ video_id, title, thumbnail_url, duration_seconds,
                view_count, channel_name, uploaded_at }],
    total_results: 42300,  ← approximate for large result sets
    next_page_token: "eyJ..."
  }
  Errors: 400 (invalid sort value), 422 (query too long > 500 chars)
```

### 13.4 Brainstorming Q&A — Part 13

**Q: How do you handle autocomplete/typeahead for the search box?**

That is Ch75 (Typeahead L5) — a separate system design interview question.
In brief: a Redis-backed prefix trie or Elasticsearch prefix query returns
top N completions for the current query prefix. For the L5 video streaming
question, you can acknowledge this: "Typeahead for the search box is a
separate system I'd keep decoupled — it queries a dedicated suggestion service."
Knowing the boundary between systems is itself an L5 signal.

**Q: How do you handle trending/recommended videos on the homepage?**

At L5: a simple trending feed based on view counts in the last 24 hours.
`SELECT video_id, title FROM videos WHERE published_at > NOW() - INTERVAL '24 hours'
ORDER BY view_count DESC LIMIT 20`. This is cached in Redis (refresh every 5 minutes).
For L6+: personalized recommendations using a collaborative filtering model —
entirely different system (offline training, feature store, serving infrastructure).
At L5, state the simplification: "I'd implement trending as view-count-ranked recent
videos. Personalized recommendations are a much larger system — would you like me to
scope that out or focus on the core streaming design?"

---

## Part 14: Security and Abuse Prevention

### 14.1 The Upload Attack Surface

The upload endpoint is one of the most abused endpoints on any video platform:

- **Storage abuse**: Users upload terabytes of content trying to exhaust your storage
- **CPU abuse**: Large videos cause expensive transcoding jobs
- **Content abuse**: Uploading prohibited content (CSAM, copyright violations, spam)
- **Rate abuse**: Automated bots uploading thousands of videos

For L5, mention at least file size limits, rate limiting, and authentication.
For L6+: content fingerprinting (PhotoDNA for CSAM, ContentID for copyright).

### 14.2 Upload Rate Limiting

```
RATE LIMITING LAYERS
======================

  Layer 1: Authentication
    - Unauthenticated users cannot upload (return 401)
    - OAuth2 / JWT authentication required

  Layer 2: Per-user upload limits
    - Redis key: "upload_rate:{user_id}:{hour}"
    - Limit: 10 uploads per hour, 50 per day (new accounts)
    - Verified creators: higher limits (100/day)
    - If exceeded: return 429 Too Many Requests with Retry-After header

  Layer 3: File size validation
    - Reject at the start of upload (in POST /uploads):
      if file_size_bytes > 10 * 1024 * 1024 * 1024:  # 10 GB
          return 413 Request Entity Too Large
    - Do NOT accept the bytes first and then validate — that wastes bandwidth

  Layer 4: File type validation
    - Allowed MIME types: video/mp4, video/quicktime, video/x-matroska, video/webm
    - Check magic bytes (first 12 bytes), not just the Content-Type header
    - Content-Type header can be spoofed; magic bytes cannot
    - Reject non-video files before storage
```

### 14.3 Signed Upload URLs (Security Pattern)

Instead of routing upload bytes through your API servers, generate a presigned S3 URL:

```
PRESIGNED URL FLOW (more secure)
==================================

  Client                    API Server                   S3
    │                           │                          │
    ├── POST /uploads ──────────►                          │
    │   (file_name, size)        │                          │
    │                           ├── Generate presigned URL ►│
    │                           │   (valid for 4 hours)    │
    │◄── { upload_url, ... } ───┤                          │
    │                           │                          │
    ├── PUT {upload_url} chunks ─────────────────────────► │
    │   (bytes go directly to S3, bypassing API server)   │
    │                           │                          │
    ├── POST /uploads/{id}/complete ────────────────────── ►│
    │                           │   Verify S3 object exists │
    │                           │   Validate checksums      │
    │                           │   Publish to queue        │
```

Benefits of presigned URLs:
- API servers don't handle gigabytes of upload bytes
- Reduces API server bandwidth and CPU costs
- S3 handles the actual byte transfer (highly optimized)
- Presigned URL expires (4 hours) — limits window for abuse

### 14.4 Content Moderation (L5 Scope)

At L5, a minimal content moderation approach:

1. **File type check**: Magic bytes validation rejects non-video files
2. **Duration limit**: Reject videos longer than 12 hours (prevents abuse)
3. **Manual review queue**: Flag newly uploaded videos for human review before
   they appear in public feeds. New accounts: all videos go to review queue.
   Established accounts: spot-check 1-5% of uploads.
4. **User reports**: Accept reports from viewers (POST /api/v1/videos/{id}/report).
   High-report-rate videos are automatically hidden and queued for review.

At L6+: Automated content analysis using ML models for explicit content, copyright
fingerprinting, and policy violation detection. These run as separate pipeline stages
after transcoding. Mentioning this as "future work" at L5 is correct.

### 14.5 Brainstorming Q&A — Part 14

**Q: How do you prevent users from hot-linking your video files from other sites?**

Signed CDN URLs: Instead of serving segments from a static CDN URL, generate
a time-limited signed URL per viewing session. The player receives signed URLs in the
manifest file. Unsigned requests to segment URLs return 403. Signed URLs expire after
the expected video duration plus a buffer (e.g., for a 10-minute video, URLs expire
in 15 minutes). This prevents external sites from embedding your video stream by
hotlinking your CDN URLs. This is the CDN-level version of DRM (though real DRM like
Widevine goes further by encrypting the content itself).

**Q: What do you do if a user's video violates copyright after it's already live?**

Three things must happen: (1) Take down the video — set status to 'removed', which
removes it from all feeds and search; (2) Invalidate the CDN cache for all manifest
and segment URLs for that video; (3) Notify the uploader of the reason. CDN invalidation
ensures new requests for the content get a 403/410, but clients who have already downloaded
segments to their player buffer can still watch the already-buffered portion. Proper DRM
(Widevine) prevents this, but DRM is outside L5 scope. At L5: acknowledge that CDN cache
invalidation takes 1-5 minutes to fully propagate, and buffered content on players cannot
be recalled.

---

## Part 15: Pre-Interview Drill

### 15.1 Five Concepts You Must Be Able to Explain in 60 Seconds Each

Practice saying these out loud before your interview. Time yourself.

**1. Why chunked upload?**
"A video can be gigabytes in size. Sending it in one HTTP request means any network
interruption causes the entire upload to restart. Chunked upload splits the file into
5 MB pieces. Each chunk is sent separately and acknowledged. If the connection drops,
only the last partial chunk is lost — the upload resumes from there. S3 multipart upload
is the backend mechanism: S3 holds partial uploads until all parts arrive, then assembles
the final object."

**2. Why transcode?**
"Users upload in any format — H.265 .mov from iPhone, VP9 .webm from Android, even
older formats like AVI. We cannot serve raw uploads because: (1) not every device can
decode every codec, (2) 4K is too large for mobile viewers on LTE, and (3) raw uploads
lack the segmented format needed for adaptive bitrate streaming. We use FFmpeg to convert
every upload to H.264 MP4, at four quality levels: 360p, 480p, 720p, and 1080p. Each
level is segmented into 6-second chunks. The result is a standardized, streamable, multi-
quality version of every video."

**3. Why a CDN?**
"Without a CDN, a 1080p video segment is 3 MB. One million concurrent viewers each
fetching a new segment every 6 seconds is 166,000 segment requests per second, or about
500 GB/second of egress from our origin servers. No server farm can sustain this economically.
A CDN caches segments at hundreds of edge nodes worldwide. The first viewer at a given
edge triggers a single S3 fetch. Every subsequent viewer gets the segment from cache.
With a 95% cache hit rate, the origin only sees 5% of total traffic."

**4. What is an HLS manifest?**
"An HLS manifest is a plain text file listing either quality variants or video segments.
The master manifest (`.m3u8`) lists all available quality variants with their bitrates:
360p at 400 Kbps, 480p at 700 Kbps, 720p at 2.5 Mbps, 1080p at 5 Mbps. The player
fetches the master manifest first. Then, based on available bandwidth, it fetches the
media playlist for one quality level — a list of all segment URLs with their durations.
The player fetches segments one at a time. To switch quality, it fetches a different
media playlist and starts downloading segments from that quality level."

**5. How does ABR work?**
"ABR — adaptive bitrate streaming — lets the player adjust video quality in real time
based on available bandwidth. After each segment download, the player measures actual
throughput. If it just downloaded a 3 MB segment in 1.2 seconds, throughput is 2.5 Mbps.
It picks the highest quality whose bitrate is ≤ 80% of measured throughput: with 2.5 Mbps
available, it picks 720p (2.5 Mbps) rather than 1080p (5 Mbps). When bandwidth drops —
like a phone entering a tunnel — the player switches to 360p or 480p within one 6-second
segment. The video continues without rebuffering, just at lower quality."

### 15.2 The Three Diagrams You Should Be Able to Draw Cold

**Diagram 1: Upload pipeline (3 boxes, 2 arrows)**
```
  [Creator] → [Upload Service] → [S3: raw video]
                    │
                    ▼
              [Job Queue] → [Transcoder Workers] → [S3: segments + manifests]
                                                          │
                                                        [CDN]
```

**Diagram 2: Streaming path (3 boxes, 2 arrows)**
```
  [Viewer] → [API Server] → [Metadata DB / Redis]
                                (returns manifest URL)
               │
               ▼
           [CDN Edge] → cache hit → serve segment to viewer
               │            └── cache miss → fetch from S3
               ▼
           [S3 Origin]
```

**Diagram 3: ABR decision loop**
```
  PLAYER LOOP (every 6 seconds):
  
  1. Download next segment at current quality
  2. Measure throughput: bytes / time_taken
  3. If buffer < 5s: → 360p (panic mode)
     Else: pick highest quality where bitrate ≤ 0.8 × measured_throughput
  4. Fetch segment at chosen quality
  5. Go to 1
```

### 15.3 The Three Questions That Expose Depth

These are the follow-up questions good interviewers ask. Know your answers.

**Q: "If the transcoding worker dies halfway through a job, what happens?"**

Answer: The job has a visibility timeout in the queue (e.g., 30 minutes for SQS).
If the worker doesn't acknowledge completion within that window, the message becomes
visible again and another worker picks it up. The new worker starts the transcoding
from scratch. This is safe because transcoding is deterministic and idempotent — the same
input always produces the same output. The partial segments written to S3 by the failed
worker are overwritten. The video record stays in `status='processing'` throughout.

**Q: "How do you handle a popular video that gets 10 million views in the first hour?"**

Answer: Three mechanisms protect the system. First, the CDN handles almost all traffic —
edge nodes cache segments and serve them without hitting the origin. Second, the metadata
cache (Redis) serves video metadata reads with a 60-second TTL — the database sees at
most one read per metadata key per minute per cache node, regardless of viewer count.
Third, view count updates are batched: Redis INCR accumulates counts, a background job
flushes to the database every minute. The database never receives 10M individual UPDATE
statements.

**Q: "How would you add support for video chapters?"**

Answer: A video chapter is metadata — start timestamp and label. No new systems needed.
Add a `video_chapters` table:
```sql
CREATE TABLE video_chapters (
  video_id     UUID REFERENCES videos(video_id),
  chapter_num  INT NOT NULL,
  start_seconds INT NOT NULL,
  title        VARCHAR(200) NOT NULL,
  PRIMARY KEY (video_id, chapter_num)
);
```
Return chapters in the GET `/videos/{id}` response. The player uses `start_seconds` to
seek directly to a chapter. In the player, chapters appear as clickable markers on the
progress bar. No changes to the transcoding pipeline, CDN, or streaming protocol needed.
This demonstrates understanding of what requires new infrastructure vs. what is purely
additive metadata.

### 15.4 Quick Reference: Key Design Decisions

| Decision | Choice | Alternative | Why this choice |
|----------|--------|-------------|-----------------|
| Upload protocol | Chunked (5 MB chunks) | Single HTTP PUT | Resumability, reliability |
| Chunk size | 5 MB | 1 MB / 50 MB | Balance: overhead vs. recovery cost |
| Transcoding codec | H.264 | HEVC, AV1 | Universal device support |
| Segment duration | 6 seconds | 2s / 30s | Balance: ABR agility vs. overhead |
| Streaming protocol | HLS | DASH, MP4 progressive | Widest device support |
| Metadata storage | PostgreSQL | DynamoDB | Complex queries, ACID needed |
| View count updates | Redis batch | Direct DB UPDATE | Write throughput at scale |
| CDN segment TTL | Long (24h+) | Short (1h) | Segments are immutable |
| CDN manifest TTL | Short (60s) | Long (24h) | Manifests change as qualities are added |
| Worker instances | Spot/preemptible | On-demand | CPU-intensive, not latency-sensitive |

### 15.5 What Distinguishes an L5 Answer from L4

An L4 candidate designs a working system. An L5 candidate designs a working system
AND demonstrates awareness of the tradeoffs at each decision point.

**L4**: "We use a CDN to cache video segments."
**L5**: "We use a CDN to cache video segments. Segments are immutable once created,
so I'd set cache TTL to 24 hours or more. The master manifest is small and changes
as qualities finish transcoding, so it gets a 60-second TTL. The CDN needs to have
the segments before viewers start watching — for popular creator uploads, we pre-warm
by pushing segments to edge nodes during the final transcoding step before publishing."

The L5 pattern is: **claim → justify → handle the edge case → state what would change at scale**.

---

## KEY TAKEAWAYS

```
╔═══════════════════════════════════════════════════════════════════════════╗
║              CHAPTER 72: VIDEO STREAMING (L5) KEY TAKEAWAYS              ║
╠═══════════════════════════════════════════════════════════════════════════╣
║                                                                           ║
║  1. SPLIT INTO TWO SYSTEMS IMMEDIATELY                                    ║
║     Upload pipeline (write) ≠ Streaming delivery (read).                 ║
║     Different scale, different latency requirements, different tech.      ║
║                                                                           ║
║  2. UPLOAD = CHUNKED + RESUMABLE + ASYNC                                 ║
║     5 MB chunks. SHA-256 checksum per chunk. S3 multipart.               ║
║     On complete: publish to queue → workers transcode.                    ║
║     Never block the upload response on transcoding.                       ║
║                                                                           ║
║  3. TRANSCODE INTO MULTIPLE QUALITIES EVERY TIME                         ║
║     360p / 480p / 720p / 1080p — the encoding ladder.                    ║
║     H.264 codec for universal compatibility.                              ║
║     Output: 6-second .ts segments + .m3u8 playlists.                     ║
║     Use worker pool + job queue. Workers are stateless + restartable.    ║
║                                                                           ║
║  4. CDN IS NOT OPTIONAL AT SCALE                                          ║
║     1M viewers × 2.5 MB/segment = 416 GB/s egress.                      ║
║     No origin server can sustain this. CDN caches at edge.               ║
║     Segments use long TTL (immutable). Manifests use short TTL.          ║
║     95% cache hit rate is the goal.                                       ║
║                                                                           ║
║  5. ADAPTIVE BITRATE = QUALITY THAT FITS BANDWIDTH                       ║
║     Master manifest lists all quality variants.                           ║
║     Player measures download speed → picks highest safe quality.         ║
║     If buffer < 5s: drop to lowest quality immediately (panic mode).     ║
║     Goal: zero rebuffering, even on variable network.                    ║
║                                                                           ║
║  6. SEEKING IS EFFICIENT BECAUSE OF SEGMENTATION                         ║
║     Jump to timestamp T → fetch segment T/6.                             ║
║     No need to download video from the start.                            ║
║                                                                           ║
║  7. TRANSCODING WORKERS → SPOT INSTANCES                                 ║
║     CPU-intensive, not latency-sensitive → ideal for preemptible VMs.    ║
║     60-70% cheaper than on-demand.                                        ║
║     Job queue + retry handles interruptions gracefully.                  ║
║                                                                           ║
║  8. VIEW COUNTS ARE BATCHED — NOT REAL TIME                              ║
║     Redis INCR per view → flush to DB every minute.                      ║
║     Displaying stale count by 60s is acceptable.                         ║
║     Avoid: UPDATE videos SET view_count=view_count+1 on every request.   ║
║                                                                           ║
║  ONE-SENTENCE SUMMARY:                                                    ║
║  "Video streaming = chunked-resumable upload to S3 → async transcoding   ║
║   to HLS segments (360p–1080p) via worker pool → CDN caching with 95%    ║
║   hit rate → adaptive bitrate player that adjusts quality per segment    ║
║   based on measured bandwidth and buffer occupancy."                      ║
╚═══════════════════════════════════════════════════════════════════════════╝
```

---

## Exercises

## Part 16: Capacity Estimation Deep Dive

### 16.1 Storage Estimation (Walk-Through for the Interview)

State your assumptions clearly, then calculate:

```
STORAGE ESTIMATION
===================

  ASSUMPTIONS:
  - 100,000 new videos uploaded per day
  - Average video duration: 10 minutes
  - Average bitrate: 500 Kbps (average of all quality levels uploaded)
  - Raw upload size: 10 min × 500 Kbps × 60s = 375 MB → round to 400 MB
  
  TRANSCODED OUTPUT (4 qualities + manifest):
  - 1080p (5 Mbps): 10 min × 5 Mbps × 60s / 8 bits = 375 MB
  - 720p  (2.5 Mbps): ~188 MB
  - 480p  (700 Kbps): ~53 MB
  - 360p  (400 Kbps): ~30 MB
  - Total transcoded: ~646 MB per video
  - Thumbnails + manifests: ~5 MB per video
  - Total per video: ~1,050 MB ≈ 1 GB per video (including raw)

  DAILY STORAGE GROWTH:
  100,000 videos/day × 1 GB/video = 100 TB/day

  ANNUAL STORAGE:
  100 TB/day × 365 days = 36.5 PB/year
  
  COST ESTIMATE (S3 Standard: $0.023/GB/month):
  100 TB/day × 30 days = 3 PB/month of new data
  Average age across all data: storage grows linearly
  After 1 year: ~18 PB average stored (trapezoidal average)
  Monthly cost: 18,000 TB × $0.023 = ~$414,000/month → about $5M/year
  
  KEY INSIGHT FOR INTERVIEW:
  This is why video platforms use storage tiering aggressively.
  90%+ of views go to content < 30 days old.
  Cold storage (S3 Glacier at $0.004/GB) for content > 1 year saves ~80% on old data.
```

### 16.2 CDN Egress Estimation

```
CDN BANDWIDTH ESTIMATION
=========================

  ASSUMPTIONS:
  - 1 million concurrent viewers at peak
  - Average bitrate consumed: 2.5 Mbps (most viewers at 720p)
  - CDN cache hit rate: 95%

  TOTAL EGRESS FROM CDN:
  1M viewers × 2.5 Mbps = 2.5 Tbps peak CDN output

  ORIGIN EGRESS (cache misses → S3):
  5% of 2.5 Tbps = 125 Gbps (what S3 must serve)

  DAILY CDN COST (at $0.05/GB egress):
  2.5 Tbps × 3600 sec × (peak_hours/24)
  Assume 8 peak hours per day, average 40% of peak the rest:
  Daily egress ≈ 2.5 Tbps × 8h × 3600s × 0.125 GB/Gb
              + 1.0 Tbps × 16h × 3600s × 0.125 GB/Gb
  ≈ 9,000 TB + 7,200 TB = 16,200 TB/day
  At $0.05/GB: $810,000/day → this is YouTube scale (10M concurrent viewers would be 8× more)
  
  KEY INSIGHT FOR INTERVIEW:
  At this scale, CDN cost dominates all other infrastructure costs.
  This is why Netflix and YouTube negotiate custom CDN contracts and run
  their own CDN infrastructure (Netflix Open Connect, YouTube Edge).
```

### 16.3 Transcoding Capacity Estimation

```
TRANSCODING WORKER SIZING
==========================

  ASSUMPTIONS:
  - 100,000 videos/day = ~1,200 new videos/hour (uniform)
  - Average video: 10 minutes
  - Transcoding time: 15 minutes per video per quality (x4 qualities in parallel)
  - So: 15 min worker-minutes per video (if 4 workers handle 4 qualities in parallel)

  WORKERS NEEDED TO KEEP PACE:
  Arriving rate: 1,200 videos/hour = 20 videos/minute
  Each video needs 15 minutes of 1 worker's time
  Workers needed = 20 videos/min × 15 min/video = 300 concurrent workers

  COST (EC2 c5.xlarge spot, ~$0.08/hr):
  300 workers × $0.08/hr = $24/hour = $576/day = ~$17,000/month
  
  IMPORTANT NUANCE:
  This assumes uniform upload distribution. Real upload patterns are NOT uniform —
  creators upload in the evening (US time). Peak rate might be 5× average:
  5 × 1,200 = 6,000 uploads/hour at peak.
  Auto-scaling workers handles this: add spot instances when queue depth rises,
  remove when queue drains. The queue absorbs the surge; workers scale to match.
```

---

**Exercise 1: Chunked Upload Math**
A user has a 2 GB video file. Your upload service uses 5 MB chunks.
(a) How many chunks are there?
(b) The user uploads at 10 Mbps average. How long does the upload take (ignore overhead)?
(c) The connection drops at chunk 120. How much data must be re-uploaded if resumable?
    How much if not resumable?

**Exercise 2: Transcoding Queue Depth**
Your platform receives 1,000 video uploads per hour at peak. Each 10-minute video
takes 15 minutes of worker time to transcode all qualities. Each worker can handle
one video at a time.
(a) How many workers do you need to keep the queue from growing?
(b) If you have 50 workers and a burst of 5,000 uploads arrives in 1 hour, how long
    until the queue drains (assuming the burst then stops)?

**Exercise 3: CDN Cache Hit Rate**
You have 10,000 videos. The top 100 videos account for 70% of all views.
Assume each video has 300 segments (at 720p), and each CDN edge serves 1,000 viewers/hour.
(a) For the top 100 videos, what is the cache hit rate at a given edge node?
(b) For the long-tail 9,900 videos, if each video gets 2 views/day at a given edge,
    what is the cache hit rate for those videos?
(c) What is the blended cache hit rate?

**Exercise 4: ABR Quality Selection**
A player measures the following download speeds for the last 5 segments:
[8 Mbps, 7 Mbps, 3 Mbps, 2 Mbps, 1.5 Mbps]

Using a simple moving average and 80% safety margin:
(a) What quality would the player select after segment 3? After segment 5?
(b) The buffer is currently at 8 seconds and the panic threshold is 5 seconds.
    Does the player have time to wait for a high-quality segment or should it
    prioritize a low-quality segment?

**Exercise 5: Schema Design**
A creator uploads a video. Walk through exactly what database records are created
at each step of the process: (1) upload session initiated, (2) all chunks received,
(3) transcoding job started, (4) 720p quality finishes, (5) all qualities finish
and the video goes live. List the table, operation (INSERT/UPDATE), and which
columns change at each step.

---

## Homework

**Homework 1: Watch a Video with Network Throttling**
In Chrome DevTools, throttle your network to "Slow 3G" and watch a YouTube video.
Open the Stats for Nerds panel (right-click player → "Stats for Nerds"). Observe:
- What quality does the player start at?
- How does quality change over the first minute?
- What is the buffer health?
- Does rebuffering occur?

Write a 1-paragraph analysis of what the ABR algorithm appears to be doing.

**Homework 2: Inspect an HLS Manifest**
Find any HLS stream (many live sports streams use HLS). Use curl or your browser's
developer tools to fetch the master manifest URL. Inspect the file:
- How many quality variants are listed?
- What bitrates are specified?
- Fetch one of the media playlists. How many segments are listed?
- What is the segment duration?

**Exercise 6: Rate Limiting Design**
Your platform allows 10 uploads per hour per user. You have 500,000 active creators.
(a) What data structure would you use in Redis to track upload counts?
    Write the pseudocode for: increment count, check limit, expire old window.
(b) Your Redis cluster handles 100,000 operations per second.
    At peak upload time, 100,000 creators all start uploading simultaneously.
    Each upload requires 2 Redis operations (read count + increment).
    Is your Redis cluster under capacity? What would you do if it is not?
(c) A creator claims the system wrongly counted one of their uploads twice
    (network retry sent the same chunk twice). How does your upload design
    prevent a single upload from counting as two against the rate limit?

**Exercise 7: Cache Design for Video Metadata**
A video homepage shows metadata (title, thumbnail, view count) for 50 videos at a time.
The most-viewed 1,000 videos account for 80% of all homepage views.
(a) Design the Redis caching strategy: what is the cache key? What TTL?
(b) If the cache has 95% hit rate for these 1,000 videos, and each video page
    loads metadata for 50 videos, what is the effective hit rate per page load?
(c) View counts update every minute (from the Redis INCR → DB flush batch).
    A video goes viral and gains 100,000 views in a 5-minute window.
    The video's metadata is cached with a 60-second TTL.
    What is the maximum number of stale view count reads a user can see?
    Is this acceptable? Justify your answer.

**Homework 3: Calculate Storage Costs**
Your platform has 1 million videos, average 15 minutes each.
- Average raw file size: 450 MB (15 min, 1080p)
- Transcoded versions add 3× the raw size in processed segments
- 20% of videos are accessed frequently (S3 Standard), 80% are cold (S3 Glacier)

Calculate monthly storage cost assuming:
- S3 Standard: $0.023/GB/month
- S3 Glacier: $0.004/GB/month

Is the cost dominated by hot or cold storage? What does this tell you about
storage tier optimization?

---

## What This Chapter Covers vs. Ch100 (Staff Level)

| Topic | Ch72 (L5 — this chapter) | Ch100 (Staff) |
|-------|--------------------------|----------------|
| Upload pipeline | Chunked upload, S3 multipart, basic resumability | TUS protocol details, deduplication via content hash, DAG-based processing |
| Transcoding | Encoding ladder, worker pool, HLS segments | Per-title encoding, codec comparison (H.264/H.265/AV1), segment-level parallelism |
| CDN delivery | Cache hit rate, segment TTL, origin miss | Origin shield, multi-CDN routing, PoP hierarchy |
| ABR | Bandwidth-based quality selection, panic mode | BOLA algorithm (buffer-based), ML-based predictive ABR |
| Geographic scale | Single-region | Multi-DC geo-routing, CDN selection by viewer location |
| DRM | Not covered | Widevine + FairPlay integration |
| Live streaming | Not covered | RTMP ingest, real-time segmentation, latency targets |

Read Ch100 after completing this chapter to see how each component scales and deepens
at the Staff level.

---

---

## What to Read Next

- **Ch100 — Video Streaming (Staff)**: The same system at 10× the depth. Adds per-title
  encoding, multi-CDN routing, origin shield, BOLA ABR algorithm, DRM with Widevine and
  FairPlay, and multi-DC geo-routing. Read Ch72 first to have the foundation.

- **Ch75 — Typeahead / Autocomplete (L5)**: The search box autocomplete that completes
  the video search experience. Redis prefix trie vs. Elasticsearch prefix queries.

- **Ch73 — News Feed (L5)**: How a feed of videos is generated, ranked, and paginated.
  The fan-out problem and read-time vs. write-time feed generation trade-off.

- **Ch33 — CDN Internals**: Deep-dive into how CDNs work: anycast routing, PoP hierarchy,
  cache invalidation, origin shield. Relevant background for understanding the delivery
  path in this chapter.

- **Ch37 — Batch Processing**: Map-Reduce and stream processing fundamentals. The
  transcoding worker pipeline is a specialized form of batch processing; understanding
  batch architecture patterns helps you extend the design to analytics and reporting.

---

---

*Chapter 72 — Section 5: Senior SWE L5 Case Studies.*
*Pairs with: Ch100 (Video Streaming Staff level), Ch69 (Live Streaming, Twitch),*
*Ch33 (CDN internals), Ch37 (Batch Processing: transcoding pipeline context).*
*Last updated: 2026-06-25.*

---

<!-- END OF CHAPTER 72 -->
<!-- Line count target: 2,000+ lines -->
<!-- Scope: L5 single-region VOD. Skip: DRM, live, multi-DC. Staff version: Ch100. -->
