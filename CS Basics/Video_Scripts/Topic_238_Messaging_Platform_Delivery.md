# Messaging Platform: Delivery and Presence

## Video Length: ~4-5 minutes | Level: Staff

---

## The Hook (20-30 seconds)

WhatsApp. You send "Happy Birthday!" to your friend. One gray tick (sent). Two gray ticks (delivered). Two blue ticks (read). Behind the scenes: message sent to server, server stores in DB, server pushes to recipient's device, device ACKs, server updates status, sender sees double tick. If recipient is offline—message stored, pushed when they reconnect. Simple to use. Complex to build. Let's see how.

---

## The Story

User sends a message. It must arrive. At least once. Ideally exactly once. The flow: client sends to server. Server persists. Server pushes to recipient. Recipient ACKs. Server updates delivery status. Sender sees "delivered." If recipient opens the app: read receipt. Blue ticks. The status pipeline: sent -> delivered -> read. Each step requires coordination. Server is the hub. Client never talks to client directly. Always through server. Offline? Message waits in DB. When recipient connects: server pushes. Bulk. "You have 15 messages." Client fetches. Marks delivered. Replies to server. Server updates sender. The sync protocol is critical. Message IDs. Deduplication. Ordering. Get it right or users lose messages. Trust is everything in messaging.

Presence: "Is she online?" Server tracks connections. WebSocket alive = online. Disconnect = offline. Grace period: 30 seconds. Don't flip to offline on a momentary blip. "Last seen 2 min ago." Privacy: users can hide last seen. Configurable. Presence is a feature. Users care. Build it in. Scale it. Millions of connections. Server tracks them all. Efficiently.

---

## Another Way to See It

Post office. You mail a letter. Post office receives. Stores. Tries to deliver. Recipient home? Letter delivered. Receipt. Recipient away? Letter held. When they return, delivery. You can track: "In transit." "Delivered." "Picked up." Same for messaging. Server is the post office. Messages are letters. Delivery status is tracking. Offline is "recipient away." Reconnect is "recipient returned." The metaphor holds. Persistence. Retry. Status. All there.

---

## Connecting to Software

**Delivery guarantees.** At-least-once. Retry until ACK. Message might arrive twice. Deduplication on recipient: message ID. "Already have msg_123? Ignore." Exactly-once is at-least-once + dedup. Design for idempotency. Same message ID = process once. Critical for messaging. Users expect "I sent it. They got it." Not "maybe." Guarantee it.

**Message flow.** Sender -> Server -> DB (persist) -> Recipient (push via WebSocket or push notification). Always persist first. Then push. If push fails, message is in DB. Sync will deliver. Never push without persist. Never. One bug. Lost messages. User trust gone. Flow is simple. The discipline is strict. Persist. Push. ACK. Update status. In that order.

**Offline handling.** Messages queue on server. Per recipient. When they connect: "Last message ID you have?" Recipient sends. Server: "Messages after that." Returns list. Bulk deliver. Client renders. Marks delivered. ACKs. Server updates senders. Sync protocol. Define it. Version it. Clients must implement it. Old clients: graceful degradation. New clients: full sync. Compatibility matters.

**Presence.** "Online/offline/last seen." WebSocket heartbeats. Ping every 30s. No ping for 90s? Disconnect. Mark offline. "Last seen" = last activity timestamp. Update on message send/receive. Privacy: user can hide. "Nobody" or "Contacts only." Server enforces. Presence is real-time. Push to contacts when someone comes online. "Sarah is online." Exciting for social apps. Implement it well.

---

## Let's Walk Through the Diagram

```MESSAGING - DELIVERY AND PRESENCE
┌─────────────────────────────────────────────────────────────────┐
│                                                                  │
|   SENDER              SERVER                 RECIPIENT           |
│                                                                  │
|   [Send msg] --> Persist DB --> Push (if online) --> [Receive]  |
|        |              |                  |              |        |
|        |              |              Offline?          |        |
|        |              |                  |              |        |
|        |              v                  v              |        |
|        |         [Queue for recipient]   Reconnect     |        |
|        |              |                  |              |        |
|        |              +-----------------> Sync ---------+        |
|        |              |                  |              |        |
|        <-- Status update (delivered/read) <-------------+        |
│                                                                  │
|   PRESENCE: WebSocket = online. Disconnect = offline. Heartbeat. |
|   DELIVERY: At-least-once. Dedup by msg ID. Persist before push. |
│                                                                  │
└─────────────────────────────────────────────────────────────────┘```

