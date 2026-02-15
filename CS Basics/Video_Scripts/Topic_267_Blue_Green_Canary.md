# Blue-Green vs Canary Deployment

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

Two stages in a theater. The blue stage has the current show—version one. The green stage has the new show—version two—rehearsing. When version two is ready, the audience is SWITCHED from blue to green. Instant. One moment blue, next moment green. If version two has problems? Switch back to blue. That's blue-green deployment. Canary is different. Instead of switching everyone, send 5% of the audience to the green stage first. If they like it, send more. If not, send them back. Gradual. Let's see when to use each.

---

## The Story

You've built a new version of your application. It's tested. It's ready. How do you get it to users? Big bang—deploy to everyone at once? Risky. One bug, everyone suffers. Blue-green and canary are two strategies to reduce that risk. Both keep the old version running. Both let you roll back. The difference is how you transition.

Blue-green is binary. Two identical environments. Blue runs v1. Green runs v2. You deploy to green. Test. When ready, you switch traffic—DNS, load balancer, whatever—from blue to green. Everyone gets v2. If something breaks, switch back. Instant rollback. But everyone is on the new version or no one is. All or nothing.

Canary is gradual. You deploy v2 to a small subset of servers—or route 5% of traffic to v2. Most users still get v1. You watch. Error rates. Latency. User feedback. If it looks good, increase to 25%. Then 50%. Then 100%. If it looks bad, route everyone back to v1. Small blast radius. You catch problems before they hit everyone.

---

## Another Way to See It

Blue-green is like a light switch. Off or on. One flip. Canary is like a dimmer. You turn the dial slowly. 5% brightness. Then 25%. Then 50%. You can stop at any point. Reverse the dial if the room looks wrong. Gradual control. Different philosophy.

---

## Connecting to Software

**Blue-green deployment:** Two production environments. Deploy new version to the idle one. Run smoke tests. Switch traffic—update load balancer pool, or flip DNS, or update Kubernetes service selector. Rollback = switch traffic back. Fast. Simple. But: double infrastructure (both environments run). And: everyone gets the new version at once. If there's a rare bug that only appears under load, you discover it when 100% of traffic hits it.

**Canary deployment:** Deploy new version to a subset. Route a percentage of traffic (5%, 10%, 25%) via load balancer or service mesh. Monitor. Prometheus metrics, error rates, latency percentiles. If metrics are good, increase percentage. If bad, decrease or roll back. Slower rollout. Smaller blast radius. You need observability—without it, you're flying blind.

**Trade-offs:** Blue-green = fast rollback, simple, but double cost and all-or-nothing. Canary = gradual risk, smaller blast radius, but more complex (routing, metrics, automation) and slower to full rollout. Pick based on your risk tolerance and how much observability you have.

---

## Let's Walk Through the Diagram

```
BLUE-GREEN:
                    Load Balancer
                          |
              ┌───────────┴───────────┐
              |                       |
         [  Blue  ]              [  Green  ]
         v1 (prod)               v2 (new)
         ●●●●●●●●●●●              ○○○○○○○○○○
         100% traffic             0% traffic
              
         SWITCH:
              |                       |
         [  Blue  ]              [  Green  ]
         v1 (idle)               v2 (prod)
         ○○○○○○○○○○              ●●●●●●●●●●●
         0% traffic              100% traffic


CANARY:
                    Load Balancer
                          |
           ┌──────────────┼──────────────┐
           |              |              |
      [ v1 servers ] [ v2 servers ]  
       ●●●●●●●●●●●○   ○●
       95% traffic    5% traffic  ← Canary
       
       Gradually: 5% → 25% → 50% → 100%
```

Blue-green: one switch. Canary: many small steps. Each has its place.

---

## Real-World Examples (2-3)

**Netflix** famously uses canary. They deploy to a tiny fraction of users first. Monitor playback quality, error rates, engagement. Roll out slowly. If something breaks, they catch it before millions see it. Their chaos engineering (Chaos Monkey) makes them think about failure constantly.

**Banks and financial apps** often prefer blue-green. Regulatory need for clear "before" and "after" states. Fast rollback. Simplicity. Canary's gradual exposure can complicate audits—"which version did this transaction use?"

**Shopify** uses both. Blue-green for major releases. Canary for riskier changes. They also use feature flags on top—deploy code, enable for percentage of users. Combines deployment strategy with runtime control.

---

## Let's Think Together

**"Canary at 5%. Error rate spikes 10x. What do you do? How fast can you roll back?"**

Immediately route all traffic back to v1. Update load balancer or service mesh config. Depending on your setup, that can be seconds (Kubernetes) or minutes (DNS propagation). Then investigate. Logs, traces, metrics. What changed? Why did errors spike? Fix the bug. Try again—maybe with 1% canary next time. The key: have the rollback path ready BEFORE you deploy. One-click or one-command. Practice it. When things go wrong, you don't want to figure out rollback on the fly.

---

## What Could Go Wrong? (Mini Disaster Story)

A team does their first canary. 5% to v2. Looks good. They jump to 50%. Within minutes, the database connection pool is exhausted. v2 has a connection leak. At 5%, it was barely noticeable. At 50%, it killed the database. The whole site goes down. v1 and v2 both fail—they share the database. Lesson: canary doesn't protect you from shared resource failures. Database, cache, message queue—if v2 misuses them, everyone suffers. Test resource usage in staging. Monitor connection pools, memory, CPU during canary. Increase gradually so you see the trend before it's too late.

---

## Surprising Truth / Fun Fact

The term "canary" comes from coal mining. Miners brought canaries into tunnels. Canaries are sensitive to toxic gas. If the canary stopped singing or died, miners knew to evacuate. A living canary = safe. A dead canary = danger. In software, the "canary" users are the first to hit new code. If they have a bad experience, you know before you expose everyone. The analogy has stuck for a century.

---

## Quick Recap (5 bullets)

- **Blue-green** = two environments; switch traffic all at once; fast rollback; double infra.
- **Canary** = gradual rollout; 5% → 25% → 100%; smaller blast radius; need observability.
- **Rollback** = blue-green: switch back; canary: route to v1.
- **Shared resources** = canary won't protect DB/cache from v2 misuse; monitor carefully.
- **Choose** = blue-green for efficiency/simplicity; canary for risky changes.

---

## One-Liner to Remember

*Blue-green is a light switch—everyone at once. Canary is a dimmer—slowly turn it up, and you can turn it back down if the room looks wrong.*

---

## Next Video

Next: Feature flags. Deploy code with the feature hidden. Flip a switch—no deployment—to turn it on for 1% of users. Safe rollout without redeploying. See you there.
