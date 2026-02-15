# Secrets Management: Never Hardcode, Always Rotate

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

You install a house alarm. The installer gives you a four-digit code. You write it on a sticky note. You paste it on the front door. "So I don't forget," you say. Anyone walking by can see it. That's exactly what hardcoding secrets in your code does. Database passwords, API keys, encryption keys—sitting in source code, committed to Git, visible to everyone with repo access. One leaked secret and your entire system can be compromised. Let's fix that.

---

## The Story

Secrets are everywhere in software. Database passwords. API keys for Stripe or SendGrid. Encryption keys. OAuth client secrets. They're the keys to your kingdom. And for decades, developers did the lazy thing: they put them directly in the code. Or in a config file. Then they committed that file to Git. Push to GitHub. Now every developer, every contractor, every bot that scrapes GitHub can see your production database password.

GitHub runs automated scans. They find millions of leaked secrets every year. AWS keys, Slack tokens, database credentials. Once a key hits the internet, it's compromised. Assume it's in the hands of attackers within minutes. There are bots that do nothing but crawl for leaked credentials. A single AWS key can spin up thousands of crypto-mining instances. Bills of $50,000 in hours are real. So is data theft. So is ransomware.

The antidote: secrets management. Store secrets in a secure vault. Access them at runtime. Never write them to code. Never commit them to Git. Rotate them regularly. If a secret leaks, rotate immediately. Automated rotation is your safety net.

---

## Another Way to See It

Think of a bank. The vault combination isn't written on the wall. It's in a secure safe, accessible only to authorized personnel, and it changes periodically. You don't hand the combination to every employee "in case they need it." You use a controlled system. Secrets management is the same: a vault (HashiCorp Vault, AWS Secrets Manager, Azure Key Vault) holds the secrets. Services request them at startup or runtime. They're injected as environment variables or fetched via API. They never touch disk in plain text. They're never logged. They're never in a config file committed to Git.

---

## Connecting to Software

**The problem:** secrets in code → pushed to GitHub → leaked. Once leaked, assume compromise. Rotate immediately. Revoke the old key. Issue a new one. Notify anyone who might have been affected.

**The solution:** use a secrets manager. HashiCorp Vault, AWS Secrets Manager, Azure Key Vault, Google Secret Manager. Store secrets there. At runtime: your app fetches the secret (over TLS, with IAM auth). Inject into the process as an env var or in-memory config. Never write to disk. Never log. Never put in a file that gets committed.

**Rotation:** keys should rotate periodically. Every 90 days for high-value keys. Every 30 days for payment or auth keys. Automated rotation means you don't forget. If a secret is compromised, rotate immediately—don't wait. Many secrets managers support automatic rotation (e.g., RDS credentials rotated by Secrets Manager). Use it.

---

## Let's Walk Through the Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    SECRETS MANAGEMENT FLOW                               │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   BAD (Hardcoded):                    GOOD (Secrets Manager):            │
│                                                                          │
│   ┌─────────────┐                     ┌─────────────┐                    │
│   │  source.py  │                     │  source.py  │                    │
│   │  DB_PASS =  │                     │  pass =     │                    │
│   │  "secret123"│  ──► Git ──► Leak!  │  get_secret()│                    │
│   └─────────────┘                     └──────┬──────┘                    │
│                                              │                           │
│                                              ▼                           │
│                                       ┌─────────────┐                    │
│                                       │   Vault /   │                    │
│                                       │   Secrets   │  Encrypted at rest │
│                                       │   Manager   │  IAM-gated access  │
│                                       │   Rotation  │  Audit logged      │
│                                       └─────────────┘                    │
│                                                                          │
│   Secret flows: App startup → fetch from Vault → in-memory only         │
│   Never: disk, logs, Git, screenshots.                                   │
└─────────────────────────────────────────────────────────────────────────┘
```

Left side: disaster. Right side: controlled, auditable, rotatable.

---

## Real-World Examples

**Uber (2016):** a developer committed an AWS key to a private GitHub repo. The key had broad permissions. Attackers found it. They exfiltrated data on 57 million users. Uber paid a $148 million settlement. The fix would have been: no keys in code, Vault or Secrets Manager, IAM roles for services.

**Code Spaces (2014):** an AWS key was compromised. Attackers deleted most of their infrastructure. The company shut down within days. One key. No rotation. No separation. Catastrophe.

**A fintech startup** uses AWS Secrets Manager for all database credentials. RDS credentials rotate every 30 days automatically. Applications fetch at startup. No one knows the production password. When an engineer left, they didn't need to "change the DB password"—the next rotation handled it. Zero manual steps.

---

## Let's Think Together

**"A developer accidentally commits an AWS secret key to GitHub. It's been there for 2 hours. What are your next 5 actions?"**

Answer: (1) Immediately revoke the key in IAM—disable or delete it. (2) Rotate: create a new key, update all services that used the old one. (3) Scrub the repo: use tools like `git-filter-repo` or BFG to remove the secret from history—because commits live forever, and the key might still be in clone caches. (4) Audit: check CloudTrail for any API calls from that key in the last 2 hours. Look for EC2 launches, S3 access, data exfil. (5) Notify: security team, leadership if data was accessed. Document the incident. Update training: why we never commit secrets.

---

## What Could Go Wrong? (Mini Disaster Story)

A SaaS company stored Stripe API keys in a `.env` file. "It's in .gitignore," they said. One developer ran `git add -A` by mistake. The `.env` went up. A security researcher found it within days. Reported it. But by then, the key had been scraped. Attackers had already created test charges, accessed customer payment metadata. The company had to rotate keys, notify Stripe, review all transactions. They moved to Secrets Manager the same week. .gitignore is not a security control. It's a convenience. Real security is: secrets never touch the repo. Period.

---

## Surprising Truth / Fun Fact

GitHub's secret scanning found over 1 million potential secrets in public repos in 2023 alone. Many were in commits from years ago—still valid, still dangerous. Deleting a file doesn't delete it from Git history. Once a secret is committed, assume it's compromised. Rotation and revocation are the only response. Prevention is: never commit in the first place.

---

## Quick Recap (5 bullets)

- **Never hardcode** secrets in code, config files, or anywhere that gets committed to Git.
- **Use a secrets manager:** HashiCorp Vault, AWS Secrets Manager, Azure Key Vault—store secrets there, fetch at runtime.
- **Injection:** secrets as environment variables or fetched at startup; never written to disk, never logged.
- **Rotation:** rotate keys regularly; if compromised, rotate immediately; automate where possible.
- **Leak response:** revoke, rotate, scrub repo history, audit usage, notify.

---

## One-Liner to Remember

*"A secret in Git is not a secret. It's a public announcement with a time delay."*

---

## Next Video

Up next: **Encryption at Rest vs in Transit**—why you need BOTH. The love letter in a locked drawer, and the sealed envelope in the mail. We'll decode when data is protected and when it's vulnerable.
