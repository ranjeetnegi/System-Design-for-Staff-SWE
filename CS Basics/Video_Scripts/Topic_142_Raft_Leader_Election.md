# Raft: Leader Election (Simple)

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

Five students. No teacher. The bell rings. Someone must lead. A hand goes up. "I'll do it." Another. "Me too." Both want the job. The class votes. One gets two votes. The other gets two. No majority. Stalemate. They wait. Try again. This time, one student's hand goes up a split second earlier. Three votes. Done. Leader chosen. That's Raft leader election. Majority wins. Random timeouts prevent endless ties. One leader. Eventually. Let me show you how it works.

---

## The Story

**Raft** is a consensus algorithm designed to be understandable. Leader election is step one. Every node starts as a **Follower**. Passive. Waiting. Listening. If a follower doesn't hear from the leader for a while—a timeout—it becomes a **Candidate**. It raises its hand. "I want to be leader." It votes for itself. Sends vote requests to all other nodes. "Vote for me." Other nodes reply. Yes or no. If the candidate gets a **majority** of votes, it becomes the **Leader**. Done. The leader sends heartbeats. "I'm alive. I'm in charge." Followers reset their timers. As long as heartbeats arrive, no one else runs for leader.

**Election timeout:** Randomized. Typically 150–300 milliseconds. Why random? If all followers timeout at the same time, they all become candidates. Split vote. Nobody wins. Random timeouts spread them out. One usually times out first. Gets a head start. Wins before others even try. Simple. Effective.

---

## Another Way to See It

Think of a race. Five runners at the start. The gun fires. But each runner has a random delay before they can start. One runner gets the shortest delay. They bolt. Others are still waiting. By the time the second runner starts, the first might have already crossed the finish line. Random delays prevent a photo finish. Same in Raft. Random timeouts prevent everyone becoming a candidate at once. One node usually gets there first. Wins cleanly.

---

## Connecting to Software

**States:** **Follower** (default)—waits for heartbeats. **Candidate**—running for leader. Requesting votes. **Leader**—won. Sends heartbeats. Handles client requests. State machine. Simple.

**Heartbeats:** The leader sends periodic "I'm alive" messages. Empty log entries. Or explicit heartbeat RPCs. If followers don't receive one within the election timeout, they assume the leader is dead. New election. New term. New leader. Possibly.

**Split vote:** Two candidates. Neither gets majority. Term ends. No leader. All nodes bump to the next term. Random timeouts again. Retry. Eventually one candidate wins. The randomness ensures convergence. In practice, split votes are rare. Elections complete in one round most of the time.

**Term:** Each election attempt uses a new term number. Term 1. Term 2. Increments. When a node receives a message with a higher term, it steps down. Becomes follower. The higher term wins. Prevents old leaders from causing confusion. "I'm leader of term 5." "No, I'm leader of term 6." Term 6 wins. Clean handover.

---

## Let's Walk Through the Diagram

```
    RAFT LEADER ELECTION

    Normal: Leader sends heartbeats
    ┌────────┐     heartbeat      ┌────────┐ ┌────────┐
    │ Leader │ ─────────────────► │Follow 1│ │Follow 2│
    │        │ ◄── reset timer ── │        │ │        │
    └────────┘                    └────────┘ └────────┘

    Leader fails → Followers timeout → Election
    ┌────────┐                    ┌────────┐ ┌────────┐
    │ Leader │  X (crash)         │Follow 1│ │Follow 2│
    └────────┘                    │timeout!│ │        │
                                 │Candidate│
                                 │Request  │
                                 │Votes    │
                                 └────┬────┘
                                      │
                                      ▼
                                 Majority? → NEW LEADER
```

The diagram shows: heartbeats keep followers calm. No heartbeats → timeout → candidate → vote request → majority → leader. The loop is simple. The randomness makes it work.

---

## Real-World Examples (2-3)

**Example 1: etcd.** Kubernetes' brain. Uses Raft for leader election and log replication. Every cluster has one etcd leader. Elected via Raft. Cluster state flows through it.

**Example 2: Consul.** Service discovery and config. Raft under the hood. Leader handles writes. Followers replicate. Same pattern.

**Example 3: TiKV.** Distributed key-value store. Raft per region. Scale by adding regions. Each region has its own leader. Raft everywhere. Proven in production at massive scale.

---

## Let's Think Together

Five nodes. Leader crashes. Nodes 2 and 3 both timeout at the same time and become candidates. What happens?

They both request votes. Node 2 might get votes from 1 and 4. Node 3 might get votes from 5. Or vice versa. Neither gets 3 (majority of 5). Split vote. The term ends with no leader. All nodes increment term. They reset. Random timeouts again. Next round: one of them—say Node 2—times out slightly sooner. Gets votes from 1, 3, 4. Majority. Node 2 becomes leader. Node 3 stays follower. Done. The randomness in the next round breaks the tie. That's the design.

---

## What Could Go Wrong? (Mini Disaster Story)

A team set election timeout to 5 seconds. "Conservative. Stable." But their network had occasional 3-second delays. Heartbeats arrived late. Followers thought the leader was dead. Started elections. Leader was fine. Chaos. Multiple nodes thought they were leader. Split-brain. They shortened the timeout. But then false positives increased. The fix: tune timeouts to your network. Typical Raft: 150–300ms election timeout. Heartbeat every 50–100ms. Network RTT should be much smaller than timeout. Otherwise you get phantom elections. Know your network. Tune accordingly.

---

## Surprising Truth / Fun Fact

Raft was designed in 2014 by Diego Ongaro specifically to be understandable. His PhD thesis compared Paxos and Raft. Students learned Raft 50% faster. Same correctness. Clearer structure. "In Search of an Understandable Consensus Algorithm." The title says it all. Sometimes the best engineering is making the complex teachable. Raft succeeded. It's everywhere now.

---

## Quick Recap (5 bullets)

- **Raft leader election:** Follower → (timeout) → Candidate → (majority votes) → Leader.
- **Heartbeats:** Leader sends regularly. Followers reset timer. No heartbeat = assume dead = new election.
- **Election timeout:** Randomized (e.g. 150–300ms). Prevents simultaneous candidates. Split votes.
- **Split vote:** Two candidates, no majority. New term. Random timeouts. Retry. Eventually one wins.
- **Used by:** etcd, Consul, TiKV. The consensus algorithm you can actually explain.

---

## One-Liner to Remember

**Raft leader election: No teacher. Five students. One raises a hand. Majority votes. Random timeouts break ties. One leader. Simple.**

---

## Next Video

Next: **Raft Log Replication.** The leader has a whiteboard. Followers copy into notebooks. Same order. Same entries. When does an entry become "committed"? When can you trust it? The log that keeps everyone in sync. See you there.
