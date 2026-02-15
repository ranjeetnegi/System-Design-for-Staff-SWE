# Scope Creep in Interviews: How to Avoid

## Video Length: ~4-5 minutes | Level: Staff

---

## The Hook (20-30 seconds)

You're painting one room. "While we're at it, let's paint the hallway. And fix the bathroom tiles. And reorganize the kitchen." Before you know it, you're renovating the entire house and have finished NOTHING. In a system design interview: you have 45 minutes. If you try to design everything in detail, you design nothing well. Scope creep is the enemy. The interviewer mentions "notifications AND analytics AND recommendations." You try to design all three in depth. You run out of time. No depth anywhere. The fix: explicitly scope. Out loud. "For this 45 minutes, I'll focus on the core. I'll touch on the rest at a high level." Control the scope. Or it will control you.

---

## The Story

Imagine a restaurant. One chef. One hour. The customer says: "I'd like a five-course meal. Appetizer, soup, salad, main course, dessert." The chef has two choices. Try to make all five in one hour. Result: five mediocre dishes. Or: make one dish exceptionally well. A main course that's memorable. Maybe add a simple salad. Result: one great experience. In an interview, you're the chef. Time is fixed. Scope is negotiable. The interviewer might mention five features. Your job: pick the CORE. Go deep. Mention the rest. Don't go deep on everything. Depth over breadth. Always.

---

## Another Way to See It

Think of an exam. Ten questions. Two hours. You could spend 12 minutes on each. Or you could identify the three high-value questions. Spend 30 minutes on those. Do them perfectly. Glance at the rest. In system design, the "high-value" part is usually the core flow. The main use case. The thing that makes the system what it is. A ride-sharing app: matching riders to drivers. That's the core. Pricing algorithm? Secondary. ETA prediction? Secondary. Design the core first. If time remains, touch on the rest. Don't start with pricing. Don't start with analytics. Start with the heart.

---

## Connecting to Software

**The trap.** The interviewer says: "Design a ride-sharing app." Your brain goes: riders, drivers, matching, pricing, ETA, payments, ratings, notifications, maps. You want to show you've thought of everything. So you sketch all of it. Shallow. You spend 5 minutes on matching. 5 on pricing. 5 on payments. 5 on notifications. Nothing has depth. The interviewer probes matching. You have nothing. You've spread yourself thin. That's scope creep. The interview becomes a shallow tour. No depth. No pass.

**The fix.** Explicitly scope. In the first 2 minutes, say: "For this 45 minutes, I'll focus on the core flow: driver-rider matching. I'll touch on payments and notifications at a high level but won't go deep unless we have time." You've set expectations. The interviewer can agree or redirect. Either way, you've controlled the scope. Now you can go deep on matching. Draw the flow. Discuss scaling. Discuss failure modes. When the interviewer asks "what about payments?" you say: "High level—we'd integrate with a payment provider, store transactions. I can go deeper if you'd like." You've signaled: I know it exists. I'm prioritizing. You're in control.

**Phrases to use.** "I'll park that for now and come back if time permits." "That's a great follow-up—let me note it and prioritize the core system first." "For depth, I'll focus on X. We can touch on Y and Z at a high level." "What's the most important part you'd like me to focus on?" (Let them prioritize.)

**Identify the core.** For every system, there's a core. URL shortener: create short URL, redirect. Chat: send message, receive message. Ride-sharing: match rider to driver. News feed: get personalized feed. Design the core first. Everything else supports it. Don't let supporting features steal time from the core.

---

## Let's Walk Through the Diagram

