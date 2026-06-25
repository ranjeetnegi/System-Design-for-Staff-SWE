# Chapter 61i: Live Streaming — Twitch / YouTube Live

> Live streaming is real-time video at scale: a streamer broadcasts to
> 500,000 concurrent viewers who each need the stream within 3 seconds of
> it being recorded. Unlike YouTube (recorded video served from CDN),
> live has no time to pre-process — you're encoding, distributing, and
> playing simultaneously.

---

```
+------------------------------------------------------------------+
|  INTERVIEW OVERVIEW — Live Streaming (Twitch/YouTube Live)       |
|  Time: 45 minutes                                                |
|                                                                  |
|  Min 0-2:   Clarify scope (ultra-low latency? chat? recording?) |
|  Min 2-8:   Users and use cases                                 |
|  Min 8-14:  Functional + Non-functional requirements            |
|  Min 14-19: Scale math                                           |
|  Min 19-23: Assumptions                                          |
|  Min 23-42: Architecture + deep dives                           |
|  Min 42-45: Failure modes, extensions                           |
|                                                                  |
|  The clarifying question that changes everything:                |
|  "What is the target end-to-end latency? < 5 seconds (standard |
|   HLS), ~1-2 seconds (LL-HLS), or < 500ms (WebRTC)?" This      |
|   choice determines ingest protocol, segment size, and the      |
|   entire CDN distribution strategy.                             |
+------------------------------------------------------------------+

+------------------------------------------------------------------+
|  L5 vs L6 AT A GLANCE                                           |
|                                                                  |
|  L5 (Senior SWE):                                               |
|  - RTMP ingest -> transcoding -> HLS segments -> CDN push       |
|  - Why CDN push (not pull) for live vs pull for VOD             |
|  - Latency budget: encode + push + player buffer = 7-9s         |
|  - Streamer disconnect: detection + reconnect + segment gap     |
|  - Multiple quality levels (adaptive bitrate streaming)         |
|                                                                  |
|  L6 (Staff):                                                     |
|  - LL-HLS: partial segments (200ms chunks), HTTP/2 push,        |
|    reducing latency to 2s                                       |
|  - WebRTC for ultra-low latency (<500ms): SFU vs MCU topology   |
|  - GPU transcoding resource allocation (cost optimization)      |
|  - P2P mesh overlay for 1M+ concurrent viewers (CDN relief)    |
|  - Multi-region ingest with stream relay backbone               |
+------------------------------------------------------------------+
```

---

## Why This Chapter Matters

Live streaming is asked at Twitch, YouTube, TikTok, Meta, LinkedIn, and any company running video events or creator tools. The question is a direct test of whether you understand real-time media pipelines — a domain with its own vocabulary (RTMP, HLS, DASH, LL-HLS, WebRTC, SFU) and its own set of constraints that do not exist in typical web services.

The one concept that immediately separates informed answers from guesses: **CDN push vs. pull**. VOD (recorded video) uses CDN pull: when the first viewer in a region requests a video, the CDN fetches it from origin and caches it locally. Live streaming cannot use pull — the first viewer would trigger a fetch that does not exist yet. Live segments must be pushed to CDN edge nodes the moment they are created. This single insight shows you understand the architectural constraint and shapes every design decision.

This chapter is explicitly about the streaming pipeline, not the chat system (Ch60), not the recommendation system, and not the payments layer. When the interviewer says "design Twitch," your first clarification should be "do you want the streaming infrastructure or the chat and recommendations too?"

---

## Phase 1: Users and Use Cases (Minutes 2-8)

### Clarify first

1. "What is the latency requirement? Standard 5-10 seconds (HLS), low latency 2-3 seconds (LL-HLS), or ultra-low under 500ms (WebRTC)?" Each choice has fundamentally different architecture.
2. "Do we need the chat system, or just the video pipeline?" Chat is a separate real-time messaging problem (Ch60).
3. "Do we need stream recording and replay (VOD after stream ends)?"
4. "How many concurrent viewers do we expect for the biggest streams — 100K, 500K, or 1M+?"

For this chapter: target latency 5 seconds (standard HLS), video pipeline only (no chat), recording + replay required, up to 500K concurrent viewers per stream.

### Who uses a live streaming platform?

**Streamers:**
- Gaming streamers broadcasting a play session from OBS to their followers
- News organizations broadcasting a live press conference
- Sports leagues broadcasting a match
- Educators running a live class or webinar
- Individual creators doing Q&A or tutorials

**Viewers:**
- Fans watching their favorite streamer play a game
- News viewers watching a breaking event live
- Sports fans watching a match

**Internal systems:**
- Recommendation system: which live streams to surface to users (not in scope here)
- Analytics: concurrent viewers, watch time, engagement rate
- Content moderation: live stream content detection (not in scope)
- Monetization: ads insertion, subscriptions (not in scope)

### Core use cases

**P0 — Must have:**
- UC1: Streamer starts broadcasting → stream available to viewers within 10 seconds
- UC2: Viewer opens stream → video starts playing with < 5s latency from live
- UC3: Adaptive bitrate: viewer's player automatically adjusts quality based on network
- UC4: Streamer disconnects → viewer sees "stream offline" within 5 seconds

**P1 — Important:**
- UC5: Stream recorded and available as replay video within 5 minutes of stream ending
- UC6: Follower notification: "streamer you follow just went live" push notification
- UC7: Stream thumbnail updated every 30 seconds (live preview)

**Out of scope:**
- Chat system (Ch60 covers WebSocket messaging)
- Stream recommendations
- Clip creation and highlight extraction
- Stream key rotation and account security

---

## Phase 2: Functional Requirements (Minutes 8-14)

### Streamer-side operations

- **F1:** `start_stream(stream_key, title, category)` — authenticate streamer, begin ingest
- **F2:** `ingest_video_chunk(stream_id, chunk_bytes, timestamp)` — continuous video data over RTMP connection
- **F3:** `end_stream(stream_id)` — gracefully close the stream

### Viewer-side operations

- **F4:** `get_stream_url(streamer_id) -> m3u8_url, thumbnail_url, viewer_count` — get HLS playlist URL
- **F5:** `fetch_playlist(m3u8_url) -> segment_urls[]` — player fetches the segment list (this is done by the video player, not our API — but our server serves it)
- **F6:** `fetch_segment(segment_url) -> video_bytes` — player downloads a video segment (served by CDN)

### Management operations

- **F7:** `get_live_streams(category, page) -> [stream metadata...]` — browse live streams
- **F8:** `get_viewer_count(stream_id) -> count` — current concurrent viewer count

### The protocol difference from web APIs

```
Unlike a typical JSON REST API, live streaming uses specialized protocols:

Ingest (streamer -> server):
  RTMP (Real-Time Messaging Protocol):
    - TCP-based, persistent connection
    - Streamer app (OBS, Streamlabs, native mobile) speaks RTMP natively
    - Sends audio/video as a continuous byte stream
    - Our ingest server listens on port 1935 (standard RTMP port)
  
  Alternative ingest protocols:
    SRT (Secure Reliable Transport): newer, UDP-based, better for lossy networks
    WebRTC: browser-based streaming, ultra-low latency but complex server-side
  
  For this chapter: RTMP as the primary ingest protocol.

Delivery (server -> viewers):
  HLS (HTTP Live Streaming):
    - Developed by Apple, now the dominant live streaming protocol
    - Video split into short segments (2-6 seconds each)
    - Playlist file (m3u8) lists the segments in order
    - Player downloads segments sequentially via regular HTTP GET
    - Works over HTTP/HTTPS, cacheable, firewall-friendly
  
  DASH (MPEG-DASH): similar to HLS, Google/MPEG standard. Less dominant.
  WebRTC: for ultra-low-latency (<500ms). Different delivery path entirely.
  
  For this chapter: HLS delivery.
```

---

## Phase 3: Scale and Capacity (Minutes 14-19)

### Traffic numbers

```
Concurrent viewers globally:      10,000,000
Top streamer peak viewers:           500,000
Active streams at peak:              100,000

Ingest bandwidth (streamer -> server):
  Average stream bitrate: 6 Mbps (1080p60)
  100K active streams * 6 Mbps = 600 Gbps ingest bandwidth

Transcoding output:
  Per stream: 4 quality levels (1080p 6Mbps, 720p 3Mbps, 480p 1.5Mbps, 360p 0.8Mbps)
  Total bitrate per stream: 11.3 Mbps
  100K streams * 11.3 Mbps = 1.13 Tbps transcoded output

Distribution (CDN deliver to viewers):
  10M viewers * average 3 Mbps watched quality = 30 Tbps total CDN delivery
  This is the dominant cost: 30 Tbps of CDN bandwidth at $0.01/GB:
    30 Tbps * 3600s/hour * $0.000000001/bit = $1,080/sec = $3.9M/hour at peak
  In practice: CDN pricing is negotiated in bulk, ~$0.004-0.008/GB for large customers.

Storage (recording):
  100K streams * avg 3 hours/stream * 11.3 Mbps = 100K * 10800s * 1.4 MB/s = 1.5 PB/day
  At $0.02/GB: $30M/day. Storage cost dominates for replay retention.
  Practical: delete replays after 60 days unless streamer opts to keep them.

Transcoding compute:
  Per stream: GPU-accelerated encoding. 1 GPU encodes 2-4 streams at 1080p.
  100K streams / 3 streams per GPU = 33,333 GPUs
  At $2/hour per GPU: 33,333 * $2 = $66,666/hour = $1.6M/day in GPU compute.
  This is why transcoding efficiency and stream start/stop management matter.
```

### Segment math for HLS

```
HLS segment size: 2 seconds of video
Segment file size: 2s * 6 Mbps / 8 bits-per-byte = 1.5 MB per segment (1080p)
Segments per minute: 30
Segments per hour: 1,800
Per stream per day (3 hours avg): 5,400 segments * 1.5 MB = 8.1 GB per stream (1080p only)
With 4 quality levels: 8.1 GB * (6+3+1.5+0.8)/6 = 8.1 * 1.88 = 15.3 GB per stream per day

CDN caching:
  Viewers within the same region download the same segments.
  For a stream with 50K viewers in the US-East region:
  All 50K viewers download the same 2s segment, ~1.5 MB each.
  Without CDN: 50K * 1.5 MB = 75 GB per segment from origin. Per minute: 2.25 TB.
  With CDN edge cache: origin sends 1 copy to CDN edge. CDN serves 50K viewers from cache.
  CDN cache hit rate for hot live streams: effectively 100% (all viewers in a region get the same segment).
```

---

## Phase 4: Non-Functional Requirements (Minutes 14-19)

### Latency

- **End-to-end streaming latency:** < 10 seconds (standard HLS). Target: < 5 seconds.
- **Stream start time:** < 10 seconds from streamer starting broadcast to first viewer being able to play.
- **Streamer disconnect detection:** < 5 seconds (RTMP keepalive timeout).

### Throughput

- Ingest: 600 Gbps of video ingest across 100K active streams.
- Distribution: 30 Tbps of CDN delivery to 10M viewers.

### Availability

- 99.9% for viewer playback. Viewers tolerate occasional buffering but not 5-minute outages.
- 99.5% for streamer ingest. Streamers expect their stream to stay up. Disconnections happen via network issues — platform-side failures should be rare.
- During ingest outage: viewers see buffering. Stream resumes automatically when ingest recovers.

### Consistency

- Viewer count: eventual consistency acceptable. Count displayed with 60-second lag is fine.
- Stream availability: when a streamer starts broadcasting, the stream should be available to viewers within 10 seconds (not 60 seconds). This drives the CDN push architecture.

---

## Phase 5: Assumptions and Constraints

- A1: Streamers use RTMP (OBS, Streamlabs, native apps). WebRTC ingest (browser-based) is an extension.
- A2: HLS delivery with 2-second segments and 5-6 second latency is the target. LL-HLS (2s latency) is an extension.
- A3: 4 quality levels: 1080p (6 Mbps), 720p (3 Mbps), 480p (1.5 Mbps), 360p (0.8 Mbps).
- A4: Transcoding is GPU-accelerated (NVIDIA NVENC or equivalent). Real-time constraint: encode 1 second of video in < 1 second wall clock time.
- A5: CDN is a third-party network (Akamai, Fastly, Cloudflare) or an in-house edge network.
- A6: Recording: all segments stored in object storage (S3). VOD available within 5 minutes of stream end.

---

## Architecture Design — HLD

### Opening analogy

Think of a live sports radio broadcast. The commentator speaks into a microphone (RTMP ingest). The radio station encodes the audio signal into FM waves (transcoding). A network of radio towers across the city immediately re-broadcasts the signal (CDN push to edge nodes). Every radio in the city (viewer player) tunes in and receives the signal directly from the nearest tower. The commentator doesn't know how many radios are listening — the tower handles the fan-out.

The critical point: the radio tower does not wait for someone to request the signal before broadcasting. It starts broadcasting immediately when it receives the signal from the station. That is the CDN push model.

### Full HLD diagram

```
[Streamer / OBS]
  RTMP (TCP, port 1935)
       |
       v
+------------------+
|  INGEST SERVER   |
|  (PoP nearest    |
|   to streamer)   |
|  - authenticate  |
|  - stream key    |
|  - validate      |
|  - forward       |
+------------------+
       |
       | (relay backbone: internal network, low latency)
       v
+------------------+
| TRANSCODING      |
| CLUSTER          |
| (GPU workers)    |
|                  |
| 1080p -> segments|
| 720p  -> segments|
| 480p  -> segments|
| 360p  -> segments|
|                  |
| + m3u8 playlists |
+------------------+
       |          \
       |           \
       v            v
+----------+   +---------+
|  CDN     |   | OBJECT  |
|  EDGE    |   | STORAGE |
|  NODES   |   | (S3)    |
| (global) |   | record. |
+----------+   +---------+
       |
       | HTTP GET (segments + m3u8)
       v
[Viewer App / Browser / Smart TV]
  HLS Player
  - fetches m3u8 every 2s
  - downloads latest segments
  - adaptive bitrate selection

[Other services]
+------------------+   +------------------+
| METADATA SVC     |   | NOTIFICATION SVC |
| title, category  |   | "stream started" |
| viewer count     |   | push to followers|
| thumbnail        |   +------------------+
+------------------+
```

### Component responsibilities

```
+------------------+----------------------------------+-----------+------------------+
| Component        | Responsibility                   | Stateful? | Scale target     |
+------------------+----------------------------------+-----------+------------------+
| Ingest Server    | Receives RTMP, authenticates,    | YES       | 100K connections |
|                  | relays to transcoder cluster     | (per-conn)| 100 PoPs global  |
+------------------+----------------------------------+-----------+------------------+
| Transcoding      | GPU encoding: raw -> HLS segs,  | YES       | 33K GPUs,        |
| Cluster          | pushes to CDN + S3 every 2s     | (per-job) | 100K jobs/peak   |
+------------------+----------------------------------+-----------+------------------+
| CDN Edge         | Caches + serves HLS segments    | YES       | 30 Tbps delivery |
|                  | to viewers globally             | (cached)  | 100+ PoPs        |
+------------------+----------------------------------+-----------+------------------+
| Object Storage   | Durable segment recording,      | YES       | 1.5 PB/day write |
| (S3-like)        | also serves cold replay         |           |                  |
+------------------+----------------------------------+-----------+------------------+
| Playlist Service | Maintains m3u8 playlist per     | NO        | 100K streams,    |
|                  | stream; served from edge CDN    |           | updated every 2s |
+------------------+----------------------------------+-----------+------------------+
| Metadata Service | Stream title, viewer count,     | NO        | 100K streams     |
|                  | thumbnail URL, live status      |           |                  |
+------------------+----------------------------------+-----------+------------------+
| Notification Svc | "Stream started" push to        | NO        | APNs/FCM         |
|                  | followers via APNs/FCM          |           |                  |
+------------------+----------------------------------+-----------+------------------+
```

---

## Component 1: Ingest — Getting Video from Streamer to Server

### RTMP connection setup

```
RTMP (Real-Time Messaging Protocol):
  Transport: TCP (reliable, ordered). Port 1935.
  Direction: one-way (streamer pushes to server). Server does not send video back.
  Established by: OBS/Streamlabs/native mobile app on the streamer's device.

Connection flow:
  1. Streamer configures OBS:
     Server URL: rtmp://ingest-nyc.example.com/live
     Stream Key:  sk_user123_abc123def456  (unique, secret, per-streamer)
  
  2. TCP connection established to nearest ingest PoP (geo-DNS routes to nearest).
  
  3. RTMP handshake (3 round trips):
     Client -> Server: C0 (version byte) + C1 (timestamp + random bytes)
     Server -> Client: S0 + S1 + S2 (echoes client's C1)
     Client -> Server: C2 (echoes server's S1)
     Handshake complete. ~15ms latency.
  
  4. Stream authentication:
     Client sends: connect command with app name and stream key.
     Server: validate stream key against database. User must have a streamer account.
     If invalid: RTMP disconnect with error "invalid stream key".
     If valid: server responds with stream_begin event. Streaming starts.
  
  5. Video data flows:
     Client sends RTMP messages continuously:
       - Video message: H.264 (AVC) encoded video frame
       - Audio message: AAC encoded audio
       - Metadata message: resolution, framerate, bitrate info
     Server receives these as a byte stream and forwards to the transcoder.
```

