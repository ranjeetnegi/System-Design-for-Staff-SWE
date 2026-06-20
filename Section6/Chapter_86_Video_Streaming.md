# Chapter 89: Video Streaming — YouTube / Netflix / TikTok

> One of the top 5 system design interview questions at every major tech company.
> The candidate who says "upload to S3 and serve from CDN" fails. The candidate
> who traces adaptive bitrate, transcoding pipelines, and CDN cache warming wins.

---

## STATUS: STUB — Full chapter coming

---

## Why This Chapter Matters

Video streaming combines every hard distributed systems problem in one question:
- Storage at extreme scale (YouTube: 500 hours of video uploaded per minute)
- Compute-intensive transcoding (one video → 15+ quality variants)
- Global low-latency delivery (CDN strategy, cache warming, anycast)
- Adaptive bitrate streaming (ABR: client-driven quality selection)
- Metadata at scale (search, recommendations, comments)

This question appears at Google, Meta, Netflix, Amazon, TikTok, and Snap at L5+.

---

## Planned Content

### Part 1: The Problem Space
- Upload path vs. playback path (completely different systems)
- Scale: YouTube serves 1 billion hours of video per day
- User expectations: < 2s start time, < 0.1% buffering ratio, instant seek
- The core tension: video files are huge, users are everywhere, networks are unreliable

### Part 2: Upload and Ingestion Pipeline
- Client-side chunked upload (resumable uploads, TUS protocol)
- Upload service: deduplication, virus scanning, metadata extraction
- Raw storage: GCS/S3 before transcoding
- Triggering the transcoding pipeline (event-driven via Pub/Sub / Kafka)
- ASCII diagram: upload flow end-to-end

### Part 3: Transcoding Pipeline
- Why transcode? Different devices, bandwidths, codecs (H.264, H.265/HEVC, AV1, VP9)
- The encoding ladder: 144p → 240p → 360p → 480p → 720p → 1080p → 4K
- Per-title encoding: Netflix's content-aware encoding (dark scenes need fewer bits)
- Transcoding architecture: worker fleet, job queue, parallel encoding
- Output: .mp4 fragments + manifest file (.m3u8 for HLS, .mpd for DASH)
- Real incident: YouTube 2018 AV1 rollout — 30% bandwidth savings, 6 months compute

### Part 4: Adaptive Bitrate Streaming (ABR)
- The fundamental problem: network bandwidth varies second-to-second
- HLS (Apple) vs. DASH (MPEG): both use manifest files + segment-based streaming
- How the client chooses quality: buffer occupancy + estimated bandwidth
- Segment duration trade-off: short segments (2s) = faster adaptation, more overhead
- Startup optimization: start at lower quality, ramp up (avoids initial buffering)
- ASCII diagram: client ABR decision loop

### Part 5: CDN Strategy
- Why CDN is non-negotiable: a 4K video is 15GB; serving from origin for 1B viewers = impossible
- CDN tier architecture: Origin → Regional PoP → Edge PoP → User
- Cache warming: pre-populate edge caches for viral/scheduled content
- Long-tail problem: 90% of YouTube videos are watched < 10 times (don't cache these)
- Anycast routing: user's DNS resolves to nearest CDN PoP
- Cache miss handling: edge → regional → origin fallback chain
- Real incident: Netflix Open Connect — Netflix built its own CDN to control cache placement

### Part 6: Playback and Seeking
- Video player state machine: idle → buffering → playing → seeking → paused
- Seeking: with ABR, the client just requests a different segment (segment-indexed)
- Thumbnail seeking: sprite sheets pre-generated for thumbnail previews on hover
- Concurrent viewer handling: same segment served to millions simultaneously (CDN hit)
- Session state: playback position, quality history, buffering events (analytics)

### Part 7: Metadata and Discovery
- Video metadata: title, description, tags, category, upload time, view count
- Separate from video storage: stored in Bigtable or relational DB
- Search index: inverted index on title/description/tags (Elasticsearch)
- Recommendation: covered in Ch64; for this chapter, just the integration point
- Comment system: hierarchical, eventually consistent, separate from video pipeline

### Part 8: Live Streaming
- Key difference: no transcoding pipeline pre-run; must transcode in real-time
- RTMP ingest → encoder → HLS/DASH manifest generation in real-time
- Latency modes: ultra-low (< 1s, WebRTC), low (2–5s, CMAF), standard (10–30s, HLS)
- DVR window: last N seconds of live stream available for rewind
- Viewer count challenge: live events have synchronized spikes (SuperBowl → 100M concurrent)

### Part 9: Interview Framework — 45-minute Answer Structure
- Minutes 0–5: clarify (upload or playback focus? live or VOD? scale?)
- Minutes 5–15: upload + transcoding pipeline
- Minutes 15–25: CDN + ABR playback
- Minutes 25–35: deep dive (pick one: transcoding scale, CDN cache strategy, ABR algorithm)
- Minutes 35–45: failure modes, monitoring, trade-offs
- L5 vs. L6 calibration examples

---

## Key Numbers to Memorize

| Metric | Value |
|--------|-------|
| YouTube uploads | 500 hours/minute |
| YouTube daily watch time | 1 billion hours/day |
| Video start latency target | < 2 seconds |
| Buffering ratio target | < 0.1% |
| Typical encoding ladder | 6–15 quality variants |
| H.264 bitrate (1080p) | ~4 Mbps |
| H.265 savings vs H.264 | ~40% |
| AV1 savings vs H.264 | ~30% |
| CDN cache hit ratio target | > 95% |
| HLS segment duration | 2–10 seconds |

---

## The One-Sentence Summary

> "Video streaming = upload pipeline (chunked upload → transcoding into 10+ quality variants) + CDN delivery (cache at edge, anycast routing) + adaptive bitrate (client picks quality based on bandwidth) — the interview is won by knowing how these three pieces interact, not each piece in isolation."

---

*Full chapter: ~2,500 lines. Pairs with Ch71 (Media Upload Pipeline) and Ch56 (Distributed Cache).*