```
SCOPE CREEP vs CONTROLLED SCOPE
┌─────────────────────────────────────────────────────────────────┐
│                                                                  │
│   SCOPE CREEP (45 min, everything)                               │
│                                                                  │
│   Matching ██  Pricing ██  Payments ██  Notifications ██  ...   │
│   Shallow. Shallow. Shallow. Shallow. No depth anywhere.         │
│                                                                  │
│   CONTROLLED SCOPE (45 min, core first)                          │
│                                                                  │
│   Matching ████████████████████  (Deep)                          │
│   Payments ████  (High level)                                     │
│   Rest: parked for later                                         │
│                                                                  │
│   DEPTH OVER BREADTH                                             │
│                                                                  │
│   "I'll focus on X. I'll touch on Y at high level."               │
│   Say it. Mean it.                                                │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

Narrate it: Left: everything shallow. Right: core deep, rest high-level. The diagram shows the trade-off. You have fixed time. Choose depth. State your scope. The interviewer will respect it. They want to see depth. They can always ask you to expand. But they can't add depth to a shallow design. You control that.

---

## Real-World Examples (2-3)

**Ride-sharing.** Core: matching. "I'll design the matching system—how we take a ride request, find nearby drivers, assign. I'll touch on pricing and ETA at a high level." You go deep on matching. Geospatial indexes. Real-time updates. Capacity. When they ask about pricing: "We'd have a pricing service that calculates based on distance, demand. Integration point here. I can elaborate if needed." You've shown awareness. You've stayed focused.

**E-commerce checkout.** Core: cart to order. "I'll focus on the checkout flow—cart, inventory check, payment, order creation. I'll mention recommendations and analytics but won't design them." You design the critical path. Atomicity. Idempotency. Failure handling. Recommendations? "We'd call a recommendation service. Cached. Non-blocking. I can go deeper if time permits." You've scoped.

**Social media feed.** Core: feed generation and delivery. "I'll focus on how we generate and deliver the feed—fanout, ranking, delivery. I'll touch on notifications—probably a push from the same events." You go deep on feed. Push vs pull. Caching. Scale. Notifications? "We'd have a notification service that subscribes to feed events. Fanout to devices. High level." Scoped.

---

## Let's Think Together

**"You're designing a ride-sharing app. Interviewer asks about pricing algorithm, driver matching, ETA prediction, payment, rating system. How do you scope?"**

Say out loud: "That's a lot. For this session, I'll prioritize. The core of ride-sharing is matching—connecting a rider to a driver. I'll go deep there. For pricing, ETA, payment, ratings—I'll outline how they fit in but won't design each in detail. Which one would you like me to focus on after matching?" You've (1) acknowledged the full scope, (2) stated your priority, (3) invited them to redirect. Often they'll say "matching is fine" or "let's do payments after." You've controlled the flow. You haven't tried to do everything. You've shown judgment. That's Staff-level time management.

---

## What Could Go Wrong? (Mini Disaster Story)

A candidate was asked to design a food delivery app. They started with the restaurant catalog. Then menu display. Then ordering. Then delivery tracking. Then payment. Then reviews. Then recommendations. They sketched boxes for 30 minutes. Every system was a single box. "Here's the order service. Here's the delivery service." The interviewer said: "Let's go deeper on the order flow. What happens when a user clicks Place Order?" The candidate had nothing. They'd drawn a box. They hadn't thought through the flow. Inventory check? Payment? Idempotency? They hadn't gone deep anywhere. They'd scope-crept across the entire problem. Result: no depth. No pass. The fix: pick one flow. The order flow. Go step by step. Draw the sequence. Discuss failure. Discuss scale. 20 minutes on that. Then you have something. Scope creep kills. Control it.

---

## Surprising Truth / Fun Fact

Interviewers often throw in extra requirements to see if you'll chase them. "What about internationalization?" "What about dark mode?" "What about offline support?" They're testing: will you try to do everything? Or will you prioritize? The best answer is often: "Good point. I'll add that to the high-level design. For depth, let me focus on the core flow first." You've acknowledged. You haven't been distracted. You've stayed focused. That's a signal. Interviewers want to see that you can manage scope. In real projects, scope creep is constant. Showing you can resist it in an interview is a strong signal for how you'd behave on the job.

---

## Quick Recap (5 bullets)

- **Scope creep kills.** 45 minutes on everything = depth nowhere.
- **Explicitly scope:** "I'll focus on X. I'll touch on Y at high level."
- **Phrases:** "I'll park that." "Let me prioritize the core first." "What would you like me to focus on?"
- **Identify the core:** The main use case. Design that first.
- **Depth over breadth.** One thing well beats five things shallow.

---

## One-Liner to Remember

**In 45 minutes, design one thing deeply—scope creep is designing everything shallowly; control the scope or it controls you.**

---

## Next Video

Next: drawing and explaining in 2 minutes. The superpower of quick, clear diagrams. Practice makes speed.
