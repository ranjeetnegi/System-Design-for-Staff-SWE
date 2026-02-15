# Raft: Log Replication (Simple)

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

The teacher writes on the whiteboard. "Step 1: Mix flour." Every student copies. "Step 2: Add water." They copy again. One student was absent for step 2. When they return, the teacher says: "Here's what you missed." The student fills the gap. Now every notebook matches the whiteboard. Exactly. Same order. Same content. That's Raft log replication. The leader appends. Followers copy. If someone falls behind, the leader resends. Everyone ends up with the same log. No exceptions. Let me show you how.

---

## The Story

**Log replication** is how Raft keeps all nodes consistent. The leader has a log—an ordered list of commands. When a client sends a request, the leader appends it to its log. Then sends the entry to all followers. "Here's the new entry. Add it." Followers append it. Reply with ACK. When a **majority** of nodes have the entry, the leader **commits** it. Committed = safe. Won't be lost. The leader applies it to its state machine. Tells the client: done. Followers eventually apply it too. Same order. Same result.

**Consistency:** All logs must match. Same entries. Same order. If a follower is behind—it has entries 1–7, leader has 1–10—the leader sends entries 8, 9, 10. The follower appends. Catches up. If a follower's entry conflicts—same index, different value—the leader overwrites. Leader is always right. Followers overwrite their conflicting entries with the leader's. One source of truth.

---

## Another Way to See It

Think of a recipe book. The head chef writes the recipes. Line cooks have copies. They must match. If a cook missed a page, the chef hands them the missing pages. The cook inserts them. No gaps. No wrong order. The chef's book is the authority. Cooks align to it. That's log replication. Leader = chef. Followers = cooks. Log = recipe book. Same idea. Kitchen scale.

---

## Connecting to Software

**Log structure:** Each entry has an index, a term, and a command. Index = position. Term = when the leader was elected. Command = the actual operation (e.g. "set x=5"). Ordered. Append-only. Never delete committed entries.

**Commit rule:** An entry is committed when the leader has replicated it to a majority. Why majority? So even if the leader crashes, the new leader (elected from the majority) has the entry. No data loss. Minority replication = risk. Majority = safety.

**Follower lag:** Leader sends AppendEntries RPC. Includes previous entry index and term. Follower checks: do I have that? If not, leader sends older entries. Log matching: follower accepts only if previous entry matches. Otherwise, leader decrements and retries. Eventually they sync.

**Log compaction:** Logs grow forever. Old entries applied to state machine. Safe to discard. Snapshot: leader takes snapshot of state at index X. Truncates log. Sends snapshot to lagging followers. They install it. Catch up faster than replaying every entry. etcd does this. Raft supports it. Production necessity.

---

## Let's Walk Through the Diagram

```
    RAFT LOG REPLICATION

    Leader log:     [1][2][3][4][5]
                        │
            ┌───────────┼───────────┐
            ▼           ▼           ▼
    Follower A    Follower B    Follower C
    [1][2][3]     [1][2][3][4][5] [1][2][3][4]
    [4][5] ✓      ✓               (needs 5)
    
    Leader sends missing entries to A and C.
    All converge to [1][2][3][4][5].
    
    Entry 5 committed when majority (Leader + B + one more) has it.
```

The diagram shows: leader has full log. Followers catch up. Leader pushes missing entries. Majority = commit. All logs converge. Simple flow. Complex edge cases (handled by the protocol).

---

## Real-World Examples (2-3)

**Example 1: etcd.** Kubernetes cluster state. Every config change goes through Raft. Create a pod? Raft log entry. Delete a deployment? Raft log entry. Commit = applied to cluster. etcd is Raft in action. You use it every time you kubectl apply.

**Example 2: Consul.** Service registration. Add a service? Log entry. Leader replicates. Majority commits. All Consul nodes see the new service. Same pattern.

**Example 3: TiKV.** Distributed transactions. Each key-range has a Raft group. Writes go to leader. Replicate. Commit. Scale by adding ranges. Raft per range. Log replication at the core.

---

## Let's Think Together

Leader has entries 1–10. Follower has 1–7. Leader sends 8, 9, 10. But the follower's entry 7 is different from the leader's. What happens?

The leader sends AppendEntries with prevLogIndex=7, prevLogTerm=X. Follower checks: do I have entry 7 with term X? No. Follower's entry 7 has a different term. Reject. Leader decrements. Sends prevLogIndex=6. Follower checks 6. Maybe matches. Leader sends entries 7, 8, 9, 10. Follower overwrites its entry 7 with the leader's. Then appends 8, 9, 10. Leader wins. Follower's wrong entry 7 is replaced. The leader always wins conflicts. Followers adopt the leader's log.

---

## What Could Go Wrong? (Mini Disaster Story)

A bug in a Raft implementation: the leader didn't check previous entry before appending. It just appended. Follower had a divergent entry at index 5. Leader sent 6, 7, 8. Follower appended. Now both had entries 1–8. But entry 5 was different on each. Inconsistent state. The system served wrong data. The fix: proper log matching. AppendEntries must verify previous entry. Reject on mismatch. Leader must retry with older entries. Raft paper spells it out. Implementation must follow. Log replication has subtle rules. Get them right.

---

## Surprising Truth / Fun Fact

etcd—used by Kubernetes for cluster config—uses Raft. Every time you deploy a pod, run kubectl, or scale a deployment, Raft consensus happens behind the scenes. Log replication. Commit. Apply. The most popular orchestration system in the world runs on Raft. You're using it without knowing. That's good design. Invisible when it works.

---

## Quick Recap (5 bullets)

- **Log replication:** Leader appends. Followers receive and append. Same order. Same entries.
- **Commit:** Entry committed when majority has it. Safe. Won't be lost.
- **Consistency:** All logs match. Leader is authority. Followers overwrite on conflict.
- **Follower behind:** Leader sends missing entries. Follower appends. Catches up.
- **etcd, Consul, TiKV:** All use Raft log replication. Kubernetes depends on it.

---

## One-Liner to Remember

**Raft log replication: Teacher writes. Students copy. Same notebook. Same order. Missing entries? Leader resends. Majority has it? Committed. Done.**

---

## Next Video

Next: **When to use Raft/Paxos.** You don't vote on every meal. Family decides small things fast. Big decisions? Family meeting. Majority rules. Same in systems. When do you use consensus? When don't you? etcd, ZooKeeper, Consul—where they fit. See you there.
