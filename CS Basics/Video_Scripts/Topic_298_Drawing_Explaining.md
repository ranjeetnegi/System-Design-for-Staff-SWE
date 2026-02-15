# Drawing and Explaining in 2 Minutes

## Video Length: ~4-5 minutes | Level: Staff

---

## The Hook (20-30 seconds)

An elevator pitch. You have 60 seconds to explain your business to an investor. No slides. No whiteboard. Just words. In a system design interview: you often need to sketch a system and explain it in 2 minutes. The interviewer wants to see if you can quickly make sense of complexity. Can you draw a clear diagram? Can you narrate it so they follow? The ability to quickly draw clear diagrams and explain them concisely is a SUPERPOWER. It's not talent. It's practice. And structure.

---

## The Story

Imagine you're at a party. Someone asks: "What do you do?" You have 10 seconds before they drift away. You don't give a 5-minute lecture. You give one crisp sentence. "I build systems that process payments for millions of users." Clear. Memorable. In an interview, when you draw a system, you're doing the same. You're making the complex simple. In 2 minutes. User goes here. Request goes there. Data flows here. Done. If you can do that, you've shown you can communicate. That's half the interview. Technical depth matters. But if you can't explain your design in 2 minutes, the depth never gets a chance to shine.

---

## Another Way to See It

Think of a map. A good map doesn't show every street. It shows the main roads. The landmarks. You can find your way in 10 seconds. A bad map shows everything. Cluttered. Confusing. Your diagram is a map. It should guide the interviewer through your system in 2 minutes. Not every detail. The structure. The flow. The key components. If they can follow, you've won. If they're lost, you've lost them before the deep dive.

---

## Connecting to Software

**Tips for fast, clear diagrams.** Start top-down. User at the top. Then load balancer. Then services. Then databases. Data flows down. Add arrows. Label everything. Don't assume they'll guess. "LB" could mean load balancer. Write "Load Balancer." Clarity over shorthand.

**Keep it simple.** Boxes for services. Cylinders for databases. Arrows for communication. Clouds for external services. That's the standard language. Interviewers read it instantly. No need for fancy shapes. Consistency matters.

**Narrate as you draw.** Don't draw in silence. Talk. "User hits our API through a load balancer. The request goes to the order service. Order service writes to the database and pushes an event to Kafka for notifications." You're building the story while you build the diagram. The interviewer hears and sees together. They stay with you.

**What to include in 2 minutes.** The core path. User → entry point → main service → data store. Dependencies. "Order service calls user service and payment service." That's it. Don't add monitoring, caching, retries in the first 2 minutes. Add them when you go deep. The 2-minute version is the skeleton. The rest is flesh.

**What to skip.** Implementation details. Specific technologies (unless asked). Edge cases. Failure modes. Those come after. The 2-minute version answers: "What are the main pieces? How does data flow?" Nothing more.

---

## Let's Walk Through the Diagram

```
2-MINUTE URL SHORTENER DIAGRAM
┌─────────────────────────────────────────────────────────────────┐
│                                                                  │
│        [User]                                                    │
│          │                                                       │
│          ▼                                                       │
│   [Load Balancer]                                                │
│          │                                                       │
│          ▼                                                       │
│   [API Service] ◄──► [Database] (short URL → long URL)          │
│          │                                                       │
│          │  Redirect flow: GET short URL → lookup → 302 redirect │
│          │  Create flow: POST long URL → generate short → store  │
│                                                                  │
│   Narrate: "User submits long URL. Service generates short ID,   │
│   stores in DB. On redirect, we lookup and send 302. Simple."   │
│                                                                  │
│   IN 2 MIN: Core flow. Boxes. Arrows. Labels. Done.              │
│   LATER: Scale, cache, collisions, analytics.                    │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

Narrate it: User at top. Request flows down. Load balancer, service, database. Arrows show flow. Labels show what each does. That's the 2-minute version. You can add caching, sharding, id generation when they ask. Start simple. Build from there. The diagram is your outline. The narration is your guide.

---

## Real-World Examples (2-3)

**URL shortener, 2 minutes.** "User submits a long URL. Request hits our API service. We generate a short code—base62 of an auto-increment ID or hash. We store the mapping in the database. When someone visits the short URL, we lookup, return a 302 redirect. That's the core." Diagram: User → LB → Service → DB. Three components. Two flows. Clear.

**Chat system, 2 minutes.** "Users connect via WebSocket to our chat service. Messages go to the service. We persist to a database and push to other connected users. For offline users, we'd have a message queue. Core: client, WebSocket server, database, optional queue." Diagram: Clients → WS Service → DB. Arrow to "other clients." Simple.

**News feed, 2 minutes.** "User requests feed. We have a fanout service. When you post, we push to your followers' feed caches. When you read, we pull from your cache. Pre-computed. Core: post service, fanout, feed cache, read service." Diagram: User → Post → Fanout → Cache. User → Read → Cache. Two flows. Clear.

---

## Let's Think Together

**"Draw and explain a URL shortener in 2 minutes. What do you include? What do you skip?"**

Include: User, API (or load balancer), service, database. Two flows: create (long→short) and redirect (short→long). Say: "Create: we generate a short code, store the mapping. Redirect: we lookup, return 302." That's 90 seconds. Skip: how we generate the ID (base62, hash, etc.), collision handling, caching, analytics, scaling. Those are follow-ups. If they ask, you answer. The 2-minute version is the architecture. The rest is implementation. Practice: set a timer. Draw. Narrate. Can you do it in 2 minutes? If not, simplify. Reduce components. One sentence per component. Speed comes from structure.

---

## What Could Go Wrong? (Mini Disaster Story)

A candidate was asked to design a ride-sharing system. They started drawing. Box after box. "Here's the rider app. Here's the driver app. Here's the matching service. Here's the pricing service. Here's the payment service. Here's the notification service. Here's the map service." 15 boxes. No arrows. No narration. The interviewer said: "Walk me through a ride request." The candidate pointed at boxes. "Well, the rider... goes to... the matching... and then..." They couldn't trace the flow. They'd drawn a heap. Not a system. The diagram had no structure. No clear path. The fix: before drawing, identify the core flow. One path. Rider requests → matching → driver assigned → ride. Draw THAT first. Three or four boxes. Arrows. Narrate. Then add supporting services. Structure before detail. The 2-minute version is a path. Not a pile.

---

## Surprising Truth / Fun Fact

Architects at Amazon practice "working backwards." They write the press release first. Then they work back to the design. The press release forces clarity: "Users can do X. It works by Y." In a diagram, the equivalent is: "Data flows from A to B to C." If you can state the flow in one sentence, you can draw it. The sentence comes first. The diagram illustrates it. Try it: before drawing, say the one-sentence flow. Then draw. It's faster. And clearer.

---

## Quick Recap (5 bullets)

- **Start top-down.** User → LB → Services → DB. Arrows for flow.
- **Keep it simple.** Boxes, cylinders, arrows. Standard notation.
- **Narrate as you draw.** Don't draw in silence. Build the story.
- **2 minutes = skeleton.** Core path only. Add detail when they ask.
- **Practice with a timer.** Can you do it in 2 minutes? Simplify until you can.

---

## One-Liner to Remember

**A 2-minute diagram is a map—main roads, key landmarks; narrate as you draw so they follow.**

---

## Next Video

Next: the end of the interview. The last 2 minutes leave the strongest impression. What to say. What not to say.