### Geo-routing to nearest ingest PoP

```
Why it matters:
  Streamer in London sends video to an ingest server in the US:
  Round-trip latency London -> US-East: ~80ms
  For RTMP (TCP): each packet acknowledgment takes 80ms RTT.
  Video is continuous — TCP backpressure from high latency causes stream quality issues.
  
  Correct: streamer should connect to the nearest ingest PoP.
  London streamer -> London ingest PoP (latency: 5ms)
  London PoP relays video to transcoder cluster via backbone (fast internal network).

Routing mechanism:
  DNS-based geo-routing: ingest.example.com resolves to the nearest PoP's IP.
  Route 53 (AWS) or similar: geolocation routing policy.
  London -> returns IP of London PoP
  New York -> returns IP of US-East PoP
  Tokyo -> returns IP of Japan PoP

Ingest PoP network:
  100+ PoPs globally, co-located with major internet exchanges.
  Each PoP: 10-20 ingest server instances.
  Each ingest server: handles 1,000-2,000 concurrent RTMP connections.
  Total capacity: 100 PoPs * 15 servers * 1,500 connections = 2.25M concurrent streamers.
```

### Stream relay from ingest PoP to transcoder

```
Transcoding is computationally expensive (GPU workers). Not co-located with ingest.
Transcoding cluster: large data centers with GPU density.
  
Relay path:
  Ingest PoP (London) -> Transcoding cluster (US-East or EU-West)
  via private backbone network (not public internet).
  
  Relay protocol: RTMP or SRT over internal network.
  Latency: 20-50ms (private backbone, London to EU-West transcoder).
  
  Load balancing at relay:
  Ingest server -> Relay manager: "I have stream sk_user123, where should it go?"
  Relay manager assigns a transcoding worker (least-loaded GPU machine).
  Same stream always goes to the same worker (for state consistency — current segment number, keyframes).
  If worker fails: reassign to another worker. Brief gap in stream (1-3 seconds).
```

---

## Component 2: Transcoding — Real-Time Encoding

**The hardest technical constraint: encode 1 second of video in less than 1 second.**

### Why multiple quality levels?

```
Streamer sends: 1080p at 6 Mbps (raw from OBS after its initial encoding)

Viewers:
  Home on gigabit fiber: can handle 6 Mbps -> serve 1080p
  On LTE in a car: maybe 3 Mbps -> serve 720p
  On crowded WiFi: maybe 1 Mbps -> serve 480p
  On 3G: 0.5 Mbps -> serve 360p

Solution: Adaptive Bitrate (ABR) streaming.
  Transcoder produces 4 quality levels from the single ingest stream.
  Viewer's player monitors download speed.
  If downloading segments faster than playback: try higher quality.
  If buffering (segments slower than playback): drop to lower quality.
  ABR ensures continuous playback despite variable network conditions.
```

### Real-time transcoding pipeline

```
Input: H.264 video at 1080p 60fps, 6 Mbps from RTMP ingest.

Step 1: Demux
  RTMP stream contains interleaved video + audio messages.
  Demuxer separates: video stream + audio stream.
  
Step 2: Decode (optional, for GPU path)
  For GPU transcoding (NVENC): decode on GPU is optional if input is already in a compatible format.
  Often: CPU decodes H.264 -> raw YUV frames -> GPU encodes at multiple bitrates.
  Hardware decode (NVDEC): GPU decodes H.264 in hardware.

Step 3: Encode at each quality level (GPU-accelerated, parallel)
  GPU uses NVENC to simultaneously encode 4 quality levels:
    1080p: 6 Mbps, 1920x1080
    720p:  3 Mbps, 1280x720
    480p:  1.5 Mbps, 854x480
    360p:  0.8 Mbps, 640x360
  
  One modern GPU (NVIDIA A100): encodes 4-6 1080p streams or 15-20 720p streams simultaneously.
  For one stream producing 4 quality levels: 1 GPU handles it with headroom.
  
  Encoding latency: must encode 2 seconds of video in < 1 second wall clock.
    Frame rate: 60fps -> 60 frames per 2-second segment = 120 frames.
    GPU encode throughput: 1000+ fps for H.264 encoding.
    2-second segment (120 frames): encoded in ~120ms. Well within the 2-second budget.

Step 4: Package into HLS segments
  HLS requires: video segments in MPEG-TS or CMAF (fMP4) container format.
  Segment duration: 2 seconds (lower = lower latency, higher = better CDN efficiency).
  Each 2-second segment file: ~1.5 MB for 1080p, ~750 KB for 720p.
  
  Segment naming:
    stream_123/1080p/seg_0001.ts
    stream_123/1080p/seg_0002.ts
    ...
    stream_123/720p/seg_0001.ts
    ...

Step 5: Update the m3u8 playlist
  m3u8 is the "menu" file that tells the player what segments are available.
  Updated every 2 seconds (as a new segment is completed).
  
  Example m3u8 (720p):
    #EXTM3U
    #EXT-X-VERSION:3
    #EXT-X-TARGETDURATION:2
    #EXT-X-MEDIA-SEQUENCE:1450
    #EXTINF:2.0,
    https://cdn.example.com/stream_123/720p/seg_1450.ts
    #EXTINF:2.0,
    https://cdn.example.com/stream_123/720p/seg_1451.ts
    #EXTINF:2.0,
    https://cdn.example.com/stream_123/720p/seg_1452.ts
  
  (Only the last 3-5 segments listed for live streams, to enforce forward progress)

Step 6: Push to CDN and S3 (simultaneously)
  CDN push: HTTP PUT to CDN origin servers for each completed segment.
  CDN immediately distributes to all edge PoPs (push distribution).
  S3 recording: same segments written to object storage for replay.
```

---

## Component 3: HLS Distribution — CDN Push Model

**The most important architectural concept in this chapter.**

### Why CDN push (not pull) for live streaming

```
VOD (recorded video) uses CDN pull:
  1. Video is pre-processed and stored in S3.
  2. When first viewer in Tokyo requests a video segment, CDN Tokyo PoP:
     - Cache miss (never served this segment before)
     - Fetches from S3 origin: 100-200ms fetch time
     - Caches locally
  3. All subsequent Tokyo viewers: cache hit, sub-10ms from CDN edge.
  
  This works for VOD because the video already exists when the first viewer requests it.

Live streaming CANNOT use pull:
  1. Viewer in Tokyo requests segment seg_1452.ts.
  2. CDN Tokyo PoP: cache miss (segment just created in the US, not yet there).
  3. CDN fetches from origin: origin is creating seg_1452.ts right now.
     seg_1452.ts might not even exist at the origin yet if the viewer fetched early.
  4. Fetch fails or is delayed. Player buffers. Viewer frustrated.
  
  The first viewer in every region triggers a race condition with segment creation.

Live streaming MUST use CDN push:
  1. Transcoder creates seg_1452.ts.
  2. Immediately: push seg_1452.ts to all 100 CDN edge PoPs before any viewer requests it.
  3. All viewers globally can immediately download from their nearest PoP.
  4. No "first viewer" cache miss race condition.

CDN push implementation:
  Transcoder: after creating each segment and m3u8 update:
    HTTP PUT https://cdn-origin.example.com/live/stream_123/1080p/seg_1452.ts
    (CDN origin distributes to all edge PoPs within 1 second via CDN's internal network)
  
  CDN PoP: when viewer requests seg_1452.ts -> immediate cache hit -> instant serve.
  
Push latency: transcoder -> CDN origin -> CDN edges = 200-500ms total.
Combined with encoding: 2s encode + 0.5s push = 2.5s from "recorded" to "available at edge."
Plus player buffer (2-3 segments): 2.5s + 4-6s = ~7-9s end-to-end latency. (Standard HLS.)
```

### The master playlist (m3u8 for adaptive streaming)

```
Two types of m3u8 files:

1. Master playlist (served once on stream load):
  #EXTM3U
  #EXT-X-STREAM-INF:BANDWIDTH=6000000,RESOLUTION=1920x1080
  https://cdn.example.com/live/stream_123/1080p/playlist.m3u8
  #EXT-X-STREAM-INF:BANDWIDTH=3000000,RESOLUTION=1280x720
  https://cdn.example.com/live/stream_123/720p/playlist.m3u8
  #EXT-X-STREAM-INF:BANDWIDTH=1500000,RESOLUTION=854x480
  https://cdn.example.com/live/stream_123/480p/playlist.m3u8
  #EXT-X-STREAM-INF:BANDWIDTH=800000,RESOLUTION=640x360
  https://cdn.example.com/live/stream_123/360p/playlist.m3u8

  Player picks the appropriate quality level based on current bandwidth estimate.
  Can switch quality levels on any segment boundary.

2. Media playlist per quality (updated every 2s):
  The playlist above per-quality, listing the last 3-5 segments.
  #EXT-X-MEDIA-SEQUENCE: increments by 1 on each new segment.
  Player polls this URL every 2s to discover new segments.
  Each poll: 1-2 KB transfer (just the text playlist).
  
  Player behavior:
    T=0s: fetch master playlist. Pick 720p. Fetch 720p/playlist.m3u8.
    T=0.1s: start downloading seg_1450, seg_1451, seg_1452 (buffer 3 segments).
    T=2.1s: re-fetch 720p/playlist.m3u8. See seg_1453 is now listed.
    T=2.2s: start downloading seg_1453.
    (Continues polling every 2s)
```

---

## Component 4: Viewer Latency Budget — Where the Time Goes

**Interviewers always ask about latency. Know every second.**

```
Latency budget (from "event happens in real world" to "viewer sees it"):

Stage 1: Camera capture + RTMP encoding on streamer's PC
  Time: 0-200ms (depends on OBS encoding settings)
  OBS buffers a keyframe interval (typically 2 seconds for streaming).
  Keyframe interval: OBS doesn't send video until it has a complete keyframe (I-frame).
  Lower keyframe interval = lower latency at higher CPU cost.
  At keyframe interval = 2s: first 2 seconds of video are buffered before sending.
  Contribution: 0-2s (keyframe buffering)

Stage 2: RTMP upload from streamer to ingest server
  Time: depends on network latency. Streamer connects to nearest PoP (5-20ms).
  TCP: latency is proportional to RTT. At 10ms RTT: negligible.
  Contribution: 10-50ms

Stage 3: Relay from ingest PoP to transcoding cluster
  Time: 20-50ms (private backbone)
  Contribution: 20-50ms

Stage 4: Transcoding (encode 2s segment)
  Time: GPU encodes 2s of video in 100-200ms.
  But: transcoder buffers incoming video until it has 2 full seconds to make a segment.
  Contribution: 2s (segment duration) + 100-200ms encoding = 2.1-2.2s

Stage 5: Push segment to CDN edge
  Time: 200-500ms (HTTP PUT to CDN origin + distribution to edge PoPs)
  Contribution: 0.2-0.5s

Stage 6: Player buffering
  Player pre-buffers 2-3 segments before starting playback.
  At 2s segments: 2 * 2 = 4s or 3 * 2 = 6s of buffering.
  Player won't start playback until it has the buffer.
  Contribution: 4-6s

Total latency: 2 (keyframe) + 0.05 (RTMP) + 0.05 (relay) + 2.2 (encode) + 0.5 (CDN) + 5 (buffer)
= ~9.8 seconds. Roughly "within 10 seconds" (standard HLS).

Reducing latency:
  Reduce keyframe interval: 1s instead of 2s -> saves 1s (OBS setting)
  Reduce segment duration: 1s instead of 2s -> CDN requests 2x more often
  Reduce player buffer: 2 segments instead of 3 -> more risk of buffering on network hiccup
  
  With optimizations: 1 + 0.05 + 0.05 + 1.1 + 0.5 + 2 = ~4.7s (< 5s target)

LL-HLS (Low-Latency HLS, Apple extension):
  Partial segments: 200ms "parts" instead of 2s segments.
  HTTP/2 Server Push: server pushes the next partial segment proactively.
  Reduces latency to 1-3 seconds. Requires player support.
  Not all players support LL-HLS yet (2024). Twitch offers LL-HLS as opt-in.
```

---

## Component 5: Handling Streamer Disconnection

**Interviewers always ask about this. Know the exact failure handling.**

### Detection

```
RTMP keepalive:
  RTMP has a built-in ping/pong mechanism.
  Server sends a ping every 30 seconds. Client responds with pong.
  If no pong within 5 seconds of ping: connection declared dead.
  TCP timeout: if no data received for 60 seconds, TCP layer detects disconnect.
  
  In practice: streamer's internet drops -> TCP RST sent (if detectable) or
  no data for timeout period.
  
  Detection time: 2-10 seconds after the disconnect occurs.

Transcoder detection:
  Transcoder is receiving frames from the relay.
  If no frames received for 3 seconds: mark stream as "disconnected."
  Stop producing segments. Do NOT produce a "silent" segment (empty video).
  
  Last action: update the m3u8 playlist with #EXT-X-ENDLIST
  (indicates the stream is over — player will stop polling for new segments).
  Wait 60 seconds before adding #EXT-X-ENDLIST (allow for fast reconnects).
```

### Viewer experience during disconnect

```
Player behavior:
  Player has downloaded segment 1452 and is playing it.
  Player fetches 720p/playlist.m3u8 every 2 seconds.
  Response: same playlist as before (no new segments listed yet).
  Player: "no new segments, but the stream isn't ended (#EXT-X-ENDLIST not present)."
  Player: continue polling. Buffer will drain if no new segments arrive.
  
  After player's buffer drains (4-6 seconds of buffered video): playback stalls.
  Player shows: spinner or "Stream is experiencing issues" message.
  
  Platform UX: show "Stream is offline" banner after 15 seconds of no new segments.
  If #EXT-X-ENDLIST added (stream officially ended): show "Stream ended" message.
  If no end marker within 60 seconds: presume disconnection. Show reconnection timer.
```

### Reconnection

```
Streamer's OBS detects RTMP disconnection (connection error).
OBS automatically reconnects (built-in retry logic in OBS).
New RTMP connection established to the same ingest PoP (or nearest if PoP also failed).

Server side:
  New RTMP connection arrives with the same stream key.
  Server authenticates: same stream key = same streamer.
  Resume the same stream: same stream_id, same CDN paths.
  Transcoder resumes from the next segment number (no rollback).
  
Segment gap:
  Between disconnect and reconnect, 5-30 seconds of video are missing.
  HLS segments: gap in sequence numbers (e.g., seg_1452 then seg_1465, skipping 1453-1464).
  Player behavior: sees a sequence gap, skips the missing segments.
  Viewer experience: brief jump in the stream (timestamp jumps forward).
  This is standard behavior. Viewers understand internet streams disconnect.

Stream key renewal:
  Same stream key allowed for reconnection within 10 minutes of disconnect.
  After 10 minutes: presume the stream ended. Finalize the VOD recording.
  If reconnect attempted after 10 minutes: treated as a new stream.
```

---

## Component 6: Recording and Replay

### Simultaneous recording during live stream

```
Every HLS segment produced by the transcoder is written to object storage (S3) in addition
to being pushed to CDN. This happens simultaneously — there is no extra encoding step for recording.

S3 path structure:
  recordings/{stream_id}/{quality}/{segment_number}.ts
  
  Example:
    recordings/stream_123/1080p/seg_1452.ts
    recordings/stream_123/720p/seg_1452.ts

Playlist recording:
  Also save a copy of each m3u8 update to S3:
    recordings/stream_123/playlist_updates/1080p/seq_1452.m3u8
  (These are used to reconstruct the final VOD playlist after the stream ends.)

Live replay (last 4 hours of active stream):
  CDN edge nodes cache the most recent 4 hours of segments (hot cache).
  A viewer who joins 2 hours late can "rewind" to the stream start by fetching older segments from CDN.
  This is the "stream DVR" feature (Twitch calls it "Live DVR").
```

### VOD creation after stream ends

```
When stream ends (gracefully or via disconnect timeout):

Step 1: VOD Creation Service triggers.
  Reads all segment files from S3 for stream_123 at 1080p (and other qualities).
  Concatenates the segment sequence into a single continuous video file.
  Produces a VOD m3u8 playlist (with #EXT-X-ENDLIST at the end).
  This is the "replay" that viewers can watch after the stream.
  
  Time to produce VOD: 5-15 minutes after stream ends (just file concatenation + manifest generation).
  For a 3-hour stream: ~5,400 segments. Concatenation: fast (no re-encoding needed).

Step 2: VOD available in metadata.
  Metadata Service: update stream record.
    is_live = false
    vod_available = true
    vod_m3u8_url = "recordings/stream_123/vod/master.m3u8"
  
  VOD served from S3 via CDN (pull model — standard VOD serving).

Step 3: Lifecycle management.
  Hot VODs (< 30 days old): kept on S3 Standard storage.
  Cold VODs (> 30 days): moved to S3 Glacier (cheaper, 12-hour retrieval).
  After 60 days (configurable): deleted unless streamer opts to keep.
  Streamers can mark clips as "highlights" to preserve permanently.
```

