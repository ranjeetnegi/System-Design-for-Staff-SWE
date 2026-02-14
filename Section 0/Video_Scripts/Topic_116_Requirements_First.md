# Requirements First: Why Clarify Before Designing

## Video Length: ~4-5 minutes | Level: Beginner

---

## The Hook (20-30 seconds)

A client says: "Build me a vehicle." You nod. You build a car. Four wheels. Engine. Seats. You deliver it. The client stares. "I wanted a boat." You assumed. You never asked. Months wasted. Money burned. Relationship damaged. In system design, if you start drawing boxes before understanding WHAT to build, you'll build the wrong thing. Every time. The interviewer WANTS you to ask questions. It shows maturity. Jumping to solutions? That's a junior mistake. Let me show you what to ask—and why it matters.

---

## The Story

Imagine the vehicle conversation. The client says "vehicle." You could build a car. A boat. A bicycle. A helicopter. Until you ask, you're guessing. So you ask. "Where will you use it? Land, water, air?" "How many passengers?" "What's your budget?" "Do you need to carry cargo?" Each answer narrows the space. Boat. For fishing. Four people. $50K. Now you know what to build. Requirements first. Design second. Build third.

Before you design any software system, you must understand the problem. Who are the users? What features do they need? How many users? What's the latency budget? What can we NOT compromise on? These aren't optional. They're the foundation. Get them wrong, and your entire design is wrong. A chat app for 100 friends is different from a chat app for 1 billion. A search engine that must return in 50ms is different from one that can take 2 seconds. Requirements shape architecture. No requirements? You're building in the dark. You're building a car when they wanted a boat. The interviewer is testing you. Do you explore? Or do you assume? Senior engineers ask. "What's the scale?" "What's the read-to-write ratio?" "Do we need real-time?" Junior engineers dive into "we'll use Redis" without knowing if Redis is even needed. Ask first. Design second. Always.

---

## Another Way to See It

Think of a tailor. Customer says "I need clothes." The tailor doesn't cut fabric. They ask. Formal or casual? For work or wedding? What size? What color? One wrong assumption—you make a tuxedo when they wanted shorts—and the whole thing is useless. Measure twice. Cut once. Requirements are the measurement.

Or a wedding planner. "I want a wedding." Great. When? How many guests? Indoor or outdoor? Budget? Theme? Catering preferences? Allergies? The plan depends on the answers. A 50-person garden wedding is different from a 500-person ballroom wedding. Same "wedding." Different everything. Requirements first. Plan second. Execute third. In software, same story. "Design a notification system." For whom? Email? SMS? Push? How many per day? Latency? Each answer changes the design. Ask. Always ask.

---

## Connecting to Software

There are two types of requirements. **Functional**: WHAT the system does. Features. Use cases. "User can send a message." "User can search products." "User can add to cart." These are the actions. The capabilities. **Non-functional**: HOW WELL it does them. Speed. Scale. Reliability. "Response time under 100ms." "99.9% availability." "Handle 1M users." These are the constraints. The quality attributes. Both matter. A system that has all the features but crashes at 10K users is useless. A system that's fast but missing critical features is useless. You need to clarify both. The functional tells you what to build. The non-functional tells you how to build it. Ask about both before you draw a single box. Preview the next video: we'll go deep on functional vs. non-functional. For now, know that both exist. Both shape the design. Both must be clarified.

---

## Let's Walk Through the Diagram

```
    WRONG ORDER                          RIGHT ORDER

    "Design a chat app"                  "Design a chat app"
              │                                    │
              │  Jump to: "We'll use               │  Ask: Who are users?
              │  WebSockets and Kafka"             │  How many? 1-on-1 or group?
              │                                    │  Real-time or eventual?
              ▼                                    ▼
         Wrong design                      Clear requirements
         (maybe Kafka is overkill)         "1-on-1, 100M users, real-time"
         (maybe WebSockets unnecessary)              │
                                                     ▼
                                              Now design
                                              (WebSockets + queues? Maybe.)
```

Clarify first. The design follows from the requirements. Not the other way around. Wrong order = wrong build. Right order = right build.

---

## Real-World Examples (2-3)

**Example 1: Uber.** "Design a ride-sharing app." Requirements matter. Real-time location? Yes. Payment at trip end? Yes. Surge pricing? Yes. Scale? Millions of concurrent users. Each requirement shapes the design. Real-time → WebSockets or similar. Scale → distributed systems, caching. Ask. Get the answers. Then design.

**Example 2: Twitter.** "Design a timeline." Requirements: Who follows whom? Chronological or algorithmic? How many tweets per user? How many followers? A user with 50M followers changes everything. The design for 100 followers is trivial. For 50M? Different problem. Different architecture. Same feature. Different requirements. Different design.

**Example 3: Netflix.** "Design video streaming." Requirements: Live or on-demand? Quality levels? Global? Offline viewing? Each answer changes the architecture. Live = different pipeline. Global = CDN strategy. Requirements drive design. No requirements = random design.

---

## Let's Think Together

Design a chat app. List 5 clarifying questions you'd ask before drawing anything.

Here are examples—and there are more. (1) Is it 1-on-1 only, or group chats too? (2) How many users? 1K or 1B? (3) Real-time delivery or is "within 5 seconds" okay? (4) Do we need message history? For how long? (5) Do we need read receipts? Typing indicators? Online status? (6) Media sharing? (7) End-to-end encryption? (8) Mobile only or web too? Each answer narrows the design space. Group chats need different storage. 1B users need sharding. Real-time needs WebSockets or long polling. History affects retention and storage. Features affect complexity. The more you ask, the better your design. Ask. Always ask.

---

## What Could Go Wrong? (Mini Disaster Story)

A team gets the spec: "Build a notification system." They assume email and push. They design it. Six months of work. Launch. The product manager asks: "Where are SMS notifications?" The team: "We didn't know you wanted SMS." PM: "It was in the original doc." Team: "We never read it. We started designing." The system wasn't built for SMS. Adding it means rearchitecting. Another six months. Delayed launch. Angry stakeholders. The lesson: requirements aren't a formality. They're the contract. Clarify. Document. Confirm. Before you draw a single box. Read the doc. Ask the questions. Get sign-off. Then build.

---

## Surprising Truth / Fun Fact

At Amazon, they write a "press release" before building a product. What would the press say when it launches? That forces clarity. Who is it for? What problem does it solve? What's the one thing that makes it great? Requirements in disguise. If you can't write the press release, you don't understand the product. Same for system design: if you can't state the requirements, you don't understand the system. The exercise forces you to clarify. Try it. Before your next design, write one paragraph: "When we launch, users will be able to..." If you can't, you're not ready to design.

---

## Quick Recap (5 bullets)

- **Always clarify before designing.** Who, what, how many, how fast, what can't we compromise?
- **Functional requirements** = WHAT the system does (features). **Non-functional** = HOW WELL (speed, scale, reliability).
- **Interviewers want you to ask.** It shows maturity. Jumping to solutions = junior mistake.
- **Requirements shape architecture.** Wrong requirements = wrong design. Every time.
- **State assumptions.** Document. Confirm. The contract before the build.

---

## One-Liner to Remember

**The client wanted a boat. You built a car. You never asked. Requirements first. Always.**

---

## Next Video

Next: **Functional vs. non-functional requirements.** A car that drives but crashes at 20 kmph. What's the difference? Let's break it down.
