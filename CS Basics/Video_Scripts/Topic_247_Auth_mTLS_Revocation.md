# Auth and Authorization: mTLS and Revocation

## Video Length: ~4-5 minutes | Level: Staff

---

## The Hook (20-30 seconds)

Two embassies. Exchanging classified documents. Each ambassador shows government-issued ID. Both verify. Mutual trust. Now imagine one ambassador is compromised. A spy. Their government REVOKES their ID. But the other embassy hasn't received the revocation list yet. The spy walks in. Freely. Certificate revocation: ensuring compromised certificates are no longer trusted. And it's surprisingly hard. Let's see why.

---

## The Story

mTLS—mutual TLS. Both sides present certificates. Client and server verify each other. Zero-trust networking. "Don't trust the network. Verify everyone." Service A calls Service B. A shows its certificate. B verifies. B shows its certificate. A verifies. Both authenticated. Encrypted. Perfect for microservices. But certificates can be compromised. Private key stolen. You revoke the certificate. "This cert is no longer valid." Problem: how do other services know? They have the certificate. They verified it before. They might cache. They might not check revocation every time. The gap: between "we revoked" and "everyone knows" can be minutes. Hours. In that window, the compromised cert still works. Revocation is the weakest link in PKI. We've known this for decades. We still don't have a perfect solution.

---

## Another Way to See It

Think of a driver's license. You lose it. Someone finds it. Uses it. You report it lost. The DMV revokes it. But the bartender across town? They don't check the revocation list. They look at the license. It looks valid. They serve. The revocation only works if everyone checks. And checks frequently. Certificates are the same. Revocation list exists. But not everyone fetches it. Not every time. The gap is real. Design for it. Assume compromise. Short cert lifetimes. Rotate often. Limit the blast radius of a revoked cert that still works.

---

## Connecting to Software

**mTLS in microservices.** Every service has a certificate. Issued by internal CA. Service A calls B: TLS handshake. A presents cert. B checks: signed by our CA? Not expired? Optionally: not revoked? B presents cert. A does the same. Connection established. All service-to-service traffic encrypted. Authenticated. No more "trust the network." The network could be compromised. Certs prove identity. Implement with Istio, Linkerd, or custom. Envoy supports mTLS. Common in Kubernetes. Service mesh makes it easy. But revocation? Still hard.

**Certificate rotation.** Certs expire. Typically 90 days. Or 24 hours for short-lived. Must rotate before expiry. Automated: cert-manager (Kubernetes), HashiCorp Vault. Issue new cert. Deploy. Old cert still valid until expiry. Overlap period. Both work. Then old expires. Rotation is operational discipline. Script it. Monitor. Alert on certs expiring in < 7 days. Rotation is solved. Revocation is the unsolved problem.

**Revocation mechanisms.** CRL: Certificate Revocation List. A list of revoked cert serial numbers. Clients download. Check. Problem: list grows. Megabits. Download latency. Stale. Clients might not refresh. OCSP: Online Certificate Status Protocol. Real-time check. "Is cert X revoked?" Query OCSP server. Get response. Problem: OCSP server is a single point of failure. DDoS it? Nobody can verify. OCSP stapling: server includes OCSP response in TLS handshake. Reduces OCSP load. But server might staple stale response. Tradeoffs. No perfect answer. Short-lived certs reduce reliance on revocation. If cert lives 24 hours, compromise window is 24 hours max. Revocation becomes less critical. Design for short lifetime. Rotate aggressively.

---

## Let's Walk Through the Diagram