---

## API Design

### Start Stream (Streamer)
```
POST /v1/streams
Request:  { channel_id: string, title: string, category: string }
Response: { stream_id: string, rtmp_url: string, stream_key: string,
            status: STARTING }
Notes:    stream_key is HMAC-signed; rotated per-stream; never reused
```

The streamer's app (OBS, Streamlabs) calls this before connecting via RTMP. The response provides the `rtmp_url` the streamer configures in OBS and the `stream_key` that authenticates the ingest connection. The key is HMAC-signed using the channel's server-side secret, making it impossible to forge without the signing key. Status starts as `STARTING` and transitions to `LIVE` once the first segment is successfully produced by the transcoder.

Why not just use a static stream key stored in OBS forever? Because static keys are a credential leak risk (visible in screenshots, OBS config files). Per-stream keys expire after stream end, limiting the blast radius of any leak.

### Get Stream Playback URL (Viewer)
```
GET /v1/streams/{stream_id}/playback
Response: { hls_url: string, ll_hls_url: string,
            qualities: [{label: "1080p", bitrate: 6000}, ...],
            viewer_count: int }
Notes:    hls_url points to CDN edge; viewer_count from HyperLogLog (+-0.81%)
```

The viewer's app calls this to get the CDN URL for the HLS master playlist. The response includes both the standard HLS URL and the LL-HLS URL — the client picks based on player capability. `viewer_count` is a HyperLogLog estimate from Redis (see Component 7 below) with at most 0.81% error. At 2M viewers, the displayed count may be off by up to ~16,000 — acceptable since the UI formats it as "2.1M" anyway.

### End Stream
```
DELETE /v1/streams/{stream_id}
Request:  { channel_id: string }
Response: { stream_id: string, status: ENDED, duration_seconds: int,
            peak_viewers: int }
Notes:    triggers VOD processing pipeline; EXT-X-ENDLIST appended to m3u8
```

Called when the streamer explicitly ends the stream from the dashboard. Also called internally after the RTMP disconnect timeout (60 seconds with no reconnect). The response includes `peak_viewers` (max concurrent viewers recorded during the stream) and triggers the VOD creation pipeline: all segments in S3 are stitched into a final m3u8 with `#EXT-X-ENDLIST`, making the replay available within 5 minutes.

### Get Live Channels (Discovery)
```
GET /v1/channels/live?category=gaming&limit=50&cursor=token
Response: { channels: [{channel_id, title, viewer_count, thumbnail_url,
                        stream_id, category}],
            next_cursor: string }
Notes:    cursor-based pagination; sorted by viewer_count DESC; 30s cache
```

The browse/discovery page calls this to list currently live streams. Cursor-based pagination (not offset) because the list is live-sorted by `viewer_count DESC` which changes constantly — offset-based pagination would skip or repeat channels as viewers join and leave. Results are cached at 30-second TTL at the CDN edge. A viewer browsing channels always sees data that is at most 30 seconds stale, which is acceptable for discovery.

Why not sort by `started_at`? Because new streams with 0 viewers should not appear at the top. Viewer count as the sort key surfaces the streams most people are already watching, reinforcing the "popularity signal" that discovery is designed to amplify.

### Ingest Heartbeat (Internal -- Encoder to Ingest)
```
POST /v1/ingest/{stream_id}/heartbeat
Request:  { segment_seq: int, segment_url: string, duration_ms: int }
Response: { next_expected_seq: int }
Notes:    ingest server calls this; used to detect dropped segments
```

This is an internal API — not called by the streamer's OBS, but by the transcoder after producing each segment. It is the mechanism by which the Ingest Coordinator tracks stream health. `segment_seq` is monotonically increasing. If the Coordinator receives `segment_seq: 1452` after `1449`, it knows segments 1450 and 1451 were dropped and can alert or trigger failover. `next_expected_seq` in the response tells the transcoder what the Coordinator expects next — if they diverge, the transcoder knows it has a gap to explain.

---

## DB Schema

```sql
CREATE TABLE streams (
  stream_id      UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  channel_id     UUID         NOT NULL,
  title          TEXT         NOT NULL,
  status         VARCHAR(20)  NOT NULL,  -- STARTING|LIVE|ENDED|ERROR
  category       VARCHAR(50),
  rtmp_ingest_url TEXT        NOT NULL,
  hls_base_url   TEXT,                  -- CDN path, set once encoding starts
  started_at     TIMESTAMPTZ,
  ended_at       TIMESTAMPTZ,
  peak_viewers   INT          NOT NULL DEFAULT 0,
  created_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_streams_channel ON streams(channel_id, created_at DESC);
CREATE INDEX idx_streams_live    ON streams(status, peak_viewers DESC)
  WHERE status = 'LIVE';               -- partial index: only live streams

CREATE TABLE channels (
  channel_id     UUID         PRIMARY KEY,
  owner_user_id  UUID         NOT NULL UNIQUE,
  name           TEXT         NOT NULL UNIQUE,
  stream_key_hash TEXT        NOT NULL,  -- bcrypt hash; raw key never stored
  subscriber_count INT        NOT NULL DEFAULT 0,
  created_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- VOD (recorded streams, post-processing)
CREATE TABLE vods (
  vod_id         UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  stream_id      UUID         NOT NULL REFERENCES streams(stream_id),
  channel_id     UUID         NOT NULL,
  duration_seconds INT        NOT NULL,
  hls_url        TEXT         NOT NULL,  -- points to VOD CDN path
  status         VARCHAR(20)  NOT NULL,  -- PROCESSING|READY|DELETED
  created_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_vods_channel ON vods(channel_id, created_at DESC);

-- Viewer analytics (sampled, not per-event)
CREATE TABLE stream_viewer_snapshots (
  stream_id      UUID         NOT NULL,
  sampled_at     TIMESTAMPTZ  NOT NULL,
  viewer_count   INT          NOT NULL,  -- HyperLogLog estimate at that moment
  PRIMARY KEY (stream_id, sampled_at)
);
-- Retention: 90 days; used for analytics dashboards, not real-time display
```

**Schema design decisions worth explaining in the interview:**

The `streams` table uses a partial index (`WHERE status = 'LIVE'`) for the discovery query. Without it, the discovery query (`SELECT ... WHERE status = 'LIVE' ORDER BY peak_viewers DESC LIMIT 50`) would scan all historical streams. With the partial index, Postgres only indexes the currently-live rows — typically 100K out of millions of historical streams. The index stays small and fast.

`stream_key_hash` stores the bcrypt hash, never the raw key. The raw stream key exists only in the response to `POST /v1/streams` and in OBS on the streamer's machine. The server only ever sees the hash. On authentication, the ingest server receives the raw key, hashes it, and compares against the stored hash — same pattern as password authentication.

`stream_viewer_snapshots` is intentionally NOT the real-time viewer count table. Real-time viewer counts live in Redis (HyperLogLog, updated every 30 seconds). This table is the analytics audit log: every 30 seconds, a background job reads the current HLL count from Redis and writes a row here. This table answers "how did viewer count evolve over the stream's lifetime?" — the analytics dashboard query, not the live display query.

Why separate `vods` from `streams`? Because a VOD has different lifecycle properties than a stream. A stream record is created when the streamer starts broadcasting and updated continuously. A VOD is created only after stream end (by the VOD processing job) and has its own status (`PROCESSING -> READY -> DELETED`). The foreign key `vods.stream_id -> streams.stream_id` links them, but keeping them in separate tables avoids making the `streams` table wide (adding 5+ VOD-specific nullable columns to every stream row, most of which are NULL during the live phase).

---

## Failure Scenarios

### Failure 1: Transcoding worker crashes mid-stream

```
Impact: stream stops producing segments. Viewers see buffering.

Detection: transcoding cluster health monitor detects that the GPU worker handling
stream_123 has stopped producing segments. Alert within 5 seconds.

Recovery:
  1. Stream re-assigned to a new GPU worker on the same cluster.
  2. New worker: receives the raw RTMP stream from the ingest server (ingest server reconnects).
     Or: RTMP relay server buffers the last 10 seconds of video and replays to new worker.
  3. New worker starts encoding from the current timestamp.
  4. Segment gap: 5-15 seconds of video missing (during re-assignment).
  5. Viewer: brief stall, then stream resumes.

Prevention:
  Run a "shadow" transcoder for high-value streams (popular streamers > 100K viewers).
  Shadow transcoder receives the same RTMP stream in parallel.
  On primary crash: switch CDN to point to shadow's output segments. Zero gap.
  Cost: 2x GPU usage for popular streams. Worth it for avoiding outages on large audiences.
```

### Failure 2: CDN PoP outage (region loses all cached segments)

```
Impact: viewers in that region see buffering. New segment requests fail.

Detection: CDN monitors report error rate spike from a specific PoP.

Recovery:
  CDN routing: redirect traffic from failed PoP to the next-nearest PoP.
    Viewer in Tokyo: failed Tokyo PoP -> redirect to Singapore PoP.
    Latency increase: 20-50ms extra per segment (Singapore vs Tokyo).
    Segment size 1.5 MB at 3 Mbps download: 4 seconds to download. Extra 50ms: barely noticeable.
  
  CDN PoPs are designed for hot-standby failover. Most CDNs handle this automatically.
  Viewer impact: brief buffering event as player detects the PoP failure and CDN re-routes.
  Typically < 5 seconds of visible impact.
```

### Failure 3: Ingest PoP goes down (streamer's RTMP connection drops)

```
Impact: same as streamer disconnect. Stream stops. Viewers buffer.

Recovery:
  RTMP is TCP. If the TCP connection drops (PoP crash): OBS detects disconnect immediately.
  OBS reconnects to the next nearest ingest PoP (DNS failover or manual retry URL).
  
  Stream relay: new ingest PoP for stream_123 -> relay to same transcoding worker.
  Resume: same as streamer disconnect + reconnect scenario.
  
  Ingest PoP redundancy: each PoP has a primary and backup ingest server.
  DNS failover between servers: sub-5-second failover within the same PoP.
```

### Failure 4: Segment explosion (viral stream suddenly gets 1M viewers)

```
Scenario: a major event starts on a popular stream. Viewer count goes from 50K to 1M in 5 minutes.
CDN edge nodes in that region: all serving the same stream.
  50K viewers at 3 Mbps = 150 Gbps from one CDN PoP. That PoP's capacity: 100 Gbps.
  Overloaded. 30% of viewers cannot download segments fast enough. Buffering.

Mitigation:
  1. CDN load balancing: the CDN distributes viewers across multiple PoPs in the region.
     NYC PoP: takes half the viewers. Newark PoP: takes the other half.
  2. Each PoP serves from cache: the segment is cached once, served to many viewers.
     CDN bandwidth scales horizontally: add more edge nodes, not bigger pipes.
  3. Notify CDN of expected large event: CDN can pre-position segments at extra PoPs.
     "Stream starts at 9pm, expect 1M viewers in US-East." CDN adds more capacity.
  4. P2P mesh (L6): browsers can share segments directly (WebTorrent-like).
     Each viewer receiving a segment: also serves it to 2-3 other nearby viewers.
     Reduces CDN origin bandwidth by 30-50% for very large events.
```

---

## Deep Concept Explanations

### Concept 1: H.264 Video Encoding Basics

```
For interviewers who ask "how does video encoding work":

Raw video: 1080p 60fps = 1920 * 1080 pixels * 3 bytes/pixel * 60 fps = 373 MB/sec.
Obviously cannot be transmitted as-is. Encoding compresses it.

H.264 (AVC) compression:
  Intra-frame (I-frame): a complete image. No reference to other frames. Large (10-50 KB).
  Predictive frame (P-frame): only the differences from the previous frame. Small (1-5 KB typically).
  Bidirectional frame (B-frame): differences from both previous and next frames. Smallest.

Keyframe interval:
  For streaming: I-frames every 2 seconds (at 60fps: I-frame every 120 frames).
  Why it matters: viewers can only join the stream at an I-frame (random access point).
  If keyframe interval = 2s: a new viewer waits up to 2 seconds for the next I-frame before playback starts.
  For lower latency: smaller keyframe interval (1s), but larger file size (more I-frames).

Bitrate:
  1080p 60fps streaming: 6 Mbps. Excellent quality for streaming.
  720p 30fps: 3 Mbps.
  480p: 1.5 Mbps.
  360p: 0.8 Mbps.

GPU acceleration (NVENC):
  CPU encoding H.264 at 1080p 60fps: 1-2x realtime speed. Cannot encode fast enough for live.
  NVIDIA NVENC (GPU hardware encoder): 10-20x realtime speed.
  One A100 GPU: encodes 10+ 1080p 60fps streams simultaneously.
  This is why GPU instances are used for live transcoding.
```

### Concept 2: Low-Latency HLS (LL-HLS)

```
Standard HLS latency: 5-10 seconds. Too slow for interactive live (gaming, auctions, sports betting).

LL-HLS (Apple, 2019): reduces latency to 1-3 seconds.

Key changes from standard HLS:
  1. Partial segments (parts):
     Standard: 2-second segments published every 2 seconds.
     LL-HLS: 200ms "parts" published every 200ms. Each 2-second segment = 10 parts.
     Player downloads parts as they are created (doesn't wait for the full segment).
  
  2. HTTP/2 Server Push (or Blocking Playlist Request):
     Standard: player polls m3u8 every 2 seconds.
     LL-HLS: player sends a request with a query parameter:
       GET /playlist.m3u8?_HLS_msn=1452&_HLS_part=7
       Server holds this request open until part 7 of segment 1452 is available.
       Server then responds immediately with the updated playlist.
       Player never polls unnecessarily; server notifies it when ready.
     This is called "blocking playlist request" (similar to long-polling).
  
  3. Preload hints:
     Playlist includes a hint of the next partial segment URL before it's available:
       #EXT-X-PRELOAD-HINT:TYPE=PART,URI="seg_1453_part0.ts"
     Player can start the request early (HTTP/2 push or preconnect).
     Reduces latency by starting the download before the URL is officially available.

Latency with LL-HLS:
  Keyframe interval: 1s
  Part size: 200ms
  Server-push wait: 200ms max (next part always arrives within 200ms)
  Player buffer: 3 parts = 600ms
  Total: 1s (keyframe) + 200ms (part) + 200ms (push) + 600ms (buffer) + 500ms (CDN) = ~2.5s

Supported by: iOS 14+, macOS Big Sur+, tvOS 14+. Limited Android support.
Twitch: offers LL-HLS as opt-in for low-latency mode.
YouTube Live: uses a similar partial-segment approach.
```

### Concept 3: WebRTC for Ultra-Low-Latency Streaming (< 500ms)

```
Use case: interactive live events — auctions, game shows, video calls-with-audience.
At < 500ms latency: viewer reaction is nearly synchronous with streamer.

How WebRTC differs from HLS:
  WebRTC: UDP-based. Peer-to-peer protocol. Sub-100ms latency.
  HLS: HTTP-based. Client-server. 5-10 second latency.

SFU (Selective Forwarding Unit) for broadcast:
  One-to-many WebRTC streaming cannot be true peer-to-peer (1 streamer, 500K viewers).
  SFU: a server that receives the stream from the streamer and forwards to all viewers.
  Viewer connects to the SFU (not directly to the streamer).
  SFU: no re-encoding. Just forwards the RTP packets (UDP) to all connected viewers.
  Each viewer: WebRTC peer connection to the SFU.
  
  Scale: one SFU server handles ~2,000 concurrent viewers (limited by outbound bandwidth).
  For 500K viewers: 250 SFU servers in a cluster.
  SFU cluster: 250 servers receive the stream from one transcoder -> forward to 500K viewers.

WebRTC latency breakdown:
  Streamer -> SFU: 10-50ms (WebRTC peer connection)
  SFU -> viewer: 10-100ms (depends on geography)
  Total: 20-150ms. Effectively real-time.

Downsides:
  WebRTC requires: ICE, STUN, TURN for NAT traversal. Complex.
  Browser-based streaming: streamer uses browser API (getUserMedia -> MediaRecorder -> WebRTC).
  Not compatible with OBS/RTMP (need WHIP protocol adapter).
  CDN caching: not possible. WebRTC is stateful per-connection. Cannot cache UDP packets.
  Scale: SFU clusters are expensive (dedicated connections per viewer). Cost 5-10x more than HLS.
  
  When to use WebRTC:
    Ultra-low-latency required (gaming, betting, interactive shows).
    Max viewers in the thousands, not millions. (HLS can scale to millions cheaper.)
  
  Hybrid approach (Twitch "low latency" + "ultra-low latency"):
    Default: HLS at 5-10s latency. Scales to millions cheaply.
    Opt-in: LL-HLS at 2-3s. Still uses CDN.
    Opt-in premium: WebRTC at <1s for special interactive events. Limited capacity, higher cost.
```

