# TCP vs UDP: When to Use Which?

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

You need to send a message to your friend. Two options. Option one: Registered post. You hand it to the post office. They track it. They confirm delivery. If it gets lost, they resend it. You get a receipt. Slow. But reliable. Option two: You shout across the playground. Fast. Instant. But did they hear you? Maybe. Maybe not. No confirmation. No retries. Which do you choose when every byte matters? Which when speed beats perfection?

---

## The Story

Two friends. Same school. Different classrooms. They need to communicate.

Method one: Registered post. One writes a letter. Hands it to the post office. The post office logs it. Tracks it. Delivers it. The recipient signs. The sender gets a receipt. If the letter is lost, the post office tries again. Every letter arrives. In order. Reliable. But it takes time. Logging. Tracking. Signing. Confirming.

Method two: Shout across the playground. "Meet me at 3!" Instant. No forms. No tracking. But the playground is loud. Maybe the friend heard. Maybe they didn't. Maybe they heard "Meet me at 4." No way to know. No retry. No confirmation. Fast. Unreliable.

That's TCP vs UDP in a nutshell. TCP is the registered post. UDP is the shout. One guarantees delivery. The other prioritizes speed and accepts that some messages might be lost. Both run on the internet. Both are crucial. The choice depends on what you're building. TCP adds overhead — acknowledgments, retransmissions, flow control. That overhead ensures nothing is lost. UDP adds almost nothing. Just a header. Send and forget. For file transfers, you need TCP. For real-time media, UDP's lightness wins. Let that sink in — sometimes reliability is the enemy of speed.

---

## Another Way to See It

TCP is like a phone call. You dial. You connect. "Hello?" "Hi!" Now you talk. Everything arrives in order. If a word gets lost, the connection retransmits it. You hang up when done. UDP is like throwing paper airplanes across a room. You throw. Some land. Some don't. No order guarantee. No "did you get that?" You just keep throwing. TCP has flow control — it slows down if the receiver is overwhelmed. UDP has no such mechanism. It just fires. That simplicity is UDP's strength and its weakness.

---

## Connecting to Software

**TCP (Transmission Control Protocol):** Connection-based. Reliable. Ordered. Your browser uses it for HTTP. Your email uses it. File transfers use it. Anything where every byte must arrive, in order, without loss.

**UDP (User Datagram Protocol):** Connectionless. No guarantees. No retransmission. Used for video streaming, gaming, voice calls, DNS. Speed matters. A dropped frame? Barely noticeable. A 100ms retransmit? Unacceptable.

---

## Let's Walk Through the Diagram

```
  TCP — The Three-Way Handshake:
  
  CLIENT                              SERVER
     |                                   |
     |  SYN "Can we talk?"               |
     |---------------------------------->|
     |                                   |
     |  SYN-ACK "Yes, let's!"            |
     |<----------------------------------|
     |                                   |
     |  ACK "Great, starting now."       |
     |---------------------------------->|
     |                                   |
     |  [Connection established. Data flows. Ordered. Reliable.]  |
     |<=================================>|
     |                                   |


  UDP — No Handshake:
  
  CLIENT                              SERVER
     |                                   |
     |  Data. (No "hello." No confirmation.)
     |---------------------------------->|
     |  More data.                       |
     |---------------------------------->|
     |  (Maybe it arrived. Maybe not. No one says.)  |
```

**When to choose:** Need every packet? Use TCP. Need low latency and can tolerate loss? Use UDP. File download? TCP. Live sports stream? UDP. Email? TCP. Online game? UDP. The rule of thumb: perfection vs speed. What matters more for your use case?

---

## Real-World Examples (2-3)

**1. Websites (TCP):** You load a page. Every HTML tag, every image byte must arrive. Missing one piece breaks the page. TCP delivers.

**2. Video streaming (UDP):** Netflix, YouTube Live. A dropped frame? You might not notice. A 200ms retransmit? Video freezes. UDP wins.

**3. Online gaming (UDP):** A packet with your position is lost. The next packet has the new position. Old one doesn't matter. Speed over perfection. Games like Fortnite and League of Legends use UDP-based protocols. A 50ms lag can mean life or death in a duel.

---

## Let's Think Together

**Question:** You're building a live video streaming app. TCP or UDP? Why?

**Pause. Think about it...**

**Answer:** UDP. Live video is real-time. If a packet is lost, retransmitting it is useless — by the time it arrives, the moment has passed. The next frame corrects the picture anyway. You want low latency. UDP gives you that. TCP would wait, retransmit, and add lag. Viewers would see stutter. UDP accepts some packet loss for the sake of speed. TCP's three-way handshake alone adds a round trip before any data flows. For live streaming, that initial delay matters. UDP sends immediately.

---

## What Could Go Wrong? (Mini Disaster Story)

You build a voice chat app. You use TCP. Seems safe. Reliable. Every packet arrives. But then — network hiccup. One packet drops. TCP notices. It asks for a retransmit. The sender resends. That packet arrives 100ms late. Your audio buffer waits. Then plays it. The user hears: "...hello... — — — can you hear me?" Laggy. Choppy. Annoying. With UDP, you'd drop that packet. The next one would have newer audio. User might hear a tiny glitch. But no 100ms pause. For real-time, TCP's reliability can hurt more than it helps.

---

## Surprising Truth / Fun Fact

**QUIC** — used by Google and the basis of HTTP/3 — combines the best of both. It runs over UDP. But it adds its own reliability and ordering on top. So you get UDP's speed and flexibility, with TCP-like guarantees where needed. The future of web traffic is QUIC. The old rules are evolving. And here's something else: TCP headers are at least 20 bytes. UDP headers are 8 bytes. For small payloads like DNS queries, that overhead matters. DNS uses UDP for a reason — speed and simplicity.

---

## Quick Recap (5 bullets)

- TCP: reliable, ordered, connection-based. Like registered post.
- UDP: fast, connectionless, no guarantees. Like shouting.
- Use TCP for: websites, email, file transfers, APIs — when every byte matters.
- Use UDP for: video, gaming, voice, DNS — when speed beats perfection.
- QUIC (HTTP/3) runs on UDP but adds reliability — a hybrid approach.

---

## One-Liner to Remember

> **TCP: slow but sure. UDP: fast but forgettable.**

---

## Next Video

Data flows. But where does it land? A server has one IP. It runs a web server, a database, a cache. How does a single machine handle so many different services? There are doors. Ports. And something called a socket. Next: What is a socket?