```
mTLS AND REVOCATION
┌─────────────────────────────────────────────────────────────────┐
│                                                                  │
│   SERVICE A                    SERVICE B                         │
│   (has cert)                   (has cert)                         │
│       │                            │                             │
│       │  TLS handshake              │                             │
│       │  A presents cert ─────────► │ B verifies: valid?         │
│       │  B presents cert ◄───────── │ A verifies: valid?         │
│       │                            │                             │
│       │  REVOCATION CHECK (optional)                              │
│       │  CRL: Download list, check serial                         │
│       │  OCSP: Query "revoked?" ──► OCSP Server (can be SPOF)    │
│       │                            │                             │
│       │  Connection established    │                             │
│       │◄──────────────────────────►│                             │
│                                                                  │
│   GAP: Revoked cert may still work until all peers check.        │
│   MITIGATION: Short cert lifetime. Rotate often.                 │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

Narrate it: A and B do mTLS. Both present certs. Both verify. Optionally check revocation. CRL or OCSP. CRL: big list, might be stale. OCSP: real-time, but OCSP server can fail. Either way, there's a gap. Revoked cert might still work. The diagram shows the flow. The weak point: revocation propagation. Mitigation: short-lived certs. 24-hour lifetime. Compromise? Max 24 hours of abuse. Then cert expires. Rotate. Revocation becomes backup, not primary. Design for the world we have. Not the one we want.

---

## Real-World Examples (2-3)

**Google.** Internal mTLS. All service-to-service. Short-lived certs. Automated rotation. They've written about it. BeyondCorp. Zero-trust. Cert-based auth. Revocation? They use short lifetimes. Less reliance on revocation. Proven at scale.

**Cloud providers.** AWS, GCP, Azure. Managed certificates. Automatic rotation. Revocation when you delete a resource. They handle the complexity. Use managed when you can. Don't build PKI yourself if you don't have to.

**Istio.** Service mesh. mTLS between pods. Automatic cert issuance. Rotation. Revocation when pod is deleted. Kubernetes-native. The mesh abstracts the pain. But understand what's happening under the hood. Revocation still matters when keys leak. Know the limits.

---

## Let's Think Together

**"A service's private key is compromised. You revoke the certificate. How long until all other services stop trusting it?"**

Depends. If everyone checks OCSP on every connection: seconds. OCSP says "revoked." Connection refused. But: OCSP might be cached. Or not queried. Many implementations don't check revocation by default. Performance. Latency. So: maybe never. Some services might never check. They verified the cert once. Cached. Keep using it. Practical answer: until cert expires. Or until every client fetches fresh revocation info. Which might not happen. Mitigation: short cert lifetime. 1 hour. Compromise? 1 hour of damage. Rotate immediately. New cert. Old cert revoked. Clients that connect get new cert. Clients with cached connections? Until they reconnect. Bottom line: revocation is best-effort. Design for it. Short lifetimes. Fast rotation. Assume revocation is slow. Plan accordingly.

---

## What Could Go Wrong? (Mini Disaster Story)

A company. mTLS everywhere. Internal services. One day: a private key leaks. GitHub repo. Accidentally committed. Key is out there. They revoke the certificate. CRL updated. But: their services don't check CRL. Or check weekly. Stale. For a week, the compromised cert still works. Attacker has the key. They authenticate as the service. Access internal systems. Data exfiltrated. Incident. Postmortem: "We revoked. Why did it still work?" Nobody was checking. Revocation only works if you check. They enabled OCSP. Shortened cert lifetime to 24 hours. Lesson: revocation is a two-part system. Revoke AND verify. Most systems do the first. Forget the second. Don't. Check. Or don't rely on revocation. Short certs. Your choice. But be explicit.

---

## Surprising Truth / Fun Fact

Most TLS clients—browsers, curl—don't check certificate revocation by default. Yes. Really. Chrome removed CRL checks in 2012. Too slow. OCSP? "Soft fail." If OCSP server is down, proceed anyway. Security vs usability. Usability won. So even the web's PKI has this problem. Revocation is theoretically required. Practically ignored. For internal mTLS, you have more control. Enforce OCSP. Or use short certs. You're not a browser. You can make different tradeoffs. Use that freedom. Design for your context.

---

## Quick Recap (5 bullets)

- **mTLS:** Both sides verify certificates. Zero-trust. Service-to-service auth. Encrypted.
- **Revocation:** CRL (list) or OCSP (real-time). Both have issues. Propagation gap.
- **Rotation:** Certs expire. Rotate before expiry. Automate. cert-manager, Vault.
- **Short lifetimes:** 24-hour certs. Compromise window = 24 hours. Less reliance on revocation.
- **Revocation only works if checked:** Many don't. Enable it. Or use short certs. Don't assume.

---

## One-Liner to Remember

**Certificate revocation is telling everyone the ambassador is a spy—the hard part is making sure every embassy gets the memo before the spy walks in.**

---

## Next Video

Next: distributed schedulers, heartbeats, and how to run millions of jobs at the right time, exactly once.
