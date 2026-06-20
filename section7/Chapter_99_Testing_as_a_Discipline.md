# Chapter 78: Testing as a Discipline

> TODO: Full chapter to be written.

---

## Planned Coverage

**Core thesis:** Testing is not about coverage numbers. It is about confidence. The question is not "how many tests do I have?" but "what would break silently without tests, and what would I catch immediately?"

**Topics to cover:**

### Part 1: The Testing Mindset
- What tests are actually for: confidence, documentation, regression prevention
- The difference between testing that code runs and testing that code is correct
- Why 100% coverage is a vanity metric (and what to measure instead)
- Intern → Staff: same feature, four levels of test strategy

### Part 2: The Test Pyramid
- Unit tests: fast, isolated, test one thing — when to write them and when not to
- Integration tests: test that components work together — the most underused layer
- End-to-end tests: expensive, slow, brittle — use sparingly and purposefully
- Contract tests: test that services agree on their interface
- The "ice cream cone" anti-pattern: too many E2E, too few unit tests

### Part 3: What to Test and What to Skip
- Test the behavior, not the implementation
- The "would this test catch a real bug?" filter
- Things that are not worth testing: getters/setters, framework behavior, logging
- Things always worth testing: business logic, edge cases, error paths, security boundaries
- The deletion test: if you deleted this test, would you feel nervous?

### Part 4: Test-Driven Development in Practice (Not Religion)
- TDD is a tool, not a religion — when it helps and when it doesn't
- Red-green-refactor in practice with a real example
- Test-driven debugging: write the failing test FIRST before fixing the bug
- When TDD is counterproductive (exploratory code, UI, data pipelines)

### Part 5: Load Testing and Performance Testing
- The difference between load testing, stress testing, and soak testing
- Writing a load test that actually represents real traffic (not just happy path)
- Tools: k6, Locust, Gatling, wrk
- What metrics to collect: p50, p95, p99, error rate, throughput
- How to set performance budgets in CI

### Part 6: Chaos Engineering
- What chaos engineering is: deliberately breaking things to find weaknesses
- The game day: designing and running one
- Starting small: chaos in staging before production
- Netflix's Chaos Monkey and what it actually tests
- What chaos engineering cannot test (design flaws, data model issues)

### Part 7: Testing in Distributed Systems
- Why unit tests miss distributed system bugs (they don't test concurrency or network)
- Integration tests with real dependencies vs mocks: when each is correct
- Testing failure modes: simulate timeouts, partial failures, network partitions
- Property-based testing for distributed invariants

### Real Examples
- Google: testing philosophy (hermetic tests, no shared state between tests)
- Netflix: chaos engineering program and what it found
- Example: a test suite that passes but misses the real bug (shown and diagnosed)

### Exercises
- Given a function, write unit tests that catch the 5 most common bugs
- Design the test strategy for a payment service (what levels, what to mock, what not to)
- Write a load test for a checkout API and interpret the results

---

*Status: TODO — placeholder only*
