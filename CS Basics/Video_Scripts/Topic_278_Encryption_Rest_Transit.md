# Encryption at Rest vs in Transit: Both, Not Either

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

You write a love letter. Sensitive stuff. You lock it in a drawer. Safe, right? But then you need to send it. You put it in an envelope—no seal—and hand it to the postal service. Anyone who opens the package can read it. Or: you send it in a sealed, tamper-proof envelope. Great. But you left the original sitting in an unlocked drawer. Someone breaks in, reads it. You need BOTH: the locked drawer when it's stored, and the sealed envelope when it travels. That's encryption at rest and encryption in transit. Miss one, and you're exposed.

---

## The Story

Encryption has two moments that matter. **At rest:** when your data is sitting still—on a disk, in a database, in a file in object storage. Like the letter in the drawer. **In transit:** when your data is moving—over the network, from your phone to a server, from one datacenter to another. Like the letter in the mail.

If you only encrypt at rest: the data is safe on disk. But the moment it leaves the server—over HTTP, unencrypted—anyone on the network path can intercept it. Man-in-the-middle. Packet sniffing. Coffee shop Wi-Fi. Your passwords, your credit cards, your private messages—visible. If you only encrypt in transit: the data is safe while it travels. But when it lands on the server, it's stored in plain text. Someone steals the disk? They read everything. Someone hacks the database? Plain text. You need BOTH.

Think of it like a treasure chest. At rest: the chest is locked (encryption on disk). In transit: the chest is in an armored truck with a guard (encryption over the network). You want both. A locked chest in an open wagon is vulnerable. An unlocked chest in an armored truck is vulnerable. Both together: that's defense in depth.

---

## Another Way to See It

A bank safe. The money sits in a vault (at rest—protected). When it moves to another branch, it travels in an armored truck (in transit—protected). The bank doesn't choose one. They do both. Because the threat is different in each phase. At rest: burglars, disgruntled employees, stolen disks. In transit: highway robbers, network snoops. Different attacks. Different protections. Both required.

---

## Connecting to Software

**At rest:** data is encrypted when stored. AES-256 is standard. Your database can use transparent data encryption (TDE). S3 offers server-side encryption (SSE). When someone steals a disk, or copies a backup, they get ciphertext—useless without the key.

**In transit:** data is encrypted when it travels. TLS/SSL. HTTPS. When you connect to an API, to a database, to a storage bucket—the connection should be TLS. If someone sniffs the network—on the same Wi-Fi, at the ISP, at a router—they see gibberish.

**Key management:** who holds the encryption key? AWS KMS is managed—Amazon holds the keys, you control access. Customer-managed keys give you more control. Bring-your-own-key (BYOK) lets you hold keys in your HSM. Critical point: losing the key means losing the data forever. There is no "decrypt without key." Key management is as important as encryption itself.

---

## Let's Walk Through the Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│              ENCRYPTION: AT REST vs IN TRANSIT                           │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   CLIENT                    NETWORK                     SERVER           │
│   ┌─────────┐               ┌─────────┐                 ┌─────────┐       │
│   │ Plain   │               │ Encrypted│                │ Plain   │       │
│   │ text    │ ──► TLS ──────► │ (HTTPS) │ ──────► TLS ─► │ text    │       │
│   │ (memory)│      🔒        │ ciphertext                │ (memory)│       │
│   └─────────┘               └─────────┘                 └────┬────┘       │
│       ▲                           │                          │           │
│       │  "In transit" = protected │                          ▼           │
│       │  Sniffing = gibberish     │                    ┌─────────┐       │
│       │                           │                    │ Encrypted│       │
│       │                           │                    │ at rest  │       │
│       └───────────────────────────┘                    │ (AES-256)│       │
│                                                        │ on disk  │       │
│                                                        └─────────┘       │
│                                                              │           │
│   "At rest" = protected. Stolen disk = ciphertext, unreadable            │
└─────────────────────────────────────────────────────────────────────────┘
```

Data is decrypted only when needed—in memory, for processing. On the wire and on the disk: always encrypted.

---

## Real-World Examples

**AWS S3:** supports both. Server-side encryption (SSE-S3, SSE-KMS) for at-rest. All S3 data transfer uses HTTPS—in transit. Enable both. Many compliance frameworks (HIPAA, PCI-DSS) require both.

**A healthcare app** stores patient records. At rest: RDS encryption with AWS KMS. In transit: all API calls over HTTPS, database connections over SSL. Auditors check both. Missing either fails the audit.

**A startup** enabled S3 encryption at rest but forgot to enforce HTTPS for their API. A developer built a mobile app that sent auth tokens over HTTP to save "a few milliseconds." Tokens were intercepted on public Wi-Fi. Account takeovers. The data at rest was fine. The data in transit was not. Both matter.

---

## Let's Think Together

**"You encrypt data at rest with AES-256. You send it over HTTPS. Is it encrypted twice during transfer? Explain."**

Answer: During transfer, it's encrypted once—by TLS. The data on disk is encrypted with AES-256. When the server reads from disk, it decrypts (in memory) and then sends over the network. The sending happens via TLS—so the data is encrypted again for the wire. So: at any moment, the data is protected. On disk: AES. On the wire: TLS. It's not "encrypted twice" at the exact same layer—it's encrypted by the appropriate mechanism for each phase. At rest = disk encryption. In transit = TLS. Different layers. Both active when they should be.

---

## What Could Go Wrong? (Mini Disaster Story)

A company stored customer PII in a database with encryption at rest. Bulletproof, they thought. Their internal admin tool connected to the database over the internal network—no TLS, "because it's internal." An attacker got a foothold on a developer's machine. They ran a packet sniffer on the internal network. Captured database credentials and query results in plain text. Hundreds of customer records exfiltrated. Internal networks are not trusted. Encrypt in transit everywhere—even inside the datacenter. Defense in depth means no weak links.

---

## Surprising Truth / Fun Fact

When you use HTTPS, the data is typically decrypted at the load balancer or the server—then re-encrypted if it goes to another service. End-to-end encryption means the data stays encrypted until it reaches the final consumer. For maximum paranoia, some systems encrypt the payload before it even leaves the client—so even the server sees ciphertext. That's "encrypt everywhere." For most apps, TLS in transit + AES at rest is the baseline. Know your threats. Layer accordingly.

---

## Quick Recap (5 bullets)

- **At rest:** data encrypted on disk (AES-256). Protects against stolen disks, backups, database dumps.
- **In transit:** data encrypted over the network (TLS/HTTPS). Protects against sniffing, man-in-the-middle.
- **You need BOTH.** Missing one creates a vulnerability—different phases, different attacks.
- **Key management:** who holds the key? KMS, customer-managed, BYOK. Losing the key = losing the data.
- **Internal traffic:** encrypt in transit even inside the datacenter. Internal networks are not safe.

---

## One-Liner to Remember

*"Encryption at rest protects the drawer. Encryption in transit protects the envelope. You need both to protect the letter."*

---

## Next Video

Up next: **Audit Logging**—what to log, why, and how to make logs tamper-proof. The bank vault camera that records who entered, when, and what they touched.
