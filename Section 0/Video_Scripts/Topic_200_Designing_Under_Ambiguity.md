# Designing Under Ambiguity

## Video Length: ~4-5 minutes | Level: Staff

---

## The Hook (20-30 seconds)

"Design a payment system at scale." That's your interview prompt. Or maybe it's a real project brief. What scale? Which payments? How consistent? The requirements are vague. At L6, that's the default. You'll never get a clean spec. So how do you design anyway?

---

## The Story

You're a chef. The customer says: "Make me something delicious." No recipe. No ingredients listed. No dietary restrictions. What do you do? You ask. "Any allergies? Preference for meat or veg? Spicy or mild?" You make assumptions. "I'll assume you want something hearty." You cook. You present. You adjust based on feedback.

L6 system design is the same. "Build a system that handles payments at scale." *What* scale? *Which* payments? *How* consistent? You ask. You assume. You design. Ambiguity is the default. Your job is to create clarity through design.

In interviews, this is intentional. Interviewers leave the problem vague on purpose. They want to see how *you* structure the ambiguity. Do you jump straight to solutions? That reads junior. Do you ask questions, state assumptions, and frame the problem first? That reads L6. The ability to operate without a clear spec is a core Staff-level skill.

---

## Another Way to See It

Requirements at L6 are like a foggy road. You can't wait for the fog to clear—it won't. You drive slowly. You use your lights. You make reasonable assumptions and adjust as you see more. Clarity doesn't arrive. You *create* it.

---

## Connecting to Software

Ambiguity is the default at L6. Requirements are vague. Scope is undefined. Multiple valid approaches exist. How do you navigate?

(1) **Ask clarifying questions.** "What's the scale? What's the consistency requirement? Who are the users?" (2) **State assumptions out loud.** "I'll assume we need strong consistency for financial transactions." (3) **Start broad, narrow down.** Don't dive into one solution. Explore the space first. (4) **Make decisions and explain why.** "Given X, I'm choosing Y because Z." (5) **Revisit assumptions as you learn more.** Designs evolve.

The trap: waiting for clarity. Clarity never comes. You create it. Many engineers freeze when requirements are fuzzy. They want a spec. They want a ticket. At L6, you learn to move forward anyway. You make reasonable assumptions. You document them. You design. You iterate as you learn. The best designs often emerge from ambiguous problems—because you're forced to think, not just implement.

```
NAVIGATING AMBIGUITY
┌─────────────────────────────────────────────────────────┐
│  Vague prompt: "Design a notification system"            │
│                                                         │
│  Step 1: ASK     →  Scale? Latency? Ordering? Users?     │
│  Step 2: ASSUME  →  "I'll assume 10M DAU, <100ms..."     │
│  Step 3: DESIGN  →  Start broad. Multiple options.       │
│  Step 4: DECIDE  →  "Given X, I choose Y because Z."     │
│  Step 5: REVISE  →  As we learn more, adjust.            │
└─────────────────────────────────────────────────────────┘
```

---

## Let's Walk Through the Diagram

The diagram shows the flow. You get a vague prompt. You don't jump to solutions. First: ask. Then: state assumptions. Then: design with options. Then: decide with rationale. Finally: revisit as you learn. Interviewers *intentionally* leave problems vague. They want to see how you structure the ambiguity. Jumping to solutions = junior. Asking questions and framing the problem = L6.

Practice this: the next time you get a vague request, spend five minutes writing down your assumptions before you design anything. "I'm assuming scale is X. I'm assuming latency requirement is Y. I'm assuming we need consistency level Z." Those sentences transform ambiguity into a design space. You've created structure from chaos.

---

## Real-World Examples (2-3)

**Example 1: "Design a notification system."** First 5 questions? (1) What's the scale—notifications per second? (2) What channels—push, email, SMS, in-app? (3) Do we need ordering? (4) What's the latency requirement? (5) Who are the users—B2B or B2C? Each answer narrows the design space.

**Example 2: Real project.** "Our data pipeline is slow." Vague. L6 asks: Which stage? What's the current latency? What's the target? What's blocking us? They turn a complaint into a structured problem before designing. The questions themselves add value—they often reveal that the problem isn't where people assumed. Maybe the bottleneck is upstream. Maybe the SLA is wrong. Questions before solutions. Always.

**Example 3: Interview.** "Design URL shortener." Junior jumps to base62, database, done. L6 asks: What's the scale? Read vs write ratio? Do we need analytics? TTL? Custom slugs? They frame the problem first.

---

## Let's Think Together

"'Design a notification system.' What are the first 5 questions you'd ask?"

(1) Scale—how many notifications per second? (2) Channels—push, email, SMS, in-app? (3) Ordering—do we need strict ordering per user? (4) Latency—real-time or batch acceptable? (5) Users—internal, B2B, B2C? Each question reduces ambiguity and guides the design. Write your assumptions down so you can revisit them later.

The key is to ask *before* you design. Many engineers are eager to show their knowledge—they jump to solutions. L6 engineers resist that urge. They spend the first few minutes of any design session framing the problem. Only then do they start drawing boxes and arrows. The framing is as important as the solution.

---

## What Could Go Wrong? (Mini Disaster Story)

An engineer gets "build a search feature." They immediately design an Elasticsearch cluster. Complex. Expensive. Ships. Turns out the product needed simple keyword search on 10K records. PostgreSQL full-text search would have been fine. The disaster? No questions asked. No assumptions stated. They solved the wrong problem at the wrong scale. An L6 would have asked: "What's the data size? What queries do we need? What's the latency bar?" Before writing a single line of design.

---

## Surprising Truth / Fun Fact

At Stripe, engineers are taught to "run toward the ambiguity." The best projects are often the fuzzy ones—nobody has figured them out yet. If you wait for clarity, someone else will create it. And they'll own the solution.

---

## Quick Recap (5 bullets)

- **Ambiguity is the default at L6.** Requirements are vague. Scope is fuzzy.
- **Don't wait for clarity.** You create it through questions, assumptions, and design.
- **Process:** Ask → Assume → Design → Decide → Revise.
- **In interviews:** Vague on purpose. They want to see how YOU structure the problem.
- **Trap:** Jumping to solutions. L6 asks questions and frames first. Structure before substance.

---

## One-Liner to Remember

**You'll never get clean requirements. Ask. Assume. Design. Create clarity—don't wait for it.**

---

## Next Video

That wraps up our Staff-level mindset series. Check the playlist for more on system design at scale.
