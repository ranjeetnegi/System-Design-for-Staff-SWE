# Run the Chapter Reviewer on Every Chapter

Use this runbook to run the **Google Staff Engineer (L6) Chapter Reviewer** prompt on each of the 57 chapters.

---

## How to run (in Cursor)

### One chapter at a time (recommended)

1. **Open Composer** (Cmd+I or Ctrl+I).
2. **Attach both:**
   - `REVIWER_PROMPT.md` (the full reviewer prompt)
   - The chapter file (e.g. `Section1/Chapter_1.md`)
3. **Send this message:**

   ```
   Run the Chapter Reviewer prompt in REVIWER_PROMPT.md on the attached chapter.
   Follow all steps (Master Review Check, Steps 1–11). Output the enriched chapter
   with all additions in place (or provide edits so I can apply them).
   ```

4. Apply the suggested edits or save the enriched chapter.
5. Mark the chapter done in the checklist below and repeat for the next chapter.

### Batch by section

- You can run the same flow once per chapter in a section (e.g. Section1: Chapter_1 through Chapter_6).
- Keep one Composer thread per chapter so you can revisit if needed.

---

## What the reviewer does

- Audits the chapter for L6 coverage (judgment, failure, scale, cost, consistency, security, observability, cross-team impact, etc.).
- Adds missing depth, real incidents, Staff vs Senior contrast, scale/cost, mental models, diagrams.
- Ensures Exercises + BRAINSTORMING at the end.
- Confirms Master Review Prompt Check passes.

---

## Chapter checklist (57 total)

Copy this into your notes and mark `[x]` when done.

### Section 1
- [ ] `Section1/Chapter_1.md`
- [ ] `Section1/Chapter_2.md`
- [ ] `Section1/Chapter_3.md`
- [ ] `Section1/Chapter_4.md`
- [ ] `Section1/Chapter_5.md`
- [ ] `Section1/Chapter_6.md`

### Section 2
- [ ] `Section2/Chapter_7.md`
- [ ] `Section2/Chapter_8.md`
- [ ] `Section2/Chapter_9.md`
- [ ] `Section2/Chapter_10.md`
- [ ] `Section2/Chapter_11.md`
- [ ] `Section2/Chapter_12.md`
- [ ] `Section2/Chapter_13.md`

### Section 3
- [ ] `Section3/Chapter_14.md`
- [ ] `Section3/Chapter_15.md`
- [ ] `Section3/Chapter_16.md`
- [ ] `Section3/Chapter_17.md`
- [ ] `Section3/Chapter_18.md`
- [ ] `Section3/Chapter_19.md`
- [ ] `Section3/Chapter_20.md`

### Section 4
- [ ] `Section4/Chapter_21.md`
- [ ] `Section4/Chapter_22.md`
- [ ] `Section4/Chapter_23.md`
- [ ] `Section4/Chapter_24.md`
- [ ] `Section4/Chapter_25.md`
- [ ] `Section4/Chapter_26.md`
- [ ] `Section4/Chapter_27.md`

### Section 5
- [ ] `Section5/Chapter_28.md`
- [ ] `Section5/Chapter_29.md`
- [ ] `Section5/Chapter_30.md`
- [ ] `Section5/Chapter_31.md`
- [ ] `Section5/Chapter_32.md`
- [ ] `Section5/Chapter_33.md`
- [ ] `Section5/Chapter_34.md`
- [ ] `Section5/Chapter_35.md`
- [ ] `Section5/Chapter_36.md`
- [ ] `Section5/Chapter_37.md`
- [ ] `Section5/Chapter_38.md`
- [ ] `Section5/Chapter_39.md`
- [ ] `Section5/Chapter_40.md`

### Section 6
- [ ] `Section6/Chapter_41.md`
- [ ] `Section6/Chapter_42.md`
- [ ] `Section6/Chapter_43.md`
- [ ] `Section6/Chapter_44.md`
- [ ] `Section6/Chapter_45.md`
- [ ] `Section6/Chapter_46.md`
- [ ] `Section6/Chapter_47.md`
- [ ] `Section6/Chapter_48.md`
- [ ] `Section6/Chapter_49.md`
- [ ] `Section6/Chapter_50.md`
- [ ] `Section6/Chapter_51.md`
- [ ] `Section6/Chapter_52.md`
- [ ] `Section6/Chapter_53.md`
- [ ] `Section6/Chapter_54.md`
- [ ] `Section6/Chapter_55.md`
- [ ] `Section6/Chapter_56.md`
- [ ] `Section6/Chapter_57.md`

---

## List all chapter paths (for scripts or copy-paste)

From the repo root:

```bash
bash scripts/list_chapters.sh
```

This prints one path per line (Section1/Chapter_1.md through Section6/Chapter_57.md) in order.

---

## Tips

- **Backup:** Consider committing to git before running the reviewer on a chapter, or keep a copy of the original so you can diff.
- **Long chapters:** If a chapter is very long, the model may suggest edits in chunks; apply them in order.
- **Consistency:** Run the same prompt and instructions for every chapter so the style and depth stay consistent across the curriculum.
