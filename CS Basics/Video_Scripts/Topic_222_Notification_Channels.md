# Notification System: Channels and Delivery

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

A school needs to notify parents about a snow day. Some parents prefer text messages. Some prefer email. Some want phone calls. Some want a push notification on the school app. FOUR channels. Each parent has preferences. The school can't send via just ONE channel. A notification system must support MULTIPLE delivery channels and respect user preferences. Let's design it together.

---

## The Story

Notifications are how your product talks to users when they're not looking. "Your order shipped." "Someone liked your post." "Payment failed." Each message needs to reach the user. But users are picky. I want critical alerts by SMS. Marketing? Email. Social updates? Push only. Miss that? Annoyed users. Unsubscribes. Bad experience.

A notification system has two jobs: decide WHAT to send and decide HOW to send it. The "how" is channels. Email, SMS, push, in-app, webhook. Each has a different provider. Different latency. Different cost. The system must route to the right channel for each user. Preferences drive routing.

---

## Another Way to See It

Think of a post office. One letter (notification) for many recipients. But each recipient has a preference: "Send to my home." "Send to my office." "Email only." The post office (notification system) must route each letter correctly. Same content. Different delivery. Preferences are the routing table. Channels are the transport.

---

## Connecting to Software

**Channels.** Push notification: mobile apps. FCM (Firebase) for Android. APNs (Apple) for iOS. Fast. In-app. Email: SMTP, SendGrid, SES. Async. Cheap at scale. SMS: Twilio, AWS SNS. Expensive. Real-time. Use for critical. In-app: store in database. User opens app, fetches. No external provider. Webhook: HTTP POST to customer's URL. For integrations. Each channel has a handler. Each handler talks to a provider.

**User preferences.** user_id → { push: true, email: true, sms: false, in_app: true }. Stored in preferences service. Per user. Maybe per category: "Payment alerts: SMS + push. Social: push only. Marketing: email." Matrix: user × category × channel. Rich. Query: "How should we notify user 123 for payment_alert?" → [SMS, push]. Route to both.

**Delivery flow.** Event triggers notification (e.g., "payment_failed"). Notification service receives. Looks up user preferences. Decides channels. For each channel: enqueue to channel-specific queue. Worker picks up. Calls provider API (Twilio for SMS, SES for email, FCM for push). Provider delivers. Worker marks done. Track delivery status. Retry on failure.

**Providers.** Don't build email SMTP. Use SendGrid, SES, Postmark. Don't build SMS. Use Twilio. Don't build push. Use FCM, APNs. Integrate. Pay per message. Focus on routing, preferences, reliability. Not transport. Building SMTP or SMS infrastructure is a company-sized project. Twilio and SendGrid have done it. Use them. Your job: route the right message to the right channel for the right user. That is the hard part. Delivery is commoditized. The real engineering challenge is at scale: millions of notifications, multiple channels, user preferences, retries, dead letter queues. Start with the routing layer. Get preferences right. Add channels one at a time. Test each integration. Providers fail. Have fallbacks.

---

## Let's Walk Through the Diagram

```
NOTIFICATION - CHANNEL ROUTING
┌─────────────────────────────────────────────────────────────────┐
│                                                                  │
│   EVENT: "Payment failed for user_123"                          │
│         │                                                        │
│         ▼                                                        │
│   Notification Service                                           │
│         │                                                        │
│         │ 1. Lookup preferences                                  │
│         ▼                                                        │
│   Preferences: user_123 → payment_alerts: [SMS, Push, Email]    │
│         │                                                        │
│         │ 2. Route to channels                                    │
│         ├──► Queue: SMS ──► Worker ──► Twilio API               │
│         ├──► Queue: Push ──► Worker ──► FCM / APNs             │
│         └──► Queue: Email ──► Worker ──► SES / SendGrid         │
│                                                                  │
│   PREFERENCES TABLE:                                             │
│   user_id | category      | push | email | sms                  │
│   123     | payment_alert | ✓    | ✓     | ✓                   │
│   123     | social        | ✓    | ✗     | ✗                   │
│   123     | marketing     | ✗    | ✓     | ✗                   │
│                                                                  │
│   Each channel: own queue, own workers, own provider              │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

Narrate it: Event arrives. Check preferences. User wants payment alerts via SMS, push, email. Route to three queues. Workers send via providers. Each channel independent. Scale separately. Add a channel? Add a queue, workers, provider integration. Clean.

---

## Real-World Examples (2-3)

**Uber.** Trip updates: push. Receipt: email. Critical account: SMS. Per-event channel selection. Preferences per category. Handles millions of notifications daily.

**Slack.** DMs: push + email + in-app. Channel mentions: push + in-app. User configures. "Notify me on mobile for DMs, desktop for mentions." Complex routing. Preference-rich.

**Banks.** Fraud alert: SMS. Statement: email. Push for marketing. Critical = SMS. Always. Regulatory. Channel choice matters for compliance.

---

## Let's Think Together

**"User wants push AND email for payment alerts, but only push for social updates. How do you model this?"**

Preferences as a matrix. user_id + notification_category → list of channels. payment_alert → [push, email]. social_update → [push]. Query at send time. Alternative: rules. "If category in [payment, security] and user has sms_verified, add SMS." More flexible. More complex. Start simple: category → channels. Store: (user_id, category, channels[]). Index by user_id. At send: lookup (user_id, event_category). Get channels. Route. Evolve to rules if needed. Don't over-engineer initially.

---

## What Could Go Wrong? (Mini Disaster Story)

A company sends all notifications via email. One type. Users complain: "Too much email! Unsubscribe!" They lose engagement. They add preferences. But migration: existing users default to "all channels." Email flood continues. They forgot: opt-in for new channels. Opt-out for reduction. And they never added push. Competitor has push. Faster. Users prefer it. Lesson: multi-channel from day one. Preferences from day one. Defaults matter. Migration matters.

---

## Surprising Truth / Fun Fact

Push notification delivery rates: 95%+ within seconds. Email: 70-90% delivery, minutes to hours. SMS: 98%+ within seconds. But cost: push is free (after setup). Email: $0.0001 per message. SMS: $0.01-0.05. Use the right channel for the right message. Critical? SMS. Bulk? Email. Engagement? Push. Cost and speed drive channel choice.

---

## Quick Recap (5 bullets)

- **Channels:** Push, SMS, email, in-app, webhook. Each has a provider.
- **Preferences:** user × category → channels. Stored. Queried at send.
- **Flow:** Event → preferences lookup → route to channel queues → workers → providers.
- **Don't build transport:** Use Twilio, SES, FCM. Integrate. Pay per message.
- **Model:** Simple matrix first. Rules engine if needed. Evolve.

---

## One-Liner to Remember

**Notifications: right message, right channel, right user. Preferences are the map.**

---

## Next Video

Next: scaling notifications. 10 million users in 5 minutes. Queues. Workers. Provider rate limits. The rush.
