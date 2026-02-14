# Authentication vs Authorization

## Video Length: ~4-5 minutes | Level: Beginner

---

## The Hook (20-30 seconds)

You're standing at the door of an exclusive club. The line stretches behind you. A guard blocks the entrance. He doesn't know you. He doesn't trust you. Yet. What happens next will decide whether you get in—or get turned away. Here's the twist: there are TWO guards. And they ask TWO completely different questions. Miss one, and you're stuck outside. Get both right, and the whole night opens up. Let me show you what those questions are—and why software systems use the exact same trick.

---

## The Story

Imagine that exclusive club. Guard 1 stands at the gate. You approach. He holds up his hand. "Stop. WHO are you? Show your ID." You pull out your driver's license. He checks the photo. He checks your face. He nods. "Okay. You are who you say you are." That's **authentication**. Proving your identity. Proving you ARE you.

You step inside. But before you can walk freely, Guard 2 blocks your path. "Wait. Are you ALLOWED in the VIP section?" You're confused. "I showed my ID. You saw it." Guard 2 shakes his head. "That proved WHO you are. I need to know what you're PERMITTED to do." He checks a list. Your name isn't there. "Regular area only. Not VIP." That's **authorization**. Checking your permissions. Checking what you're allowed to do.

See the difference? Auth = WHO are you? Authz = WHAT can you do? You can be fully authenticated—the whole club knows you're "Ravi"—but still not authorized to enter the VIP room. Two guards. Two questions. Both matter.

---

## Another Way to See It

Think of an office building. Security at the front desk checks your badge. That's authentication. You proved you're an employee. But when you try to enter the server room? Another check. Does your badge have server-room access? That's authorization. Same person. Different permission. The building trusts your identity. It doesn't trust that identity for EVERY room.

Or think of a house key. Your key fits the front door—authentication proves you have the right key. But that key doesn't open the safe. The safe needs a different permission. You're in the house (authenticated). You can't open the safe (not authorized). Two layers. Both protect.

---

## Connecting to Software

Every time you log into Gmail, you authenticate. You type your password. Google verifies: "Yes, this is really you." That's auth. But when you try to open a shared document? Google checks: "Is this user allowed to view this doc?" If the owner didn't share it with you, you're denied. That's authorization. Auth passed. Authz failed.

Your bank app works the same way. Login = authentication. Viewing your own account = authorized. Trying to view someone else's account? Auth still says "you're logged in." But authz says "you're not allowed to see that." The system knows WHO you are. It also knows WHAT you can access.

Admin vs regular user is the clearest example. Both log in (both authenticated). The admin can delete users. The regular user cannot. Same authentication. Different authorization.

---

## Let's Walk Through the Diagram

```
    ┌─────────────────────────────────────────────────────────────┐
    │                    CLUB WITH TWO GUARDS                       │
    │                                                               │
    │   YOU ──► [Guard 1: AUTHENTICATION] ──► "WHO are you?"        │
    │                  │                                            │
    │                  │  ID checked ✓ → Identity proven            │
    │                  ▼                                            │
    │   YOU ──► [Guard 2: AUTHORIZATION] ──► "WHAT can you do?"     │
    │                  │                                            │
    │                  │  Permission checked ✓ → Access granted      │
    │                  ▼                                            │
    │              [VIP Section / Regular Area]                     │
    │                                                               │
    │   Auth = Identity    |    Authz = Permission                  │
    └─────────────────────────────────────────────────────────────┘
```

Guard 1 answers: "Is this person who they claim to be?" Guard 2 answers: "Is this person allowed to do what they're trying to do?" Both must pass. One guard alone is not enough.

---

## Real-World Examples (2-3)

**Example 1: Gmail.** You log in with password and 2FA. Authentication complete. You click a shared doc link. If the owner shared it with you, you see it—authorization granted. If not, you get "Access denied." Auth said you're you. Authz said you can't see that doc.

**Example 2: Admin vs regular user.** Sarah and John both work at a company. Both log into the internal dashboard. Authentication: both passed. Sarah is admin. She can delete users, change settings. John is regular. He can only view reports. Same login system. Different permissions. That's authorization in action.

**Example 3: Bank app.** You're logged in. You try to transfer money to a new recipient. The app asks for OTP. You enter it. Auth still valid. But the app also checks: "Is this user allowed to add new recipients?" Maybe your account has restrictions. Auth passed. Authz might still block.

---

## Let's Think Together

You're logged into your bank app. Your session is valid. You're authenticated. Now you type in a URL to view someone else's account. You change the account number in the request. What stops you?

Think about it. The server already knows you're you. Authentication is done. The answer: **authorization**. Before returning any account data, the server checks: "Does this authenticated user have permission to view THIS account?" It compares the requested account with your user ID. They don't match. Access denied. Auth proves identity. Authz enforces the rule: "You can only see YOUR data."

---

## What Could Go Wrong? (Mini Disaster Story)

A startup builds a social app. They nail authentication. Passwords hashed. Sessions secure. Login works perfectly. But they forget about authorization. They assume: "If you're logged in, you can see everything." One user discovers that changing a number in the URL—from `/profile/123` to `/profile/456`—shows another user's private messages. No extra login. No hack. Just a missing authorization check. Overnight, thousands of private chats are exposed. The company faces lawsuits. The fix? One line of code: "If requested_user_id != current_user_id, deny." Authorization. The guard they forgot to hire.

---

## Surprising Truth / Fun Fact

Many developers use the terms "auth" and "authz" interchangeably. But they're not the same. In fact, OAuth 2.0—the protocol behind "Login with Google" or "Login with Facebook"—is purely an **authorization** protocol. It doesn't authenticate users. It delegates authorization. "Let this app access my contacts." The app gets a token. The identity part? That's often handled by OpenID Connect, which sits on top of OAuth. Auth and authz: different problems, different solutions. Mix them up, and you build the wrong thing.

---

## Quick Recap (5 bullets)

- **Authentication** answers "WHO are you?"—proving your identity (password, 2FA, biometrics).
- **Authorization** answers "WHAT can you do?"—checking your permissions (roles, access lists).
- You can be authenticated but not authorized (logged in, but denied access to a resource).
- Both are required: identity first, then permission.
- Real systems: Gmail (auth + doc sharing authz), admin vs user (same auth, different authz).

---

## One-Liner to Remember

**Authentication is who you are. Authorization is what you're allowed to do.**

---

## Next Video

Next, we'll see how systems remember you after you log in—**session-based authentication**. The gym, the wristband, and the logbook. Stay tuned.