Narrate it: Sender sends. Server persists. Recipient online? Push. Offline? Queue. Reconnect? Sync. Bulk deliver. Status flows back. Delivered. Read. Presence: connection state. Heartbeats. Online. Offline. Last seen. The diagram shows the flow. The details: retries, ordering, idempotency. All matter. Build for production. Millions of messages. No lost. No duplicate. Users trust you. Honor it.

---

## Real-World Examples (2-3)

**WhatsApp.** Billions of users. E2E encryption. But delivery flow is the same. Persist. Push. Sync. Ticks. They scale it. The principles are universal. Encryption adds a layer. Delivery is foundational. They got it right.

**Slack.** Similar. Messages. Presence. Read receipts. Threads. Richer model. Same delivery guarantees. At-least-once. Dedup. Sync on reconnect. They've scaled to millions. The pattern works.

**Telegram.** Fast. Sync across devices. Messages persist. delivered. Read. Same architecture. Different polish. The core is identical. Learn it once. Apply everywhere.

---

## Let's Think Together

**"Group chat: 500 members. You send a message. How does the server deliver to 500 people efficiently?"**

Options. 1) Fan-out: For each member, push. 500 pushes. Per message. At 100 msg/sec = 50K pushes/sec. Doable. 2) Fan-out with batching: Don't push to each. Put message in each member's "mailbox" (queue or inbox). Workers push from mailboxes. Spread load. 3) Recipients pull: "Any new messages?" Poll or long poll. Less push load. More read load. 4) Hybrid: Online members get push. Offline: store in mailbox. On connect: sync. Most systems use fan-out to online + mailbox for offline. Scale: 500 is small. 50,000 member groups? Different. Shard. Partition. The principle: don't send 50K individual connections. Batch. Queue. Distribute. Efficient delivery is an engineering problem. Solve it. The math will guide you.

---

## What Could Go Wrong? (Mini Disaster Story)

A messaging app. No persistence. Push only. User A sends to B. B's phone is off. Message never stored. B turns on phone. No message. A: "Did you get it?" B: "No." Ghost message. User trust broken. "Your app loses messages." Fix: persist first. Always. Then push. Sync on reconnect. Every production messaging system does this. No exceptions. One shortcut. Thousands of lost messages. Support nightmare. Build it right. From day one.

---

## Surprising Truth / Fun Fact

WhatsApp's "last seen" was controversial. Users wanted to hide it. "I don't want people to know when I'm online." They added privacy settings. "Nobody." "Contacts only." "Everyone." Product decision. Technical implementation: server tracks. Client sends privacy preference. Server filters. "Can user X see user Y's last seen?" Logic in the server. Simple to describe. Complex at scale. Billions of user pairs. Cached. Optimized. The feature seems small. The engineering is not. Never underestimate "simple" features in messaging. They're rarely simple.

---

## Quick Recap (5 bullets)

- **Delivery:** At-least-once. Retry until ACK. Dedup by message ID on recipient.
- **Flow:** Sender -> Server -> Persist -> Push (or queue) -> Recipient -> ACK -> Status update.
- **Offline:** Message in DB. Sync on reconnect. Bulk deliver. Never lose a message.
- **Presence:** WebSocket = online. Heartbeats. Disconnect = offline. Last seen. Privacy options.
- **Group chat:** Fan-out to online. Mailbox for offline. Scale with batching and sharding.

---

## One-Liner to Remember

**Messaging is a post office—persist, push, retry until delivered. Presence is the front porch light—on when connected, off when not.**

---

## Next Video

Next: we've covered pipelines, queues, payments, gateways, chat, config, rate limiters, cache, feeds, collaboration, and messaging. What's next? Deep dives. Case studies. Staff-level trade-offs. The journey continues.