---

## L5 vs L6 Calibration Table

```
+---------------------+----------------------------+--------------------------------+
| Dimension           | L5 (Senior SWE)             | L6 (Staff)                     |
+---------------------+----------------------------+--------------------------------+
| Ingest protocol     | RTMP, stream key auth,     | SRT vs RTMP trade-offs. RTMP   |
|                     | geo-routing to nearest PoP  | over lossy networks fails.     |
|                     |                            | SRT handles packet loss. WHIP  |
|                     |                            | for WebRTC browser ingest.     |
+---------------------+----------------------------+--------------------------------+
| Transcoding         | 4 quality levels, GPU,     | NVENC throughput math. Shadow  |
|                     | 2-second segments           | transcoder for high-value      |
|                     |                            | streams. Keyframe interval     |
|                     |                            | impact on latency. Per-GOP     |
|                     |                            | encoding for LL-HLS parts.    |
+---------------------+----------------------------+--------------------------------+
| CDN delivery        | Push vs pull, explains why | Proactive CDN warming for      |
|                     | pull doesn't work for live  | known large events. P2P mesh   |
|                     |                            | for 1M+ viewer relief. CDN     |
|                     |                            | bandwidth cost math ($x/Tbps). |
+---------------------+----------------------------+--------------------------------+
| Latency budget      | Knows 7-9s total, major    | Quantifies every stage. Knows  |
|                     | components                  | keyframe interval = biggest    |
|                     |                            | tunable. LL-HLS parts reduce   |
|                     |                            | to 2-3s. WebRTC for <500ms.   |
+---------------------+----------------------------+--------------------------------+
| Streamer disconnect | Detect within 5s, viewer   | m3u8 #EXT-X-ENDLIST timing.   |
|                     | sees buffering, reconnect   | RTMP buffer replay on new      |
|                     | via same stream key         | worker. Shadow transcoder for  |
|                     |                            | zero-gap failover. Segment     |
|                     |                            | gap handling in player.       |
+---------------------+----------------------------+--------------------------------+
| Recording/replay    | Segments saved to S3 during| Segment stitching into VOD.    |
|                     | live, VOD after stream ends | S3 lifecycle: Standard ->      |
|                     |                            | Glacier at 30 days. Clip       |
|                     |                            | extraction service (separate   |
|                     |                            | from full stream recording).   |
+---------------------+----------------------------+--------------------------------+
| Scale spike         | CDN handles fan-out,        | CDN capacity planning for      |
|                     | viral event scenario        | known events. P2P WebTorrent   |
|                     |                            | for 1M+ viewer loads. Pre-     |
|                     |                            | warming CDN before events.     |
+---------------------+----------------------------+--------------------------------+
```

---

## Production Incidents

### Incident 1: Twitch Transcoding Cascade Failure (2015)

**Company:** Twitch  
**What happened:** A popular gaming event (a major tournament final) started simultaneously for 800K+ viewers. The transcoding cluster received a spike in viewer joins, which caused heavy load on the CDN origin servers (segments being pushed). The CDN origin nodes became the bottleneck. CDN origin latency spiked from 50ms to 8 seconds. Transcoder workers waited for the CDN push acknowledgment before starting the next segment. The transcoder pipeline stalled. Stream latency grew to 60+ seconds. Viewers saw live events 60 seconds behind real time.

**Root cause:** Synchronous CDN push in the transcoding pipeline. Transcoder waited for the CDN HTTP PUT to succeed before continuing. When CDN was slow, the entire pipeline stalled. Write back-pressure flowed backward through the pipeline.

**Fix:** Made CDN push asynchronous. Transcoder writes segment to S3 and immediately starts the next segment. A separate CDN push agent reads segments from S3 and pushes to CDN independently. If CDN is slow: CDN push agent queues up. Transcoder is not blocked.

**Staff lesson:** Never let a downstream write (CDN push) block an upstream pipeline (transcoding). Real-time pipelines must be designed with backpressure management. The transcoder's job is to produce segments; the CDN push is a separate responsibility. Decouple them with an async queue.

---

### Incident 2: YouTube Live Thundering M3u8 Refresh (2020)

**Company:** YouTube  
**What happened:** A major live event with 2M+ concurrent viewers caused a thundering herd on YouTube Live's playlist servers. Every viewer's player fetched the m3u8 playlist every 2 seconds. At 2M viewers: 2M / 2 = 1M playlist requests per second. YouTube's playlist servers were configured for 500K requests per second for that event. Overload. Playlist servers began returning 503 errors. Players that received 503 errors retried immediately (no backoff). Retry storm doubled the request rate. Cascade: playlist servers crashed.

**Root cause:** No retry jitter in the HLS player implementation. Player retry on 503 was immediate. Combined with the pre-existing overload: a 2x amplification loop.

**Fix:** Added exponential backoff with jitter to playlist fetch retries. If 503: wait `rand(0.5, 2.0) * 2^attempts` seconds before retry. This spreads retry load over time. Added playlist server autoscaling with a pre-configured event capacity quota: "for this event, pre-scale to 2x expected request rate."

**Staff lesson:** Client retry behavior must be designed conservatively. Players are not one client — they are millions. "Immediate retry" from millions of clients is a distributed DDoS on your own infrastructure. All retry logic must have jitter.

---

### Incident 3: AWS re:Invent Keynote CDN Failure (2019)

**Company:** AWS (streaming the re:Invent keynote on Twitch and AWS media services)  
**What happened:** During a major keynote, a CDN PoP in US-East failed. 200K viewers in the US-East region experienced stream failures. Fallback routing to US-West caused 150ms additional latency per segment. Viewers experienced buffering as their players adjusted to the new CDN endpoint. Additionally, the master playlist was cached on the failed CDN PoP. Viewers who tried to load the stream during the outage received a stale master playlist pointing to the failed PoP's segment URLs.

**Root cause:** Master playlist (m3u8) was cached at the CDN edge with too-long a TTL (1 hour). When the PoP failed, new viewers loaded the stale master playlist and got segment URLs pointing to the failed PoP. They could not reach those segments and had no fallback.

**Fix:** Reduced master playlist CDN TTL to 30 seconds. Players that reload the master playlist (on error) get the updated URLs pointing to healthy PoPs within 30 seconds. Changed segment URLs to be relative (not absolute) in the master playlist — let the CDN resolve to the nearest healthy PoP dynamically.

**Staff lesson:** Cache TTLs on URLs that reference infrastructure must be short during failure scenarios. Long-lived cached pointers to failed infrastructure are as bad as having no fallback. Any URL that points to a specific server or PoP should have a short TTL or use relative/dynamic resolution.

---

### Incident 4: Twitch RTMP Ingest Overload at TwitchCon 2018

