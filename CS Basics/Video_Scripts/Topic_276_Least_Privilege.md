# Least Privilege: Give Only What's Needed

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

Picture this. You check into a hotel. The front desk hands you a key. You open your room. You try the pool door. Locked. You try the kitchen. Locked. You try the manager's office. Locked. Your key opens ONE door—your room. Nothing more. That's not a mistake. That's by design. That's the principle of least privilege. And in software, it saves companies from disaster every single day.

---

## The Story

A hotel is a masterclass in access control. The guest gets a key that opens only their room. The cleaner gets a key that opens guest rooms on their floor—not the safe, not the server room. The manager gets a master key that opens everything. Each person gets ONLY the access they NEED to do their job. Nothing more.

Why does this matter? Because if someone steals the cleaner's key, they can't open the safe. They can't access the server room with credit card data. The damage is contained. In software, we apply the same logic. Every service, every user, every process should have the MINIMUM permissions required to do its job. No extra read access. No extra delete permissions. No wildcards that grant "everything."

Think of it like giving a child a knife. You don't hand them the entire kitchen drawer. You give them one butter knife, for one task. If they drop it, the damage is limited. Least privilege works the same way: if a service gets compromised, the attacker gets ONLY what that service had access to. Blast radius is limited.

---

## Another Way to See It

Imagine a school. The lunch lady has a key to the cafeteria. She doesn't need the principal's office key. The janitor has keys to classrooms—not the payroll filing cabinet. The principal has broad access, but even they don't have the IT admin's server passwords. Everyone has a role. Everyone gets keys for that role. Nothing more. That's least privilege in the real world. Software should mirror this. Every piece of code is like an employee with a specific job. Give it only the keys it needs.

---

## Connecting to Software

In practice, least privilege means: the database service gets SELECT and INSERT on its own tables—not DROP, not ALTER, not access to other schemas. The Lambda function that processes images gets S3 read on one bucket—not S3 delete, not EC2 access, not DynamoDB. Developers get staging access—not production. Production access is restricted to deploy pipelines and on-call engineers.

IAM roles in AWS are the perfect vehicle. Create a role per service. Attach a policy with exact permissions. No wildcards in production. A policy might say: "Allow s3:GetObject on arn:aws:s3:::my-bucket/*." Not "Allow s3:* on *." The latter grants delete, write, everything. One compromised Lambda could wipe your entire S3 estate. Least privilege prevents that.

The same applies to databases, Kubernetes service accounts, API keys, and human users. Principle is identical: grant the minimum. Review regularly. Remove what's no longer needed.

---

## Let's Walk Through the Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        LEAST PRIVILEGE IN ACTION                         │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   User Service                    Database Service         Admin User   │
│   ┌─────────────┐                 ┌─────────────┐         ┌───────────┐ │
│   │ IAM Role:   │                 │ IAM Role:   │         │ IAM:      │ │
│   │ - S3 Read   │                 │ - RDS Read  │         │ - Full   │ │
│   │ - SQS Send  │                 │ - RDS Write │         │   Access │ │
│   │ - DynamoDB  │                 │ (its tables │         │ (prod)   │ │
│   │   on users  │                 │  only!)     │         │           │ │
│   └──────┬──────┘                 └──────┬──────┘         └─────┬─────┘ │
│          │                              │                       │       │
│          ▼                              ▼                       ▼       │
│   ┌─────────────────────────────────────────────────────────────────┐  │
│   │                    RESOURCES (S3, RDS, etc.)                     │  │
│   │   Each principal touches ONLY what it needs. No overlap.         │  │
│   └─────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│   If User Service is hacked → attacker gets S3 read, SQS send.          │
│   NOT: RDS drop, S3 delete, EC2 launch. Blast radius = LIMITED.          │
└─────────────────────────────────────────────────────────────────────────┘
```

Each box has a small, focused keyring. No master keys. No "allow all." That's least privilege visualized.

---

## Real-World Examples

**Netflix** runs thousands of microservices. Each has its own IAM role. The recommendation service reads from the viewing-history database—it cannot write to the billing database. When a service is compromised (and it happens), the attacker's reach is bounded.

**Stripe** famously locks down production. Engineers don't SSH into prod. Deploys go through pipelines with tightly scoped permissions. Keys rotate. Access is audited. Least privilege isn't optional—it's the baseline.

**A major retailer** gave their web app database credentials with DROP privileges "for migrations." A bug in the app led to a malformed query. Entire product catalog dropped. Hours of downtime. Millions lost. The fix? Remove DROP. The app only needed SELECT, INSERT, UPDATE. Least privilege would have prevented it.

---

## Let's Think Together

**"Your microservice needs to read from S3 and write to SQS. What IAM policy would you create?"**

Answer: Two statements. One for S3: `Allow s3:GetObject` on the specific bucket (and prefix if needed). One for SQS: `Allow sqs:SendMessage` on the specific queue. That's it. No `s3:*`. No `sqs:*`. No `*` on resources. Exact ARNs. If someone asks "what about ListBucket?"—add it only if the service actually needs it. Start minimal. Add when proven necessary.

---

## What Could Go Wrong? (Mini Disaster Story)

A startup gave their payment service an IAM role with "Allow ec2:*" because "someday we might need to scale workers from the payment flow." They never did. Six months later, a dependency in the payment service had a vulnerability. Attacker got in. They used the EC2 permissions to spin up hundreds of crypto-mining instances. Bill: $47,000 in 72 hours. The payment service never needed EC2. It needed S3 for receipts and DynamoDB for transaction logs. That's it. Least privilege would have capped the damage to a few hundred dollars. The blast radius expanded because of permissions that were never used.

---

## Surprising Truth / Fun Fact

NASA's Viking landers in 1976 used a least-privilege-like design: each subsystem had isolated power and logic. If one failed, others kept working. Software adopted this from physical systems. The principle is decades old in safety-critical domains—aviation, nuclear, space. We're finally applying it consistently in cloud software. Better late than never.

---

## Quick Recap (5 bullets)

- **Least privilege** = give each service, user, and process only the minimum permissions it needs.
- **Why:** if compromised, the attacker's reach is limited; blast radius stays small.
- **How:** IAM roles per service, policies with exact permissions, no wildcards in production.
- **Examples:** database service gets SELECT/INSERT on its tables only; Lambda gets S3 read on one bucket.
- **Review:** regularly audit and remove unused permissions—least privilege degrades over time.

---

## One-Liner to Remember

*"Give every service only the keys it needs. If someone steals one key, they shouldn't get the whole building."*

---

## Next Video

Up next: **Secrets Management**—why hardcoding a password in code is like writing it on a sticky note on the front door. We'll cover Vault, rotation, and what to do when a secret leaks.
