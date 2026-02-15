# News Feed: Backpressure and Load Shedding

## Video Length: ~4-5 minutes | Level: Staff

---

## The Hook (20-30 seconds)

World Cup final. Everyone tweets at the same time. 500K tweets per second instead of the usual 50K. The fan-out pipeline can't keep up. Queue grows. Memory fills. Options: (1) Let it crash. Bad. (2) Slow down ingestion—backpressure. Better. (3) Drop non-critical fan-outs—load shedding. Best. "Sorry, your tweet's fan-out is delayed by 30 seconds" is better than "Twitter is down." Let's see how.

---

## The Story

Normal day: 50K tweets/sec. Fan-out pipeline handles it. Queue depth: steady. Then: goal. Penalty. Viral moment. 500K tweets/sec. 10x spike. The pipeline processes 100K/sec. Queue grows. 400K/sec excess. In 10 seconds: 4 million tweets in the queue. Memory? Disk? How much do you have? At some point: OOM. Crash. Nobody gets anything. Total failure.

The alternative: backpressure. Downstream says "I'm full. Slow down." Upstream stops accepting. Or: load shedding. "We'll fan-out to active users first. Inactive users? Delayed." Or: "We'll skip fan-out to users who haven't logged in for 30 days." Drop the work that matters least. Keep the system up. Degraded is better than dead. Staff engineers design for this. "What do we drop when we must?" Answer before the crisis.

---

## Another Way to See It

A buffet during rush hour. Too many people. Line out the door. Option 1: Keep letting people in. Kitchen can't keep up. Everyone waits. Food runs out. Chaos. Option 2: Slow the line. "One person every 30 seconds." Backpressure. Option 3: Serve full plates to premium guests first. Others get smaller portions. Load shedding. The buffet stays open. Nobody gets everything. Everyone gets something. Same for systems. When demand exceeds capacity, you must choose what to protect. Plan it. Don't improvise during the flood.

---

## Connecting to Software

**Backpressure.** Downstream signals upstream to slow down. Queue has max size. When full: reject. Or: apply backpressure to the producer. "Wait before sending more." Kafka: consumer lag. If lag grows, producers slow. Or: API returns 503. "Try again later." Client retries. With backoff. The key: the system communicates "I'm overwhelmed." Upstream responds. Without backpressure, producers keep pushing. Queue explodes. cascade failure.

**Load shedding.** Drop low-priority work. Fan-out to inactive users? Skip. Or delay. Fan-out to power users? Priority. Criteria: last active, engagement score, tier. "Free users get delayed feed. Premium gets real-time." Or: "Users who haven't opened the app in 7 days—skip their fan-out." The work is still in the queue. But we process it last. Or never if the queue never drains. Harsh? Yes. But it keeps the system up. Document it. Users may not notice. Inactive users rarely check. Active users get the experience. Fair? Debatable. Survivable? Yes.

**Graceful degradation.** Show stale feed with "Updating..." instead of error page. "Your feed is a few minutes behind. We're catching up." Better than 503. Users understand delays. They don't understand "something went wrong." Psychologically, delay is acceptable. Failure is not. Design for degradation. Have a "degraded mode" that still works. Slower. Stale. But works.

---

## Let's Walk Through the Diagram

```BACKPRESSURE AND LOAD SHEDDING
┌─────────────────────────────────────────────────────────────────┐
│                                                                  │
|   INGESTION (500K/sec)     QUEUE (max 1M)     FAN-OUT (100K/sec) |
│                                                                  │
|   Tweets --> [Gate] --> [====Queue====] --> [Workers] --> Feeds  |
|                |              |                   |              |
|           Backpressure    FULL?              Load Shed:        |
|           Close gate     Reject new         Priority order     |
|                |              |                   |              |
|           Slow producers  Return 503        Active users first  |
|                           "Try later"       Inactive: skip      |
│                                                                  │
|   Key: Communicate overload. Drop low-value work. Stay up.       |
│                                                                  │
└─────────────────────────────────────────────────────────────────┘```

Narrate it: Tweets pour in. Queue fills. Backpressure: close the gate. Reject or slow. Load shedding: process high-priority first. Active users. Premium. Inactive? Skip. Queue drains. System survives. The diagram shows the flow. The decision: what is high priority? Define it. Implement it. Test it. Before the spike. Not during.

---

## Real-World Examples (2-3)

**Twitter.** Spike during events. They've built for it. Backpressure. Load shedding. Stale feeds with "show more" to catch up. They've been through elections, World Cups, viral moments. The system holds. Most of the time. When it doesn't, they learn. Iterate.

**Facebook.** Similar. Feed pipeline has priority lanes. Hot content first. Long-tail later. They've published on it. The infrastructure is battle-tested. Scale teaches hard lessons. They learned.

**Uber.** Surge pricing is a form of load shedding. "Too many requests? Raise price. Reduce demand." Economic backpressure. Same idea. Different lever. Creative systems use many tools.

---

## Let's Think Together

**"Feed pipeline is 10 min behind. Should you prioritize catching up or serving current requests?"**

Serve current. New requests get fresh merge: old feed + latest from pull path. Catching up: process backlog. If you prioritize backlog, new requests wait. User opens app. Blank. "Loading." 10 seconds. Terrible. Better: serve new requests with "feed is delayed" notice. Process backlog in background. User sees something. Backlog drains eventually. Prioritize user-facing latency. Backlog is internal. Users care about "when I open the app, what do I see?" See something. Quickly. Even if stale. Then update. Catching up is secondary. Current experience is primary. Always.

---

## What Could Go Wrong? (Mini Disaster Story)

A company has no load shedding. Queue grows. They add more workers. Queue grows faster. They add more. Infinite loop. More workers = more reads from queue = more downstream pressure. Database overloads. Everything slows. The fix: cap queue size. Reject when full. Backpressure at the source. "We're at capacity. Please retry." Better than slow death. They learned the hard way. One midnight. Three hours of outage. Postmortem: "We needed backpressure." Add it before you need it. Not after.

---

## Surprising Truth / Fun Fact

Some systems use "circuit breakers" as backpressure. Downstream failing? Open circuit. Stop sending. Let it recover. Closed circuit: resume. The breaker is a signal. "I'm unhealthy. Don't send more." Same idea as backpressure. Different implementation. Netflix popularized it. Now it's standard. Resilience patterns are reusable. Learn them. Apply them. Your system will thank you.

---

## Quick Recap (5 bullets)

- **Backpressure:** Downstream signals "slow down." Queue full = reject or throttle. Prevent cascade failure.
- **Load shedding:** Drop low-priority work. Active users first. Inactive: skip or delay.
- **Graceful degradation:** Stale feed with "Updating..." beats error page. Users accept delay.
- **Prioritize current requests over backlog.** User opens app = serve something. Fast. Backlog can wait.
- **Plan before the spike.** Define priority. Implement. Test. Don't improvise at 3 AM.

---

## One-Liner to Remember

**Backpressure says slow down. Load shedding says drop the rest. Together they keep the system up when the world goes viral.**

---

## Next Video

Next: real-time collaboration. Google Docs. Two people typing at once. How do you merge without conflicts? CRDTs. Operational transformation.