**Company:** Twitch  
**What happened:** At TwitchCon (Twitch's annual conference), 5,000 streamers simultaneously went live from the venue on a shared WiFi network. The venue's WiFi was shared with 10,000 attendees' phones. All RTMP streams competed for the same uplink. RTMP streams dropped constantly due to network congestion. Twitch's ingest servers saw 5,000 streams connecting and disconnecting repeatedly (reconnect loops). The disconnect/reconnect storm created thousands of new stream sessions per minute. Twitch's stream metadata service (which creates a new session record on each stream start) was overwhelmed. Database write queue backed up. Stream metadata was delayed by 5-10 minutes.

**Root cause:** Stateful session creation for every reconnect. Each reconnect (even for the same stream within 60 seconds) created a new session record in the database. At 5,000 streams * 10 reconnects/hour: 50,000 new session records per hour.

**Fix:** Added stream session de-duplication: reconnect within 5 minutes of disconnect = resume same session (no new DB record). New session created only if reconnect occurs more than 5 minutes after disconnect. This reduced database writes by 90% during flappy network conditions.

**Staff lesson:** Transient reconnects (network hiccups) should not generate new lifecycle events in the database. A stream that disconnects and reconnects within 5 minutes is logically the same stream. Idempotent session management (reconnect = resume) prevents write storms during bad network conditions.

---

### Incident 5: Twitch Account Compromise via Stream Key Leak (2017)

**Company:** Twitch  
**What happened:** A streamer's stream key was exposed (via a screenshot in a video where OBS settings were visible). An attacker began broadcasting from the streamer's account (using the leaked stream key). The streamer could not immediately stop the unauthorized broadcast because the stream key was valid. By the time the streamer changed their stream key (a manual process via the dashboard), 40 minutes of unauthorized content had been broadcast under their account.

**Root cause:** Stream keys are long-lived (never expire) and single-factor (knowing the key is sufficient to broadcast). Once leaked, there is no fast revocation mechanism.

**Fix:** Added stream key invalidation API: one click in the streamer dashboard generates a new key and immediately terminates any active connection using the old key. Changed stream key rotation to be easy and encouraged. Added optional two-factor authentication for going live (streamer must confirm on their phone before the RTMP connection is accepted).

**Staff lesson:** Authentication credentials for live systems must have a fast revocation path. "Change your password" on a delayed dashboard is not sufficient for real-time streams. Design for the breach: assume credentials will leak, ensure revocation is a single action with immediate effect.

---

## Exercises

### Exercise 1: HLS Playlist Construction

**Problem:** A streamer has been live for 10 minutes. Currently producing segment number 300 (2-second segments). Write a valid m3u8 playlist file that a viewer's player would receive when fetching the 720p media playlist. Include the last 3 segments. What does the player do next?

**Solution:**

```
720p media playlist (served at: cdn.example.com/live/stream_123/720p/playlist.m3u8):

#EXTM3U
#EXT-X-VERSION:3
#EXT-X-TARGETDURATION:2
#EXT-X-MEDIA-SEQUENCE:298

#EXTINF:2.0,
https://cdn.example.com/live/stream_123/720p/seg_0298.ts
#EXTINF:2.0,
https://cdn.example.com/live/stream_123/720p/seg_0299.ts
#EXTINF:2.0,
https://cdn.example.com/live/stream_123/720p/seg_0300.ts

(No #EXT-X-ENDLIST — stream is live, keep polling)

Key fields:
  #EXT-X-VERSION:3    -- HLS version 3 (minimum for live streaming)
  #EXT-X-TARGETDURATION:2  -- each segment is 2 seconds maximum
  #EXT-X-MEDIA-SEQUENCE:298  -- the sequence number of the FIRST segment in the list
    (player uses this to know what came before and detect gaps)

What does the player do next?
  1. Download seg_0298 and seg_0299 from CDN (already pre-buffering).
     Download rate: at 3 Mbps quality and 3 Mbps network, 1 segment downloads in 1 second.
  2. Wait approximately 2 seconds (one segment duration).
  3. Re-fetch the playlist: GET cdn.example.com/live/stream_123/720p/playlist.m3u8
  4. New playlist should show seg_0301 added, seg_0298 may be removed.
     #EXT-X-MEDIA-SEQUENCE:299 (or 300, depending on implementation).
  5. Player downloads seg_0301 and adds to buffer.
  6. Repeat forever until #EXT-X-ENDLIST appears (stream ended).

Segment numbering:
  300 segments * 2 seconds = 600 seconds = 10 minutes of stream. Correct.
  
At 10 minutes with 2s segments: sequence 1 to 300. Media sequence starts at 298 (last 3).
Older segments (1-297) not listed in the live playlist but available in S3 for DVR/replay.
```

---

### Exercise 2: Latency Budget Calculation

**Problem:** Calculate the end-to-end latency for a standard HLS stream with the following parameters: keyframe interval = 2 seconds, segment duration = 2 seconds, streamer-to-nearest-PoP RTT = 20ms, PoP-to-transcoder relay = 50ms, GPU encoding time = 150ms, transcoder-to-CDN-edge push = 400ms, player buffer = 3 segments. What is the total latency? What is the single biggest contributor?

**Solution:**

```
Latency components (all cumulative):

1. Keyframe buffering (OBS buffers until keyframe):
   Keyframe interval = 2 seconds.
   OBS does not send video until it has a complete Group of Pictures (GOP).
   Maximum keyframe buffer: 2 seconds.
   Average: 1 second (viewer joins mid-GOP on average).
   Use: 2s (worst case for consistent analysis)

2. RTMP upload latency:
   RTT to ingest PoP: 20ms.
   RTMP is streaming (not request-response), so RTT is not additive per frame.
   TCP ACK delay: ~10ms per TCP window.
   Contribution: ~20-30ms.
   Use: 0.030s

3. Relay from PoP to transcoder:
   50ms (private backbone).
   Contribution: 0.050s

4. Segment accumulation (transcoder must receive 2 full seconds of video before encoding):
   Transcoder receives continuous video. Buffers 2 seconds to create one segment.
   This is NOT the same as encoding time. It is the wait for enough video to arrive.
   Contribution: 2.0s

5. GPU encoding time:
   150ms to encode 2 seconds of video (4 quality levels in parallel).
   Contribution: 0.150s

6. CDN push:
   Transcoder pushes segment to CDN origin. CDN distributes to edges.
   400ms end-to-end from transcoder to viewer's nearest CDN edge.
   Contribution: 0.400s

7. Player pre-buffering:
   Player downloads 3 segments before starting playback.
   At 3 Mbps quality (segment = 750 KB): download time per segment = 750KB / (3Mbps/8) = 2s.
   But player downloads segments while streaming, so it buffers "ahead."
   Pre-buffer: 3 segments * 2 seconds each = 6 seconds held back.
   Contribution: 6.0s

Total latency:
  2.0 (keyframe) + 0.030 (RTMP) + 0.050 (relay) + 2.0 (segment accumulation)
  + 0.150 (encoding) + 0.400 (CDN) + 6.0 (player buffer) = 10.63 seconds

Biggest contributor: player buffer at 6 seconds (56% of total latency).
Second: segment accumulation at 2 seconds (19%).
Third: keyframe buffering at 2 seconds (19%).
CDN and encoding together: only 5%.

Optimization priority:
  1. Reduce player buffer: 2 segments (4s) instead of 3 (6s). Saves 2 seconds. Risk: more buffering on network hiccup.
  2. Reduce segment duration to 1s: halves segment accumulation and keyframe buffer. New total: ~6.7s.
  3. LL-HLS (200ms parts): eliminates keyframe wait and reduces player buffer to 600ms. New total: ~3s.
```

---

## Homework

**Short 1:** Open Twitch and inspect the network tab in browser DevTools while watching a live stream. Watch for: (a) requests to `.m3u8` files (playlist requests — how often?), (b) requests to `.ts` files (segment downloads), (c) the response time for each. Does the observed polling interval match the 2-second segment duration described in this chapter?

**Short 2:** Open OBS Studio and find the "Stream" settings. Note the RTMP URL format, keyframe interval option, and bitrate setting. Set the keyframe interval to 1 second and 4 seconds and note what changes in the quality vs. latency discussion. What is the default keyframe interval in OBS?

**Short 3:** Read Apple's documentation on Low-Latency HLS (search "WWDC 2019 LL-HLS"). What are the three main changes LL-HLS introduces over standard HLS? What server requirements does LL-HLS add (hint: HTTP/2 is required)?

**Deep:** Build a minimal live streaming pipeline:
- Use `ffmpeg` to capture your webcam and encode to RTMP: `ffmpeg -f avfoundation -i "0" -c:v libx264 -f flv rtmp://localhost/live/stream`
- Set up `nginx-rtmp-module` as the ingest server (open source RTMP server).
- Configure nginx-rtmp to transcode to HLS: `hls on; hls_path /tmp/hls; hls_fragment 2s`
- Open the resulting `.m3u8` in VLC or Safari. Measure the actual latency.
- Experiment: change `hls_fragment` to 1s and 4s. Observe latency and buffering changes.

---

## Glossary

**RTMP (Real-Time Messaging Protocol):** A TCP-based streaming protocol developed by Macromedia (now Adobe) for delivering audio, video, and data from encoder to server. The dominant ingest protocol for live streaming from OBS and similar tools. Port 1935.

**HLS (HTTP Live Streaming):** An adaptive streaming protocol developed by Apple. Video is split into short segments (2-6 seconds), listed in an m3u8 playlist file. Players fetch the playlist and download segments via standard HTTP. The dominant delivery protocol for live video.

**m3u8:** The playlist file format used by HLS. A text file listing the URLs of video segments in order. For live streams, the playlist is updated every segment interval (2 seconds) with new segments appended and old ones removed.

**MPEG-TS:** A container format for multiplexing audio and video streams. Used as the segment format in HLS. Each .ts segment contains a fixed duration of encoded audio and video.

**Adaptive Bitrate (ABR):** A technique where multiple quality levels of the same stream are provided. The player monitors download speed and switches between quality levels to maintain smooth playback. If network is fast: high quality. If slow: lower quality.

**CDN push:** A content delivery strategy where the origin server proactively sends content to CDN edge nodes as it is created, without waiting for a viewer request. Required for live streaming (contrast with CDN pull used for VOD).

**Ingest PoP (Point of Presence):** A geographically distributed server location that accepts RTMP connections from streamers. Streamers connect to the nearest PoP to minimize upload latency. The PoP relays the stream to the transcoding cluster via a backbone network.

**Transcoding:** Converting a video stream from one encoding (codec, bitrate, resolution) to another. For live streaming: converting the streamer's single-bitrate RTMP input into multiple HLS quality levels in real time. GPU-accelerated (NVIDIA NVENC) for speed.

**Keyframe (I-frame):** A video frame that is encoded as a complete image, without reference to other frames. Viewers can only start playback at a keyframe. The keyframe interval determines how often these appear and directly affects stream start latency.

**LL-HLS (Low-Latency HLS):** Apple's extension to HLS that reduces latency from 5-10 seconds to 1-3 seconds. Key techniques: partial segments (200ms "parts"), blocking playlist requests (server pushes playlist update instead of client polling), and HTTP/2 push.

**SFU (Selective Forwarding Unit):** A WebRTC server that receives a media stream from a publisher and forwards (selects and relays) it to all connected subscribers. Used for low-latency (<500ms) broadcasting via WebRTC. Does not re-encode; just routes packets.

**Shadow transcoder:** A redundant transcoding worker that receives the same stream as the primary transcoder but whose output is not served to viewers. On primary failure, the shadow is promoted to primary. Achieves zero-gap failover at 2x GPU cost.

---

## The One-Sentence Summary

> "Live streaming = RTMP ingest (streamer → nearest ingest PoP via geo-DNS) → relay to GPU transcoding cluster → real-time encode into 4 HLS quality levels as 2-second segments → CDN push (segments proactively forwarded to all edge PoPs the moment they are created, NOT pulled by first viewer) → adaptive bitrate HLS playback (player polls m3u8 playlist every 2 seconds, downloads the latest segments) — the fundamental difference from VOD is CDN push vs. pull: live segments don't exist until just before they're needed, so there is no time to cache on first request, and every design decision (segment duration, keyframe interval, player buffer size) is a direct trade-off between latency and rebuffering probability."

---

## Interview Q&A — Most Common Cross-Questions

---

**Q1: Why use RTMP for ingest instead of HTTP upload?**

RTMP is a persistent TCP connection specifically designed for continuous media streaming. It handles the session negotiation, authentication, and framing of interleaved audio and video chunks natively. HTTP upload (PUT) would require breaking the stream into chunks manually, re-establishing connections on each chunk, and does not have the same real-time framing guarantees. More practically: OBS, Streamlabs, and every streaming software package speaks RTMP natively. If we switched to HTTP upload, we would need to change every streamer's client. RTMP is the established standard on port 1935. Newer alternatives like SRT (more resilient to packet loss) and WHIP (WebRTC-based, browser-native) exist, but RTMP remains dominant because of ecosystem lock-in.

---

**Q2: Why can't live streaming use the same CDN pull model as YouTube VOD?**

CDN pull requires the content to already exist on the origin when the first viewer requests it. For VOD, the video file is pre-processed and sitting in S3 — the CDN can pull it on first request and cache it for everyone after. For live streaming, the content does not exist until the streamer records it. When a viewer in Tokyo requests segment 1452, that segment might have been created at the transcoder 200ms ago. The CDN Tokyo PoP has never seen it. A pull from origin would work, but there is a race: the viewer might request the segment before it has arrived at the CDN origin from the transcoder. CDN push solves this: the transcoder pushes each segment to all CDN PoPs immediately upon creation, so by the time any viewer requests it, every edge node already has it cached.

---

**Q3: What is adaptive bitrate streaming and how does the player decide which quality to use?**

Adaptive bitrate (ABR) means the server provides the same content at multiple quality levels — for example, 1080p at 6 Mbps, 720p at 3 Mbps, 480p at 1.5 Mbps. The player selects which quality to download based on its estimate of the viewer's available bandwidth. This estimate is computed by measuring how fast recent segments downloaded. If a 750 KB segment (720p, 2 seconds) downloaded in 1 second, the available bandwidth is at least 6 Mbps — the player can try 1080p. If it downloaded in 3 seconds, bandwidth is only 2 Mbps — the player drops to 480p. The quality switch happens at segment boundaries (every 2 seconds), so viewers experience smooth quality transitions rather than buffering. This is the mechanism behind the "quality" dropdown on streaming platforms — the automatic setting is just the player's ABR algorithm running without user override.

---

**Q4: What happens to the stream when a transcoding worker crashes?**

The stream stops producing segments for 5-15 seconds during the reassignment. The transcoding cluster's health monitor detects that the worker handling the stream has stopped producing output. It selects a new GPU worker and re-establishes the RTMP relay from the ingest PoP to the new worker. The new worker starts encoding from the current timestamp, producing segments with a gap in the sequence number (the missing seconds). The CDN serves the gap as missing segments — the player sees no new segments listed in the playlist and stalls briefly. After the new worker starts producing segments, the player resumes. Viewers see 5-15 seconds of buffering. For high-profile streams (large audiences), a shadow transcoder running in parallel eliminates this gap: on primary failure, CDN immediately switches to the shadow's output with no gap.

---

**Q5: How is the streamer's disconnect handled differently from a transcoder crash?**

A streamer disconnect is caused by the streamer's network failing — the RTMP connection drops. Detection: RTMP keepalive timeout (5-10 seconds). The transcoder stops receiving frames and stops producing segments. Viewers see buffering after their buffer drains. The key difference from a transcoder crash: the stream can resume when the streamer reconnects. The server waits 60 seconds before marking the stream as ended (#EXT-X-ENDLIST). If the streamer reconnects within 60 seconds using the same stream key, the stream resumes — same stream_id, same CDN paths, same segment numbering. Viewers see a brief stall then continuation. If no reconnect within 60 seconds: the stream is finalized, VOD creation begins, and viewers see a "stream ended" message. A transcoder crash is server-side and triggers immediate worker reassignment without waiting for reconnect.

---

**Q6: How do you record the stream for replay while it is live?**

Every HLS segment produced by the transcoder is written to object storage (S3) simultaneously with being pushed to CDN. There is no extra transcoding or post-processing step for recording — the recording is a natural by-product of segment production. When the stream ends, a VOD Creation Service concatenates all segment files in order (by segment number) into a single m3u8 playlist with #EXT-X-ENDLIST appended. This becomes the replay VOD, available within 5 minutes of stream end. The same CDN can serve VOD segments in pull mode since they already exist in S3. Hot recent segments (last 4 hours) may still be cached at CDN edge from the live stream, making early replay access immediate.

---

**Q7: What is LL-HLS and when would you use it?**

LL-HLS (Low-Latency HLS) reduces streaming latency from 5-10 seconds to 1-3 seconds using three techniques: partial segments (200ms "parts" published every 200ms instead of waiting for a full 2-second segment), blocking playlist requests (player's playlist fetch is held open by the server until a new part is available, eliminating polling overhead), and preload hints (server announces the next partial segment URL before it's available so the player can start the request early). Use LL-HLS when: the interactive experience matters at the 2-3 second scale — sports betting, auctions, live Q&A where the viewer needs to react quickly. LL-HLS is not needed for casual entertainment viewing (gaming, music) where 5-10 second latency is fine. The trade-off: LL-HLS requires HTTP/2, partial segment support in the CDN, and LL-HLS-compatible player implementations. Standard HLS is simpler and more universally supported.

---

**Q8: How do you handle a viral event where a stream suddenly gets 10x more viewers?**

The CDN is the primary scaling mechanism. Segments are cached at each CDN edge PoP — when 100,000 viewers in the same region request the same segment, the CDN serves all of them from cache after the first request. Adding more viewers in the same region does not increase CDN origin load. For viewers spread across new regions: CDN automatically serves from the nearest edge PoP that already has the segment from the push. The origin (transcoder + CDN push) load stays constant regardless of viewer count — only the transcoding workload (fixed per stream) and the CDN push bandwidth (also fixed per segment) matter. The CDN's edge network scales horizontally. For truly extreme events (1M+ viewers): pre-notify the CDN provider to pre-position additional capacity at the expected high-traffic regions.

---

*Section 5 — L5 / Senior SWE. Frequently asked at Twitch, YouTube, TikTok, Meta, LinkedIn. Pairs with Ch60 (Real-Time Chat for the WebSocket live chat that accompanies streams) and Ch52 (Object Storage for the underlying S3 segment storage).*

---

**Q9: How do you handle the situation where a stream's viewer count grows from 100 to 1,000,000 in 5 minutes (viral event)?**

CDN absorbs the viewer spike with no changes to the origin. Each CDN edge PoP already has the latest HLS segments (pushed from the transcoder). Adding 999,900 viewers in the same region means 999,900 more cache hits — no additional load on the transcoder or ingest PoP. The critical path is: (1) CDN edge capacity — most CDN providers auto-scale edge capacity (Cloudflare, Fastly) but notify them for > 1M viewers to pre-position bandwidth. (2) WebSocket notification tier — if the stream uses push notifications for chat and viewer count updates, the notification fan-out from 100 to 1M connections is the bottleneck. Pre-scale WebSocket tiers based on viewer growth rate: if viewers are growing > 10,000/min, add WebSocket nodes.

For platforms like Twitch: a truly viral stream (DSP swatting, President tweet about a streamer) can spike from 10K to 500K in 2 minutes. Mitigation: implement adaptive connection throttling at the WebSocket gateway — shed chat connections beyond 800K and fall back to "chat disabled" status rather than crashing the notification tier.

---

**Q10: How does the player decide between HLS and DASH? Are they interchangeable?**

HLS (HTTP Live Streaming, Apple's standard) and DASH (Dynamic Adaptive Streaming over HTTP, MPEG standard) are functionally equivalent: both serve media as short HTTP segments with a manifest file (m3u8 for HLS, MPD for DASH) that describes quality levels. The differences that matter architecturally:

Container format: HLS historically used MPEG-TS segments (.ts files). Newer HLS uses fragmented MP4 (fMP4) — same container as DASH. DASH always uses fMP4.

Browser native support: HLS is natively supported in Safari (iOS mandatory). DASH requires a JS Media Source Extensions (MSE) player. Chrome, Firefox, and Edge support MSE. For maximum compatibility without a JS player, HLS is preferred. For non-Apple platforms (Android, smart TVs with DASH support), DASH is fine.

DRM: DASH has native support for MPEG-CENC DRM (PlayReady, Widevine). HLS uses FairPlay DRM (Apple-specific). For a cross-platform DRM solution: support both (Common Encryption with different DRM systems).

Most live streaming platforms transcode to HLS and serve it. DASH is more common in VOD (Netflix, Disney+) where MPEG-CENC multi-DRM is a requirement.

---

**Q11: How do you implement stream key rotation and security to prevent unauthorized streaming to a channel?**

A stream key is a secret string that authenticates the streamer's RTMP connection: `rtmp://ingest.example.com/live/{stream_key}`. The ingest server validates the key against the database before accepting the stream. If a key is leaked (shared on stream accidentally, exposed in OBS config files), anyone can stream to the channel.

Key rotation: streamers can regenerate their stream key in account settings. The old key is invalidated immediately. Any RTMP connection using the old key is rejected with a 401 error. If an unauthorized stream was active using the old key, it's disconnected. Streamers are advised to reset keys after every stream and to never display their stream key on camera.

Secure token alternative: instead of a static key, generate a time-limited signed token: `HMAC-SHA256(channel_id + expires_at, server_secret)`. The token is valid only for 24 hours. The RTMP URL becomes `rtmp://ingest.example.com/live/{channel_id}?token={signed_token}&expires={timestamp}`. Leaked tokens self-expire. The ingest server validates: check signature, check expires_at > NOW(), check the channel is not already streaming from another connection.

---

**Q12: How do you implement live captions / subtitles for accessibility?**

Live captions require real-time speech recognition. The architecture: the audio track of the stream (extracted from the RTMP ingest) is sent to a speech recognition service (AWS Transcribe Streaming, Google Speech-to-Text streaming, or Whisper running locally on the transcoder). The speech recognition service returns text with word-level timestamps and confidence scores.

The caption text is embedded in the HLS stream as WebVTT cues. Each HLS segment has an associated `.vtt` sidecar file: `segment_0148.ts` → `segment_0148.vtt`. The m3u8 playlist lists both the segment and its caption track. The player downloads both and renders captions in sync.

Latency: speech recognition adds 2-4 seconds of latency to captions (the model needs to hear a complete phrase before transcribing). For the HLS stream at 8-10 second total latency, captions at +3 seconds are still synchronized. For LL-HLS at 2-3 second latency, captions lag the audio — acceptable for accessibility, but noted.

Accuracy: for gaming streams with background music, accuracy drops significantly. Offer streamers the option to provide their own caption source (OBS caption plugin, or a human captioner on a separate WebSocket connection that pushes text directly to the caption ingest API).

---

**Q13: How do you limit who can watch a private stream (subscription-only or invite-only)?**

The CDN segment URLs must be protected. Two approaches:

Approach A — Signed URLs: every m3u8 playlist request and segment request requires a signed token in the query string. The signing service generates tokens: `HMAC-SHA256(user_id + channel_id + expires_at, signing_key)`. The CDN validates the signature on every request using a Lambda@Edge (or Cloudflare Worker) that runs the validation logic. Signed tokens expire every 10 minutes — the player periodically renews. Users without a valid subscription cannot generate a token.

Approach B — Token-authenticated segment encryption: segments are encrypted at rest (AES-128 with a key unique to the stream). The m3u8 manifest points to a key server: `#EXT-X-KEY:METHOD=AES-128,URI="https://keys.example.com/streams/{stream_id}/key"`. The key server only returns the decryption key to authenticated subscribers. Unauthenticated users download segments but cannot decrypt them. This approach has lower CDN integration complexity (standard CDN serving) at the cost of crypto overhead per segment.

For most platforms: Approach A (signed CDN URLs) is preferred for content that is paywalled at the request time. Approach B (encryption) is preferred for content that is cached widely but restricted by decryption key access.

---

**Q14: How does stream clipping work — users create short clips of live streams?**

A clip is a short video (15-60 seconds) that a user creates by clicking "Clip" at any moment during a live stream. The clip should contain the 60 seconds leading up to the click.

Implementation: the last 120 seconds of segments are always stored in S3 with a rolling window (segments older than 120 seconds are still in S3, not yet GC'd). When a user clicks "Clip": (1) record the clip_timestamp (current server time). (2) A Clip Service identifies the relevant segments: all HLS segments whose time range includes [clip_timestamp - 60s, clip_timestamp]. (3) Transcode these segments into a self-contained MP4 file (re-encode to embed the exact start and end frames). (4) Store the MP4 in a "clips" S3 bucket with a unique clip_id. (5) Return the clip URL to the user.

The transcoding step (3) takes 10-30 seconds depending on clip length and GPU availability. Users see a "clip creating" loading state during this time. The clip is then shareable as a standard video (CDN-served, no subscription required — clips are public by default).

For scale: Twitch processes millions of clips per day. The clip creation jobs run on a Spot Instance GPU pool (cost-optimized since clip creation has no hard latency requirement). Job queue: SQS → ECS Spot tasks.

---

**Q15: How do you handle a 24/7 continuous stream (like a looping channel or ambient stream)?**

A continuous stream never disconnects. The challenges: (1) segment accumulation — 24 hours of 2-second segments = 43,200 segments per quality level × 4 levels = 173,000 files. If S3 stores them all, storage costs grow unboundedly. (2) m3u8 playlist size — a standard VOD m3u8 with 43,200 entries is 1.7 MB per playlist request — too large for frequent polling. (3) Transcoder continuity — the transcoding worker must run 24/7 without crashing.

Solutions:
1. **Rolling m3u8 playlist (live window):** the m3u8 only lists the last 5 segments (10 seconds of video). Older segments are omitted from the playlist. The player always starts from the live edge, not the beginning. The `#EXT-X-PLAYLIST-TYPE:EVENT` type allows both live and catchup; for pure live: `#EXT-X-PLAYLIST-TYPE` is omitted and only a rolling window is served.
2. **DVR window:** keep only the last 4 hours of segments in the "live" S3 prefix. Older segments are moved to a "vod" prefix or deleted. Set S3 lifecycle rules: segments in `live/` older than 4 hours are auto-moved to `archive/` with a Glacier transition after 30 days.
3. **Transcoder continuity:** shadow transcoder running in parallel at all times. If primary fails, CDN switches to shadow output within 5 seconds (no 30-second recovery gap). For 24/7 streams, downtime is never acceptable — dual-transcoder is the baseline, not a luxury.

---

## Monitoring and Observability

### Key Metrics by Subsystem

**Ingest health:**

| Metric | Healthy | Alert |
|--------|---------|-------|
| `rtmp_connection_rate` /sec | varies | Spike > 10× baseline in 60s (bot attack on ingest) |
| `ingest_bitrate_kbps` per stream | 3,000–6,000 | < 1,000 sustained (streamer bandwidth issue) |
| `segment_production_rate` segs/sec | 0.5 per stream | Drop to 0 (transcoder stalled — immediate alert) |
| `ingest_pop_latency_ms` | < 50ms | > 200ms (routing issue, use geo-DNS failover) |

**Transcoding:**

| Metric | Healthy | Alert |
|--------|---------|-------|
| `gpu_utilization_%` per worker | 60–85% | > 95% sustained (transcoder can't keep up — add capacity) |
| `keyframe_interval_deviation_ms` | < 100ms | > 500ms (stream will cause ABR switching issues) |
| `segment_generation_latency_ms` | < 200ms | > 500ms (player will stall waiting for next segment) |
| `transcoder_crash_rate` /hour | 0 | > 0 (worker instability — investigate GPU memory leaks) |

**CDN delivery:**

| Metric | Healthy | Alert |
|--------|---------|-------|
| `segment_cache_hit_rate_%` | > 99% | < 95% (CDN not serving from cache — origin overloaded) |
| `segment_delivery_latency_p99_ms` | < 200ms | > 1,000ms (CDN edge degraded) |
| `origin_segment_requests_per_sec` | < 100 | > 10,000 (cache not propagating — mass cache miss) |

**Player-side (via client telemetry):**

| Metric | Healthy | Alert |
|--------|---------|-------|
| `rebuffer_rate_%` (% of sessions with stall) | < 2% | > 10% (CDN degraded or ingest issue) |
| `startup_latency_p99_ms` | < 3,000ms | > 8,000ms (player slow to find first segment) |
| `quality_switch_rate` per session | 1–3 | > 10 (network instability, ABR oscillating) |

### Distributed Trace: Segment Delivery Flow

```
Trace: segment_request (segment = stream_0148_1080p.ts)
  ├─ Span 1: CDN edge (cache lookup)           0.5ms ← HIT: done in 0.5ms total
  │         (cache MISS continues)
  ├─ Span 2: CDN origin (S3 fetch)             45ms
  ├─ Span 3: S3 read (segment bytes)           30ms
  └─ Span 4: CDN edge cache store              5ms
```

Alert on: Span 2 rate > 100/sec (cache miss storm — push not reaching CDN), Span 3 > 200ms (S3 overloaded or segment not yet written).

---

## Capacity Planning — Major Live Event (Stadium Concert Stream)

**Event:** Beyoncé concert livestream, 2M simultaneous global viewers.

**Ingest:**
```
1 RTMP stream from venue (4K source, 20 Mbps bitrate)
1 ingest PoP (nearest to venue)
Bandwidth at ingest PoP: 20 Mbps inbound + 40 Mbps relay to transcoder = 60 Mbps → trivial
```

**Transcoding:**
```
4 quality levels: 1080p@6Mbps, 720p@3Mbps, 480p@1.5Mbps, 360p@0.75Mbps
Total encoded bitrate: 11.25 Mbps
Segment duration: 2 seconds
GPU transcoding: 1 NVENC GPU encodes all 4 levels simultaneously (no CPU bottleneck)
Shadow transcoder: 1 additional GPU instance in standby
Total: 2 GPU instances
```

**CDN push bandwidth:**
```
Total transcoder output: 11.25 Mbps × 1 segment every 2s = 11.25 Mbps steady state
CDN push: each new segment pushed to 50 global PoPs × 4 quality levels
50 PoPs × 11.25 Mbps = 562.5 Mbps CDN push bandwidth (paid to CDN provider)
```

**CDN pull bandwidth (viewer requests):**
```
2M viewers, each pulling 1 segment every 2 seconds
90% watch at 1080p (from home): 1.8M × 6 Mbps = 10.8 Tbps
10% watch at 720p (mobile): 200K × 3 Mbps = 600 Gbps
Total CDN egress: ~11.4 Tbps
Cost (Cloudflare): ~$0.01/GB, 11.4 Tbps × 7200 sec (2h) = 1,026 TB → $10,260 CDN cost
(Pre-negotiate with CDN for event pricing — typical 50% discount for pre-announced events)
```

**Origin load:**
```
With 99% cache hit rate: 1% of 1M segment requests/sec = 10,000 requests/sec to origin
S3: 10,000 GET requests/sec — manageable (S3 handles millions of requests/sec per prefix)
To avoid S3 hot prefix: distribute segments across 4 prefixes (stream_0/, stream_1/, stream_2/, stream_3/)
```

---

## Common Anti-Patterns

**Anti-pattern 1: CDN pull model for live segments (race condition)**
```
# WRONG: CDN pull for live content
viewer → CDN edge: GET segment_0148.ts
CDN edge: cache MISS → pull from origin (S3)
S3: segment_0148.ts does NOT exist yet (transcoder hasn't finished writing it)
CDN: returns 404 → player error
```
Fix: CDN push — transcoder proactively pushes each segment to CDN immediately after writing to S3. By the time any viewer requests the segment, CDN already has it. Pushes should use CDN's `PUT` API or a CDN-optimized relay network (e.g., Akamai's SureRoute, Cloudflare's Workers KV).

**Anti-pattern 2: Segment duration longer than keyframe interval**
```
# WRONG: 4-second segments with 2-second keyframe intervals
# Player cannot start a segment at a non-keyframe position
# Seeking to segment N requires decoding from previous keyframe
# Wasted bytes: player downloads frames it can't start from
```
Fix: Keyframe interval = segment duration. If segments are 2 seconds, force a keyframe every 2 seconds in the encoder. In FFmpeg: `-g 60 -keyint_min 60 -sc_threshold 0` (at 30fps, this forces a keyframe every 60 frames = 2 seconds). Each segment boundary is always a keyframe.

**Anti-pattern 3: Storing uncompressed audio/video in the pipeline**
```
# WRONG: store raw frames between ingest and transcoding
rtmp_frames → frame_buffer (raw YUV420, 4K) → transcoder
# 4K raw video: 3840×2160×1.5 bytes × 30fps = 373 MB/sec of raw video
# Any buffer with > 1 second of raw video = 373 MB → impractical
```
Fix: The RTMP stream carries already-compressed H.264 or H.265 video. Transcoding decodes this and re-encodes at lower bitrates — never store raw frames. The intermediate format between ingest and transcoder is the original compressed stream.

**Anti-pattern 4: Using a static segment URL scheme (breaks CDN cache on reconnect)**
```
# WRONG: segment URLs reset to 0000 on streamer reconnect
stream/{stream_id}/segment0000.ts → reconnect → stream/{stream_id}/segment0000.ts
# CDN may serve stale segment0000.ts from before the reconnect
```
Fix: Use monotonically increasing global segment numbers (or wall-clock timestamps in segment names). On reconnect, the counter continues: segment_3210.ts → reconnect → segment_3211.ts. CDN never confuses new segments with old cached content.

**Anti-pattern 5: Player polls m3u8 at segment duration interval (too slow)**

Polling every 2 seconds for 2-second segments means: the player downloads the current segment, waits until exactly the next poll interval, fetches the new playlist, and only then begins downloading the next segment. If the poll fires even 100ms late, the player is already in a deficit. Fix: poll at half the segment duration (every 1 second for 2-second segments) so the player always has the next segment URL before it needs it. Better: use LL-HLS blocking playlist requests (server holds the response until a new segment is available, avoiding polling jitter entirely).

---

## Production Incident Deep Dives (Extended)

### Incident 6: Twitch RTMP Ingest Overload — World Cup 2018

**Date:** July 15, 2018 (France vs Croatia World Cup Final)
**Duration:** 45 minutes of degraded service

**What happened:** Thousands of streamers decided to simultaneously restream the World Cup final on their own Twitch channels. Within 10 minutes of kickoff, RTMP ingest connections increased 8× above normal. The ingest cluster was sized for normal load + 3× headroom. The 8× spike saturated the ingest PoPs in Europe (where the match was playing at 5 PM local time). New RTMP connections were rejected with connection refused. Streamers attempted to reconnect — exacerbating the load. Even streamers doing unrelated content (gaming) experienced connection failures because the same RTMP ingest servers handled all traffic.

**Root cause:** No partitioning of ingest load by geography or stream importance. All streamers shared the same ingest pool.

**Fixes:**
1. **Prioritized ingest pools:** high-follower channels (Partners and Affiliates) route to a dedicated ingest cluster. New accounts route to a separate, lower-capacity cluster. This ensures high-value streamers are unaffected by a flood of small streamers.
2. **Ingest rate limiting per account tier:** new accounts are limited to 6 Mbps bitrate. Partners can stream at up to 20 Mbps. Total bandwidth consumption scales with account tier rather than allowing any account to use 20 Mbps.
3. **RTMP connection queuing:** instead of immediate rejection when capacity is reached, new connections are held in a brief queue (10 seconds) to absorb transient spikes, then rejected if capacity is still full.

---

### Incident 7: YouTube Live — Thumbnail Generation Cascade (2021)

**Date:** Multiple incidents in 2021
**Impact:** Live streams showed incorrect or missing thumbnails for 5-30 minutes

**What happened:** YouTube generates live stream thumbnails from keyframes (takes a frame every 30 seconds and resizes it). The thumbnail generation service received jobs via an SQS queue. During high viewership events, the queue backed up: thumbnail jobs took 2 seconds to process (GPU resize), but arrived at 5/sec per popular stream × 100 high-traffic streams = 500 jobs/sec. The queue grew from 0 to 50,000 jobs in ~90 seconds. Thumbnail generation workers were provisioned at 200 workers, each handling 1 job at a time → 200 jobs/sec — not enough.

The backlog meant thumbnails were 250 seconds (4+ minutes) stale. But the real problem: when the backlog cleared (live event ended), 50,000 thumbnail jobs ran simultaneously, each making S3 PutObject calls. The S3 prefix `thumbnails/` received 50,000 writes/sec from all workers simultaneously — triggering S3 429 rate-limit errors on the prefix. Workers retried with backoff, creating another wave 10 seconds later.

**Root cause:** (1) Thumbnail generation workers under-provisioned for event traffic. (2) S3 prefix hot-spot under concurrent writes from all workers.

**Fix:**
1. Auto-scale thumbnail workers based on SQS queue depth (CloudWatch alarm: queue depth > 10,000 → add 100 workers).
2. S3 prefix sharding: spread thumbnails across 16 prefixes (`thumbnails/0/`, `thumbnails/1/`, ...) based on `stream_id % 16`. S3 rate limits are per prefix — 16 prefixes × 3,500 writes/prefix/sec = 56,000 writes/sec total capacity.
3. Thumbnail quality tiers: for low-viewership streams (< 1K viewers), generate thumbnails every 120 seconds instead of 30. High-viewership streams (> 100K) get 10-second thumbnails. Reduces total job volume by 4× while maintaining quality where it matters.

---

## Additional Exercises

### Exercise 4: CDN Push Architecture Design

**Problem:** Design the segment push pipeline for a global CDN. The transcoder produces a new 2-second segment. Within 500ms, all 50 CDN PoPs globally should have the segment. The transcoder is in us-east-1.

**Solution:**

```
Option A: Transcoder → S3 → CDN origin poll (wrong for live)
  - S3 write: 50ms
  - CDN origin polls S3 every 2 seconds
  - CDN propagation: up to 2 seconds additional delay
  - Total to all PoPs: 2s + propagation = too slow

Option B: Transcoder direct push to CDN (correct)
  Transcoder produces segment → simultaneously:
  1. Write to S3 (for durability and VOD replay)                    50ms
  2. Push to CDN's origin shield (a single CDN node near transcoder) 20ms
  3. CDN origin shield propagates to all 50 PoPs (internal CDN network) 200-400ms
  Total: ~450ms → within 500ms target ✓
```

The S3 write and CDN push run in parallel (not sequentially). The transcoder does not wait for the S3 write to complete before pushing to CDN — both are fire-and-forget async operations. The m3u8 playlist update is pushed to CDN with a 2-second TTL so polling players always see fresh data. The segment files themselves get a long TTL (5+ minutes) since a segment's content never changes once written.

---

### Exercise 5: Latency Budget for LL-HLS

**Problem:** Calculate the theoretical minimum end-to-end latency for a LL-HLS stream. Break down each component. Compare to standard HLS.

**Solution:**

```
Standard HLS latency budget (seconds):
  Keyframe interval (encoder must accumulate full segment): 2.0s
  RTMP relay delay (ingest PoP → transcoder):             0.1s
  Transcoding time (GPU encode + segment write):          0.2s
  CDN push latency (transcoder → CDN edge):               0.3s
  Player buffer (player pre-buffers 3 segments before play): 6.0s
  ─────────────────────────────────────────────────────────────
  Total standard HLS:                                     8.6s

LL-HLS latency budget (seconds):
  Partial segment duration (200ms chunks instead of 2s):  0.2s
  RTMP relay delay:                                       0.1s
  Partial transcoding (encode 200ms chunk, not 2s):       0.05s
  CDN push (partial segments are small, push faster):     0.1s
  Player buffer (1 partial segment = 200ms):              0.2s
  Blocking playlist round-trip (server waits for next part): 0.2s
  ─────────────────────────────────────────────────────────────
  Total LL-HLS:                                           0.85s → ~1s

Reality check:
  LL-HLS in production: 1.5–3s (network jitter, TCP retransmits, CDN propagation variance)
  Standard HLS in production: 6–12s (player buffer strategies vary, DVR seeking adds latency)

When to use LL-HLS:
  - Sports betting (viewer bets before seeing outcome)
  - Live auctions (bid before hammer falls)
  - Interactive Q&A with streamers (reduce conversation delay)
  
When standard HLS is fine:
  - Gaming entertainment (5-10s latency unnoticeable)
  - Concerts, performances (passive viewing)
  - News (slight delay acceptable)
```

---

## L5 vs L6 Calibration Table — Live Streaming

| Topic | L5 Answer | L6/Staff Answer |
|-------|-----------|-----------------|
| Ingest protocol | RTMP to nearest ingest PoP via geo-DNS | Plus: SRT (UDP-based, resilient to 30% packet loss); WHIP (WebRTC-based, browser-native streaming); multi-bitrate adaptive ingest (encoder adjusts bitrate if ingest bandwidth fluctuates) |
| Transcoding | GPU NVENC; 4 quality levels; segment = keyframe interval | Plus: ABR ladder optimization (VMAF perceptual quality score per ladder rung, not fixed bitrates); per-GOP encoding (encode GOP by GOP for parallelism across GPUs); codec selection (AVC for compatibility, HEVC for 50% bitrate saving, AV1 for 30% additional saving vs HEVC) |
| CDN distribution | Push segments on production; 50 edge PoPs | Plus: multi-CDN (primary Cloudflare, failover Fastly with health-check-based routing); CDN token signing for subscriber-only content; tiered CDN (regional aggregation PoPs reduce origin push fan-out from 50 to 5 regional hubs that propagate further) |
| HLS delivery | 2-second segments; rolling m3u8; ABR player | Plus: LL-HLS (200ms partial segments, blocking playlist requests); CMAF (MPEG-DASH + HLS compatibility in same segments); chunk transfer encoding to reduce first-byte latency |
| Latency | ~8-10s for standard HLS; ~2-3s for LL-HLS | Plus: ultra-low latency via WebRTC SFU (< 500ms) for interactive streams; latency class selection per content type; RTSP for IP camera ingest (not streamer software) |
| Viewer scale | CDN serves all viewers; origin load constant | Plus: predictive CDN pre-positioning for announced events; viewer count aggregation via HyperLogLog in Redis; adaptive manifest manipulation (hide 4K quality tier from cellular viewers to control bandwidth) |
| VOD creation | S3 stores all segments; m3u8 finalized at stream end | Plus: frame-accurate clip creation; distributed FFmpeg transcode farm for post-stream processing; chapter markers from manual input or silence detection; automatic highlight reel using ML engagement scoring |
| Stream security | Stream key validation at ingest; signed CDN URLs for private streams | Plus: watermarking each user's stream with imperceptible steganographic mark (for piracy detection); DRM with FairPlay (iOS), Widevine (Android/Chrome), PlayReady (Edge/IE); token-bound CDN URLs with 10-min renewal |

---

## Additional Exercises

### Exercise 6: HLS Segment Recovery Design

**Problem:** A CDN edge node serving viewers in Tokyo loses all cached segments for stream S123 (node restart). Design the recovery so Tokyo viewers experience at most 3 seconds of buffering, not a stream failure.

**Solution:**

```
CDN pull-from-origin recovery:
  
  Step 1: Viewer requests segment: GET cdn-tokyo.example.com/live/S123/segment_0148_1080p.ts
  Step 2: CDN Tokyo: cache MISS (node just restarted)
  Step 3: CDN Tokyo: pull from CDN origin shield (us-east-1 origin)
    - Segment was pushed to origin shield 8 seconds ago (current live position)
    - Pull: ~200ms round-trip Tokyo → us-east-1
  Step 4: CDN Tokyo: cache segment, return to viewer
  Step 5: CDN Tokyo: cache is warm for all subsequent viewers
  
  Total viewer impact: first viewer gets 200ms extra latency (imperceptible)
  All subsequent Tokyo viewers: cache hit, no impact
  
The key insight: origin pull (CDN "cache miss and fetch from origin") is the
recovery mechanism. Unlike VOD where pull is the PRIMARY mechanism,
in live streaming pull is the FALLBACK when push fails.

If the segment is not yet at the CDN origin:
  The segment may not exist if the transcoder is more than 8 seconds behind
  (a transcoder crash scenario). In this case:
  
  CDN Tokyo: pull from CDN origin → 404 (segment doesn't exist yet)
  CDN Tokyo: returns 404 to the viewer's player
  Player: waits for next playlist fetch (1 second later)
  Player: sees the segment listed in m3u8 → retries
  
  Recovery time = time until transcoder restarts and produces the segment
  Target: < 30 seconds (shadowed transcoder takes over in 5-10 seconds)
  Viewer sees: 5-30 seconds of buffering (within tolerance for known failure modes)
  
Buffer sizing for recovery:
  Player buffer = 6 seconds (3 × 2-second segments pre-downloaded)
  Transcoder recovery time: 5-10 seconds (shadow transcoder)
  Gap: 5-10 second transcoder gap - 6 second player buffer = 0-4 seconds of stall
  If shadow transcoder recovers in < 6 seconds: zero viewer-visible stall
```

---

### Exercise 7: Viewer Count at Scale

**Problem:** A viral stream has 2 million viewers. Design a system to display the accurate live viewer count, updated every 30 seconds, without overloading the backend with 2 million concurrent connections all sending heartbeats.

**Solution:**

```python
# Problem: 2M viewers × 1 heartbeat/30sec = 66,667 requests/sec just for viewership
# This is manageable (not a problem), but accurate counting needs care

# Approach 1: Exact count with Redis TTL
# Each viewer heartbeat:
def viewer_heartbeat(stream_id, viewer_token):
    # viewer_token = unique per session (anonymous UUID)
    redis.set(f"viewer:{stream_id}:{viewer_token}", 1, ex=90)  # 90s TTL (3 heartbeat intervals)
    
def get_viewer_count(stream_id):
    # EXPENSIVE: scans all keys matching pattern
    return len(redis.keys(f"viewer:{stream_id}:*"))  # O(N) — DO NOT USE at scale

# Problem: KEYS is O(N) over 2M keys — blocks Redis for seconds

# Approach 2: HyperLogLog (approximate, < 1% error, 12 KB memory regardless of count)
def viewer_heartbeat(stream_id, viewer_token):
    redis.pfadd(f"viewers_hll:{stream_id}", viewer_token)
    # No TTL on individual viewers — HLL accumulates all-time viewers
    # Limitation: can't subtract departed viewers

# Better: windowed HLL (rolling 5-minute window)
def viewer_heartbeat_windowed(stream_id, viewer_token):
    window_key = f"viewers_hll:{stream_id}:{current_5min_window}"
    redis.pfadd(window_key, viewer_token)
    redis.expire(window_key, 600)  # 10 min TTL (2 windows)
    
def get_current_viewers(stream_id):
    # Count viewers in last 5-minute window
    window_key = f"viewers_hll:{stream_id}:{current_5min_window}"
    return redis.pfcount(window_key)  # O(1), approximate count ±0.81%

# Approach 3: Exact count with Redis COUNTER (best for display, not for analytics)
def viewer_joined(stream_id):
    redis.incr(f"viewer_count:{stream_id}")
    
def viewer_left(stream_id):
    redis.decr(f"viewer_count:{stream_id}")

# Problem: how do you know when a viewer left vs. just closed the tab?
# Use DECR only on explicit disconnect events (WebSocket close)
# For clients that crash without sending disconnect: reconcile via HLL

# Production decision:
# Display counter: Redis INCR/DECR (exact for engaged viewers with WebSocket)
# Analytics: HyperLogLog (unique viewers over time, even if they refreshed)
# Peak viewer count: record max(viewer_count) every 30 seconds in TimescaleDB

# Final: show "2.1M viewers" (formatted, not "2,139,847") — viewers don't need exact count
```

---

### Exercise 8: Multi-Quality Transcoder Failover

**Problem:** The primary GPU transcoding worker crashes mid-stream. You have a shadow transcoder running. Design the CDN failover so viewers see no more than 5 seconds of buffering.

**Solution:**

```
Setup:
  Primary transcoder: NVENC GPU worker A (main)
  Shadow transcoder: NVENC GPU worker B (running in parallel from same RTMP relay)
  Both produce identical segments (same RTMP input → same encode params → same output)
  
  CDN path: all viewers point to primary's output CDN path:
    https://cdn.example.com/live/{stream_id}/primary/segment_{N}.ts
  
  Shadow produces to a parallel path:
    https://cdn.example.com/live/{stream_id}/shadow/segment_{N}.ts
  
  Important: both transcoders see the same RTMP relay (via multicast from ingest PoP)
  Shadow's segments may differ slightly (encoding is not deterministic) but are
  perceptually identical at the same quality level.

Failover sequence:
  T=0: Primary crashes. No new segments in primary/ path.
  T=5s: Health monitor detects: no new segment in primary/ for > 5 seconds (SLA).
  
  Health monitor: checks S3 last-modified timestamp for primary's latest segment key
    if NOW() - s3.head_object("primary/segment_latest.ts").last_modified > 5s:
        trigger_failover(stream_id)
        
  Failover action:
    1. Update the stream's master m3u8 playlist to point to shadow/ path
    2. Push the updated m3u8 to CDN (immediate cache invalidation)
    3. Players polling the m3u8 (every 1-2 seconds) pick up the new path on next poll
    
  Player perspective:
    T=0: Primary crashes. Player buffer has 6 seconds of pre-downloaded segments.
    T=5s: Failover triggered. m3u8 updated to shadow path.
    T=6s: Player's 6-second buffer runs out (or next m3u8 poll, whichever first).
    T=7s: Player polls m3u8, sees shadow path, begins downloading from shadow.
    T=7.5s: Shadow segment downloads successfully.
    
    Viewer stall: at most 1-2 seconds (time between buffer exhaustion and shadow segment ready)
    
  Segment number gap:
    Primary: produced segments 0–1439 (48 minutes)
    Shadow: produced segments 0–1439 in parallel (same wall-clock time)
    After failover: shadow continues producing 1440, 1441, ...
    No gap in segment numbers from the viewer's perspective.
    
  Start new shadow:
    After primary crashes, start replacement GPU worker immediately.
    New shadow becomes the new standby for the current shadow (which is now primary).
    1→2 shadow redundancy restored within 30 seconds (GPU instance boot time).
```

---

## Key Interview Signals — What L5 Looks Like In the Room

**Signal 1: You correctly identify CDN push (not pull) as the key live streaming insight.**
The single most revealing question in a live streaming interview is "how does the CDN serve segments to millions of viewers?" Candidates who say "the CDN caches segments and pulls from origin on first request" show they haven't thought about the timing: the segment doesn't exist on the origin until a second after it's produced — a viewer might request it before it's arrived. L5 candidates explain CDN push proactively, and then explain that pull becomes a fallback (not the primary path).

**Signal 2: You give the latency budget breakdown without being asked.**
"End-to-end latency is about 8-10 seconds" is the adjective answer. The L5 answer: "2-second keyframe interval + 150ms encode + 50ms relay + 400ms CDN push + 6-second player buffer = ~8.6 seconds" — a summation of identifiable components. This level of breakdown tells the interviewer you could optimize any specific component if asked ("how would you reduce latency to 3 seconds?").

**Signal 3: You distinguish between CDN load and origin load.**
Many candidates say "the CDN scales horizontally as viewers increase." L5 candidates go further: "the CDN origin (transcoder output) stays constant regardless of viewer count, because segments are pushed once and cached at every edge. Adding 1 million viewers in Tokyo means 1 million cache hits at the Tokyo PoP — no new load on the transcoder or origin. This is the fundamental scaling property of CDN push for live streaming."

**Signal 4: You mention the shadow transcoder for high-profile streams.**
Fault tolerance comes in two flavors: recovery (detect failure, restart, resume) and redundancy (run two instances, promote on failure). For live streaming, recovery causes a visible gap (5-30 seconds). Redundancy eliminates the gap. The L5 answer is: for ordinary streams, recovery is acceptable. For high-profile streams (large audiences, paying viewers, major events), shadow transcoding is mandatory — the cost of one extra GPU instance is trivial compared to the cost of a 30-second outage on a 1M-viewer stream.

---

## Related Topics to Review After This Chapter

- **Ch60 (Real-Time Chat):** Live streaming always accompanies live chat (Twitch chat, YouTube Live chat). The WebSocket architecture for delivering 50,000 chat messages per second to millions of viewers uses identical fan-out and throttling patterns as the price delivery in Ch61k. If you understand CDN push for segments, Ch60's WebSocket scaling is a natural extension.
- **Ch52 (Object Storage):** Every HLS segment is a file in S3. Understanding S3's request rate limits (3,500 PUTs/sec per prefix), prefix sharding strategies, and S3 Transfer Acceleration is directly applicable to the segment storage design. Ch52 covers the operational details of running object storage at scale.
- **Ch33 (Caching at Scale):** CDN caching of HLS segments is the largest-scale caching problem in this chapter. The cache TTL for live segments (2-5 seconds) vs. VOD segments (24 hours) vs. m3u8 playlists (2 seconds) illustrates different cache TTL strategies for content with different update frequencies. Ch33 covers TTL strategy, cache eviction, and cache warming in general terms.
- **FFmpeg documentation (external tool):** FFmpeg is the reference implementation of HLS transcoding. Understanding the flags `-hls_time 2` (segment duration), `-hls_list_size 5` (rolling window size), `-hls_flags delete_segments` (auto-delete old segments), and `-g 60 -keyint_min 60` (keyframe interval forcing) makes you credible in system design interviews at streaming companies. These are the actual command-line knobs that implement the architecture choices described in this chapter.
- **HLS specification (RFC 8216):** The m3u8 playlist format is formally specified. Understanding `#EXT-X-TARGETDURATION`, `#EXT-X-MEDIA-SEQUENCE`, `#EXT-X-DISCONTINUITY` (used when a stream reconnects with a gap), and `#EXT-X-ENDLIST` (marks VOD vs live) gives you precise language for interviewer questions about "how does the player know it's watching live vs. replay?"

---

## Quick Reference: Codec and Container Facts

| Codec | Container | Browser Support | Bitrate Savings vs H.264 |
|-------|-----------|-----------------|--------------------------|
| H.264 (AVC) | MPEG-TS, fMP4 | All browsers, all devices | Baseline |
| H.265 (HEVC) | fMP4 | Safari + hardware decode only | ~50% smaller at same quality |
| AV1 | WebM, fMP4 | Chrome, Firefox (slow encode) | ~30% smaller than HEVC |
| VP9 | WebM | Chrome, Firefox | ~30% smaller than H.264 |

**For live streaming in 2024:** H.264 in MPEG-TS segments is the universal baseline. Add H.265 for iOS Safari viewers (they get better quality at same bandwidth). AV1 is not yet viable for live encoding (too slow for real-time GPU encode at scale).

---

## Viewer Analytics — Measuring Stream Health From the Client Side

### What to Instrument

Client-side telemetry is the most important signal in a live streaming system. The CDN and transcoder appear healthy, but the viewer experience can still be poor if the player is rebuffering constantly or the quality is oscillating. Collect these metrics from every player:

**Rebuffer ratio:** `total_rebuffer_time_ms / total_watch_time_ms`. Healthy streams: < 0.5%. Alert threshold: > 2%. A rebuffer ratio of 5% means the viewer spent 3 minutes of a 60-minute stream staring at the loading spinner — a significant quality degradation.

**Startup time:** time from user clicking "play" to the first frame rendered. Target p50: < 1,500ms, p99: < 5,000ms. High startup time indicates the player had trouble fetching the first segment (CDN miss or high origin latency).

**Bitrate switches per hour:** how often the player's ABR algorithm changes quality levels. Target: < 5 switches/hour. High switch rate indicates unstable user network — the player is oscillating between quality levels. If all users in a region show high switch rates simultaneously, it's likely a CDN edge issue, not individual user networks.

**Exit before 30 seconds:** what percentage of viewers leave within the first 30 seconds. High rate indicates a problem with stream discovery, content mismatch, or a first-segment loading failure that triggered immediate abandonment.

### Pipeline for Client Telemetry at Scale

```
Player (every 60 seconds) → POST /analytics/player_heartbeat
  body: { stream_id, viewer_id, rebuffer_ms, watch_ms, current_quality, 
          startup_time_ms, switches_in_last_60s }

Backend:
  1. API Gateway → Kafka topic "player_telemetry" (partitioned by stream_id)
  2. Flink job consumes Kafka, aggregates per-stream per-minute:
     - avg_rebuffer_ratio = SUM(rebuffer_ms) / SUM(watch_ms)
     - viewer_count = COUNT(DISTINCT viewer_id)
     - quality_distribution = GROUP BY current_quality
  3. Results written to TimescaleDB (time-series DB)
  4. Grafana dashboard: real-time stream health per stream_id
  5. Alert: if avg_rebuffer_ratio > 2% for stream_id for 5 consecutive minutes → PagerDuty
```

This pipeline handles: 2M viewers × 1 heartbeat/60 sec = 33,333 events/sec → a Kafka cluster with 3 partitions per stream handles this trivially. The aggregation (Flink) reduces the raw event stream to one row per stream per minute in TimescaleDB, making dashboards fast (query 1 row, not 2M rows, to get the current state of a stream).

---

## Quick Reference: HLS Playlist Anatomy

Every viewer's player polls the m3u8 playlist to know what segments to download next. Understanding the m3u8 format is often tested in streaming interviews:

```m3u8
#EXTM3U
#EXT-X-VERSION:3
#EXT-X-TARGETDURATION:2          ← max segment duration in seconds (player uses for poll interval)
#EXT-X-MEDIA-SEQUENCE:1441       ← sequence number of the first segment listed (rolling window)

#EXTINF:2.000,                   ← this segment is 2.000 seconds long
https://cdn.example.com/live/S123/segment_1441_1080p.ts

#EXTINF:2.000,
https://cdn.example.com/live/S123/segment_1442_1080p.ts

#EXTINF:2.000,
https://cdn.example.com/live/S123/segment_1443_1080p.ts

#EXTINF:2.000,
https://cdn.example.com/live/S123/segment_1444_1080p.ts

#EXTINF:2.000,
https://cdn.example.com/live/S123/segment_1445_1080p.ts
```

**Key fields to know:**
- `EXT-X-MEDIA-SEQUENCE`: tells the player which segments were removed from the rolling window. Player infers that segment_1440 was removed since the last poll — it won't try to re-download it.
- `EXT-X-TARGETDURATION`: player polls the playlist at this interval (2 seconds). The playlist must be updated at least this frequently.
- No `EXT-X-ENDLIST`: the absence of this tag tells the player the stream is live. If it appears, the stream is complete and the player stops polling.
- `EXT-X-DISCONTINUITY`: appears before the first segment after a stream reconnect (where timestamps reset). Tells the player to reset its decoder state — without this, the player might try to decode segments with mismatched timestamps and produce garbage frames.

**Master playlist vs. media playlist:** the HLS manifest structure has two levels. The master playlist (`index.m3u8`) lists all available quality variants with their bandwidth, resolution, and codec. Each variant points to a media playlist (`1080p.m3u8`, `720p.m3u8`, etc.) which lists the actual segments. The player fetches the master playlist once, chooses a variant based on available bandwidth, then polls the media playlist for that variant. On an ABR quality switch, the player changes which media playlist it polls — not the master playlist. This two-level structure allows adding new quality variants (e.g., a 4K tier) without changing the URL the player was given at startup.

**Segment URL stability:** segment URLs should be permanent and never change content. A URL like `.../segment_1441_1080p.ts` always serves the same bytes. If you need to update a segment (e.g., to censor content), create a new URL and update the m3u8 to point to it. Do not overwrite the original URL's content — CDN caches across the world may have already cached the original bytes and will serve stale content to viewers for hours.

**Byte range requests for partial segment download:** HTTP supports `Range: bytes=0-99999` headers for downloading only part of a file. Players can use this to start playback before a full segment downloads — important for large segments (e.g., 6-second segments at 6 Mbps = 4.5 MB). For 2-second segments at 6 Mbps (1.5 MB), byte-range requests are less critical. LL-HLS relies on byte-range requests for partial segment streaming: each 200ms partial segment is a byte range within the final 2-second segment file.

**CDN Vary header caution:** do not set `Vary: Accept-Encoding` on HLS segment responses. If a CDN varies its cache by encoding, it may cache separate copies for gzip and no-gzip, halving the effective cache capacity. HLS segments are already compressed video — gzip compression adds no benefit and doubles cache entries. Set `Cache-Control: public, max-age=31536000, immutable` on segments (they never change content) and `Cache-Control: public, max-age=2` on m3u8 playlists (they update every 2 seconds).

**CORS headers for browser-based players:** if the HLS player runs in a browser (JavaScript-based, using Media Source Extensions), the segment responses must include `Access-Control-Allow-Origin: *` (or the specific player origin). Without CORS headers, the browser blocks the XHR/fetch request for segments from a CDN domain different from the player's page domain. Native players (iOS, Android, smart TVs) are not subject to CORS restrictions and can download segments from any URL without special headers. This is a subtle but common bug in first-time live streaming deployments where the CDN is configured but CORS is forgotten.

**Audio-only playlist for low-bandwidth fallback:** add a fifth quality tier to the ABR ladder that serves audio-only (no video): `#EXT-X-STREAM-INF:BANDWIDTH=128000,CODECS="mp4a.40.2"`. When a viewer's bandwidth drops below ~200 Kbps (throttled mobile, deep subway), the ABR algorithm switches to the audio-only tier. The viewer continues to follow the stream via audio (important for music streams, podcast-style streams, sports commentary) rather than buffering on the lowest video quality. This adds one audio-only transcode track — trivial CPU cost — but dramatically improves retention for mobile viewers on poor connections. Configure the ABR player to switch to audio-only only when bandwidth estimate drops below 180 Kbps (not 200 Kbps) to add a 20 Kbps hysteresis buffer — preventing oscillation between the lowest video tier (360p at ~200 Kbps) and audio-only when bandwidth is right at the threshold.

**I-frame only playlist for fast seeking in VOD replay:** HLS supports an `EXT-X-I-FRAMES-ONLY` playlist variant that contains only the I-frames (keyframes) from each segment. When a viewer scrubs rapidly through a recorded stream's timeline, the player downloads only I-frames — one every 2 seconds of content (one per segment) — rather than full segments. This reduces bandwidth during scrubbing from ~6 Mbps (full 1080p) to ~200 Kbps (I-frames only at ~5 KB each × 30 frames/sec of scrub speed). The I-frame playlist is generated as a post-processing step after the stream ends (during VOD creation) — it's not needed for live streaming, only for VOD replay of recorded streams.

---

## Interview Simulation — Live Streaming (Twitch/YouTube Live)

*45-minute system design interview. Phases follow the Section 2 framework: Requirements → Estimation → API → Data Model → HLD + Deep Dive.*

### Phase 1: Requirements (8 min)

> **Interviewer:** Design a live streaming platform like Twitch.

**Candidate:** A few clarifications. First: what is the target end-to-end latency? Standard HLS gives 5-10 seconds, Low-Latency HLS gets to 2-3 seconds, WebRTC can go below 500ms. These three choices produce completely different architectures — especially on the CDN and transcoding side.

> **Interviewer:** Standard latency, around 5-10 seconds is fine.

**Candidate:** Second: is the chat system in scope, or just the video pipeline?

> **Interviewer:** Video pipeline only. Assume chat is handled elsewhere.

**Candidate:** Third: do we need stream recording and replay after the stream ends?

> **Interviewer:** Yes, VOD replay should be available within 5 minutes of the stream ending.

**Candidate:** Scope: RTMP ingest, GPU transcoding to HLS, CDN distribution, up to 500K concurrent viewers per stream, up to 100K active streams globally, recording to S3 with VOD available 5 minutes after stream end, standard ~5-10 second end-to-end latency.

Core use cases — P0: streamer goes live and viewers can watch within 10 seconds of stream start; adaptive bitrate so viewers on different connections get the best quality they can handle; streamer disconnects and viewers see "stream offline" within 5 seconds. P1: replay available within 5 minutes of stream end; follower notification "streamer went live"; thumbnail updated every 30 seconds.

*(Cross-question: "What is the difference between CDN pull and CDN push?" — this should come up organically, and getting it right before being asked is an L5 signal.)*

**Candidate:** The key architectural constraint I want to flag upfront: live streaming cannot use the standard CDN pull model. VOD works with pull — the first viewer in Tokyo triggers a CDN cache miss, the CDN fetches from S3, and subsequent viewers get a cache hit. For live streaming, the first viewer in Tokyo requests a segment that doesn't exist yet in S3 or at the CDN edge — the transcoder is creating it right now. Pull causes a race between viewer request and segment creation. Live streaming requires CDN push: the transcoder pushes each completed segment to all CDN edge nodes before any viewer requests it.

---

### Phase 2: Estimation (4 min)

**Candidate:** 100,000 active streams. Average ingest: 6 Mbps per stream (1080p60 from OBS) = 100K × 6 Mbps = 600 Gbps total ingest. Transcoding output: 4 quality levels per stream summing to ~11.3 Mbps → 100K × 11.3 Mbps = 1.13 Tbps transcoded.

CDN delivery: 10M concurrent viewers globally, average quality 3 Mbps = 30 Tbps delivery bandwidth. That is the cost-dominant number. At $0.004/GB negotiated CDN pricing: 30 Tbps × 3600s × $0.000000004/bit = ~$430K/hour at peak.

Transcoding compute: 1 GPU (NVIDIA A100) encodes 3-4 streams at 1080p. 100K streams / 3 = ~33,000 GPUs. At $2/hour: $66K/hour. GPU cost and CDN bandwidth together are why Twitch charges subscription fees.

Segment math: 2-second segments at 6 Mbps = 1.5 MB per segment. At 1,800 segments/hour per stream and 4 quality levels: ~15 GB per stream per 3-hour session. 100K streams × 15 GB = 1.5 PB written to S3 per day. Storage is the third major cost center.

---

### Phase 3: API Design (4 min)

**Candidate:** Five endpoints.

`POST /v1/streams` — streamer starts a stream. Returns stream_id, rtmp_url, and a per-stream stream_key (HMAC-signed, expires on stream end). Per-stream keys prevent the permanent credential leak risk of static keys stored in OBS settings.

`GET /v1/streams/{stream_id}/playback` — viewer fetches the CDN URL for the HLS master playlist. Returns hls_url pointing to the CDN edge, qualities array, and viewer_count (HyperLogLog estimate, ±0.81% error). The master playlist is the entry point — the player reads it once to discover all quality-level URLs.

`DELETE /v1/streams/{stream_id}` — streamer ends the stream. Triggers VOD processing pipeline (segment stitching + `#EXT-X-ENDLIST` appended to m3u8). Returns duration_seconds and peak_viewers.

`GET /v1/channels/live?category=gaming&limit=50&cursor=token` — browse live streams, sorted by viewer_count DESC. Cursor-based pagination (not offset) because the list is sorted by a constantly-changing metric — offset-based pagination would skip or repeat channels as viewer counts shift. 30-second CDN cache TTL on this response.

`POST /v1/ingest/{stream_id}/heartbeat` — internal endpoint called by the transcoder after each segment. Payload: segment_seq, segment_url. The Ingest Coordinator uses this to detect dropped segments (sequence gaps) and trigger failover.

> **Interviewer:** Why is viewer_count a HyperLogLog estimate rather than an exact count?

**Candidate:** Exact concurrent viewer counting would require an entry in a data store for every viewer, updated on every connection event and heartbeat. At 10M concurrent viewers that is a write-heavy table under continuous churn. HyperLogLog uses a probabilistic sketch of ~12 KB to estimate cardinality with at most 0.81% error. At 2M viewers the error is at most ~16,000 — the UI rounds to "2.1M" anyway. The tradeoff is negligible display error in exchange for constant-space O(1) updates instead of a growing table requiring range scans.

---

### Phase 4: Data Model (4 min)

**Candidate:** Four tables.

`streams`: stream_id UUID PK, channel_id, title, status (STARTING/LIVE/ENDED/ERROR), rtmp_ingest_url, hls_base_url (CDN path, set once encoding starts), started_at, ended_at, peak_viewers. Partial index `WHERE status = 'LIVE'` for the discovery query — keeps the index small (100K live rows vs millions of historical rows).

`channels`: channel_id UUID PK, owner_user_id, name, stream_key_hash (bcrypt hash, raw key never stored), subscriber_count.

`vods`: vod_id UUID PK, stream_id FK, channel_id, duration_seconds, hls_url (points to VOD CDN path), status (PROCESSING/READY/DELETED). Separate from streams because VOD has different lifecycle properties and write patterns — the streams table would accumulate 5+ nullable columns if VOD fields lived there.

`stream_viewer_snapshots`: (stream_id, sampled_at) PK, viewer_count. Written by a background job every 30 seconds that reads the HyperLogLog from Redis. This is the analytics audit log for "how did viewer count evolve over this stream" — not used for real-time display.

`stream_key_hash` stores bcrypt hash only. On ingest authentication, the server receives the raw key over RTMP, hashes it, compares against stored hash. Same pattern as password authentication — raw credential never persisted.

---

### Phase 5: HLD + Deep Dive (15 min)

**Candidate:**

```
[Streamer / OBS]
  RTMP (TCP, port 1935)
        |
        v
+--------------------+
| INGEST SERVER      |
| (nearest PoP via   |
|  geo-DNS routing)  |
| - auth stream key  |
| - relay to GPU     |
+--------------------+
        |
        | (private backbone: 20-50ms London -> EU-West GPU cluster)
        v
+--------------------+       +----------+
| TRANSCODING        |       | S3       |
| CLUSTER (GPU)      |------>| segment  |
|                    |       | recording|
| 1080p -> seg_N.ts  |       +----------+
| 720p  -> seg_N.ts  |
| 480p  -> seg_N.ts  |
| 360p  -> seg_N.ts  |
| + m3u8 playlist    |
+--------------------+
        |
        | HTTP PUT (async, decoupled)
        v
+--------------------+
| CDN ORIGIN         |
| distributes to     |
| all 100+ edge PoPs |
+--------------------+
        |
        | HTTP GET (segments + m3u8)
        v
[Viewer App / Browser / Smart TV]
  HLS Player (polls m3u8 every 2s, downloads segments from nearest CDN edge)

+------------------+   +------------------+
| METADATA SVC     |   | NOTIFICATION SVC |
| title, status    |   | "went live" push |
| viewer count     |   | to followers     |
| thumbnail URL    |   +------------------+
+------------------+
```

Ingest path: OBS connects to nearest RTMP ingest PoP (geo-DNS routes to lowest-latency PoP). PoP authenticates stream key (bcrypt comparison against stored hash), then relays raw RTMP via private backbone to a GPU transcoding worker assigned by the load balancer. The transcoder decodes the H.264 stream, GPU-encodes 4 quality levels simultaneously (NVIDIA NVENC, one A100 handles 3-4 streams), packages into 2-second MPEG-TS segments, and pushes each completed segment to CDN origin asynchronously — the CDN push is decoupled from the transcoding pipeline so CDN slowness does not stall encoding.

> **Interviewer:** Why must CDN push be asynchronous and decoupled from the transcoder?

**Candidate:** In the Twitch 2015 cascade failure, synchronous CDN push stalled the transcoding pipeline. The transcoder waited for an HTTP PUT acknowledgment before starting the next segment. When a major tournament created a CDN origin spike (latency went from 50ms to 8 seconds), the transcoder was blocked — stream latency grew to 60+ seconds for 800K viewers. The fix: transcoder writes segments to S3 and immediately starts encoding the next segment. A separate CDN push agent reads from S3 and pushes to CDN independently, with its own retry queue. Backpressure in the CDN tier cannot propagate backward into the encoding pipeline.

> **Interviewer:** Walk me through the viewer latency budget.

**Candidate:** From real-world event to viewer eyes, the stages are: camera capture + OBS keyframe buffering (~2 seconds — OBS does not send video until it has a complete keyframe interval); RTMP upload to nearest ingest PoP (~50ms on a good connection); relay to transcoder cluster (~50ms via private backbone); transcoding 2 seconds of video into a segment (~100-200ms on GPU, but the transcoder buffers 2 seconds of content first — so this stage adds the 2-second segment duration); CDN push from origin to edge nodes (~200-500ms); player pre-buffering 2-3 segments before playback starts (~4-6 seconds). Total: ~9-10 seconds for standard HLS.

Reducing latency: cut keyframe interval to 1 second (saves 1s, higher CPU); cut segment duration to 1 second (CDN requests 2× more often); cut player buffer to 2 segments (slightly higher buffering risk on poor connections). Optimized: ~4.7 seconds, within the 5-second target. LL-HLS uses 200ms partial segments and HTTP/2 server push to get to 2-3 seconds; WebRTC via SFU topology gets below 500ms for interactive events.

> **Interviewer:** What happens when a streamer disconnects unexpectedly?

**Candidate:** RTMP keepalive: server sends a ping every 30 seconds; if no pong within 5 seconds, connection is declared dead. TCP: if no data for 60 seconds, TCP layer detects disconnect. Transcoder detects no frames for 3 seconds → marks stream disconnected → stops producing segments. Critically, the transcoder does NOT add `#EXT-X-ENDLIST` immediately — it waits 60 seconds to allow fast reconnects. During those 60 seconds, the m3u8 playlist stops updating. The viewer's player polls every 2 seconds, sees no new segments, and its buffer drains. After ~4-6 seconds of no new segments, playback stalls. The platform shows "Stream is experiencing issues." If reconnect occurs within 60 seconds: transcoder resumes from the next segment number, segments have a sequence gap (e.g., seg_1452 then seg_1465), the player skips the gap. If no reconnect after 60 seconds: `#EXT-X-ENDLIST` is added, viewer sees "Stream ended," VOD processing begins.

---

### Common Cross-Questions and Strong Answers

**Q: How does the ABR (Adaptive Bitrate) player decide which quality to download?**

The player maintains a download speed estimate based on how fast recent segments arrived. If it downloaded a 720p segment (750 KB) in 200ms, the estimated bandwidth is 3 Mbps. If the segment took 500ms, bandwidth is 1.2 Mbps. The ABR algorithm (BOLA, MPC, or Throughput-Based) compares the estimated bandwidth against the bitrate ladder and picks the highest quality whose bitrate is below, say, 80% of the estimated bandwidth (leaving a safety margin). Hysteresis prevents thrashing: switching up requires bandwidth to exceed the target quality's bitrate for 3 consecutive segments; switching down happens immediately on a miss. The player uses the master playlist to discover the quality ladder and polls each quality's media playlist independently once selected.

**Q: Why use RTMP for ingest if it is an old protocol (originally from 2002)?**

RTMP has two durable advantages: it is TCP-based (reliable, ordered delivery — important for video where a dropped frame destroys every subsequent frame in a GOP), and it is the native output protocol of every major streaming tool including OBS (500M+ installs), Streamlabs, Wirecast, and all hardware encoders. Replacing RTMP with SRT or WebRTC would require all streamers to update their tools. SRT (Secure Reliable Transport) is UDP-based with application-layer loss recovery — better for high-packet-loss networks (remote locations, satellite). Twitch, YouTube, and Facebook all support both RTMP and SRT on the ingest side, with RTMP as the default and SRT as the professional option.

**Q: How do you handle a viral event where viewer count spikes from 50K to 1M in 5 minutes?**

Three mechanisms work together. CDN load balancing distributes viewers across multiple PoPs in the affected region — no single PoP is the single point of failure. CDN caching means the spike is felt primarily as more cache hits (all viewers in a region download the same segment from the same CDN edge, which cached it on the first request). For truly massive events (1M+ in one region), contact the CDN in advance: "this event starts at 9 PM, expect 1M viewers in US-East" — the CDN can pre-position segments at additional edge nodes and reserve capacity. For L6 depth: P2P mesh overlay (WebTorrent-style), where each viewer serves segments to 2-3 nearby viewers, can reduce CDN origin bandwidth by 30-50% for very large events.

**Q: What is the I-frame only playlist and when would you generate it?**

An I-frame only playlist (`#EXT-X-I-FRAMES-ONLY` in HLS) contains only the I-frames (keyframes) extracted from each segment — one I-frame per 2-second segment, or one per keyframe interval. When a VOD viewer scrubs the timeline (dragging the playhead rapidly), the player downloads this playlist and fetches I-frames only, reducing scrubbing bandwidth from ~6 Mbps (full segments) to ~200 Kbps (I-frames at ~5 KB each). The I-frame only playlist is generated as a post-processing step during VOD creation, after the stream ends — it requires the complete segment files and is not useful during live streaming (you cannot scrub a live stream). Generating it during live would be wasted work.
