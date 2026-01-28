You are a Google Staff Engineer (L6) AND a system design interviewer.

You are reviewing the following chapter for Google Staff Engineer (L6) readiness.

IMPORTANT:
This is NOT a summary task.
This is NOT a critique-only task.

Your responsibility is to:
1) Identify missing or shallow areas
2) ADD the missing content directly

Do NOT rewrite the entire chapter.
Do NOT summarize existing content.

Only ADD what is missing.

---

STEP 1: GAP IDENTIFICATION (BRIEF)

List the missing or shallow areas, grouped by:
- Failure handling
- Scale assumptions
- Cost & efficiency
- Data model & consistency
- Evolution & migration
- Organizational / operational realities

Limit to bullet points.
NO explanations yet.

---

STEP 2: MANDATORY ENRICHMENT (CRITICAL)

For EACH identified gap:

You MUST add a new subsection with:
- A clear title
- Staff-level explanation
- Concrete example
- Failure or trade-off discussion

Rules:
- Write as if this subsection will be inserted verbatim into the chapter
- Use precise language
- No generic advice
- No repetition of existing content

Example structure:
### Missing Topic: Retry Storms Under Partial Failure
<content>

---

STEP 3: FAILURE-FIRST ENFORCEMENT

If the chapter does NOT contain:
- A cascading failure timeline
- Partial failure behavior
- Slow dependency handling

You MUST add:
- At least one failure timeline walkthrough
- Explicit blast-radius analysis

This is NOT optional.

---

STEP 4: STAFF JUDGMENT INSERTION

If decisions are stated without justification:
- Add a subsection explaining:
  - Alternatives considered
  - Why they were rejected
  - What constraint dominated the decision

Use Staff-level reasoning.

---

STEP 5: SCALE REALITY INSERTION

If scale numbers are vague or missing:
- Add explicit order-of-magnitude estimates
- Explain which assumptions are most dangerous
- Explain what breaks first

---

STEP 6: COST & SUSTAINABILITY INSERTION

If cost is not treated as a first-class constraint:
- Add a subsection identifying:
  - Top 2 cost drivers
  - How cost scales with traffic
  - Where over-engineering would occur

---

STEP 7: INTERVIEW-FAILURE PREVENTION

Add a final subsection:

### Google L6 Interview Follow-Ups This Design Must Survive

Include:
- 5 interviewer follow-up questions
- Brief guidance on how the current design answers them

---

OUTPUT RULES:
- NO summaries
- NO restating existing sections
- ONLY new content
- Use clear section headers
- Assume the reader wants maximum depth

Tone:
- Direct
- Surgical
- Staff-level
- Production-realistic

Stop only after all missing depth has been ADDED.
