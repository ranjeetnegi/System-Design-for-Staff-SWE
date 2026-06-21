# Chapter 61i: Live Streaming — Twitch / YouTube Live

> Live streaming is real-time video at scale: a streamer broadcasts to
> 500,000 concurrent viewers who each need the stream within 3 seconds of
> it being recorded. Unlike YouTube (recorded video served from CDN),
> live has no time to pre-process — you're encoding, distributing, and
> playing simultaneously.

---

## STATUS: STUB — Full chapter coming

---

## Why This Chapter Matters

Live streaming is asked at companies building video products (Twitch, YouTube,
TikTok Live, Instagram Live, LinkedIn Live) and increasingly at any company
running virtual events. It is architecturally distinct from Chapter 121
(Video Streaming — VOD/YouTube) because there is no pre-processing window:
every design decision must work in real time. Key concepts: RTMP ingest,
HLS/DASH adaptive streaming, edge CDN push, and the latency vs. reliability trade-off.

---

## Planned Content

### Part 1: Requirements and Scale
- Streamer broadcasts video → viewers watch with < 5s latency
- Functional: stream ingest, viewer playback, chat (separate service), stream recording/replay
- Non-functional: < 5s end-to-end latency, 500K concurrent viewers per top streamer, 99.9% uptime
- Scale: 10M concurrent viewers globally, 100K active streams at peak
- Not in scope: chat system (Ch60), recommendations, payments, clip creation
- Key distinction from VOD: no pre-transcoding, no CDN pre-positioning — everything is live

### Part 2: Ingest — Getting Video from Streamer to Server
- Protocol: RTMP (Real-Time Messaging Protocol) — streamer's OBS/XSplit sends RTMP to ingest server
- RTMP vs. WebRTC: RTMP is simpler, one direction (streamer→server); WebRTC is for ultra-low-latency (< 1s) but complex
- Ingest server: receives raw video stream, authenticates streamer (stream key), validates bitrate
- Geo-routing: streamer connects to nearest ingest PoP (Point of Presence) to minimize upload latency
- Redundancy: primary + backup ingest servers; if primary drops, failover in < 2s
- Stream key: unique secret per streamer → authenticates without username/password mid-stream

### Part 3: Transcoding — Real-Time Encoding
- Raw stream comes in at one bitrate (e.g., 1080p 6Mbps)
- Viewers have different network speeds — need multiple quality levels (1080p, 720p, 480p, 360p)
- Real-time transcoding: must encode faster than real-time (< 1s to transcode 1s of video)
- Hardware encoding: GPU-accelerated (NVENC) — 10–20× faster than CPU encoding
- Segment-based: encode in 2-second HLS segments; viewers download segments sequentially
- Output: for each quality level, produce HLS segments + update the m3u8 playlist file every 2s

### Part 4: Distribution — Delivering to 500K Viewers
- CDN push model (not pull): transcoder pushes segments to CDN edge nodes immediately
  - Pull model (VOD) doesn't work for live — first viewer in each region would have to wait for origin
  - Push model: segments forwarded to 100+ edge PoPs within 1s of creation
- HLS playback: viewer's player fetches m3u8 playlist → fetches 2s segments in sequence
  - Playlist updated every 2s with new segment URLs
  - Player buffers 2–3 segments ahead for smooth playback
- Latency breakdown: encode 2s + push to CDN 1s + player buffer 4–6s = ~7–9s total latency
- Low-latency HLS (LL-HLS): Apple's extension — reduces segment size to 200ms, latency to ~2s

### Part 5: Stream Storage and Replay
- Record all segments as they're produced → store in object storage (S3-like)
- After stream ends: stitch segments → produce VOD file → make available for replay
- Hot segments (last hour of active stream): cached on CDN edge nodes
- Cold segments (older replays): stored in object storage, served on demand

### Part 6: Handling Streamer Disconnection
- Streamer's internet drops mid-stream (very common)
- Ingest server: detect disconnection within 2s (RTMP keepalive timeout)
- Viewer experience: player buffers → shows "stream is offline" or reconnecting spinner
- On reconnect: new RTMP connection, streamer picks up same stream key
- Segment gap: timestamp gap in HLS segments → player skips gap seamlessly
- SLA: < 2s to detect disconnect, < 10s to resume after reconnect

### Part 7: System Architecture
- Ingest service: RTMP receiver → authenticate → forward to transcoding cluster
- Transcoding cluster: GPU workers → produce HLS segments + push to CDN + push to object storage
- CDN: edge network (Akamai, Fastly, or internal) → distributes segments globally
- Playlist service: maintains m3u8 playlist per stream → served from edge (updated every 2s)
- Metadata service: stream title, thumbnail, viewer count, start time
- Notification service: "stream started" push to followers (APNs/FCM)

### Part 8: Interview Framework
- Immediately distinguish from VOD: "this is live — no pre-processing window, CDN push not pull"
- Walk the pipeline: RTMP ingest → transcode → HLS segments → CDN push → viewer playback
- Explain the latency budget explicitly: each stage adds seconds; know where the time goes
- Cover streamer disconnect — interviewers always ask about failure handling
- L5 bar: ingest, transcode pipeline, HLS distribution, disconnect handling
- L6 bar: global ingest network (100+ PoPs), ultra-low-latency WebRTC path, dynamic
  transcoding resource allocation, P2P mesh for extreme viewer counts (1M+)

---

## The One-Sentence Summary

> "Live streaming = RTMP ingest (streamer → nearest PoP) → real-time GPU transcoding (1080p → multiple quality levels, 2s HLS segments) → CDN push (segments forwarded to edge nodes immediately, not on first request) → HLS playback (viewer fetches m3u8 playlist + sequential 2s segments) — the architectural difference from VOD is CDN push vs. pull, because there's no time to cache on first request."

---

*Full chapter: ~2,500 lines. Section 5 — L5 / Senior SWE. Distinct from Ch121 (VOD streaming = YouTube-style).*
