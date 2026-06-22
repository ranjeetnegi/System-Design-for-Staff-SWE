# Chapter 81: Refactoring Large Systems

> TODO: Full chapter to be written.

---

## Planned Coverage

**Core thesis:** Refactoring a large system is not about rewriting it. It is about changing it incrementally while it runs, without ever having a "big bang" cutover that can fail catastrophically.

**Topics to cover:**

### Part 1: Why Big Rewrites Fail
- The second-system syndrome: rewrite accumulates all the features you forgot the first time
- Joel Spolsky's "Things You Should Never Do" — why Netscape's rewrite killed the company
- The cost of a rewrite: feature freeze, bug accumulation, knowledge loss
- When refactoring is the right answer vs when replacement is justified

### Part 2: The Seam-Based Approach
- Finding seams: places where you can change one side without affecting the other
- Characterization tests: test the existing behavior (even wrong behavior) before changing it
- The "scratch refactoring": explore the change without committing
- Mikado method: work backward from the goal to find the safe order of changes

### Part 3: Extracting Services from a Monolith
- Why to extract: team autonomy, independent scaling, technology choice
- Why not to extract prematurely: distributed systems are harder, not easier
- The extraction playbook: identify boundary → test the boundary → extract behind interface → deploy separately
- Domain-driven design as a guide for extraction boundaries
- Avoiding the "distributed monolith": extracted but still tightly coupled

### Part 4: Managing Technical Debt
- Technical debt is not always bad: sometimes it was the right tradeoff at the time
- The debt quadrant: deliberate vs reckless, prudent vs imprudent
- How to make the business case for paying down debt (in numbers, not feelings)
- The "boy scout rule": leave the code better than you found it
- When to prioritize debt over features: the productivity tax model

### Part 5: Safe Refactoring Techniques
- Extract method, extract class, introduce parameter object
- Replace conditional with polymorphism
- Strangler fig for code (not just services)
- Feature flags for code migration (old path and new path coexist, flag controls routing)
- Parallel implementation: run old and new, compare outputs, switch over

### Real Examples
- Martin Fowler's Refactoring book: key patterns
- How Basecamp refactored their monolith incrementally over 20 years
- Google's large-scale change tooling for refactoring across millions of lines

### Exercises
- Given a 500-line God class, identify the seams and design the extraction plan
- Write the characterization test suite for a function before refactoring it
- Design the feature-flag strategy for migrating from one data model to another

---

*Status: TODO — placeholder only*
